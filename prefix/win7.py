#!/usr/bin/env python3
"""Create and stage a dedicated 64-bit (WoW64) prefix for Windows 7's shell (experimental).

  win7.py create ASSETS PREFIX [--home HOME] [--wine WINE]
  win7.py stage PREFIX [--wine WINE]
  win7.py builtin PREFIX PROGRAM... [--undo] [--wine WINE]

ASSETS is the output of extract/win7.py (the image's language decides the
prefix's: Japanese or English).

Windows 7's x64 explorer runs as C:\\w7\\w7-explorer.exe, a 64-bit process.
Its shell DLLs are kept in C:\\w7\\native and placed in system32, each with
its MUI file in the language's folder (system32\\ja-JP\\shell32.dll.mui), as
Windows 7 keeps them; Wine reads MUI files (patch 0102). Windows 7's Common
Controls 6 is C:\\w7\\comctl32.dll, beside the shell (patch 0126); Wine's own
assembly stays every other program's. The files are placed as they are on
the media, under the names the prefix uses. Every program of the prefix gets
the DLLs that a file dialog needs (DllOverrides native,builtin: Windows
applications open and save files with Windows 7's dialogs), and only
w7-explorer.exe the rest (AppDefaults). Wine's own programs keep Wine's DLLs,
and "builtin" gives them back to other programs that do not work with
Windows 7's.
DLLs that the shell only reads for their strings and icons (imageres) are
placed in system32 without overrides. The registry gets what the components
of these files register (their manifests, extract/manifests.py), not the
registry of an installed Windows.

The session runs "stage" before each start: a Wine update of the prefix
(wineboot -u, from a newer wine.inf) replaces DLLs and rewrites
registrations that Windows 7's shell reads, such as the name of Computer.
"""
import argparse
import filecmp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'win7-shell.json'
# Bump when the registry settings below change; stage then applies them again.
VERSION = 17
LOCALES = {'ja': 'ja_JP.UTF-8', 'en': 'en_US.UTF-8'}
# Wine's own Common Controls 6 (which an earlier version of this prefix replaced).
SXS = 'amd64_microsoft.windows.common-controls_6595b64144ccf1df_6.0.2600.2982_none_deadbeef'
# Windows 7's names of shell items whose registration wine.inf writes with Wine's own string.
NAMES = (
    ('{20D04FE0-3AEA-1069-A2D8-08002B30309D}', r'@%SystemRoot%\system32\shell32.dll,-9216'),  # Computer
    ('{21EC2020-3AEA-1069-A2DD-08002B30309D}', r'@%SystemRoot%\system32\shell32.dll,-4161'),  # Control Panel
    # Network names itself in NetworkExplorer.dll, which is not installed; shell32 has the same name.
    ('{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}', r'@%SystemRoot%\system32\shell32.dll,-9217'),  # Network
    # Help and Support names itself in explorer.exe; %SystemRoot%\explorer.exe is Wine's.
    ('{2559a1f1-21d7-11d4-bdaf-00c04f60b9f0}', r'@C:\w7\w7-explorer.exe,-7021'),
)
# Windows 7's shell DLLs, 64-bit and 32-bit: native in every program of the
# session (the shell, and the file dialogs of Windows applications), but for
# Wine's own programs (WINE_PROGRAMS) and those the user gives Wine's DLLs
# back (win7.py builtin). Windows 7's DLLs get Windows 7's Common Controls 6
# from C:\w7 (Wine 0126); the programs keep Wine's. These are what an
# application's file dialog loads (explorerframe's browser, its views and
# thumbnails).
NATIVE = ('explorerframe', 'shell32', 'shlwapi', 'propsys', 'shdocvw', 'dui70', 'duser', 'profapi',
          'thumbcache', 'linkinfo')
# Native in the shell only: the taskbar's volume, the Start menu's
# branding, user picture and shut down.
SHELL_ONLY = ('sndvolsso', 'winbrand', 'shacct', 'authui')
# Wine's programs that keep Wine's shell DLLs: its desktop and services, the
# programs that link Wine to Linux (menus, the browser, start for `wine NAME`
# and Linux launchers) and those built on Wine's shell32 (its Control Panel).
WINE_PROGRAMS = ('explorer.exe', 'winemenubuilder.exe', 'winebrowser.exe', 'wineboot.exe', 'services.exe',
                 'plugplay.exe', 'winedevice.exe', 'rpcss.exe', 'svchost.exe', 'conhost.exe', 'start.exe',
                 'control.exe', 'rundll32.exe', 'winecfg.exe', 'uninstaller.exe', 'winefile.exe')
