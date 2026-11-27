# Especificação para Fedora/RHEL-like. Suposições:
#   * o tarball é gerado na raiz do repositório (git archive) com prefixo
#     linux-iso-flasher-0.1.0/;
#   * o wheel é instalado com pip --root=%%{buildroot} --prefix=/usr;
#   * em distros com %py3_build_wheel/%py3_install_wheel, esses macros podem
#     substituir os comandos pip abaixo.
Name:           linux-iso-flasher
Version:        0.1.0
Release:        1%{?dist}
Summary:        Gravador de imagens ISO/IMG para dispositivos removíveis
License:        GPL-3.0-or-later
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz
# URL: ajuste ao seu repositório antes de publicar.

BuildRequires:  python3 >= 3.11
BuildRequires:  python3-build
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       udisks2
Requires:       polkit
Requires:       zstd

%description
Interface GTK4/libadwaita para gravar imagens em dispositivos removíveis.
A enumeração e a desmontagem usam UDisks2; a gravação é feita por um helper
privilegiado autorizado por Polkit, com verificação byte a byte.

Write ISO/IMG images to removable devices with a GTK4/libadwaita interface.
Devices are enumerated and unmounted through UDisks2; a Polkit-authorized
root helper writes and verifies the image.

%prep
%autosetup -n %{name}-%{version}

%build
%{__python3} -m build --wheel --no-isolation

%install
%{__python3} -m pip install --no-deps --ignore-installed \
    --root=%{buildroot} --prefix=%{_prefix} dist/*.whl

# O wheel instala packaging/helper/helper como
# %{_libexecdir}/%{name}/helper, exigido pela política Polkit.

%files
%license LICENSE
%doc README.md CONTRIBUTING.md docs/INSTALL.md docs/ARCHITECTURE.md docs/TESTING.md
%{_bindir}/linux-iso-flasher
%{python3_sitelib}/linux_iso_flasher*
%{python3_sitelib}/linux_iso_flasher-%{version}.dist-info/
%{_libexecdir}/%{name}/helper*
%{_datadir}/applications/linux-iso-flasher.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.linuxisoflasher.svg
%{_datadir}/polkit-1/actions/org.linuxisoflasher.pkexec.policy

%changelog
* Thu Nov 27 2026 Linux ISO Flasher contributors - 0.1.0-1
- Versão inicial.
