#!/bin/bash
# install.sh [--reactos | --win7] [--wayland LABWC] : the XP shell's X11 session, and
# with a labwc built by wayland/build.sh also its Wayland session. With --reactos,
# instead the "ReactOS Shell" session, which reads ~/.config/win4wine/reactos-session.json
# (with --wayland also its Wayland session). With --win7, instead the "Windows 7 Shell"
# session, which reads ~/.config/win4wine/win7-session.json (with --wayland
# also its Wayland session). The sessions of shells set up earlier stay.
# Also, per user, ~/.local/bin/win4wine-wine (session/wine.py).
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $root != *$'\n'* ]] || exit 1
labwc=
reactos=no
win7=no
if [[ ${1:-} == --reactos ]]; then
    reactos=yes
    shift
elif [[ ${1:-} == --win7 ]]; then
    win7=yes
    shift
fi
if [[ ${1:-} == --wayland ]]; then
    labwc=$(realpath -e -- "${2:?--wayland needs the labwc binary}")
    [[ $labwc != *$'\n'* ]] || exit 1
fi
# As root (a fresh system without sudo) or through sudo
as_root() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }
wrapper=$(mktemp)
trap 'rm -f "$wrapper"' EXIT
# The XP shell's session only when that is the shell being set up: with
# --reactos or --win7 alone there is no session.json, and the login screen
# would list an "XP Shell" session that ends at once.
if [[ $reactos == no && $win7 == no ]]; then
    printf '#!/bin/bash\nexec python3 %q "$@"\n' "$root/session/supervisor.py" > "$wrapper"
    as_root install -Dm755 "$wrapper" /usr/local/bin/xp-shell-session
    as_root install -Dm644 "$root/session/xp-shell.desktop" /usr/share/xsessions/xp-shell.desktop
    printf 'Installed Xsession. Configuration: ~/.config/win4wine/session.json\n'
fi
# win4wine-wine: "wine" as the session runs it, for terminals outside the
# session. Per user, as it runs this user's checkout and session.json.
printf '#!/bin/bash\nexec python3 %q "$@"\n' "$root/session/wine.py" > "$wrapper"
install -Dm755 "$wrapper" "$HOME/.local/bin/win4wine-wine"
printf 'Installed ~/.local/bin/win4wine-wine\n'
if [[ $reactos == yes ]]; then
    printf '#!/bin/bash\nexec python3 %q --config "${XDG_CONFIG_HOME:-$HOME/.config}/win4wine/reactos-session.json" "$@"\n' \
        "$root/session/supervisor.py" > "$wrapper"
    as_root install -Dm755 "$wrapper" /usr/local/bin/reactos-shell-session
    as_root install -Dm644 "$root/session/reactos-shell.desktop" /usr/share/xsessions/reactos-shell.desktop
    printf 'Installed the ReactOS shell Xsession. Configuration: ~/.config/win4wine/reactos-session.json\n'
fi
if [[ $win7 == yes ]]; then
    printf '#!/bin/bash\nexec python3 %q --config "${XDG_CONFIG_HOME:-$HOME/.config}/win4wine/win7-session.json" "$@"\n' \
        "$root/session/supervisor.py" > "$wrapper"
    as_root install -Dm755 "$wrapper" /usr/local/bin/windows7-shell-session
    as_root install -Dm644 "$root/session/windows7-shell.desktop" /usr/share/xsessions/windows7-shell.desktop
    printf 'Installed the Windows 7 shell Xsession. Configuration: ~/.config/win4wine/win7-session.json\n'
fi
if [[ -n $labwc ]]; then
    if [[ $reactos == no && $win7 == no ]]; then
        printf '#!/bin/bash\nexec %q %q\n' "$root/wayland/session.sh" "$labwc" > "$wrapper"
        as_root install -Dm755 "$wrapper" /usr/local/bin/xp-shell-wayland-session
        as_root install -Dm644 "$root/session/xp-shell-wayland.desktop" \
            /usr/share/wayland-sessions/xp-shell-wayland.desktop
        printf 'Installed the Wayland session (%s)\n' "$labwc"
    fi
    if [[ $reactos == yes ]]; then
        printf '#!/bin/bash\nexec %q %q --config "${XDG_CONFIG_HOME:-$HOME/.config}/win4wine/reactos-session.json" "$@"\n' \
            "$root/wayland/session.sh" "$labwc" > "$wrapper"
        as_root install -Dm755 "$wrapper" /usr/local/bin/reactos-shell-wayland-session
        as_root install -Dm644 "$root/session/reactos-shell-wayland.desktop" \
            /usr/share/wayland-sessions/reactos-shell-wayland.desktop
        printf 'Installed the ReactOS shell Wayland session\n'
    fi
    if [[ $win7 == yes ]]; then
        printf '#!/bin/bash\nexec %q %q --config "${XDG_CONFIG_HOME:-$HOME/.config}/win4wine/win7-session.json" "$@"\n' \
            "$root/wayland/session.sh" "$labwc" > "$wrapper"
        as_root install -Dm755 "$wrapper" /usr/local/bin/windows7-shell-wayland-session
        as_root install -Dm644 "$root/session/windows7-shell-wayland.desktop" \
            /usr/share/wayland-sessions/windows7-shell-wayland.desktop
        printf 'Installed the Windows 7 shell Wayland session\n'
    fi
fi
