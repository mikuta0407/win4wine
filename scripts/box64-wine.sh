#!/bin/bash
# Wine on an ARM64 machine: a directory whose bin/wine and bin/wineserver run
# a Wine built by wine/build.sh (x86-64 Unix, i386 and x86-64 PE) under Box64.
#
#   scripts/box64-wine.sh WINE_INSTALL DIRECTORY [--libs DIR] [--box64 PATH]
#
#   WINE_INSTALL  the .local/wine-install of an x86-64 Debian 13 machine (or of
#                 scripts/debian.sh's chroot there), copied to this machine
#   DIRECTORY     the directory to write (it must not exist). Give it to
#                 scripts/setup.sh --wine-install, or its bin/wine to
#                 session.json's "wine" and the prefix tools' --wine
#   --libs DIR    x86-64 libraries that Box64 does not replace with the native
#                 ones (libgcc_s.so.1 and others): for example the
#                 usr/lib/x86_64-linux-gnu of that Debian 13 (Box64's
#                 BOX64_LD_LIBRARY_PATH)
#   --box64 PATH  the box64 program (default: box64 in PATH)
#
# The session, win4wine-wine and the prefix tools resolve the "wine" they are
# given (following links), take wineserver beside it and Wine's lib/ and share/
# beside its bin/, and put its directory first in PATH. So bin/wine and
# bin/wineserver here are files: a link to Wine's own would resolve to the
# x86-64 program and leave Box64 out. lib/, share/ and win4wine-patches are
# links to WINE_INSTALL's. Wine starts its other processes and wineserver
# through WINELOADER and WINESERVER, which name these files too.
set -euo pipefail
usage='Usage: scripts/box64-wine.sh WINE_INSTALL DIRECTORY [--libs DIR] [--box64 PATH]'
install=
directory=
libs=
box64=
while (($#)); do
    case $1 in
        --libs) libs=$(realpath -e -- "${2:?--libs needs a directory}"); shift 2 ;;
        --box64) box64=${2:?--box64 needs the box64 program}; shift 2 ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        -*) printf 'Unknown option %s (see --help)\n' "$1" >&2; exit 2 ;;
        *)
            if [[ -z $install ]]; then install=$1
            elif [[ -z $directory ]]; then directory=$1
            else printf '%s\n' "$usage" >&2; exit 2
            fi
            shift ;;
    esac
done
[[ -n $install && -n $directory ]] || { printf '%s\n' "$usage" >&2; exit 2; }
install=$(realpath -e -- "$install")
[[ -f $install/lib/wine/x86_64-windows/win4wine-controls.dll && -x $install/bin/wine && -x $install/bin/wineserver ]] ||
    { printf '%s is not a Wine install built by wine/build.sh\n' "$install" >&2; exit 1; }
box64=$(command -v -- "${box64:-box64}") || { printf 'box64 not found; give it with --box64\n' >&2; exit 1; }
box64=$(realpath -e -- "$box64")
[[ ! -e $directory && ! -L $directory ]] || { printf 'Refusing existing %s\n' "$directory" >&2; exit 1; }
mkdir -p -- "$directory/bin"
directory=$(realpath -e -- "$directory")
for name in lib share win4wine-patches; do
    [[ ! -e $install/$name ]] || ln -s -- "$install/$name" "$directory/$name"
done
for name in wine wineserver; do
    {
        printf '#!/bin/bash\n'
        printf '# Written by win4wine'"'"'s scripts/box64-wine.sh: %s under Box64.\n' "$install/bin/$name"
        if [[ -n $libs ]]; then
            printf 'BOX64_LD_LIBRARY_PATH=%q${BOX64_LD_LIBRARY_PATH:+:$BOX64_LD_LIBRARY_PATH}\n' "$libs"
            printf 'export BOX64_LD_LIBRARY_PATH\n'
        fi
        # Box64 prints its version and settings when each program starts.
        printf 'export BOX64_LOG="${BOX64_LOG:-0}"\n'
        printf 'export WINELOADER=%q WINESERVER=%q\n' "$directory/bin/wine" "$directory/bin/wineserver"
        printf 'exec %q %q "$@"\n' "$box64" "$install/bin/$name"
    } > "$directory/bin/$name"
    chmod 755 "$directory/bin/$name"
done
printf 'Wrote %s: %s\n' "$directory" "$("$directory/bin/wine" --version)"
