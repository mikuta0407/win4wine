#!/usr/bin/env python3
"""Extract the files of Windows 7's shell from a user supplied Windows 7 SP1 x64 ISO.

  win7.py ISO OUTPUT

The ISO's sources/install.wim holds one image per edition; the shell's files
are the same in all of them, and the Professional image is used when there is
one (else the last). Only the files that the Windows 7 shell prefix uses are
kept (prefix/win7.py), with the MUI files of the image's language, and the
registry entries of their components (extract/manifests.py). Nothing is
downloaded; the ISO and the extracted files stay on this machine.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifests  # noqa: E402
import media  # noqa: E402

RT_GROUP_ICON = 14

# Bump when the extracted files change; setup.sh then extracts again.
EXTRACT_VERSION = 8
# The image's language -> our language (the session's and the prefix's).
LANGUAGES = {'ja-JP': 'ja', 'en-US': 'en'}
# Windows 7's shell and the DLLs it uses from Windows 7 (prefix/win7.py says which
# are loaded only by the shell and which only for their resources).
SYSTEM32 = ('explorerframe.dll', 'shell32.dll', 'shlwapi.dll', 'propsys.dll', 'shdocvw.dll',
            'dui70.dll', 'duser.dll', 'profapi.dll', 'sndvolsso.dll', 'winbrand.dll', 'shacct.dll',
            'thumbcache.dll', 'authui.dll', 'linkinfo.dll', 'actxprxy.dll',
            'imageres.dll', 'sud.dll', 'DeviceCenter.dll')
# Their 32-bit copies (SysWOW64): every program of the session uses Windows 7's
# shell DLLs for its file dialogs (prefix/win7.py).
SYSWOW64 = ('explorerframe.dll', 'shell32.dll', 'shlwapi.dll', 'propsys.dll', 'shdocvw.dll', 'dui70.dll',
            'duser.dll', 'profapi.dll', 'sndvolsso.dll', 'winbrand.dll', 'shacct.dll', 'thumbcache.dll',
            'authui.dll', 'linkinfo.dll', 'actxprxy.dll', 'imageres.dll')
# The components of these files, whose registry entries the prefix gets.
COMPONENTS = ('microsoft-windows-explorer', 'microsoft-windows-explorerframe', 'microsoft-windows-shell32',
              'microsoft-windows-shlwapi', 'microsoft-windows-propsys', 'microsoft-windows-shdocvw',
              'microsoft-windows-dui70', 'microsoft-windows-duser', 'microsoft-windows-profapi',
              'microsoft-windows-audio-volumecontrol', 'microsoft-windows-branding-engine',
              'microsoft-windows-shacct', 'microsoft-windows-thumbnailcache',
              'microsoft-windows-authentication-authui', 'microsoft-windows-linkinfo',
              'microsoft-windows-activexproxy', 'microsoft-windows-imageres', 'microsoft-windows-sud',
              'microsoft-windows-devicecenter',
              # The shell's settings (Explorer\Advanced) and the Network folder's registration.
              'microsoft-windows-shell-client', 'microsoft-windows-networkexplorer',
              # Text files' type, icon and verbs (Wine's Notepad opens them).
              'microsoft-windows-notepad')
# Fonts: Segoe UI, Tahoma and Microsoft Sans Serif (MS Shell Dlg 2, MS Shell Dlg),
# and Meiryo and MS UI Gothic (msgothic.ttc) for Japanese.
FONTS = {'ja': r'(segoeui\w*\.ttf|tahoma\w*\.ttf|micross\.ttf|meiryo\w*\.ttc|msgothic\.ttc)$',
         'en': r'(segoeui\w*\.ttf|tahoma\w*\.ttf|micross\.ttf)$'}
# The localized names of the Start menu's folders.
START_MENU = ('Start Menu', 'Start Menu/Programs', 'Start Menu/Programs/Startup',
              'Start Menu/Programs/Administrative Tools')
# The default user's Quick Launch folder: Show Desktop, Window Switcher and
# their localized names.
QUICK_LAUNCH = ('Shows Desktop.lnk', 'Window Switcher.lnk', 'desktop.ini')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def version(name):
    m = re.search(r'_(\d+)\.(\d+)\.(\d+)\.(\d+)_', name)
    return tuple(int(x) for x in m.groups()) if m else (0,)


def images(wim, temp):
    """[(index, edition, default language)] of install.wim."""
    run('7z', 'x', '-y', f'-o{temp}', str(wim), '[1].xml', stdout=subprocess.DEVNULL)
    root = __import__('xml.etree.ElementTree', fromlist=['ET']).fromstring(
        (Path(temp) / '[1].xml').read_bytes().decode('utf-16'))
    found = []
    for image in root.iter('IMAGE'):
        arch = image.findtext('WINDOWS/ARCH')
        if arch != '9':
            continue
        found.append((image.get('INDEX'), image.findtext('WINDOWS/EDITIONID') or '',
                      image.findtext('WINDOWS/LANGUAGES/DEFAULT') or ''))
    return found


def listing(wim, index):
    """The paths of image INDEX in install.wim, keyed by their lower case path."""
    out = run('7z', 'l', '-ba', '-slt', str(wim), stdout=subprocess.PIPE).stdout.decode('utf-8', 'replace')
    prefix = f'{index}/'
    paths = {}
    for line in out.splitlines():
        if line.startswith('Path = ') and line[7:].startswith(prefix):
            path = line[7:][len(prefix):]
            paths[path.lower()] = path
    return paths


def select(paths, lang_dir, lang):
    """Image path -> output path of the files to extract."""
    wanted = {}

    def want(path, target, required=True):
        real = paths.get(path.lower())
        if real:
            wanted[real] = target
        elif required:
            raise SystemExit(f'Not in this Windows 7 image: {path}')

    def controls_mui(arch, system):
        """Common Controls 6's own MUI file: the newest resources assembly of the
        language. The one in System32 (SYSTEM, used when the image has no such
        assembly) is that of Common Controls 5.82 and lacks version 6's strings,
        among them the word break characters (4193, 4194): without them
        the Start menu's shut down button has no text and the user picture is
        placed at the top of the screen (seen with English media)."""
        found = sorted((p for p in paths if re.match(
            rf'windows/winsxs/{arch}_microsoft\.windows\.c\.\.-controls\.resources_6595b64144ccf1df_6\.0\.[\d.]+_'
            rf'{re.escape(lang_dir.lower())}_[0-9a-f]+/comctl32\.dll\.mui$', p)), key=version)
        return paths[found[-1]] if found else system

    want('Windows/explorer.exe', 'shell/explorer.exe')
    # Only their strings: the Welcome, log-off and shut-down lines (greeter/w7-splash.py)
    for name in ('winlogon.exe', 'wininit.exe'):
        want(f'Windows/System32/{lang_dir}/{name}.mui', f'system32/{lang_dir}/{name}.mui', required=False)
    want(f'Windows/{lang_dir}/explorer.exe.mui', f'shell/{lang_dir}/explorer.exe.mui')
    for name in SYSTEM32:
        want(f'Windows/System32/{name}', f'system32/{name}')
        want(f'Windows/System32/{lang_dir}/{name}.mui', f'system32/{lang_dir}/{name}.mui', required=False)
    # Common Controls 6: the newest amd64 assembly.
    sxs = sorted((p for p in paths if re.match(
        r'windows/winsxs/amd64_microsoft\.windows\.common-controls_6595b64144ccf1df_6\.0\.[\d.]+_none_[0-9a-f]+/comctl32\.dll$', p)),
        key=version)
    if not sxs:
        raise SystemExit('Not in this Windows 7 image: Common Controls 6 (amd64)')
    want(sxs[-1], 'sxs/comctl32.dll')
    want(controls_mui('amd64', f'Windows/System32/{lang_dir}/comctl32.dll.mui'), f'sxs/{lang_dir}/comctl32.dll.mui')
    # The 32-bit Common Controls 6, for the 32-bit copies of the shell DLLs
    sxs = sorted((p for p in paths if re.match(
        r'windows/winsxs/x86_microsoft\.windows\.common-controls_6595b64144ccf1df_6\.0\.[\d.]+_none_[0-9a-f]+/comctl32\.dll$', p)),
        key=version)
    if not sxs:
        raise SystemExit('Not in this Windows 7 image: Common Controls 6 (x86)')
    want(sxs[-1], 'sxs/wow64/comctl32.dll')
    want(controls_mui('x86', f'Windows/SysWOW64/{lang_dir}/comctl32.dll.mui'),
         f'sxs/wow64/{lang_dir}/comctl32.dll.mui')
    for path, real in paths.items():
        name = PurePosixPath(path).name
        if path.startswith('windows/fonts/') and re.match(FONTS[lang], name):
            wanted[real] = f'fonts/{PurePosixPath(real).name}'
        elif path.startswith('windows/resources/themes/aero/') and not path.endswith('/'):
            wanted[real] = 'themes/' + real[len('Windows/Resources/Themes/'):]
        elif re.match(r'windows/cursors/aero_[a-z]+\.(cur|ani)$', path):
            # The Aero cursor scheme (normal size), for the session's X cursor theme
            wanted[real] = 'cursors/' + PurePosixPath(real).name
        elif path.startswith('programdata/microsoft/user account pictures/'):
            wanted[real] = 'pictures/' + real[len('ProgramData/Microsoft/User Account Pictures/'):]
    for name in SYSWOW64:
        want(f'Windows/SysWOW64/{name}', f'syswow64/{name}')
        want(f'Windows/SysWOW64/{lang_dir}/{name}.mui', f'syswow64/{lang_dir}/{name}.mui', required=False)
    # The edition's name on the logon screen (greeter/w7logon.py)
    want('Windows/Branding/Basebrd/basebrd.dll', 'branding/basebrd.dll')
    # Read for its I-beam and crosshair cursors only (greeter/cursors.py --win7)
    want('Windows/System32/user32.dll', 'cursors/user32.dll')
    # Read for the text file's type names only ("Text Document", prefix/win7.py)
    want(f'Windows/System32/{lang_dir}/notepad.exe.mui', f'res/{lang_dir}/notepad.exe.mui', required=False)
    want('Windows/Resources/Themes/aero.theme', 'themes/aero.theme')
    want('Windows/Web/Wallpaper/Windows/img0.jpg', 'web/img0.jpg')
    for folder in START_MENU:
        want(f'ProgramData/Microsoft/Windows/{folder}/desktop.ini', f'startmenu/{folder}/desktop.ini',
             required=False)
    for name in QUICK_LAUNCH:
        want(f'Users/Default/AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/{name}',
             f'quicklaunch/{name}', required=False)
    # Component manifests, for the registry (not kept).
    # The 32-bit view of a component is in a manifest of its own: wow64_ for
    # components with 64-bit counterparts, x86_ for the others.
    for arch, prefixes in (('amd64', ('amd64',)), ('wow64', ('wow64', 'x86'))):
        for component in COMPONENTS:
            for prefix in prefixes:
                found = sorted((p for p in paths if re.match(
                    rf'windows/winsxs/manifests/{prefix}_{re.escape(component)}_31bf3856ad364e35_[\d.]+_[a-z-]+_[0-9a-f]+\.manifest$', p)),
                    key=version)
                if found:
                    wanted[paths[found[-1]]] = f'manifests/{arch}/{component}.manifest'
                    break
            else:
                if arch == 'amd64':
                    raise SystemExit(f'Not in this Windows 7 image: the manifest of {component}')
    return wanted


def extract(iso, output):
    iso, output = iso.resolve(strict=True), output.resolve()
    if output.exists():
        raise SystemExit(f'Refusing existing destination: {output}')
    with tempfile.TemporaryDirectory(prefix='win7-extract-') as temp:
        temp = Path(temp)
        run('7z', 'x', '-y', f'-o{temp}', str(iso), 'sources/install.wim', stdout=subprocess.DEVNULL)
        wim = temp / 'sources/install.wim'
        if not wim.is_file():
            raise SystemExit(f'{iso}: no sources/install.wim (not Windows 7 installation media)')
        found = images(wim, temp)
        if not found:
            raise SystemExit(f'{iso}: no x64 image (only Windows 7 x64 is supported)')
        index, edition, lang_dir = next((i for i in found if i[1] == 'Professional'), found[-1])
        lang = LANGUAGES.get(lang_dir)
        if not lang:
            print(f'Warning: this Windows 7 is neither Japanese nor English ({lang_dir}). It is set up as '
                  'English Windows 7 with its own MUI files; it has not been tested at all.', file=sys.stderr)
            lang = 'en'
        paths = listing(wim, index)
        wanted = select(paths, lang_dir, lang)
        files = temp / 'image'
        listfile = temp / 'list.txt'
        listfile.write_text(''.join(f'{index}/{p}\n' for p in wanted), encoding='utf-8')
        run('7z', 'x', '-y', f'-o{files}', str(wim), f'@{listfile}', stdout=subprocess.DEVNULL)
        output.mkdir(parents=True)
        manifest = []
        manifest_paths = {'amd64': [], 'wow64': []}
        for source, target in sorted(wanted.items(), key=lambda item: item[1]):
            if (files / index / source).is_dir():
                continue
            data = (files / index / source).read_bytes()
            if target.startswith('manifests/'):
                manifest_paths[target.split('/')[1]].append(files / index / source)
                continue
            dest = output / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            manifest.append({'name': target, 'source': f'{index}/{source}',
                             'sha256': hashlib.sha256(data).hexdigest()})
        icons = {'shell32.dll': media.resource_ids(output / 'system32/shell32.dll', RT_GROUP_ICON)}
        # registry.reg: the 64-bit view; registry-wow64.reg: the 32-bit view
        for arch, name in (('amd64', 'registry.reg'), ('wow64', 'registry-wow64.reg')):
            text, missing = manifests.convert(manifest_paths[arch], icons)
            (output / name).write_text(text, encoding='utf-16')
            for item in missing:
                print(f'Registry entry left out ({arch}):', item, file=sys.stderr)
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (output / 'media.json').write_text(json.dumps(
            {'lang': lang, 'ui_language': lang_dir, 'image': int(index), 'edition': edition,
             'extract_version': EXTRACT_VERSION}, indent=2) + '\n')
        print(f'Extracted {len(manifest)} files of Windows 7 {edition} ({lang_dir}) to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('iso', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.iso, args.output)