# Read only for their resources (strings and icons): placed in system32, no override.
RESOURCES = ('imageres', 'sud', 'DeviceCenter')
# Windows 7's interface proxies, under another name: Wine's own actxprxy.dll
# keeps the proxies of Wine's builtin DLLs.
PROXIES = ('actxprxy', 'w7actxprxy', '{C90250F3-4D7D-4991-9B69-A5C5BC1C2AE6}')
# Japanese Windows 7's font links and dialog fonts (read on the reference machine), for
# the fonts that extract/win7.py takes: MS Shell Dlg is MS UI Gothic, MS Shell Dlg 2 Tahoma.
FONT_LINKS = {
    'Segoe UI': r'TAHOMA.TTF\0MEIRYO.TTC,Meiryo,128,85\0MEIRYO.TTC,Meiryo\0MSGOTHIC.TTC,MS UI Gothic',
    'Tahoma': 'MSGOTHIC.TTC,MS UI Gothic',
    'Microsoft Sans Serif': 'MSGOTHIC.TTC,MS UI Gothic',
    'Lucida Sans Unicode': 'MSGOTHIC.TTC,MS UI Gothic',
    'Meiryo': r'SEGOEUI.TTF,133,83\0SEGOEUI.TTF\0MSGOTHIC.TTC,MS UI Gothic',
    'Meiryo UI': r'SEGOEUI.TTF,133,83\0SEGOEUI.TTF\0MSGOTHIC.TTC,MS UI Gothic',
    'Meiryo Bold': r'SEGOEUIB.TTF,133,83\0SEGOEUIB.TTF\0MSGOTHIC.TTC,MS UI Gothic',
    'Meiryo UI Bold': r'SEGOEUIB.TTF,133,83\0SEGOEUIB.TTF\0MSGOTHIC.TTC,MS UI Gothic',
    'MS UI Gothic': r'MICROSS.TTF,128,142\0MICROSS.TTF',
}
FONT_SUBSTITUTES = {'MS Shell Dlg': 'MS UI Gothic', 'MS Shell Dlg 2': 'Tahoma'}
# Prefixes of extracted files without MS UI Gothic and Tahoma: Meiryo UI stands in.
OLD_FONT_LINKS = ('Segoe UI', 'Tahoma', 'MS Shell Dlg', 'MS Shell Dlg 2', 'Microsoft Sans Serif', 'MS UI Gothic')
OLD_FONT_SUBSTITUTES = ('MS Shell Dlg', 'MS Shell Dlg 2', 'MS UI Gothic')
X11_DRIVER = (('Managed', 'Y'), ('Decorated', 'N'))
# Wine's own desktop items that Windows 7's desktop does not show: My Documents,
# the Unix root folder and Internet Explorer.
HIDDEN_DESKTOP_ITEMS = ('{450D8FBA-AD25-11D0-98A8-0800361B1103}', '{9D20AAE8-0625-44B0-9CA7-71889C2254D9}',
                        '{871C5380-42A0-1069-A2EA-08002B30309D}')


