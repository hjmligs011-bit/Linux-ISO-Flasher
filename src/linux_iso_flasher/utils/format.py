"""Formatação legível de tamanhos, tempo, velocidade e datas."""

from __future__ import annotations

from datetime import datetime

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")


def human_size(size: int | float | None, precision: int = 1) -> str:
    if size is None:
        return "—"
    value = float(size)
    for unit in _UNITS:
        if abs(value) < 1024.0 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.{precision}f} {unit}"
        value /= 1024.0
    return f"{value:.{precision}f} PiB"  # pragma: no cover


def human_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return "—"
    return f"{human_size(bytes_per_second)}/s"


def human_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def human_datetime(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d/%m/%Y %H:%M")
