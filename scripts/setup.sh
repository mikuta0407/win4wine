#!/bin/bash
# Set up the XP shell session on this Debian 13 machine, from a fresh install
# (Arch Linux and its derivatives such as CachyOS: the packages come from pacman;
# Fedora and its derivatives: the packages come from dnf).
#
#   scripts/setup.sh --media PATH [--greeter | --no-greeter] [--theme luna|classic]
#                    [--dpi N] [--font-smoothing standard|cleartype] [--wayland]
#                    [--wine-install DIR | --jobs N]
#   scripts/setup.sh --shell reactos [--lang ja|en] [--theme T] [--greeter] [--dpi N]
#                    [--wayland] [--wine-install DIR | --jobs N]
#   scripts/setup.sh --shell win7 --media ISO [--greeter] [--dpi N] [--wine-install DIR | --jobs N]
#
#   --media PATH   the user's Windows XP SP3 (x86) ISO or Windows directory; with
#                  --shell win7, the user's Windows 7 SP1 x64 ISO
#   --shell S      xp (the default), reactos or win7. reactos: ReactOS's shell
#                  (classic look), downloaded from the ReactOS release, so no XP media
#                  is needed. win7 (experimental): Windows 7's shell (Windows 7 Basic)
#                  from the user's Windows 7 ISO, in the language of its media.
#                  Each is registered as its own session ("ReactOS Shell (Wine, X11)",
#                  "Windows 7 Shell (Wine, X11)"), beside the others that are set up
#   --lang L       ja or en: the language of the ReactOS shell and its session
#                  (default: ja when the current locale is Japanese, else en;
#                  an existing prefix keeps its language: move it away to change
#                  it); with --greeter, LightDM shows ReactOS's logon screen instead
#                  of XP's Welcome screen
#   --greeter      also make LightDM show XP's Welcome screen (greeter/), with XP's
#                  cursors; LightDM becomes the display manager. With --shell win7,
#                  Windows 7's logon screen
#   --no-greeter   keep the display manager's own login screen (the default); XP's
#                  cursors are still installed for the session
#   --theme T      luna (XP's default, the default here, with XP's Start menu) or
#                  classic (with the classic Start menu), for a new prefix; given
#                  explicitly, it is applied to an existing prefix too. For the
#                  ReactOS shell: classic (the default) or one of ReactOS's visual
#                  styles, lautus, lunar or mizu
#   --dpi N        the screen's DPI as XP sets it (LogPixels): 96 (normal), 120 (large)
#                  or any value from 19 to 480; for the XP shell, the Linux
#                  applications in its session and the Welcome screen
#   --font-smoothing S
#                  XP's screen font smoothing (Display Properties, Effects): standard
#                  (XP's default) or cleartype; for the XP shell and the Linux
#                  applications in its session. Given explicitly, it is applied to an
#                  existing prefix too
#   --wayland      also build win4wine's labwc (wayland/build.sh) and register the
#                  shell's Wayland session ("XP Shell (Wine, Wayland)", and so on):
#                  per-monitor and fractional scales (session.json "outputs"),
#                  Wayland applications with the shell's frames
#   --wine-install DIR
#                  use a Wine built elsewhere with this repository's patches (the
#                  .local/wine-install of another Debian 13 machine, copied anywhere)
#                  instead of building it here
#   --jobs N       parallel jobs for the Wine build (default: the number of CPUs)
#   --no-shadowfb  on a virtual machine whose graphics card X draws into directly
#                  (QEMU's standard VGA, Hyper-V, VirtualBox's VBoxVGA/VBoxSVGA),
#                  do not make X draw in memory first (see "Virtual machines" below)
#
# Run it as the user who will log in to the XP shell (not as root); it uses sudo
# for packages and system files. It builds Wine with this repository's patches,
# extracts the XP files, creates the XP prefix and registers the "XP Shell"
# session. Steps already done are skipped, so it can be run again after a failure.
# Everything it builds stays in .local/ of this checkout.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
local=$root/.local
media=
shell=xp
lang=
greeter=no
jobs=$(nproc)
theme=luna
theme_given=no
dpi=
smoothing=
wayland=no
prebuilt=
shadowfb=yes
while (($#)); do
    case $1 in
        --media) media=${2:?--media needs a path}; shift 2 ;;
        --shell) shell=${2:?--shell needs xp, reactos or win7}; shift 2 ;;
        --lang) lang=${2:?--lang needs ja or en}; shift 2 ;;
        --greeter) greeter=yes; shift ;;
        --no-greeter) greeter=no; shift ;;
        --jobs) jobs=${2:?--jobs needs a number}; shift 2 ;;
        --theme) theme=${2:?--theme needs luna or classic}; theme_given=yes; shift 2 ;;
        --dpi) dpi=${2:?--dpi needs a number}; shift 2 ;;
        --font-smoothing) smoothing=${2:?--font-smoothing needs standard or cleartype}; shift 2 ;;
        --wayland) wayland=yes; shift ;;
        --no-shadowfb) shadowfb=no; shift ;;
        --wine-install) prebuilt=$(realpath -e -- "${2:?--wine-install needs a directory}"); shift 2 ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) printf 'Unknown option %s (see --help)\n' "$1" >&2; exit 2 ;;
    esac