class Prefix:
    def __init__(self, path, wine, lang):
        self.path = path
        self.wine = Path(shutil.which(str(wine)) or wine).resolve(strict=True)
        self.lang = lang
        locale = LOCALES[lang]
        self.env = dict(os.environ, WINEPREFIX=str(path), WINEDEBUG=os.environ.get('WINEDEBUG', '-all'),
                        WINEDLLOVERRIDES='mscoree,mshtml=', LANG=locale, LC_ALL=locale)
        self.env.pop('WINEARCH', None)

    @property
    def system(self):
        return self.path / 'drive_c/windows/system32'

    def run(self, *args, timeout=300, check=True, env=None):
        return subprocess.run([str(self.wine), *args], env=env or self.env, check=check, timeout=timeout,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reg(self, key, name, value, kind='REG_SZ'):
        self.run('reg', 'add', key, *(('/ve',) if name is None else ('/v', name)), '/t', kind, '/d', str(value), '/f')

    def wait(self):
        server = str(self.wine.with_name('wineserver'))
        subprocess.run([server, '-w'], env=self.env, check=False, timeout=120)

    def stop(self):
        # Wine's services stay until the server times out; end them so that a
        # wait does not block, and the registry is saved.
        server = str(self.wine.with_name('wineserver'))
        subprocess.run([server, '-k'], env=self.env, check=False, timeout=15)

    def place(self, source, target):
        """Copy SOURCE over TARGET unless equal, without truncating a mapped image."""
        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.w7-stage-', delete=False) as temp:
            path = Path(temp.name)
        try:
            shutil.copyfile(source, path)
            os.replace(path, target)
        finally:
            path.unlink(missing_ok=True)

    def copy(self, dll, mui, target):
        """Copy DLL to TARGET, and its MUI file (MUI, if any) to the language's folder beside it."""
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dll, target)
        if mui.is_file():
            (target.parent / mui.parent.name).mkdir(exist_ok=True)
            shutil.copyfile(mui, target.parent / mui.parent.name / f'{target.name}.mui')

    def place_files(self):
        # C:\w7\native: 64-bit, into system32; C:\w7\wow64: 32-bit, into syswow64
        # (its comctl32.dll stays there, for Windows 7's DLLs only)
        for folder, system in (('native', self.system), ('wow64', self.path / 'drive_c/windows/syswow64')):
            native = self.path / 'drive_c/w7' / folder
            for source in sorted(native.glob('*.dll')):
                if source.name.lower() == 'comctl32.dll':
                    continue
                self.place(source, system / source.name)
            for source in sorted(native.glob('*/*.mui')):
                self.place(source, system / source.parent.name / source.name)
        # Wine's own Common Controls 6, for every other program.
        wine_controls = self.wine.parent.parent / 'lib/wine/x86_64-windows/comctl32_v6.dll'
        assembly = self.path / f'drive_c/windows/winsxs/{SXS}/comctl32.dll'
        if wine_controls.is_file() and assembly.is_file():
            self.place(wine_controls, assembly)

    def overrides(self):
        """Windows 7's shell DLLs in every program but Wine's own (see NATIVE)."""
        for name in NATIVE + ('comctl32',):
            # native,builtin: a program finds Wine's comctl32 (and any DLL that
            # is missing) as before; Wine's builtin files load as builtin anyway.
            self.reg(r'HKCU\Software\Wine\DllOverrides', name, 'native,builtin')
            self.reg(r'HKCU\Software\Wine\AppDefaults\w7-explorer.exe\DllOverrides', name, 'native')
            for program in WINE_PROGRAMS:
                self.reg(rf'HKCU\Software\Wine\AppDefaults\{program}\DllOverrides', name, 'builtin')
        for name in SHELL_ONLY:
            # Prefixes made before SHELL_ONLY had them in every program.
            self.run('reg', 'delete', r'HKCU\Software\Wine\DllOverrides', '/v', name, '/f', check=False)
            self.reg(r'HKCU\Software\Wine\AppDefaults\w7-explorer.exe\DllOverrides', name, 'native')
        # The thumbnail cache's surrogate keeps Wine's Common Controls 6 (with
        # Windows 7's, explorer started a new surrogate every few seconds).
        self.reg(r'HKCU\Software\Wine\AppDefaults\dllhost.exe\DllOverrides', 'comctl32', 'builtin')
        _, proxies, clsid = PROXIES
        for view, system in (('/reg:64', 'system32'), ('/reg:32', 'syswow64')):
            self.run('reg', 'add', rf'HKCR\CLSID\{clsid}\InProcServer32', '/ve', '/t', 'REG_EXPAND_SZ',
                     '/d', rf'%SystemRoot%\{system}\{proxies}.dll', '/f', view)

    def builtin(self, program, undo=False):
        """Give PROGRAM (an executable's name) Wine's shell DLLs instead of Windows 7's
        (its file dialogs are then Wine's), or (UNDO) Windows 7's again."""
        key = rf'HKCU\Software\Wine\AppDefaults\{program}\DllOverrides'
        for name in NATIVE + ('comctl32',):
            if undo:
                self.run('reg', 'delete', key, '/v', name, '/f', check=False)
            else:
                self.reg(key, name, 'builtin')

    def wow64_registry(self, assets):
        """The 32-bit view of the components' registrations (32-bit programs: icons, file types)."""
        reg = assets / 'registry-wow64.reg'
        if reg.is_file():
            self.run(r'C:\windows\syswow64\regedit.exe', '/s', windows_path(reg), timeout=600)
            self.wait()

    def registrations(self):
        """What a Wine update of the prefix, or Wine's font setup, rewrites."""
        # Wine frames the proxy windows itself (the WM does not decorate them).
        for name, value in X11_DRIVER:
            self.reg(r'HKCU\Software\Wine\X11 Driver', name, value)
        nt = r'HKLM\Software\Microsoft\Windows NT\CurrentVersion'
        if self.lang == 'ja' and windows_fonts(self.path):
            for name in ('MS Shell Dlg', 'MS Shell Dlg 2'):
                self.run('reg', 'delete', nt + r'\FontLink\SystemLink', '/v', name, '/f', check=False)
            self.run('reg', 'delete', nt + r'\FontSubstitutes', '/v', 'MS UI Gothic', '/f', check=False)
            for name, value in FONT_LINKS.items():
                self.reg(nt + r'\FontLink\SystemLink', name, value, 'REG_MULTI_SZ')
            for name, value in FONT_SUBSTITUTES.items():
                self.reg(nt + r'\FontSubstitutes', name, value)
            # Notepad's font as Japanese Windows 7's Notepad starts with (MS Gothic,
            # 12 points, Western); Wine's own default (System) has no Japanese, and
            # without a Linux font that has, Japanese showed as boxes. Kept when set.
            notepad = r'HKCU\Software\Microsoft\Notepad'
            if self.run('reg', 'query', notepad, '/v', 'lfFaceName', check=False).returncode:
                self.reg(notepad, 'lfFaceName', '\uff2d\uff33 \u30b4\u30b7\u30c3\u30af')
                self.reg(notepad, 'iPointSize', 120, 'REG_DWORD')
                self.reg(notepad, 'lfCharSet', 0, 'REG_DWORD')
        elif self.lang == 'ja':
            for name in OLD_FONT_LINKS:
                self.reg(nt + r'\FontLink\SystemLink', name, r'MEIRYO.TTC,Meiryo UI\0MEIRYO.TTC,Meiryo', 'REG_MULTI_SZ')
            for name in OLD_FONT_SUBSTITUTES:
                self.reg(nt + r'\FontSubstitutes', name, 'Meiryo UI')
        elif windows_fonts(self.path):
            # English Windows 7's dialog fonts
            self.reg(nt + r'\FontSubstitutes', 'MS Shell Dlg', 'Microsoft Sans Serif')
            self.reg(nt + r'\FontSubstitutes', 'MS Shell Dlg 2', 'Tahoma')
        for clsid, name in NAMES:
            for view in ('/reg:64', '/reg:32'):
                self.run('reg', 'add', rf'HKCR\CLSID\{clsid}', '/v', 'LocalizedString', '/t', 'REG_EXPAND_SZ',
                         '/d', name, '/f', view)
        # The open dialog that shell32's Browse buttons (the Run dialog's) create:
        # Windows 7's comdlg32 component registers it, and Wine's comdlg32
        # implements it; the component's files are Wine's, so it is not extracted.
        self.reg(r'HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer', 'FileOpenDialog',
                 '{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}')
        # The text file's type names: Windows 7 reads them from its Notepad,
        # whose strings are kept as data (notepad_strings).
        if (self.path / 'drive_c/w7/res/notepad.exe.mui').is_file():
            for view in ('/reg:64', '/reg:32'):
                self.run('reg', 'add', r'HKCR\txtfile', '/v', 'FriendlyTypeName', '/t', 'REG_EXPAND_SZ',
                         '/d', r'@C:\w7\res\notepad.exe.mui,-469', '/f', view)
                self.run('reg', 'add', r'HKCR\.txt\ShellNew', '/v', 'ItemName', '/t', 'REG_EXPAND_SZ',
                         '/d', r'@C:\w7\res\notepad.exe.mui,-470', '/f', view)
        # Linux tray icons and the input method's mode stay in the notification
        # area (Windows 7's "always show all icons and notifications").
        self.reg(r'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer', 'EnableAutoTray', 0, 'REG_DWORD')
        icons = r'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel'
        for clsid in HIDDEN_DESKTOP_ITEMS:
            self.reg(icons, clsid, 1, 'REG_DWORD')
        user = pwd.getpwuid(os.getuid()).pw_name
        wallpaper = Path(f'users/{user}/AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper.bmp')
        if (self.path / 'drive_c' / wallpaper).is_file():
            desktop = r'HKCU\Control Panel\Desktop'
            self.reg(desktop, 'Wallpaper', 'C:\\' + str(wallpaper).replace('/', '\\'))
            self.reg(desktop, 'WallpaperStyle', '10')
            self.reg(desktop, 'TileWallpaper', '0')


