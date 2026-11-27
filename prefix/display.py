#!/usr/bin/env python3
"""Set classic/Luna, the Start menu, the DPI and the font smoothing of a dedicated prefix; only what is given changes.

Restart the session afterwards."""
import argparse
import os
import pwd
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--theme', choices=('classic', 'luna'))
parser.add_argument('--menu', choices=('classic', 'xp'), help='Start menu layout, independent of theme')
def dpi(value):
    # XP offers 96 (normal) and 120 (large); its custom setting takes 20% to 500% of 96.
    value = int(value)
    if not 19 <= value <= 480:
        raise argparse.ArgumentTypeError('DPI must be between 19 and 480, as XP allows')
    return value
parser.add_argument('--dpi', type=dpi, help='96, 120, 144, 192 or any value from 19 to 480')
parser.add_argument('--font-rendering', choices=('xp', 'wine'),
                    help='Prefix-wide Wine synthetic bold/italic antialiasing policy')
parser.add_argument('--font-smoothing', choices=('standard', 'cleartype'),
                    help="XP's screen font smoothing (Display Properties, Effects): standard, "
                         'the default, or ClearType')
args = parser.parse_args()
prefix = Path(os.environ['WINEPREFIX']).resolve(strict=True)
reactos = (prefix / 'reactos-shell.json').is_file()
win7 = (prefix / 'win7-shell.json').is_file()
if not reactos and not win7 and not (prefix / 'xp-shell.json').is_file():
    raise SystemExit('Not a dedicated XP prefix')
if reactos and (args.theme or args.menu or args.font_smoothing):
    raise SystemExit("The ReactOS shell has the classic look and Start menu only; give --dpi alone")
if win7 and (args.theme or args.menu or args.font_smoothing):
    raise SystemExit("The Windows 7 shell has its own look, Start menu and ClearType; give --dpi alone")
if args.theme == 'luna' and not (prefix / 'drive_c/windows/Resources/Themes/Luna/luna.msstyles').is_file():
    raise SystemExit('Luna must be extracted from your local XP media first')
theme_helper = Path(__file__).resolve().parents[1] / '.local/bridge/theme-settings.exe'
if args.theme and not theme_helper.is_file():
    raise SystemExit('Build bridge-wm before selecting a theme')
wine = os.environ.get('WINE', 'wine')
env = dict(os.environ, WINEDLLOVERRIDES='explorer,shell32,shdocvw,browseui,shlwapi,uxtheme=b;mscoree,mshtml=')
def reg(key, name, value, kind='REG_SZ'):
    subprocess.run([wine, 'reg', 'add', key, '/v', name, '/t', kind, '/d', str(value), '/f'], env=env, check=True)
if args.font_rendering:
    reg(r'HKCU\Software\Wine\Fonts', 'AntialiasFakeBoldOrItalic',
        'N' if args.font_rendering == 'xp' else 'Y')
if args.menu:
    helper = Path(__file__).resolve().parents[1] / '.local/bridge/menu-settings.exe'
    if not helper.is_file():
        raise SystemExit('Build bridge-wm before selecting a Start menu')
    reg(r'HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer',
        'NoSimpleStartMenu', int(args.menu == 'classic'), 'REG_DWORD')
    # n,b: in a 64-bit prefix Wine starts the 32-bit helper through the 64-bit
    # start.exe, which has no native shell32 and must keep the builtin one.
    menu_env = dict(env, WINEDLLOVERRIDES='shell32,shlwapi=n,b;explorer=b;mscoree,mshtml=')
    subprocess.run([wine, str(helper), args.menu], env=menu_env, check=True)
if args.dpi:
    reg(r'HKCU\Control Panel\Desktop', 'LogPixels', args.dpi, 'REG_DWORD')
if args.font_smoothing:
    # What XP's Display Properties write (SPI_SETFONTSMOOTHING and
    # SPI_SETFONTSMOOTHINGTYPE): ClearType with XP's RGB order. The shell's
    # session reads them when it starts (Wine patch 0062, session/dpi.py).
    desktop = r'HKCU\Control Panel\Desktop'
    reg(desktop, 'FontSmoothing', '2')
    reg(desktop, 'FontSmoothingType', 2 if args.font_smoothing == 'cleartype' else 1, 'REG_DWORD')
    reg(desktop, 'FontSmoothingOrientation', 1, 'REG_DWORD')
if args.theme:
    subprocess.run([wine, str(theme_helper), args.theme],
                   env=dict(env, WIN4WINE_EXTERNAL_SHELL='1'), check=True)
    # The wallpaper of XP's themes: none over the classic theme's blue-grey
    # (Windows Classic.theme), Bliss with Windows XP's (luna.theme), here the
    # bitmap stage.py makes of it as XP does for the default user.
    user = pwd.getpwuid(os.getuid()).pw_name
    reg(r'HKCU\Control Panel\Desktop', 'Wallpaper',
        '' if args.theme == 'classic' else rf'C:\users\{user}\AppData\Local\Microsoft\Wallpaper1.bmp')
    reg(r'HKCU\Control Panel\Desktop', 'WallpaperStyle', '2')
    reg(r'HKCU\Control Panel\Desktop', 'TileWallpaper', '0')
print('Display settings saved. Restart the dedicated Wine session to apply.')