done
[[ $shell == xp || $shell == reactos || $shell == win7 ]] || { printf -- '--shell is xp, reactos or win7\n' >&2; exit 2; }
if [[ $shell == win7 ]]; then
    [[ -n $media ]] || { printf 'Give the Windows 7 ISO with --media (see --help)\n' >&2; exit 2; }
    [[ -z $lang ]] || { printf -- '--lang is for the ReactOS shell; the Windows 7 shell follows its media\n' >&2; exit 2; }
    [[ $theme_given == no ]] || { printf -- '--theme is not available for the Windows 7 shell yet\n' >&2; exit 2; }
    [[ -z $smoothing ]] || { printf -- '--font-smoothing is for the XP shell\n' >&2; exit 2; }
elif [[ $shell == reactos ]]; then
    [[ -z $media ]] || { printf -- '--media is for the XP shell; the ReactOS shell needs no media\n' >&2; exit 2; }
    [[ $theme_given == yes ]] || theme=classic
    [[ -z $smoothing ]] || { printf -- '--font-smoothing is for the XP shell\n' >&2; exit 2; }
    [[ $theme =~ ^(classic|lautus|lunar|mizu)$ ]] ||
        { printf -- '--theme for the ReactOS shell is classic, lautus, lunar or mizu\n' >&2; exit 2; }
    # An existing prefix keeps the language it was made in.
    made=
    if [[ -f $local/prefix-reactos/reactos-shell.json ]]; then
        made=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("lang", "en"))' \
            "$local/prefix-reactos/reactos-shell.json")
    fi
    if [[ -n $made && -n $lang && $lang != "$made" ]]; then
        printf '%s is in %s; move it away to make one in %s\n' "$local/prefix-reactos" "$made" "$lang" >&2
        exit 2
    fi
    if [[ -z $lang ]]; then
        if [[ -n $made ]]; then
            lang=$made
        else
            [[ ${LANG:-} == ja* ]] && lang=ja || lang=en
        fi
    fi
    [[ $lang == ja || $lang == en ]] || { printf -- '--lang is ja or en\n' >&2; exit 2; }
else
    [[ -z $lang ]] || { printf -- '--lang is for the ReactOS shell; the XP shell follows its media\n' >&2; exit 2; }
    [[ -n $media ]] || { printf 'Give the XP media with --media (see --help)\n' >&2; exit 2; }
fi
[[ $shell != xp || $theme == luna || $theme == classic ]] || { printf -- '--theme is luna or classic\n' >&2; exit 2; }
[[ -z $dpi || ( $dpi =~ ^[0-9]+$ && $dpi -ge 19 && $dpi -le 480 ) ]] ||
    { printf -- '--dpi is a number from 19 to 480\n' >&2; exit 2; }
[[ -z $smoothing || $smoothing == standard || $smoothing == cleartype ]] ||
    { printf -- '--font-smoothing is standard or cleartype\n' >&2; exit 2; }
[[ -z $media ]] || media=$(realpath -e -- "$media")
[[ $EUID -ne 0 ]] || { printf 'Run this as the user who will log in, not as root\n' >&2; exit 2; }
[[ $root != *[[:space:]]* ]] || { printf 'The checkout path must not contain spaces: %s\n' "$root" >&2; exit 2; }
# Debian 13 is the tested system; Arch Linux and its derivatives (CachyOS,
# EndeavourOS, ...) get their packages from pacman instead of apt.
# Fedora and its derivatives (Nobara, Ultramarine, ...) get them from dnf. The image-based
# Fedoras (Silverblue, Kinoite, Bazzite, ...) cannot install the session into /usr.
if [[ -e /run/ostree-booted ]]; then
    printf 'This is an image-based system (%s): /usr is read-only, so the session cannot be installed here.\n' \
        "$(. /etc/os-release; echo "$PRETTY_NAME")" >&2
    printf 'Use a package-based Debian, Arch or Fedora install (a VM is fine) for now.\n' >&2
    exit 2
fi
if command -v pacman >/dev/null && ! command -v apt-get >/dev/null; then
    distro=arch
elif command -v dnf >/dev/null && ! command -v apt-get >/dev/null; then
    distro=fedora
else
    distro=debian
    if ! grep -q '^VERSION_CODENAME=trixie' /etc/os-release; then
        printf 'Warning: written for Debian 13 (trixie); this is %s\n' "$(. /etc/os-release; echo "$PRETTY_NAME")" >&2
    fi