def windows_path(path):
    return 'Z:' + str(Path(path).resolve()).replace('/', '\\')


def create(assets, dest, home, wine):
    assets, dest, home = assets.resolve(strict=True), dest.resolve(), home.resolve(strict=True)
    if dest.exists():
        raise SystemExit(f'Refusing existing prefix: {dest}')
    for tool in ('theme-fonts.exe', 'theme-settings.exe', 'wallpaper-convert.exe', 'user-profile.exe'):
        if not (ROOT / '.local/bridge' / tool).is_file():
            raise SystemExit(f'Run bridge-wm/build.sh first: missing {tool}')
    media = json.loads((assets / 'media.json').read_text())
    lang, ui = media['lang'], media['ui_language']
    prefix = Prefix(dest, wine, lang)
    dest.parent.mkdir(parents=True, exist_ok=True)
    prefix.run('wineboot', '-u', timeout=900, env=dict(prefix.env, WINEARCH='win64'))
    # A new prefix's own first update may still be writing the system directories.
    prefix.wait()
    if not (dest / 'drive_c/windows/syswow64').is_dir():
        raise SystemExit('Expected a 64-bit prefix: use the WoW64 build of the patched Wine')
    c = dest / 'drive_c'
    native = c / 'w7/native'
    native.mkdir(parents=True)
    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        prefix.copy(assets / 'shell/explorer.exe', assets / f'shell/{ui}/explorer.exe.mui', c / 'w7/w7-explorer.exe')
        for name in NATIVE:
            prefix.copy(assets / f'system32/{name}.dll', assets / f'system32/{ui}/{name}.dll.mui',
                        native / f'{name}.dll')
        source, name, _ = PROXIES
        prefix.copy(assets / f'system32/{source}.dll', assets / f'system32/{ui}/{source}.dll.mui',
                    native / f'{name}.dll')
        for name in RESOURCES:
            prefix.copy(assets / f'system32/{name}.dll', assets / f'system32/{ui}/{name}.dll.mui',
                        prefix.system / f'{name}.dll')
        wow64_files(prefix, assets, ui)
        shell_only_files(prefix, assets)
        prefix.copy(assets / 'sxs/comctl32.dll', assets / f'sxs/{ui}/comctl32.dll.mui', c / 'w7/comctl32.dll')
        system_icons(dest, assets)
        notepad_strings(dest, assets)
        for font in (assets / 'fonts').iterdir():
            shutil.copyfile(font, c / 'windows/Fonts' / font.name)
        shutil.copytree(assets / 'themes', c / 'windows/Resources/Themes', dirs_exist_ok=True)
        shutil.copytree(assets / 'pictures', c / 'ProgramData/Microsoft/User Account Pictures', dirs_exist_ok=True)
        wallpaper = c / 'windows/Web/Wallpaper/Windows/img0.jpg'
        wallpaper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / 'web/img0.jpg', wallpaper)
        # Windows 7 shows a JPEG wallpaper from a bitmap it converts it to.
        themes = c / f'users/{user}/AppData/Roaming/Microsoft/Windows/Themes'
        themes.mkdir(parents=True, exist_ok=True)
        prefix.run(str(ROOT / '.local/bridge/wallpaper-convert.exe'), windows_path(wallpaper),
                   windows_path(themes / 'TranscodedWallpaper.bmp'))
        start_menu(prefix, assets, user)
        quick_launch(prefix, assets, user)
        (dest / 'dosdevices/h:').symlink_to(home)
        prefix.run('regedit', '/s', windows_path(assets / 'registry.reg'), timeout=600)
        prefix.wow64_registry(assets)
        prefix.wait()
        settings(prefix, lang)
        prefix.wait()
        appearance(prefix)
    finally:
        prefix.stop()
    prefix.place_files()
    try:
        # Windows 7's shell32 (in system32 from here on) makes the libraries.
        user_profile(prefix, user)
        profile_folders(prefix, user)
    finally:
        prefix.stop()
    update = (dest / '.update-timestamp').read_text().strip()
    (dest / '.w7-registry-version').write_text(f'{VERSION} {update}\n')
    # The registry settings the session's stage keeps.
    stage_registrations(prefix)
    (dest / MARKER).write_text(json.dumps({'assets': str(assets), 'home': str(home), 'wine': str(prefix.wine),
                                           'lang': lang, 'edition': media['edition']}, indent=2) + '\n')
    print(f'Prefix ready: {dest}')


