#!/bin/bash
# The XP shell's session in a window of the current desktop, for debugging
# (Arch / CachyOS, Debian or Fedora, no system files touched; scripts/setup.sh installs the real session,
# xp-explorer/xp.sh runs XP Explorer in a Wine virtual desktop instead).
#
#   ./xp.sh setup ISO       build Wine and the bridge, extract the XP files, create the prefix
#   ./xp.sh run [WxH]       open the XP session in a Xephyr window (default: 1280x800)
#   ./xp.sh log [NAME]      follow a log of the running session (default: xp-shell)
#   ./xp.sh kill            stop the session and everything that runs in the prefix
#
# Switches, for a test copy beside your own:
#   XP_PREFIX     the Wine prefix (default: .local/prefix, the one scripts/setup.sh makes)
#   XP_LOG        the session's state and log directory (default: .local/xp-run)
#   XP_DISPLAY    the nested X display (default: the first free one from :5)
#   XP_WINEDEBUG  Wine's debug channels (default: +timestamp,fixme-all)
#   XP_THEME      luna or classic, for a new prefix (default: luna)
#   XP_ISO        the XP media, for files a later version extracts (default: setup's)
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")" && pwd)
local=$root/.local
assets=$local/assets
prefix=$(realpath -m -- "${XP_PREFIX:-$local/prefix}")
state=$(realpath -m -- "${XP_LOG:-$local/xp-run}")
wine=$local/wine-install/bin/wine
if command -v dnf >/dev/null && ! command -v pacman >/dev/null; then
    install='sudo dnf install'
    packages='wine cabextract 7zip mingw32-gcc mingw64-gcc xorg-x11-server-Xephyr xorg-x11-server-Xvfb python3-xlib python3-gobject python3-cairo xterm xsetroot'
elif command -v apt-get >/dev/null; then
    install='sudo apt-get install'
    packages='wine cabextract p7zip-full gcc-mingw-w64 xserver-xephyr xvfb python3-xlib python3-gi python3-gi-cairo xterm x11-xserver-utils'
else
    install='sudo pacman -S --needed'
    packages='wine cabextract 7zip mingw-w64-gcc xorg-server-xephyr xorg-server-xvfb python-xlib python-gobject python-cairo xterm xorg-xsetroot'
fi

