"""Janela principal: três etapas, progresso, resultado e histórico."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import __version__  # noqa: E402
from ..core.config import save_config  # noqa: E402
from ..core.errors import FlasherError  # noqa: E402
from ..core.i18n import current_language  # noqa: E402
from ..core.models import (  # noqa: E402
    DeviceIdentity,
    DeviceInfo,
    FlashResult,
    ImageInfo,
)
from ..devices.manager import DeviceManager  # noqa: E402
from ..history.store import HistoryStore  # noqa: E402
from ..images.detector import inspect_image  # noqa: E402
from ..permissions.polkit import HelperLauncher  # noqa: E402
from ..utils.format import (  # noqa: E402
    human_datetime,
    human_duration,
    human_size,
    human_speed,
)
from ..utils.logging import get_logger  # noqa: E402
from .dialogs import PreferencesDialog, about_dialog  # noqa: E402

log = get_logger("window")


def css(widget: Gtk.Widget, *classes: str) -> Gtk.Widget:
    for name in classes:
        widget.add_css_class(name)
    return widget


def label(text: str = "", *classes: str, **props: Any) -> Gtk.Label:
    widget = Gtk.Label(label=text, **props)
    css(widget, *classes)
    return widget


class FlasherWindow(Adw.ApplicationWindow):
    def __init__(self, config: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(
            title=_("Linux ISO Flasher"),
            default_width=900,
            default_height=780,
            **kwargs,
        )
        self.config = config
        self.image_info: ImageInfo | None = None
        self.selected_device: DeviceInfo | None = None
        self.devices: list[DeviceInfo] = []
        self.device_checks: dict[str, Gtk.CheckButton] = {}
        self.busy = False
        self.cancel_event: threading.Event | None = None
        self._updating_devices = False

        self.device_manager = DeviceManager()
        self.history = HistoryStore(limit=int(config.get("history_limit", 100)))
        self.launcher = HelperLauncher()

        self._build_ui()
        self._install_actions()
        self.device_manager.subscribe(self._devices_changed)
        self.device_manager.refresh()
        self.connect("destroy", self._on_destroy)

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        toolbar = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar)
        toolbar.add_top_bar(self._build_header())

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(220)
        toolbar.set_content(self.stack)

        self._build_main_page()
        self._build_flash_page()
        self._build_result_page()
        self._build_history_page()
        self.stack.set_visible_child_name("main")

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=_("Linux ISO Flasher"), subtitle=_("Gravador de imagens"))
        )

        menu = Gio.Menu()
        menu.append(_("Preferências"), "win.preferences")
        menu.append(_("Histórico"), "win.history")
        menu.append(_("Sobre"), "win.about")
        menu.append(_("Sair"), "app.quit")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text=_("Menu"))
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        refresh = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text=_("Atualizar dispositivos")
        )
        refresh.connect("clicked", lambda *_: self._refresh_devices())
        header.pack_start(refresh)
        return header

    def _build_main_page(self) -> None:
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        clamp = Adw.Clamp(maximum_size=780, tightening_threshold=600)
        scroll.set_child(clamp)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_margin_top(24)
        box.set_margin_bottom(30)
        clamp.set_child(box)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero.append(label(_("Grave seu sistema com simplicidade"), "lif-hero-title"))
        hero.append(
            label(
                _("Selecione uma imagem, escolha um dispositivo removível e grave com verificação."),
                "lif-hero-subtitle",
                wrap=True,
            )
        )
        box.append(hero)

        self.image_card, image_content = self._card(
            1, _("Selecionar imagem"), _("ISO, IMG, RAW, BIN ou imagem comprimida")
        )
        box.append(self.image_card)
        self._build_image_card(image_content)

        device_card, device_content = self._card(
            2, _("Selecionar dispositivo"), _("USB, cartões SD e microSD detectados automaticamente")
        )
        box.append(device_card)
        self._build_device_card(device_content)

        flash_card, flash_content = self._card(
            3, _("Gravar imagem"), _("Confirme os dados antes de apagar o destino")
        )
        box.append(flash_card)
        self._build_flash_card(flash_content)

        self.main_status = label(
            _("Aguardando uma imagem e um dispositivo."), "lif-step-hint"
        )
        self.main_status.set_xalign(0)
        box.append(self.main_status)

        self.stack.add_named(scroll, "main")

    def _card(self, number: int, title: str, hint: str) -> tuple[Gtk.Box, Gtk.Box]:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        css(card, "lif-card")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        css(header, "lif-card-header")
        badge = label(str(number), "lif-step-number")
        badge.set_valign(Gtk.Align.CENTER)
        header.append(badge)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.append(label(title, "lif-step-title", xalign=0))
        titles.append(label(hint, "lif-step-hint", xalign=0))
        header.append(titles)
        card.append(header)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.append(content)
        return card, content

    def _build_image_card(self, content: Gtk.Box) -> None:
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        select = Gtk.Button(label=_("Selecionar imagem"), icon_name="document-open-symbolic")
        select.add_css_class("suggested-action")
        select.connect("clicked", self._open_file_chooser)
        buttons.append(select)
        self.clear_image_button = Gtk.Button(
            icon_name="edit-clear-symbolic", tooltip_text=_("Limpar imagem"), visible=False
        )
        self.clear_image_button.connect("clicked", lambda *_: self._set_image(None))
        buttons.append(self.clear_image_button)
        buttons.append(
            label(_("ou arraste o arquivo para esta área"), "lif-step-hint", hexpand=True)
        )
        content.append(buttons)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.image_name_label = label(_("Nenhuma imagem selecionada"), "lif-device-name", xalign=0)
        self.image_name_label.set_hexpand(True)
        self.image_badge = label("", "lif-badge", visible=False)
        head.append(self.image_name_label)
        head.append(self.image_badge)
        info.append(head)
        self.image_size_label = label("", "lif-device-meta", xalign=0)
        info.append(self.image_size_label)
        self.image_path_label = label(
            "", "lif-path", xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE
        )
        self.image_path_label.set_selectable(True)
        info.append(self.image_path_label)
        self.image_status_label = label("", "lif-step-hint", xalign=0, visible=False)
        info.append(self.image_status_label)
        content.append(info)

        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self._on_file_drop)
        target.connect("enter", lambda *_: self.image_card.add_css_class("lif-drop-active"))
        target.connect("leave", lambda *_: self.image_card.remove_css_class("lif-drop-active"))
        self.image_card.add_controller(target)

    def _build_device_card(self, content: Gtk.Box) -> None:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.device_count_label = label(_("Nenhum dispositivo detectado"), "lif-step-hint", hexpand=True)
        self.device_count_label.set_xalign(0)
        toolbar.append(self.device_count_label)
        refresh = Gtk.Button(label=_("Atualizar"), icon_name="view-refresh-symbolic")
        refresh.connect("clicked", lambda *_: self._refresh_devices())
        toolbar.append(refresh)
        content.append(toolbar)

        self.device_placeholder = label(
            _(
                "Conecte um pendrive ou cartão SD. Discos internos ficam bloqueados por segurança."
            ),
            "lif-step-hint",
            wrap=True,
        )
        self.device_placeholder.set_xalign(0)
        content.append(self.device_placeholder)

        self.device_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        css(self.device_list, "boxed-list")
        self.device_list.set_visible(False)
        content.append(self.device_list)

    def _build_flash_card(self, content: Gtk.Box) -> None:
        self.summary_label = label(
            _("Escolha uma imagem e um dispositivo para continuar."), "lif-device-meta", xalign=0
        )
        content.append(self.summary_label)
        self.flash_button = Gtk.Button(
            label=_("Gravar imagem"), icon_name="drive-harddisk-symbolic"
        )
        self.flash_button.add_css_class("suggested-action")
        self.flash_button.set_sensitive(False)
        self.flash_button.connect("clicked", lambda *_: self._confirm_flash())
        content.append(self.flash_button)

        warning = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        icon.set_pixel_size(18)
        icon.set_valign(Gtk.Align.CENTER)
        warning.append(icon)
        warning.append(
            label(
                _("A gravação apaga todos os dados do dispositivo e é verificada ao final."),
                "lif-step-hint",
                wrap=True,
            )
        )
        content.append(warning)

    def _build_flash_page(self) -> None:
        clamp = Adw.Clamp(maximum_size=620)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_valign(Gtk.Align.CENTER)
        clamp.set_child(box)

        self.flash_image_label = label("", "lif-hero-title")
        self.flash_target_label = label("", "lif-device-meta")
        self.percent_label = label("0%", "lif-percent")
        self.progress_bar = Gtk.ProgressBar()
        css(self.progress_bar, "lif-progress-bar")
        self.stage_label = label(_("Preparando…"), "lif-device-meta", xalign=0)

        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        metrics.set_homogeneous(True)
        self.written_metric = self._metric(_("Gravado"), box=metrics)
        self.speed_metric = self._metric(_("Velocidade"), box=metrics)
        self.eta_metric = self._metric(_("Tempo restante"), box=metrics)

        self.cancel_button = Gtk.Button(label=_("Cancelar"), icon_name="process-stop-symbolic")
        self.cancel_button.add_css_class("destructive-action")
        self.cancel_button.connect("clicked", self._on_cancel)

        for widget in (
            self.flash_image_label,
            self.flash_target_label,
            self.percent_label,
            self.progress_bar,
            self.stage_label,
            metrics,
            self.cancel_button,
        ):
            box.append(widget)
        self.stack.add_named(clamp, "flash")

    def _metric(self, title: str, box: Gtk.Box) -> Gtk.Label:
        group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        group.append(label(title, "lif-metric-label"))
        value = label("—", "lif-metric-value")
        group.append(value)
        box.append(group)
        return value

    def _build_result_page(self) -> None:
        clamp = Adw.Clamp(maximum_size=620)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_valign(Gtk.Align.CENTER)
        clamp.set_child(box)

        self.result_icon = Gtk.Image()
        self.result_icon.set_pixel_size(64)
        self.result_icon.set_valign(Gtk.Align.CENTER)
        css(self.result_icon, "lif-result-icon")
        self.result_title = label("", "lif-hero-title")
        self.result_message = label("", "lif-device-meta", wrap=True)
        self.result_details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.CENTER)
        self.result_back = Gtk.Button(label=_("Concluir"))
        self.result_back.connect("clicked", lambda *_: self._go_main())
        self.result_history = Gtk.Button(label=_("Ver histórico"))
        self.result_history.connect("clicked", lambda *_: self._show_history())
        buttons.append(self.result_back)
        buttons.append(self.result_history)

        for widget in (
            self.result_icon,
            self.result_title,
            self.result_message,
            self.result_details,
            buttons,
        ):
            box.append(widget)
        self.stack.add_named(clamp, "result")

    def _build_history_page(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_margin_top(20)
        box.set_margin_bottom(24)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(label(_("Histórico de gravações"), "lif-hero-title", hexpand=True))
        clear = Gtk.Button(label=_("Limpar histórico"), icon_name="user-trash-symbolic")
        clear.connect("clicked", lambda *_: self._confirm_clear_history())
        head.append(clear)
        box.append(head)

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.history_list = Gtk.ListBox()
        css(self.history_list, "boxed-list")
        scroll.set_child(self.history_list)
        box.append(scroll)

        back = Gtk.Button(label=_("Voltar"), halign=Gtk.Align.START)
        back.connect("clicked", lambda *_: self._go_main())
        box.append(back)
        self.stack.add_named(box, "history")

    # ------------------------------------------------------------------ ações
    def _install_actions(self) -> None:
        for name, callback in (
            ("refresh", lambda *_: self._refresh_devices()),
            ("history", lambda *_: self._show_history()),
            ("preferences", lambda *_: self._show_preferences()),
            ("about", lambda *_: about_dialog().present(self)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _on_destroy(self, *_args: Any) -> None:
        self.device_manager.close()

    def _toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast.new(message))

    # ------------------------------------------------------------ seleção img
    def _open_file_chooser(self, *_args: Any) -> None:
        dialog = Gtk.FileChooserDialog(
            title=_("Selecionar imagem"),
            action=Gtk.FileChooserAction.OPEN,
            transient_for=self,
            modal=True,
        )
        for name, pattern in (
            (_("Imagens de sistema"), "*"),
            (_("ISO"), "*.iso"),
            (_("Imagens cruas"), "*.img"),
            (_("Comprimidas"), "*.xz"),
            (_("Comprimidas"), "*.gz"),
            (_("Comprimidas"), "*.zst"),
        ):
            filter_ = Gtk.FileFilter()
            filter_.set_name(name)
            filter_.add_pattern(pattern)
            dialog.add_filter(filter_)
        dialog.open(None, self._file_chosen)

    def _file_chosen(self, dialog: Gtk.FileChooserDialog, result: Gio.AsyncResult) -> None:
        try:
            file_ = dialog.open_finish(result)
            path = file_.get_path() if file_ is not None else None
            if path:
                self._set_image(Path(path))
        except GLib.Error as exc:
            if exc.code != Gtk.FileChooserError.CANCELLED.value:
                self._toast(str(exc.message))
        finally:
            dialog.destroy()

    def _on_file_drop(self, _target: Gtk.DropTarget, value: Gdk.FileList, _x: float, _y: float) -> bool:
        files = value.get_files()
        if not files:
            return False
        path = files[0].get_path()
        if path:
            self._set_image(Path(path))
        return True

    def _set_image(self, path: Path | None) -> None:
        self.image_card.remove_css_class("lif-drop-active")
        if path is None:
            self.image_info = None
            self.image_name_label.set_label(_("Nenhuma imagem selecionada"))
            self.image_badge.set_visible(False)
            self.image_size_label.set_label("")
            self.image_path_label.set_label("")
            self.image_status_label.set_visible(False)
            self.clear_image_button.set_visible(False)
            self._update_flash_state()
            return
        try:
            info = inspect_image(path)
        except FlasherError as exc:
            self._toast(str(exc))
            return
        self.image_info = info
        self.image_name_label.set_label(info.name)
        self.image_badge.set_label(info.display_format)
        self.image_badge.set_visible(True)
        size = human_size(info.uncompressed_size or info.size)
        extra = (
            _(" · comprimida de {size}").format(size=human_size(info.size))
            if info.container
            else ""
        )
        self.image_size_label.set_label(size + extra)
        self.image_path_label.set_label(str(info.path))
        self.image_status_label.set_label(_("Imagem válida"))
        css(self.image_status_label, "lif-success")
        self.image_status_label.set_visible(True)
        self.clear_image_button.set_visible(True)
        self.config["last_image_dir"] = str(info.path.parent)
        save_config(self.config)
        self._update_flash_state()

    # ---------------------------------------------------------- dispositivos
    def _refresh_devices(self) -> None:
        self.device_manager.refresh()
        self._toast(_("Lista de dispositivos atualizada."))

    def _devices_changed(self, devices: list[DeviceInfo]) -> None:
        if self.busy:
            return
        self.devices = devices
        if self.selected_device is not None and not any(
            d.identity.fingerprint == self.selected_device.identity.fingerprint
            and d.identity.sysname == self.selected_device.identity.sysname
            for d in devices
        ):
            self.selected_device = None
            self._toast(_("O dispositivo selecionado foi removido."))
        self._render_devices()
        self._update_flash_state()

    def _render_devices(self) -> None:
        while self.device_list.get_first_child() is not None:
            self.device_list.remove(self.device_list.get_first_child())
        self.device_checks.clear()
        self._updating_devices = True

        count = len(self.devices)
        self.device_count_label.set_label(
            _("Dispositivos encontrados: {count}").format(count=count)
            if count
            else _("Nenhum dispositivo detectado")
        )
        self.device_placeholder.set_visible(count == 0)
        self.device_list.set_visible(count > 0)

        group: Gtk.CheckButton | None = None
        for device in self.devices:
            row = Gtk.ListBoxRow()
            css(row, "lif-device-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            check.set_sensitive(device.safe)
            if group is not None:
                check.set_group(group)
            else:
                group = check
            check.connect("toggled", self._on_device_toggled, device)
            self.device_checks[device.identity.sysname] = check

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.set_hexpand(True)
            identity = device.identity
            text.append(label(identity.name or identity.sysname, "lif-device-name", xalign=0))
            meta = " · ".join(
                part
                for part in (
                    identity.devpath,
                    identity.transport.upper() or _("USB"),
                    human_size(identity.size),
                    device.connection,
                )
                if part
            )
            text.append(label(meta, "lif-device-meta", xalign=0))
            if device.partitions:
                parts = ", ".join(
                    p.description + (f" ({human_size(p.size)})" if p.size else "")
                    for p in device.partitions
                )
                text.append(label(parts, "lif-device-meta", xalign=0))
            if device.available is not None:
                text.append(
                    label(
                        _("Espaço disponível: {size}").format(size=human_size(device.available)),
                        "lif-device-meta",
                        xalign=0,
                    )
                )
            if not device.safe:
                warning = label(
                    _("DISCO INTERNO — BLOQUEADO"), "lif-warning", xalign=0
                )
                text.append(warning)

            inner.append(check)
            inner.append(text)
            row.set_child(inner)
            self.device_list.append(row)

            if (
                self.selected_device is not None
                and device.identity.sysname == self.selected_device.identity.sysname
            ):
                check.set_active(True)

        self._updating_devices = False

    def _on_device_toggled(
        self, button: Gtk.CheckButton, device: DeviceInfo
    ) -> None:
        if self._updating_devices or self.busy or not button.get_active():
            return
        self.selected_device = device
        self._update_flash_state()

    def _update_flash_state(self) -> None:
        if self.image_info is not None and self.selected_device is not None:
            self.summary_label.set_label(
                _("{image} → {device} ({path})").format(
                    image=self.image_info.name,
                    device=self.selected_device.display_name,
                    path=self.selected_device.identity.devpath,
                )
            )
            self.flash_button.set_sensitive(not self.busy)
            self.main_status.set_label(_("Pronto para gravar. Confirme na próxima etapa."))
        else:
            missing = []
            if self.image_info is None:
                missing.append(_("uma imagem"))
            if self.selected_device is None:
                missing.append(_("um dispositivo"))
            self.summary_label.set_label(
                _("Selecione {items} para continuar.").format(items=" e ".join(missing))
            )
            self.flash_button.set_sensitive(False)
            self.main_status.set_label(_("Aguardando uma imagem e um dispositivo."))

    # -------------------------------------------------------------- confirmação
    def _confirm_flash(self) -> None:
        if self.busy or self.image_info is None or self.selected_device is None:
            return
        device = self.selected_device
        dialog = Adw.AlertDialog(
            heading=_("Apagar todos os dados?"),
            body=_(
                "A imagem “{image}” será gravada em {device} ({path}, {size}).\n\n"
                "TODOS OS DADOS DESTE DISPOSITIVO SERÃO APAGADOS.\n"
                "Verifique se selecionou o pendrive ou cartão correto."
            ).format(
                image=self.image_info.name,
                device=device.display_name,
                path=device.identity.devpath,
                size=human_size(device.identity.size),
            ),
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("confirm", _("Gravar agora"))
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        check = Gtk.CheckButton(
            label=_("Confirmo que todos os dados do dispositivo serão apagados")
        )
        dialog.set_extra_child(check)
        dialog.connect("response", self._on_confirm_response, check)
        dialog.present(self)

    def _on_confirm_response(
        self, dialog: Adw.AlertDialog, response: str, check: Gtk.CheckButton
    ) -> None:
        if response != "confirm":
            return
        if not check.get_active():
            self._toast(_("Marque a confirmação para continuar."))
            dialog.present(self)
            return
        self._begin_flash()

    # ---------------------------------------------------------------- gravação
    def _begin_flash(self) -> None:
        assert self.image_info is not None and self.selected_device is not None
        self.busy = True
        self.cancel_event = threading.Event()
        self.flash_button.set_sensitive(False)
        self.flash_image_label.set_label(self.image_info.name)
        self.flash_target_label.set_label(
            _("{device} · {path}").format(
                device=self.selected_device.display_name,
                path=self.selected_device.identity.devpath,
            )
        )
        self.percent_label.set_label("0%")
        self.progress_bar.set_fraction(0.0)
        self.stage_label.set_label(_("Preparando…"))
        self.written_metric.set_label("—")
        self.speed_metric.set_label("—")
        self.eta_metric.set_label("—")
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_label(_("Cancelar"))
        self.stack.set_visible_child_name("flash")

        request = {
            "image_path": str(self.image_info.path),
            "target_sysname": self.selected_device.identity.sysname,
            "expected_fingerprint": self.selected_device.identity.fingerprint,
            "chunk_size": int(self.config.get("chunk_size", 1024 * 1024)),
            "verify": True,
        }
        threading.Thread(target=self._flash_worker, args=(request,), daemon=True).start()

    def _flash_worker(self, request: dict[str, Any]) -> None:
        assert self.cancel_event is not None
        try:
            result = self.launcher.flash(
                request,
                lambda progress: GLib.idle_add(self._apply_progress, progress),
                self.cancel_event,
            )
        except FlasherError as exc:
            log.error("Falha reportada pelo helper: %s", exc)
            GLib.idle_add(self._show_error, str(exc))
        except Exception as exc:  # pragma: no cover - último resource de defesa
            log.exception("Erro inesperado na interface de gravação")
            GLib.idle_add(self._show_error, _("Erro inesperado: {error}").format(error=exc))
        else:
            GLib.idle_add(self._show_result, result)

    def _apply_progress(self, data: dict[str, Any]) -> None:
        stage = data.get("stage", "write")
        done = int(data.get("done", 0))
        total = max(1, int(data.get("total", 1)))
        fraction = min(1.0, done / total)
        self.progress_bar.set_fraction(fraction)
        self.percent_label.set_label(f"{fraction * 100:.0f}%")
        self.written_metric.set_label(human_size(done))
        self.speed_metric.set_label(human_speed(float(data.get("speed") or 0)))
        self.eta_metric.set_label(human_duration(data.get("eta")))
        messages = {
            "prepare": _("Preparando dispositivo…"),
            "write": _("Gravando imagem…"),
            "verify": _("Verificando dados gravados…"),
            "finish": _("Finalizando…"),
        }
        self.stage_label.set_label(messages.get(stage, str(data.get("message") or stage)))
        if self.cancel_event is not None and self.cancel_event.is_set():
            self.cancel_button.set_sensitive(False)
            self.cancel_button.set_label(_("Cancelando…"))

    def _on_cancel(self, *_args: Any) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_button.set_sensitive(False)
            self.cancel_button.set_label(_("Cancelando…"))
            self.stage_label.set_label(_("Cancelando com segurança…"))

    def _result_from_dict(self, data: dict[str, Any]) -> FlashResult:
        image_data = data.get("image") or {}
        device_data = data.get("device") or {}
        current = self.image_info
        image = ImageInfo(
            path=Path(image_data.get("path", current.path if current else "/")),
            size=int(image_data.get("size", current.size if current else 0)),
            fmt=image_data.get("format", current.fmt if current else "iso"),
            container=image_data.get("container", current.container if current else None),
            uncompressed_size=image_data.get(
                "uncompressed_size", current.uncompressed_size if current else None
            ),
        )
        fields = (
            "sysname", "syspath", "devpath", "size", "major", "minor", "vendor",
            "model", "serial", "transport", "removable", "media",
        )
        device = DeviceIdentity(**{key: device_data.get(key, "") for key in fields})
        return FlashResult(
            success=bool(data.get("success")),
            image=image,
            device=device,
            bytes_written=int(data.get("bytes_written", 0)),
            duration=float(data.get("duration", 0)),
            sha256=data.get("sha256"),
            verified=bool(data.get("verified")),
            error=data.get("error"),
            cancelled=bool(data.get("cancelled")),
            timestamp=datetime.now(),
        )

    def _show_result(self, data: dict[str, Any]) -> None:
        result = self._result_from_dict(data)
        self.busy = False
        if not result.cancelled:
            self.history.add(result)
        self._render_result(result)
        self.stack.set_visible_child_name("result")

    def _show_error(self, message: str) -> None:
        self.busy = False
        self.result_icon.set_from_icon_name("dialog-error-symbolic")
        css(self.result_icon, "lif-error")
        self.result_title.set_label(_("Não foi possível gravar"))
        self.result_message.set_label(message)
        self._clear_details()
        self.result_history.set_visible(len(self.history.load()) > 0)
        self.stack.set_visible_child_name("result")

    def _render_result(self, result: FlashResult) -> None:
        self._clear_details()
        if result.cancelled:
            self.result_icon.set_from_icon_name("process-stop-symbolic")
            css(self.result_icon, "lif-warning")
            self.result_title.set_label(_("Gravação cancelada"))
            self.result_message.set_label(
                _("A operação foi interrompida. O dispositivo pode estar parcialmente gravado.")
            )
        elif result.success and result.verified:
            self.result_icon.set_from_icon_name("emblem-ok-symbolic")
            css(self.result_icon, "lif-success")
            self.result_title.set_label(_("Gravação concluída e verificada"))
            self.result_message.set_label(
                _("Os dados gravados conferem byte a byte com a imagem original.")
            )
        else:
            self.result_icon.set_from_icon_name("dialog-error-symbolic")
            css(self.result_icon, "lif-error")
            self.result_title.set_label(_("A gravação falhou"))
            self.result_message.set_label(result.error or _("Verificação não aprovada."))

        rows = (
            (_("Imagem"), result.image.name),
            (_("Dispositivo"), f"{result.device.name} ({result.device.devpath})"),
            (_("Dados gravados"), human_size(result.bytes_written)),
            (_("Duração"), human_duration(result.duration)),
            (_("Verificação"), _("Aprovada") if result.verified else _("Não aprovada")),
            (_("SHA-256"), (result.sha256 or "—")[:16] + "…"),
        )
        for title, value in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.append(label(title, "lif-metric-label", hexpand=True, xalign=0))
            row.append(label(value, "lif-device-meta", xalign=1))
            self.result_details.append(row)
        self.result_history.set_visible(True)

    def _clear_details(self) -> None:
        while self.result_details.get_first_child() is not None:
            self.result_details.remove(self.result_details.get_first_child())

    # --------------------------------------------------------------- histórico
    def _show_history(self) -> None:
        self._render_history()
        self.stack.set_visible_child_name("history")

    def _render_history(self) -> None:
        while self.history_list.get_first_child() is not None:
            self.history_list.remove(self.history_list.get_first_child())
        entries = self.history.load()
        if not entries:
            placeholder = Gtk.ListBoxRow()
            placeholder.set_child(
                label(
                    _("Nenhuma gravação registrada."),
                    "lif-step-hint",
                    margin_top=16,
                    margin_bottom=16,
                    margin_start=16,
                    margin_end=16,
                )
            )
            self.history_list.append(placeholder)
            return
        for entry in entries:
            row = Gtk.ListBoxRow()
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            inner.set_margin_start(12)
            inner.set_margin_end(12)
            inner.set_margin_top(8)
            inner.set_margin_bottom(8)
            inner.append(
                label(entry.image_name or _("Imagem desconhecida"), "lif-history-title", xalign=0)
            )
            inner.append(
                label(
                    _("{date} · {device} · {duration}").format(
                        date=human_datetime(entry.timestamp),
                        device=entry.device or entry.device_sysname,
                        duration=human_duration(entry.duration),
                    ),
                    "lif-history-meta",
                    xalign=0,
                )
            )
            status = (
                _("Sucesso · verificação aprovada")
                if entry.success and entry.verified
                else _("Falha · verificação não aprovada")
            )
            status_widget = label(status, "lif-history-meta", xalign=0)
            css(status_widget, "lif-success" if entry.success else "lif-error")
            inner.append(status_widget)
            row.set_child(inner)
            self.history_list.append(row)

    def _confirm_clear_history(self) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Limpar histórico?"),
            body=_("Todas as gravações registradas serão removidas deste dispositivo."),
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("clear", _("Limpar"))
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_clear_history)
        dialog.present(self)

    def _on_clear_history(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "clear":
            self.history.clear()
            self._render_history()
            self._toast(_("Histórico limpo."))

    def _show_preferences(self) -> None:
        def on_theme(theme: str) -> None:
            self.config["theme"] = theme
            save_config(self.config)
            self.get_application().set_theme(theme)

        def on_language(language: str) -> None:
            if language == current_language():
                return
            self.get_application().set_language(language)

        dialog = PreferencesDialog(self.config, on_theme, on_language)
        dialog.present(self)

    def _go_main(self) -> None:
        self.busy = False
        self.stack.set_visible_child_name("main")