def system_icons(dest, assets):
    """Windows 7's user32.dll, only read for its icons (Wine's user32 takes the system icons,
    IDI_APPLICATION to IDI_SHIELD, from it in the Windows 7 shell session), under another name
    than Wine's user32.dll and not beside a program."""
    source, target = assets / 'cursors/user32.dll', dest / 'drive_c/w7/res/user32-w7.dll'
    if source.is_file() and not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def notepad_strings(dest, assets):
    """Windows 7's notepad.exe.mui, only read for the text file's type names (Notepad
    itself is Wine's, whose resources have no such strings), not beside a program."""
    lang_dir = json.loads((assets / 'media.json').read_text()).get('ui_language', '')
    source, target = assets / f'res/{lang_dir}/notepad.exe.mui', dest / 'drive_c/w7/res/notepad.exe.mui'
    if lang_dir and source.is_file() and not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


# Windows 7's desktop.ini of the user's Documents and Libraries folders (read on the
# reference machine); the other profile folders get theirs when the prefix is made.
PROFILE_INI = {
    'Documents': '[.ShellClassInfo]\r\nLocalizedResourceName=@%SystemRoot%\\system32\\shell32.dll,-21770\r\n'
                 'IconResource=%SystemRoot%\\system32\\imageres.dll,-112\r\nIconFile=%SystemRoot%\\system32\\shell32.dll\r\n'
                 'IconIndex=-235\r\n',
    'AppData/Roaming/Microsoft/Windows/Libraries':
        '\r\n[.ShellClassInfo]\r\n\r\n[LocalizedFileNames]\r\n'
        'Documents.library-ms=@@%SystemRoot%\\system32\\shell32.dll,-34575\r\n'
        'Pictures.library-ms=@@%SystemRoot%\\system32\\shell32.dll,-34595\r\n'
        'Videos.library-ms=@@%SystemRoot%\\system32\\shell32.dll,-34620\r\n'
        'Music.library-ms=@@%SystemRoot%\\system32\\shell32.dll,-34584\r\n',
}
PROFILE_FOLDERS = ('Documents', 'Desktop', 'Favorites', 'Links', 'Contacts', 'Saved Games', 'Searches', 'Videos',
                   'Music', 'Pictures', 'AppData/Roaming/Microsoft/Windows/Libraries')


def profile_folders(prefix, user):
    """Localized names of the user's folders and libraries, as on Windows 7: a desktop.ini
    in a folder marked for it. Windows 7 marks them read-only; Wine keeps no read-only
    folders, and the system attribute serves alike. Folders that are links (to the
    Linux home) are left alone."""
    home = prefix.path / f'drive_c/users/{user}'
    for name in PROFILE_FOLDERS:
        folder = home / name
        if not folder.is_dir() or folder.is_symlink():
            continue
        ini = folder / 'desktop.ini'
        if not ini.exists() and name in PROFILE_INI:
            ini.write_bytes(b'\xff\xfe' + PROFILE_INI[name].encode('utf-16-le'))
            path = 'C:\\' + str(ini.relative_to(prefix.path / 'drive_c')).replace('/', '\\')
            prefix.run('attrib', '+h', path, check=False)
            prefix.run('attrib', '+s', path, check=False)
        if ini.exists():
            prefix.run('attrib', '+s', 'C:\\' + str(folder.relative_to(prefix.path / 'drive_c')).replace('/', '\\'),
                       check=False)


# Windows 7's desktop.ini of the Links folder, with the names of the links
# user-profile.exe makes (read on the reference machine).
LINKS_INI = ('[.ShellClassInfo]\r\nLocalizedResourceName=@%SystemRoot%\\system32\\shell32.dll,-21810\r\n'
             'IconResource=%SystemRoot%\\system32\\imageres.dll,-185\r\nDefaultDropEffect=4\r\n'
             '[LocalizedFileNames]\r\nRecentPlaces.lnk=@shell32.dll,-37217\r\nDesktop.lnk=@shell32.dll,-21769\r\n'
             'Downloads.lnk=@shell32.dll,-21798\r\n')


def user_profile(prefix, user):
    """What Windows 7 gives a new user (user-profile.exe): the default libraries, and
    Favorites in folder windows, the Links folder's links to the desktop, Downloads and
    Recent Places, with their Japanese names."""
    tool = ROOT / '.local/bridge/user-profile.exe'
    folder = prefix.path / f'drive_c/users/{user}/Links'
    if not tool.is_file():
        print(f'Skipping the libraries and Favorites links: missing {tool} (run bridge-wm/build.sh)', flush=True)
        return
    prefix.run(str(tool), check=False)
    if not folder.is_dir() or folder.is_symlink():
        return
    ini = folder / 'desktop.ini'
    if ini.exists() and b'L\x00o\x00c\x00a\x00l\x00i\x00z\x00e\x00d\x00F\x00i\x00l\x00e' in ini.read_bytes():
        return
    if ini.exists():
        ini.unlink()
    ini.write_bytes(b'\xff\xfe' + LINKS_INI.encode('utf-16-le'))
    path = 'C:\\' + str(ini.relative_to(prefix.path / 'drive_c')).replace('/', '\\')
    prefix.run('attrib', '+h', path, check=False)
    prefix.run('attrib', '+s', path, check=False)
    prefix.run('attrib', '+s', 'C:\\' + str(folder.relative_to(prefix.path / 'drive_c')).replace('/', '\\'), check=False)