fi
step() { printf '\n=== %s\n' "$*"; }
# Japanese input (session.json "input_method": "fcitx5"), only for a Japanese
# shell: the packages also start fcitx5 in the other desktops of the machine
# (its autostart entry), where its own layout (us) replaces the desktop's.
install_input_method() {
    if [[ $distro == arch ]]; then
        mapfile -t missing < <(pacman -T fcitx5 fcitx5-mozc fcitx5-gtk fcitx5-qt fcitx5-configtool || true)
        ((${#missing[@]} == 0)) || sudo pacman -S --needed --noconfirm "${missing[@]}"
    elif [[ $distro == fedora ]]; then
        fedora_install fcitx5 fcitx5-mozc fcitx5-gtk fcitx5-qt fcitx5-configtool
    else
        missing=()
        for package in fcitx5 fcitx5-mozc fcitx5-frontend-gtk3 fcitx5-frontend-gtk4 \
                fcitx5-frontend-qt5 fcitx5-frontend-qt6 fcitx5-config-qt; do
            dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
        done
        ((${#missing[@]} == 0)) ||
            sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
    fi
}
mkdir -p "$local"

# The same packages on Arch Linux (pacman). Arch's display manager is the
# target of display-manager.service.
arch_display_manager() {
    basename "$(readlink -f /etc/systemd/system/display-manager.service 2>/dev/null)" .service
}
arch_packages() {
    packages=(
        # Wine build (WoW64: 64-bit Unix libraries, i686 and x86_64 MinGW for the PE modules)
        base-devel flex bison pkgconf git ca-certificates gettext
        libx11 libxext libxrender libxrandr libxi libxcursor libxinerama
        freetype2 fontconfig gnutls libglvnd alsa-lib dbus systemd-libs
        mingw-w64-gcc
        # extraction, prefix creation (xvfb-run is in xorg-server-xvfb)
        cabextract xorg-server-xvfb xorg-xauth
        # the session: X, the WM and tray bridge, recovery terminal, root cursor
        xorg-server xorg-xsetroot xorg-setxkbmap xterm python python-xlib
        python-gobject glib2 gdk-pixbuf2 librsvg
    )
    # 7z: 7zip, unless p7zip (which conflicts with it) already gives one
    command -v 7z >/dev/null || packages+=(7zip)
    if [[ $wayland == yes ]]; then
        packages+=(
            # labwc and wlroots (wayland/build.sh), Xwayland, the outputs' settings
            meson ninja wayland-protocols wayland libxkbcommon libxml2
            cairo pango glib2 libinput pixman libpng
            librsvg libdrm mesa seatd libdisplay-info
            libliftoff lcms2 hwdata libxcb xcb-util-errors xcb-util-wm xcb-util-renderutil
            xorg-xwayland wlr-randr
        )
    fi
    if [[ $shell == reactos && $lang == ja ]]; then
        packages+=(noto-fonts-cjk)
    fi
    if [[ $greeter == yes ]]; then
        packages+=(lightdm lightdm-gtk-greeter gtk3 python-cairo)
    elif [[ -z $(arch_display_manager) ]]; then
        # No display manager yet: LightDM with its usual login screen.
        packages+=(lightdm lightdm-gtk-greeter)
    fi
    mapfile -t missing < <(pacman -T "${packages[@]}" || true)
    if ((${#missing[@]})); then
        sudo pacman -S --needed --noconfirm "${missing[@]}"
    else
        printf 'All installed\n'
    fi
    if [[ $(arch_display_manager) != lightdm ]] && [[ $greeter == yes || -z $(arch_display_manager) ]]; then
        printf 'Making LightDM the display manager (it was %s)\n' "$(arch_display_manager || true)"
        sudo systemctl enable --force lightdm.service
    fi
}

# The same packages on Fedora (dnf). Like Arch, the display manager is the
# target of display-manager.service.
fedora_install() {
    local package missing=()
    for package in "$@"; do
        rpm -q --whatprovides "$package" >/dev/null 2>&1 || missing+=("$package")
    done
    if ((${#missing[@]})); then
        sudo dnf install -y --setopt=install_weak_deps=False "${missing[@]}"
    else
        printf 'All installed\n'
    fi
}
fedora_packages() {
    packages=(
        # Wine build (WoW64: 64-bit Unix libraries, i686 and x86_64 MinGW for the PE modules)
        gcc gcc-c++ make flex bison pkgconf-pkg-config git ca-certificates gettext
        libX11-devel libXext-devel libXrender-devel libXrandr-devel libXi-devel libXcursor-devel libXinerama-devel
        freetype-devel fontconfig-devel gnutls-devel libglvnd-devel alsa-lib-devel dbus-devel systemd-devel
        mingw32-gcc mingw64-gcc
        # extraction, prefix creation
        cabextract xorg-x11-server-Xvfb xorg-x11-xauth
        # the session: X, the WM and tray bridge, recovery terminal, root cursor
        xorg-x11-server-Xorg xsetroot setxkbmap xterm python3 python3-xlib
        python3-gobject glib2 gdk-pixbuf2 librsvg2
    )
    # 7z: Fedora's 7zip package (it also provides p7zip-plugins), unless one is installed
    command -v 7z >/dev/null || packages+=(7zip)
    if [[ $wayland == yes ]]; then
        packages+=(
            # labwc and wlroots (wayland/build.sh), Xwayland, the outputs' settings
            meson ninja-build wayland-protocols-devel wayland-devel libxkbcommon-devel libxml2-devel
            cairo-devel pango-devel glib2-devel libinput-devel pixman-devel libpng-devel
            librsvg2-devel libdrm-devel mesa-libgbm-devel mesa-libEGL-devel libseat-devel libdisplay-info-devel
            libliftoff-devel lcms2-devel hwdata hwdata-devel libxcb-devel
            xcb-util-errors-devel xcb-util-wm-devel xcb-util-renderutil-devel
            xorg-x11-server-Xwayland wlr-randr
        )
    fi
    if [[ $shell == reactos && $lang == ja ]]; then
        packages+=(google-noto-sans-cjk-fonts)
    fi
    if [[ $greeter == yes ]]; then
        packages+=(lightdm lightdm-gtk lightdm-gobject gtk3 python3-cairo)
    elif [[ -z $(arch_display_manager) ]]; then
        # No display manager yet: LightDM with its usual login screen.
        packages+=(lightdm lightdm-gtk)
    fi
    fedora_install "${packages[@]}"
    if [[ $(arch_display_manager) != lightdm ]] && [[ $greeter == yes || -z $(arch_display_manager) ]]; then
        printf 'Making LightDM the display manager (it was %s)\n' "$(arch_display_manager || true)"
        sudo systemctl enable --force lightdm.service
    fi
    # The X session needs the default target to be graphical
    [[ $(systemctl get-default) == graphical.target ]] || sudo systemctl set-default graphical.target
}

step 'Packages'
if [[ $distro == arch ]]; then
    arch_packages
elif [[ $distro == fedora ]]; then
    fedora_packages
else
    packages=(
        # Wine build (WoW64: 64-bit Unix libraries, i686 and x86_64 MinGW for the PE modules)
        build-essential flex bison pkg-config git ca-certificates
        # Wine's translations (msgfmt): Wine's own programs and dialogs in the session's language
        gettext
        libx11-dev libxext-dev libxrender-dev libxrandr-dev libxi-dev libxcursor-dev libxinerama-dev
        libfreetype-dev libfontconfig-dev libgnutls28-dev libgl-dev libasound2-dev libdbus-1-dev libudev-dev
        gcc-mingw-w64-i686 gcc-mingw-w64-x86-64
        # extraction, prefix creation
        cabextract p7zip-full xvfb xauth
        # the session: X, the WM and tray bridge, recovery terminal, root cursor
        xserver-xorg x11-xserver-utils x11-xkb-utils xterm python3 python3-xlib
        python3-gi gir1.2-glib-2.0 gir1.2-gdkpixbuf-2.0 librsvg2-common
        locales
    )
    if [[ $wayland == yes ]]; then
        packages+=(
            # labwc and wlroots (wayland/build.sh), Xwayland, the outputs' settings
            meson ninja-build wayland-protocols libwayland-dev libxkbcommon-dev libxml2-dev
            libcairo2-dev libpango1.0-dev libglib2.0-dev libinput-dev libpixman-1-dev libpng-dev
            librsvg2-dev libdrm-dev libgbm-dev libegl-dev libgles-dev libseat-dev libdisplay-info-dev
            libliftoff-dev liblcms2-dev hwdata libxcb1-dev libxcb-composite0-dev libxcb-dri3-dev
            libxcb-errors-dev libxcb-ewmh-dev libxcb-icccm4-dev libxcb-present-dev libxcb-randr0-dev
            libxcb-render0-dev libxcb-render-util0-dev libxcb-res0-dev libxcb-shm0-dev
            libxcb-xfixes0-dev libxcb-xinput-dev xwayland wlr-randr
        )
    fi
    if [[ $shell == reactos && $lang == ja ]]; then
        # Japanese text where ReactOS's DroidSansFallback is not linked in (the folder
        # window's address bar, Linux applications); the XP shell has XP's MS Gothic
        packages+=(fonts-noto-cjk)
    fi
    if [[ $greeter == yes ]]; then
        packages+=(lightdm lightdm-gtk-greeter gir1.2-lightdm-1 gir1.2-gtk-3.0 python3-gi-cairo)
    elif [[ ! -e /etc/X11/default-display-manager ]]; then
        # No display manager yet: LightDM with its usual login screen.
        packages+=(lightdm lightdm-gtk-greeter)
    fi
    missing=()
    for package in "${packages[@]}"; do
        dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
    done
    if ((${#missing[@]})); then
        sudo apt-get update
        sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
    else
        printf 'All installed\n'
    fi
    if [[ $greeter == yes && $(cat /etc/X11/default-display-manager 2>/dev/null) != /usr/sbin/lightdm ]]; then
        printf 'Making LightDM the display manager (it was %s)\n' "$(cat /etc/X11/default-display-manager 2>/dev/null || echo none)"
        echo /usr/sbin/lightdm | sudo tee /etc/X11/default-display-manager >/dev/null
        sudo systemctl enable --force lightdm.service
    fi
fi

# The Unix locale of the session and its Wine prefix, in the shell's language:
# for the XP shell that of its media (Japanese or English XP), for the
# ReactOS shell --lang.
make_locale() {
    locale=ja_JP.UTF-8
    [[ $lang == ja ]] || locale=en_US.UTF-8
    [[ $lang != ja ]] || install_input_method
    step "Locale $locale"
    if [[ $distro == fedora ]]; then
        # Fedora has no locale-gen: each language's locales are a glibc langpack
        fedora_install "glibc-langpack-${locale%%_*}"
    elif ! locale -a | grep -qix "${locale%.UTF-8}.utf8"; then
        sudo sed -i "s/^# *\\($locale UTF-8\\)/\\1/" /etc/locale.gen
        grep -q "^$locale UTF-8" /etc/locale.gen || echo "$locale UTF-8" | sudo tee -a /etc/locale.gen >/dev/null
        sudo locale-gen
    else
        printf '%s exists\n' "$locale"
    fi
}

step 'Wine'
wine=$local/wine-install/bin/wine
# The patches of this checkout; a build records those it was made with.
patches=$(python3 "$root/wine/patch-state.py" --digest "$root/wine/patches")
if [[ -n $prebuilt ]]; then
    [[ -f $prebuilt/lib/wine/x86_64-windows/win4wine-controls.dll && -x $prebuilt/bin/wine ]] ||
        { printf '%s is not a Wine install built by wine/build.sh\n' "$prebuilt" >&2; exit 1; }
    wine=$prebuilt/bin/wine
    printf 'Using %s: %s\n' "$prebuilt" "$("$wine" --version)"
    [[ $(cat "$prebuilt/win4wine-patches" 2>/dev/null) == "$patches" ]] ||
        printf 'Warning: %s was not built with the patches of this checkout\n' "$prebuilt" >&2
elif [[ -x $wine && -f $local/wine-install/lib/wine/x86_64-windows/win4wine-controls.dll &&
        $(cat "$local/wine-install/win4wine-patches" 2>/dev/null) == "$patches" ]]; then
    printf 'Built: %s\n' "$("$wine" --version)"
else
    if [[ -x $wine ]]; then
        printf 'The patches changed since the last build; rebuilding what they touch\n'
    fi
    printf 'Building Wine with %s jobs (log: .local/wine-build.log); this takes a long time\n' "$jobs"
    JOBS=$jobs python3 "$root/scripts/progress.py" "$local/wine-build.log" Wine -- "$root/wine/build.sh" ||
        { tail -20 "$local/wine-build.log" >&2; printf 'Wine build failed; see .local/wine-build.log\n' >&2; exit 1; }
    "$wine" --version
fi

step 'Bridge'
"$root/bridge-wm/build.sh"
printf 'Built .local/bridge\n'

labwc=$local/labwc-install/bin/labwc
if [[ $wayland == yes ]]; then
    step 'Wayland compositor'
    labwc_patches=$(python3 "$root/wine/patch-state.py" --digest "$root/wayland/patches/labwc" "$root/wayland/patches/wlroots")
    if [[ -x $labwc && $(cat "$local/labwc-install/win4wine-patches" 2>/dev/null) == "$labwc_patches" ]]; then
        printf 'Built: %s\n' "$("$labwc" --version)"
    else
        [[ ! -x $labwc ]] || printf 'The patches changed since the last build; rebuilding what they touch\n'
        printf 'Building labwc and wlroots (log: .local/labwc-build.log)\n'
        JOBS=$jobs python3 "$root/scripts/progress.py" "$local/labwc-build.log" labwc -- "$root/wayland/build.sh" ||
            { tail -20 "$local/labwc-build.log" >&2; printf 'labwc build failed; see .local/labwc-build.log\n' >&2; exit 1; }
        "$labwc" --version
    fi
fi

if [[ $shell == xp ]]; then
    step 'XP files'
    assets=$local/assets
    if [[ -f $assets/manifest.json ]]; then
        printf 'Extracted already: %s\n' "$assets"
    else
        # 7z needs room for the whole medium; keep it out of a small /tmp.
        mkdir -p "$local/tmp"
        TMPDIR=$local/tmp python3 "$root/extract/extract.py" "$media" "$assets"
    fi
    # Files that XP Explorer's additions brought, for an extraction made before them.
    read -r -a added <<< "$(python3 "$root/extract/extract.py" --missing "$assets")"
    if ((${#added[@]})); then
        printf 'Adding %s to the extraction\n' "${added[*]}"
        mkdir -p "$local/tmp"
        TMPDIR=$local/tmp python3 "$root/extract/extract.py" "${added[@]/#/--only=}" "$media" "$assets"
    fi
    lang=$(python3 "$root/extract/media.py" --warn "$assets")
    printf 'Windows XP in %s\n' "$([[ $lang == ja ]] && echo Japanese || echo English)"
    make_locale

    step 'XP prefix'
    prefix=$local/prefix
    if [[ -f $prefix/xp-shell.json ]]; then
        printf 'Created already: %s\n' "$prefix"
    else
        [[ ! -e $prefix ]] || { printf '%s exists but is incomplete; move it away and run again\n' "$prefix" >&2; exit 1; }
        xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/create.py" "$assets" "$prefix" \
            --home "$HOME" --wine "$wine" > "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; printf 'Prefix creation failed; see .local/prefix.log\n' >&2; exit 1; }
        printf 'Created %s\n' "$prefix"
        # Until the theme is set, a later run sets it too
        touch "$prefix/.theme-pending"
    fi
    [[ ! -f $prefix/.theme-pending ]] || theme_given=yes
    if [[ $theme_given == yes ]]; then
        WINEPREFIX=$prefix WINE=$wine xvfb-run -a -s '-screen 0 1280x800x24' \
            python3 "$root/prefix/display.py" --theme "$theme" --menu "$([[ $theme == luna ]] && echo xp || echo classic)" \
            >> "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; printf 'Setting the theme failed; see .local/prefix.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        rm -f "$prefix/.theme-pending"
        printf 'Theme: %s\n' "$theme"
    fi
    if [[ -n $dpi ]]; then
        WINEPREFIX=$prefix WINE=$wine python3 "$root/prefix/display.py" --dpi "$dpi" >> "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; printf 'Setting the DPI failed; see .local/prefix.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        printf 'DPI: %s\n' "$dpi"
    fi
    if [[ -n $smoothing ]]; then
        WINEPREFIX=$prefix WINE=$wine python3 "$root/prefix/display.py" --font-smoothing "$smoothing" \
            >> "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; printf 'Setting the font smoothing failed; see .local/prefix.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        printf 'Font smoothing: %s\n' "$smoothing"
    fi
    # XP Explorer's additions (prefix/extras.py): the notification area's
    # network, battery and volume icons, the folder task pane, Display
    # Properties, XP's sounds, IE6, Windows Media Player, the Start menu's
    # left column and Regional and Language Options, whose input languages
    # start as the system's keyboard layout. Again when they change or after
    # a Wine build.
    if ! python3 "$root/prefix/extras.py" "$prefix" --check "$wine"; then
        printf 'Adding the XP Explorer additions (log: .local/prefix.log)\n'
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -k 2>/dev/null || true
        xvfb-run -a -s '-screen 0 1280x800x24' bash -c '
            python3 "$1/prefix/extras.py" "$2" --wine "$3" &&
            python3 "$1/session/linux_apps.py" "$2" --wine "$3" &&
            python3 "$1/xp-explorer/scripts/pins.py" "$2" --wine "$3"' _ "$root" "$prefix" "$wine" \
            >> "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; printf 'The XP Explorer additions failed; see .local/prefix.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -k 2>/dev/null || true
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        printf 'Added\n'
    else
        printf 'XP Explorer additions: up to date\n'
    fi
elif [[ $shell == win7 ]]; then
    step 'Windows 7 files'
    assets=$local/assets-win7
    wanted=$(sed -n 's/^EXTRACT_VERSION = //p' "$root/extract/win7.py")
    have=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("extract_version", 1))' \
        "$assets/media.json" 2>/dev/null || echo 0)
    if [[ -f $assets/manifest.json && $have == "$wanted" ]]; then
        printf 'Extracted already: %s\n' "$assets"
    else
        # 7z needs room for install.wim; keep it out of a small /tmp.
        mkdir -p "$local/tmp"
        rm -rf "$assets.new"
        TMPDIR=$local/tmp python3 "$root/extract/win7.py" "$media" "$assets.new"
        # An earlier extraction: replaced; the prefix's stage takes the new files.
        rm -rf "$assets"
        mv "$assets.new" "$assets"
    fi
    lang=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["lang"])' "$assets/media.json")
    printf 'Windows 7 in %s\n' "$([[ $lang == ja ]] && echo Japanese || echo English)"
    make_locale

    step 'Windows 7 shell prefix'
    prefix=$local/prefix-win7
    if [[ -f $prefix/win7-shell.json ]]; then
        printf 'Created already: %s\n' "$prefix"
    else
        [[ ! -e $prefix ]] || { printf '%s exists but is incomplete; move it away and run again\n' "$prefix" >&2; exit 1; }
        xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/win7.py" create "$assets" "$prefix" \
            --home "$HOME" --wine "$wine" > "$local/prefix-win7.log" 2>&1 ||
            { tail -20 "$local/prefix-win7.log" >&2; printf 'Prefix creation failed; see .local/prefix-win7.log\n' >&2; exit 1; }
        printf 'Created %s\n' "$prefix"
    fi
    if [[ -n $dpi ]]; then
        WINEPREFIX=$prefix WINE=$wine python3 "$root/prefix/display.py" --dpi "$dpi" >> "$local/prefix-win7.log" 2>&1 ||
            { tail -20 "$local/prefix-win7.log" >&2; printf 'Setting the DPI failed; see .local/prefix-win7.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        printf 'DPI: %s\n' "$dpi"
    fi
else
    step 'ReactOS files'
    assets=$local/assets-reactos
    if [[ -f $assets/manifest.json ]]; then
        printf 'Extracted already: %s\n' "$assets"
    else
        # The release zip is kept in .local/dl; 7z needs room for the ISO, out of a small /tmp.
        mkdir -p "$local/tmp"
        TMPDIR=$local/tmp python3 "$root/extract/reactos.py" "$assets" --cache "$local/dl"
    fi
    make_locale

    step 'ReactOS shell prefix'
    prefix=$local/prefix-reactos
    if [[ ! -f $prefix/reactos-shell.json ]]; then
        [[ ! -e $prefix ]] || { printf '%s exists but is incomplete; move it away and run again\n' "$prefix" >&2; exit 1; }
        xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/reactos.py" create "$assets" "$prefix" \
            --home "$HOME" --wine "$wine" --lang "$lang" --theme "$theme" > "$local/prefix-reactos.log" 2>&1 ||
            { tail -20 "$local/prefix-reactos.log" >&2; printf 'Prefix creation failed; see .local/prefix-reactos.log\n' >&2; exit 1; }
        printf 'Created %s\n' "$prefix"
    elif [[ $theme_given == yes ]]; then
        xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/reactos.py" theme "$prefix" "$theme" --wine "$wine" \
            >> "$local/prefix-reactos.log" 2>&1 ||
            { tail -20 "$local/prefix-reactos.log" >&2; printf 'Setting the theme failed; see .local/prefix-reactos.log\n' >&2; exit 1; }
        printf 'Theme: %s\n' "$theme"
    else
        printf 'Created already: %s\n' "$prefix"
    fi
    if [[ -n $dpi ]]; then
        WINEPREFIX=$prefix WINE=$wine python3 "$root/prefix/display.py" --dpi "$dpi" >> "$local/prefix-reactos.log" 2>&1 ||
            { tail -20 "$local/prefix-reactos.log" >&2; printf 'Setting the DPI failed; see .local/prefix-reactos.log\n' >&2; exit 1; }
        WINEPREFIX=$prefix "$(dirname "$wine")/wineserver" -w 2>/dev/null || true
        printf 'DPI: %s\n' "$dpi"
    fi
fi

step 'Session'
case $shell in
    xp) config_name=session.json ;;
    reactos) config_name=reactos-session.json ;;
    win7) config_name=win7-session.json ;;
esac
config=${XDG_CONFIG_HOME:-$HOME/.config}/win4wine/$config_name
if [[ -f $config ]]; then
    # Kept, with the Wine and the language of the prefix (a new prefix may be
    # made with another Wine, or be in another language)
    python3 - "$config" "$locale" "$wine" <<'EOF'
import json, sys
config, locale, wine = sys.argv[1:]
settings = json.load(open(config))
changes = []
if settings.get('wine') != wine:
    settings['wine'] = wine
    changes.append(f'Wine {wine}')
if settings.get('locale') != locale:
    settings['locale'] = locale
    if locale.startswith('ja'):
        settings['input_method'] = 'fcitx5'
    else:
        settings.pop('input_method', None)
    changes.append(f'locale {locale}')
if settings.get('shell') == 'win7' and settings.get('cursor_theme') == '':
    # Made before the Windows 7 shell had its cursors
    settings['cursor_theme'] = 'win4wine-win7'
    changes.append('Windows 7 cursors')
if changes:
    open(config, 'w').write(json.dumps(settings, indent=2) + '\n')
    print(f'Updated {config}: {", ".join(changes)}')
else:
    print(f'Keeping {config}')
EOF
else
    mkdir -p "$(dirname "$config")"
    python3 - "$config" "$wine" "$prefix" "$shell" "$locale" <<'EOF'
import json, sys
config, wine, prefix, shell, locale = sys.argv[1:]
settings = {'wine': wine, 'prefix': prefix, 'locale': locale}
if locale.startswith('ja'):
    settings['input_method'] = 'fcitx5'
if shell == 'reactos':
    settings.update(shell='reactos', cursor_theme='win4wine-reactos')
elif shell == 'win7':
    settings.update(shell='win7', cursor_theme='win4wine-win7')
open(config, 'w').write(json.dumps(settings, indent=2) + '\n')
EOF
    printf 'Wrote %s\n' "$config"
fi
if [[ $wayland == yes && $shell == reactos ]]; then
    "$root/session/install.sh" --reactos --wayland "$labwc"
elif [[ $wayland == yes && $shell == win7 ]]; then
    "$root/session/install.sh" --win7 --wayland "$labwc"
elif [[ $wayland == yes ]]; then
    "$root/session/install.sh" --wayland "$labwc"
elif [[ $shell == reactos ]]; then
    "$root/session/install.sh" --reactos
elif [[ $shell == win7 ]]; then
    "$root/session/install.sh" --win7
else
    "$root/session/install.sh"
fi

step 'Virtual machines'
# Without a GPU of its own, X's modesetting driver draws straight into the
# graphics memory of these virtual cards, and every window moved is read back
# from it, which is slow (most of the X server's work while dragging a window
# in QEMU). Drawing in memory first (ShadowFB) leaves only writes to it.
# Cards whose memory is the guest's own (virtio-gpu, VMware's) need nothing.
drivers=()
for card in /sys/class/drm/card*/device/driver; do
    [[ -e $card ]] || continue
    driver=$(basename "$(readlink -f "$card")")
    case $driver in
        bochs-drm|bochs|hyperv_drm|vboxvideo|cirrus|cirrus-qemu) drivers+=("$driver") ;;
    esac
done
xorg_conf=/etc/X11/xorg.conf.d/20-win4wine-shadowfb.conf
if [[ ${#drivers[@]} -eq 0 ]]; then
    printf 'No virtual graphics card that needs it\n'
elif [[ $shadowfb == no ]]; then
    printf 'Left X as it is (--no-shadowfb)\n'
else
    sudo mkdir -p /etc/X11/xorg.conf.d
    sudo tee "$xorg_conf" >/dev/null <<EOF
# Written by win4wine's scripts/setup.sh: X draws in memory first on virtual
# graphics cards whose memory is slow to read back (moving windows). Remove
# this file to undo; it applies to every X session from the next start of X.
Section "OutputClass"
    Identifier "win4wine: shadow framebuffer on virtual graphics cards"
    MatchDriver "$(IFS='|'; echo "${drivers[*]}")"
    Driver "modesetting"
    Option "ShadowFB" "true"
EndSection
EOF
    printf 'Wrote %s (%s)\n' "$xorg_conf" "${drivers[*]}"
fi

step 'Login screen and cursors'
if [[ $shell == win7 ]]; then
    # Windows 7's Aero cursors for the session (and the logon screen).
    theme=$(mktemp -d)
    python3 "$root/greeter/cursors.py" --win7 "$assets/cursors/user32.dll" "$assets/cursors" "$theme/win4wine-win7"
    sudo rm -rf /usr/share/icons/win4wine-win7
    sudo cp -r "$theme/win4wine-win7" /usr/share/icons/
    sudo chmod -R a+rX /usr/share/icons/win4wine-win7
    rm -rf "$theme"
    printf 'Installed Windows 7 cursors\n'
    if [[ $greeter == yes ]]; then
        "$root/greeter/install.sh" --win7 "$assets" \
            "$([[ $wayland == yes ]] && echo windows7-shell-wayland || echo windows7-shell)"
    fi
elif [[ $shell == reactos ]]; then
    if [[ $greeter == yes ]]; then
        "$root/greeter/install.sh" --reactos "$assets" "$lang" \
            "$([[ $wayland == yes ]] && echo reactos-shell-wayland || echo reactos-shell)"
    fi
    # ReactOS's cursors for the session (and the logon screen).
    theme=$(mktemp -d)
    python3 "$root/greeter/cursors.py" "$assets/resources/user32.dll" "$theme/win4wine-reactos" --reactos
    sudo rm -rf /usr/share/icons/win4wine-reactos
    sudo cp -r "$theme/win4wine-reactos" /usr/share/icons/
    sudo chmod -R a+rX /usr/share/icons/win4wine-reactos
    rm -rf "$theme"
    printf 'Installed ReactOS cursors\n'
elif [[ $greeter == yes ]]; then
    "$root/greeter/install.sh" "$assets" "$([[ $wayland == yes ]] && echo xp-shell-wayland || echo xp-shell)"
    if [[ -n $dpi ]]; then
        # XP's Welcome screen takes the machine's DPI.
        sudo python3 - "$dpi" <<'EOF'
import json, sys
path = '/etc/win4wine/greeter.json'
config = json.load(open(path))
config['dpi'] = int(sys.argv[1])
open(path, 'w').write(json.dumps(config) + '\n')
EOF
    fi
else
    # XP's cursors for the session only; LightDM, if any, keeps its own greeter.
    theme=$(mktemp -d)
    python3 "$root/greeter/cursors.py" "$assets/resources/user32.dll" "$theme/win4wine-xp"
    sudo rm -rf /usr/share/icons/win4wine-xp
    sudo cp -r "$theme/win4wine-xp" /usr/share/icons/
    sudo chmod -R a+rX /usr/share/icons/win4wine-xp
    rm -rf "$theme"
    printf 'Installed XP cursors; the display manager keeps its login screen\n'
fi

step 'Done'
if [[ $shell == reactos && $greeter == yes ]]; then
    printf 'Restart the display manager (or reboot): the ReactOS logon screen logs in to the ReactOS shell.\n'
elif [[ $shell == reactos ]]; then
    printf 'Restart the display manager (or reboot) and choose "ReactOS Shell (Wine, X11)" at the login screen.\n'
elif [[ $shell == win7 && $greeter == yes ]]; then
    printf 'Restart the display manager (or reboot): the Windows 7 logon screen logs in to the Windows 7 shell.\n'
elif [[ $shell == win7 ]]; then
    printf 'Restart the display manager (or reboot) and choose "Windows 7 Shell (Wine, X11)" at the login screen.\n'
elif [[ $greeter == yes ]]; then
    printf 'Restart the display manager (or reboot): the XP Welcome screen logs in to the XP shell.\n'
else
    printf 'Restart the display manager (or reboot) and choose "XP Shell (Wine, X11)" at the login screen.\n'
fi
if [[ $wayland == yes && $shell == reactos ]]; then
    printf 'The Wayland session is "ReactOS Shell (Wine, Wayland)"; outputs and scales: reactos-session.json "outputs".\n'
elif [[ $wayland == yes && $shell == win7 ]]; then
    printf 'The Wayland session is "Windows 7 Shell (Wine, Wayland)"; outputs and scales: win7-session.json "outputs".\n'
elif [[ $wayland == yes ]]; then
    printf 'The Wayland session is "XP Shell (Wine, Wayland)"; outputs and scales: session.json "outputs".\n'
fi
printf 'Logs of the session: ~/.local/state/win4wine/\n'