need() {
    local tool missing=()
    for tool in "$@"; do command -v "$tool" >/dev/null || missing+=("$tool"); done
    python3 -c 'import Xlib, gi, cairo' 2>/dev/null || missing+=(python-xlib)
    if ((${#missing[@]})); then
        printf 'Missing %s: %s %s\n' "${missing[*]}" "$install" "$packages" >&2
        exit 1
    fi
}

# Our nested display: the one recorded by the last run while its Xephyr is alive.
running_display() {
    local display
    display=$(cat "$state/display" 2>/dev/null) || return 1
    [[ -e /tmp/.X11-unix/X${display#:} ]] && pgrep -f "^Xephyr $display " >/dev/null && echo "$display"
}

stop_prefix() {
    [[ -x $wine ]] || return 0
    WINEPREFIX=$prefix timeout 20 "${wine%/wine}/wineserver" -k 2>/dev/null || true
    WINEPREFIX=$prefix timeout 20 "${wine%/wine}/wineserver" -w 2>/dev/null || true
}

# Files that XP Explorer's additions brought, for an extraction made before them.
add_media_files() {
    local added
    read -r -a added <<< "$(python3 "$root/extract/extract.py" --missing "$assets")"
    ((${#added[@]})) || return 0
    [[ -n ${1:-} && -e ${1:-} ]] ||
        { echo "The extraction lacks ${added[*]}: run $0 setup /path/to/the.iso again" >&2; exit 1; }
    echo "Adding ${added[*]} to the extraction"
    mkdir -p "$local/tmp"
    TMPDIR=$local/tmp python3 "$root/extract/extract.py" "${added[@]/#/--only=}" "$1" "$assets"
}

# XP Explorer's additions (prefix/extras.py), as scripts/setup.sh adds them:
# the notification area's icons, Display Properties, IE6, XP's sounds and so
# on; again when they change or after a Wine build.
add_extras() {
    python3 "$root/prefix/extras.py" "$prefix" --check "$wine" && return 0
    need xvfb-run
    echo "Adding the XP Explorer additions to the prefix (log: .local/prefix.log)"
    stop_prefix
    xvfb-run -a -s '-screen 0 1280x800x24' bash -c '
        python3 "$1/prefix/extras.py" "$2" --wine "$3" &&
        python3 "$1/session/linux_apps.py" "$2" --wine "$3" &&
        python3 "$1/xp-explorer/scripts/pins.py" "$2" --wine "$3"' _ "$root" "$prefix" "$wine" \
        >> "$local/prefix.log" 2>&1 ||
        { tail -20 "$local/prefix.log" >&2; echo 'The XP Explorer additions failed; see .local/prefix.log' >&2; exit 1; }
    stop_prefix
}

case ${1:-} in
setup)
    media=$(realpath -e -- "${2:?usage: $0 setup /path/to/WindowsXP-SP3.iso}")
    need cabextract 7z i686-w64-mingw32-gcc x86_64-w64-mingw32-gcc xvfb-run Xephyr
    [[ $root != *[[:space:]]* ]] || { echo "The checkout path must not contain spaces: $root" >&2; exit 2; }
    mkdir -p "$local"
    patches=$(python3 "$root/wine/patch-state.py" --digest "$root/wine/patches")
    if [[ -x $wine && $(cat "$local/wine-install/win4wine-patches" 2>/dev/null) == "$patches" ]]; then
        echo "Wine: built ($("$wine" --version))"
    else
        echo "Building Wine (log: .local/wine-build.log); this takes a long time"
        JOBS=${JOBS:-$(nproc)} "$root/wine/build.sh" > "$local/wine-build.log" 2>&1 ||
            { tail -20 "$local/wine-build.log" >&2; echo 'Wine build failed; see .local/wine-build.log' >&2; exit 1; }
    fi
    "$root/bridge-wm/build.sh"
    if [[ ! -f $assets/manifest.json ]]; then
        mkdir -p "$local/tmp"
        TMPDIR=$local/tmp python3 "$root/extract/extract.py" "$media" "$assets"
    fi
    # run takes it again for files that a later version extracts.
    echo "$media" > "$local/media-path"
    add_media_files "$media"
    if [[ ! -f $prefix/xp-shell.json ]]; then
        [[ ! -e $prefix ]] || { echo "$prefix exists but is incomplete; move it away and run again" >&2; exit 1; }
        theme=${XP_THEME:-luna}
        xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/create.py" "$assets" "$prefix" \
            --home "$HOME" --wine "$wine" > "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; echo 'Prefix creation failed; see .local/prefix.log' >&2; exit 1; }
        WINEPREFIX=$prefix WINE=$wine xvfb-run -a -s '-screen 0 1280x800x24' python3 "$root/prefix/display.py" \
            --theme "$theme" --menu "$([[ $theme == luna ]] && echo xp || echo classic)" >> "$local/prefix.log" 2>&1 ||
            { tail -20 "$local/prefix.log" >&2; echo 'Setting the theme failed; see .local/prefix.log' >&2; exit 1; }
        stop_prefix
    fi
    add_extras
    echo "Done. Start it with: $0 run"
    ;;
run)
    need Xephyr dbus-run-session
    [[ -x $wine ]] || { echo "Run $0 setup ISO first" >&2; exit 1; }
    [[ -f $prefix/xp-shell.json ]] || { echo "No XP prefix in $prefix: run $0 setup ISO first" >&2; exit 1; }
    "$root/bridge-wm/build.sh"
    add_media_files "${XP_ISO:-$(cat "$local/media-path" 2>/dev/null)}"
    add_extras
    size=${2:-1280x800}
    [[ $size =~ ^[0-9]+x[0-9]+$ ]] || { echo "usage: $0 run [WIDTHxHEIGHT]" >&2; exit 2; }
    "$0" kill >/dev/null 2>&1 || true
    display=${XP_DISPLAY:-}
    if [[ -z $display ]]; then
        for n in $(seq 5 99); do
            [[ -e /tmp/.X11-unix/X$n || -e /tmp/.X$n-lock ]] || { display=:$n; break; }
        done
    fi
    mkdir -p "$state"
    # The session's settings: the prefix's language, and Start menu > Turn Off
    # Computer ends this window's session, never the machine.
    language=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("language", "en"))' \
        "$prefix/xp-shell.json" 2>/dev/null || echo en)
    python3 - "$state/session.json" "$wine" "$prefix" "$state" "$language" "${XP_WINEDEBUG:-+timestamp,fixme-all}" <<'EOF'
import json, sys
path, wine, prefix, state, language, debug = sys.argv[1:]
settings = dict(wine=wine, prefix=prefix, state=state, debug=debug,
                locale='ja_JP.UTF-8' if language == 'ja' else 'en_US.UTF-8',
                shutdown_command=['true'], reboot_command=['true'])
if language == 'ja':
    settings['input_method'] = 'fcitx5'
open(path, 'w').write(json.dumps(settings, indent=2) + '\n')
EOF
    echo "$display" > "$state/display"
    Xephyr "$display" -screen "$size" -dpi 96 -title "XP Shell (debug, $display)" -no-host-grab \
        -nolisten tcp > "$state/xephyr.log" 2>&1 &
    xephyr=$!
    trap 'kill $xephyr 2>/dev/null || true' EXIT
    for _ in $(seq 50); do
        [[ -e /tmp/.X11-unix/X${display#:} ]] && break
        kill -0 $xephyr 2>/dev/null || { cat "$state/xephyr.log" >&2; exit 1; }
        sleep 0.1
    done
    echo "XP session on $display ($size); logs in $state (./xp.sh log)"
    # Only X in the window: no Wayland, and a D-Bus of its own, so that the
    # session's tray bridge does not take the desktop's StatusNotifierWatcher.
    env -u WAYLAND_DISPLAY -u WIN4WINE_IPC -u XDG_SESSION_TYPE -u SESSION_MANAGER \
        DISPLAY="$display" GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb XDG_SESSION_TYPE=x11 \
        dbus-run-session -- python3 "$root/session/supervisor.py" --config "$state/session.json" ||
        echo "The session ended with an error; see $state" >&2
    ;;
log)
    tail -n 50 -F "$state/${2:-xp-shell}.log"
    ;;
kill)
    if display=$(running_display); then
        pkill -f "^Xephyr $display " || true
    fi
    stop_prefix
    ;;
*)
    sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
    exit 2
    ;;
esac