def start_menu(prefix, assets, user):
    """The Start menu folders' Windows 7 names (desktop.ini), in the shared and the user's menu."""
    roots = ('ProgramData', f'users/{user}/AppData/Roaming')
    for source in sorted((assets / 'startmenu').rglob('desktop.ini')):
        folder = source.parent.relative_to(assets / 'startmenu')
        for root in roots:
            # Wine names the startup folder StartUp, Windows 7 Startup.
            target = prefix.path / 'drive_c' / root / 'Microsoft/Windows'
            for part in folder.parts:
                target = next((p for p in target.iterdir() if p.name.lower() == part.lower()), target / part) \
                    if target.is_dir() else target / part
            if not target.is_dir() or (target / 'desktop.ini').exists():
                continue
            shutil.copyfile(source, target / 'desktop.ini')
            path = 'C:\\' + str(target.relative_to(prefix.path / 'drive_c')).replace('/', '\\')
            # A folder with desktop.ini is a system folder; the file is hidden and
            # system (Wine's attrib applies only the last of several flags).
            prefix.run('attrib', '+s', path, check=False)
            prefix.run('attrib', '+h', path + '\\desktop.ini', check=False)
            prefix.run('attrib', '+s', path + '\\desktop.ini', check=False)


def quick_launch(prefix, assets, user):
    """The default user's Quick Launch items (Show Desktop, Window Switcher), once.

    Windows 7 copies them into a new profile; its taskbar shows the folder as
    a toolbar when the user adds it (Toolbars, New toolbar). Items the user
    removed later are not put back."""
    source = assets / 'quicklaunch'
    marker = prefix.path / '.w7-quick-launch'
    if marker.exists() or not source.is_dir():
        return
    folder = prefix.path / f'drive_c/users/{user}/AppData/Roaming/Microsoft/Internet Explorer/Quick Launch'
    folder.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        if not (folder / item.name).exists():
            shutil.copyfile(item, folder / item.name)
    if (folder / 'desktop.ini').is_file():
        # Its localized names, as start_menu() marks the Start menu's folders.
        path = 'C:\\' + str(folder.relative_to(prefix.path / 'drive_c')).replace('/', '\\')
        prefix.run('attrib', '+s', path, check=False)
        prefix.run('attrib', '+h', path + '\\desktop.ini', check=False)
        prefix.run('attrib', '+s', path + '\\desktop.ini', check=False)
    marker.write_text('1\n')


def mark_folders(prefix, user):
    """Mark the profile's and the Start menu's folders that have a desktop.ini as
    system folders again: Windows 7 makes some of them read-only in the first
    session (its known folders' attributes), which cleared the system attribute
    before Wine kept the read-only one (Wine 0121), and their items lost their
    localized names (Links' "Recent Places", the Start menu's "Startup")."""
    profile_folders(prefix, user)
    for root in ('ProgramData', f'users/{user}/AppData/Roaming'):
        menu = prefix.path / 'drive_c' / root / 'Microsoft/Windows/Start Menu'
        for ini in sorted(menu.rglob('desktop.ini')) if menu.is_dir() else ():
            prefix.run('attrib', '+s', 'C:\\' + str(ini.parent.relative_to(prefix.path / 'drive_c')).replace('/', '\\'),
                       check=False)


def wow64_files(prefix, assets, ui):
    """The 32-bit shell DLLs (and Common Controls 6) in C:\\w7\\wow64, from extract/win7.py's SysWOW64 files."""
    wow64 = prefix.path / 'drive_c/w7/wow64'
    source, renamed, _ = PROXIES
    for name in NATIVE + ('imageres', source):
        if (assets / f'syswow64/{name}.dll').is_file():
            prefix.copy(assets / f'syswow64/{name}.dll', assets / f'syswow64/{ui}/{name}.dll.mui',
                        wow64 / f'{renamed if name == source else name}.dll')
    if (assets / 'sxs/wow64/comctl32.dll').is_file():
        prefix.copy(assets / 'sxs/wow64/comctl32.dll', assets / f'sxs/wow64/{ui}/comctl32.dll.mui',
                    wow64 / 'comctl32.dll')


def controls_strings(prefix, assets):
    """Common Controls 6's MUI files as extracted now: prefixes made from an
    extraction before EXTRACT_VERSION 7 have those of Common Controls 5.82."""
    ui = json.loads((assets / 'media.json').read_text())['ui_language']
    for source, folder in ((assets / f'sxs/{ui}/comctl32.dll.mui', 'drive_c/w7'),
                           (assets / f'sxs/wow64/{ui}/comctl32.dll.mui', 'drive_c/w7/wow64')):
        if source.is_file() and (prefix.path / folder / 'comctl32.dll').is_file():
            prefix.place(source, prefix.path / folder / ui / 'comctl32.dll.mui')


def start_panel_defaults(prefix, assets):
    """The defaults of the Start menu's options, once, for a prefix made from an
    extraction before EXTRACT_VERSION 8: that left out the settings which the
    explorer component declares with wcm:default (extract/manifests.py), and
    Windows 7 leaves out an option that has no DefaultValue: Customize Start
    Menu had no Run command and no Connect To, and no choices for Control Panel,
    Games, Music, Pictures, the personal folder and the search of files."""
    marker = prefix.path / '.w7-start-panel'
    if marker.exists():
        return
    options = r'Microsoft\Windows\CurrentVersion\Explorer\StartMenu\StartPanel'
    probe = ('Software\\' + options + '\\ShowRun').replace('\\', '\\\\')
    if 'DefaultValue' in registry_values(prefix.path / 'system.reg', probe):
        marker.write_text('1\n')
        return
    start = f'[HKEY_LOCAL_MACHINE\\SOFTWARE\\{options}\\'.lower()
    imports = []
    for name, regedit in (('registry.reg', 'regedit'), ('registry-wow64.reg', r'C:\windows\syswow64\regedit.exe')):
        try:
            sections = re.split(r'\n(?=\[)', (assets / name).read_text(encoding='utf-16'))
        except (OSError, UnicodeError):
            continue
        sections = [s for s in sections if s.lower().startswith(start) and '"DefaultValue"=' in s]
        if any(s.lower().startswith(start + 'showrun]') for s in sections):
            imports.append((regedit, sections))
    if not imports:
        return  # The extraction is an earlier one: setup.sh extracts again.
    print("Adding the defaults of the Start menu's options", flush=True)
    done = True
    try:
        with tempfile.TemporaryDirectory(prefix='w7-start-panel-') as temp:
            for number, (regedit, sections) in enumerate(imports):
                file = Path(temp) / f'{number}.reg'
                file.write_text('Windows Registry Editor Version 5.00\n\n' + '\n'.join(sections) + '\n',
                                encoding='utf-16')
                done &= prefix.run(regedit, '/s', windows_path(file), check=False).returncode == 0
            prefix.wait()
    finally:
        prefix.stop()
    if done:
        marker.write_text('1\n')


def shell_only_files(prefix, assets):
    """The shell's own DLLs (SHELL_ONLY), 64-bit and 32-bit, where they are missing:
    prefixes made by win4wine 0.9.0 to 0.12.0 lack them (the shell did not start).
    Whether any was missing."""
    ui = json.loads((assets / 'media.json').read_text())['ui_language']
    missing = False
    for folder, system in (('native', 'system32'), ('wow64', 'syswow64')):
        for name in SHELL_ONLY:
            target = prefix.path / f'drive_c/w7/{folder}/{name}.dll'
            if not target.exists() and (assets / f'{system}/{name}.dll').is_file():
                prefix.copy(assets / f'{system}/{name}.dll', assets / f'{system}/{ui}/{name}.dll.mui', target)
                missing = True
    return missing


def effects(prefix):
    """Windows 7's visual effects, UserPreferencesMask read on the reference machine: among
    others, access keys underlined only while the keyboard is used, hot tracking and shadows."""
    prefix.reg(r'HKCU\Control Panel\Desktop', 'UserPreferencesMask', '9e3e078012000000', 'REG_BINARY')


def settings(prefix, lang):
    """DLL overrides, the shell, fonts and Wine settings of a new prefix."""
    prefix.overrides()
    for view in ('/reg:32', '/reg:64'):
        prefix.run('reg', 'add', r'HKLM\Software\Microsoft\Windows NT\CurrentVersion\Winlogon', '/v', 'Shell',
                   '/d', 'w7-explorer.exe', '/f', view)
    # ClearType, Windows 7's default.
    prefix.reg(r'HKCU\Control Panel\Desktop', 'FontSmoothing', '2')
    prefix.reg(r'HKCU\Control Panel\Desktop', 'FontSmoothingType', 2, 'REG_DWORD')
    prefix.reg(r'HKCU\Control Panel\Desktop', 'LogPixels', 96, 'REG_DWORD')
    effects(prefix)
    # The user's documents are the Linux home (H:), as in the XP session.
    for suffix in ('Shell Folders', 'User Shell Folders'):
        prefix.reg('HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\' + suffix, 'Personal', 'H:\\')


def appearance(prefix):
    """Windows 7 Basic: Aero's visual style, and its fonts saved as the user's."""
    env = dict(prefix.env, WIN4WINE_EXTERNAL_SHELL='1', WIN4WINE_SHELL='win7')
    prefix.run(str(ROOT / '.local/bridge/theme-settings.exe'), 'msstyles',
               r'C:\windows\Resources\Themes\Aero\aero.msstyles', 'NormalColor', 'NormalSize', env=env)
    prefix.wait()
    prefix.run(str(ROOT / '.local/bridge/theme-fonts.exe'), env=env)


def stage_registrations(prefix):
    try:
        prefix.registrations()
    finally:
        prefix.stop()


def registry_values(path, key):
    """The values of KEY (as a .reg section names it) in a prefix's registry file."""
    values, section = {}, False
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return values
    for line in lines:
        if line.startswith('['):
            section = line.startswith(f'[{key}]')
        elif section and line.startswith('"') and '"=' in line:
            name, value = line[1:].split('"=', 1)
            values[name] = value
    return values


def windows_fonts(dest):
    """Whether the prefix has Windows 7's Tahoma (and, for Japanese, MS UI Gothic)."""
    return (dest / 'drive_c/windows/Fonts/tahoma.ttf').is_file()


def copy_fonts(dest, assets):
    """The extracted fonts that the prefix does not have yet (files extracted later add some)."""
    fonts = dest / 'drive_c/windows/Fonts'
    for font in sorted((assets / 'fonts').glob('*')):
        if not (fonts / font.name).exists() and not (fonts / font.name.lower()).exists():
            shutil.copyfile(font, fonts / font.name)


def fonts_current(dest, lang):
    """Whether Japanese text still falls back to Meiryo.

    Wine sets up its font links again (to fonts that are not installed) when a
    process starts under other code pages than those it recorded; a 32-bit
    process (the session's proxy) has its own record, so the first session
    does it once."""
    if lang != 'ja':
        return True
    links = registry_values(dest / 'system.reg', r'Software\\Microsoft\\Windows NT\\CurrentVersion\\FontLink\\SystemLink')
    if windows_fonts(dest):
        return all(value.split('\\0')[0].upper() in links.get(face, '').upper() for face, value in FONT_LINKS.items())
    return all('MEIRYO' in links.get(face, '') for face in OLD_FONT_LINKS)


def stage(dest, wine=None):
    config = json.loads((dest / MARKER).read_text())
    prefix = Prefix(dest, wine or config['wine'], config.get('lang', 'ja'))
    inf = prefix.wine.parent.parent / 'share/wine/wine.inf'
    timestamp = dest / '.update-timestamp'
    version = dest / '.w7-registry-version'
    current = timestamp.read_text().strip() if timestamp.is_file() else ''
    wine_current = inf.is_file() and current == str(int(inf.stat().st_mtime))
    applied = version.read_text().split() if version.is_file() else []
    if config.get('assets'):
        system_icons(dest, Path(config['assets']))
        notepad_strings(dest, Path(config['assets']))
        copy_fonts(dest, Path(config['assets']))
        controls_strings(prefix, Path(config['assets']))
        start_panel_defaults(prefix, Path(config['assets']))
        if not (dest / '.w7-quick-launch').exists() and (Path(config['assets']) / 'quicklaunch').is_dir():
            # Prefixes made before the default Quick Launch items
            try:
                quick_launch(prefix, Path(config['assets']), pwd.getpwuid(os.getuid()).pw_name)
            finally:
                prefix.stop()
        if shell_only_files(prefix, Path(config['assets'])):
            # Wine's shell, which the session fell back to, cleared the
            # profile folders' attributes: their localized names were lost.
            prefix.place_files()
            try:
                mark_folders(prefix, pwd.getpwuid(os.getuid()).pw_name)
            finally:
                prefix.stop()
    if wine_current and applied == [str(VERSION), current] and fonts_current(dest, prefix.lang):
        # Nothing changed, but a first wineboot or an update may have replaced files.
        prefix.place_files()
        return
    print('Updating the Windows 7 shell prefix', flush=True)
    try:
        if not wine_current:
            prefix.run('wineboot', '-u', timeout=900)
        if applied[:1] != [str(VERSION)] and config.get('assets'):
            assets = Path(config['assets'])
            if not (applied and applied[0].isdigit() and int(applied[0]) >= 7):
                # Prefixes made before Windows 7's 32-bit shell DLLs and their
                # registrations (VERSION 7), once: the file also has the defaults of
                # the user's own settings, and importing it again with every VERSION
                # moved Documents from the Linux home (H:) back to the profile.
                prefix.wow64_registry(assets)
            wow64_files(prefix, assets, json.loads((assets / 'media.json').read_text())['ui_language'])
            prefix.overrides()
        prefix.registrations()
        if applied and applied[0].isdigit() and int(applied[0]) < 9:
            # Prefixes made before Wine kept the style's padded border and caption widths
            appearance(prefix)
        if applied and applied[0].isdigit() and int(applied[0]) < 10:
            effects(prefix)
    finally:
        prefix.stop()
    # After every Wine process of the prefix has ended: a Wine update can go on
    # writing system32 after wineboot returns.
    prefix.place_files()
    if applied and applied[0].isdigit() and int(applied[0]) < 14:
        # Prefixes made before the default libraries and the Favorites links
        # (Windows 7's shell32 makes the libraries: after place_files)
        try:
            user_profile(prefix, pwd.getpwuid(os.getuid()).pw_name)
            profile_folders(prefix, pwd.getpwuid(os.getuid()).pw_name)
        finally:
            prefix.stop()
    if applied and applied[0].isdigit() and int(applied[0]) < 17:
        try:
            mark_folders(prefix, pwd.getpwuid(os.getuid()).pw_name)
        finally:
            prefix.stop()
    current = timestamp.read_text().strip() if timestamp.is_file() else ''
    temp = version.with_suffix('.tmp')
    temp.write_text(f'{VERSION} {current}\n')
    temp.replace(version)


def session_wine(path):
    """The Wine of the session that uses the prefix at PATH (its session.json): the
    prefix records the Wine that created it, which a later setup may have replaced."""
    for config in sorted((Path.home() / '.config/win4wine').glob('*.json')):
        try:
            values = json.loads(config.read_text())
            if values.get('wine') and Path(values.get('prefix', '')).resolve() == path:
                return values['wine']
        except (OSError, ValueError, AttributeError):
            continue
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('create')
    p.add_argument('assets', type=Path)
    p.add_argument('prefix', type=Path)
    p.add_argument('--home', type=Path, default=Path.home())
    p.add_argument('--wine', default=os.environ.get('WINE', 'wine'))
    p = commands.add_parser('stage')
    p.add_argument('prefix', type=Path)
    p.add_argument('--wine')
    p = commands.add_parser('builtin', help="give programs Wine's shell DLLs instead of Windows 7's")
    p.add_argument('prefix', type=Path)
    p.add_argument('programs', nargs='+', metavar='PROGRAM', help='an executable\'s name, such as app.exe')
    p.add_argument('--undo', action='store_true', help="give them Windows 7's again")
    p.add_argument('--wine')
    args = parser.parse_args()
    if args.command == 'create':
        create(args.assets, args.prefix, args.home, args.wine)
        raise SystemExit(0)
    path = args.prefix.resolve(strict=True)
    if not (path / MARKER).is_file():
        raise SystemExit('Not a Windows 7 shell prefix')
    if args.command == 'builtin':
        config = json.loads((path / MARKER).read_text())
        prefix = Prefix(path, args.wine or session_wine(path) or config['wine'], config.get('lang', 'ja'))
        for program in args.programs:
            if '\\' in program or '/' in program or not program.lower().endswith('.exe'):
                raise SystemExit(f'Expected the name of an executable, such as app.exe: {program}')
            prefix.builtin(program.lower(), args.undo)
        raise SystemExit(0)
    stage(path, args.wine)
