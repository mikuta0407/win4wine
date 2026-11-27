#!/usr/bin/env python3
"""Registry entries of Windows 7 component manifests, as a .reg file.

Windows 7 installs each component from a manifest in WinSxS\\Manifests that
lists its files and its registry keys and values: COM classes, shell folders,
file types, and the default values of its settings (the configuration
schema). extract/win7.py writes the entries of the components whose files the
Windows 7 shell prefix uses, so the prefix gets what those components
register, not the whole registry of an installed Windows.

  manifests.py OUT.reg MANIFEST...
"""
import re
import sys
import xml.etree.ElementTree as ET

NS = '{urn:schemas-microsoft-com:asm.v3}'
XSD = '{http://www.w3.org/2001/XMLSchema}'
WCM = '{http://schemas.microsoft.com/WMIConfig/2002/State}'
# The folders of a new Windows 7 installation, as the prefix lays them out.
RUNTIME = {
    'runtime.windows': r'C:\windows',
    'runtime.system32': r'C:\windows\system32',
    'runtime.system': r'C:\windows\system',
    'runtime.inf': r'C:\windows\inf',
    'runtime.fonts': r'C:\windows\Fonts',
    'runtime.help': r'C:\windows\Help',
    'runtime.programFiles': r'C:\Program Files',
    'runtime.programFilesX86': r'C:\Program Files (x86)',
    'runtime.commonFiles': r'C:\Program Files\Common Files',
    'runtime.programData': r'C:\ProgramData',
    'runtime.public': r'C:\users\Public',
    'runtime.startMenu': r'C:\ProgramData\Microsoft\Windows\Start Menu',
    'runtime.documentsSettings': r'C:\users',
    'runtime.userProfile': '%USERPROFILE%',
    'runtime.bootDrive': 'C:',
    'runtime.systemDrive': 'C:',
}
# HKEY_USERS\.DEFAULT is the profile a new user starts from.
HIVES = ('HKEY_CLASSES_ROOT', 'HKEY_LOCAL_MACHINE', 'HKEY_CURRENT_USER')


def number(raw):
    """Manifests write numbers as 0x..., decimal, true/false, or plain hex digits of the value's width."""
    raw = raw.strip()
    if not raw or raw.lower() == 'false':
        return 0
    if raw.lower() == 'true':
        return 1
    if raw.lower().startswith('0x'):
        return int(raw, 16)
    if raw.startswith('-'):
        return int(raw, 10)
    return int(raw, 16) if len(raw) >= 8 else int(raw, 10)


def quote(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def hexdata(kind, raw):
    data = ','.join(raw[i:i + 2] for i in range(0, len(raw), 2))
    return f'hex({kind:x}):{data}' if kind is not None else f'hex:{data}'


def utf16hex(text):
    return text.encode('utf-16-le').hex()


def value_line(name, kind, raw):
    label = '@' if name == '' else f'"{quote(name)}"'
    if kind == 'REG_SZ':
        return f'{label}="{quote(raw)}"'
    if kind == 'REG_EXPAND_SZ':
        return f'{label}={hexdata(2, utf16hex(raw) + "0000")}'
    if kind == 'REG_DWORD':
        return f'{label}=dword:{number(raw) & 0xffffffff:08x}'
    if kind == 'REG_QWORD':
        return f'{label}={hexdata(11, (number(raw) & (1 << 64) - 1).to_bytes(8, "little").hex())}'
    if kind == 'REG_BINARY':
        return f'{label}={hexdata(None, re.sub(r"[^0-9a-fA-F]", "", raw).lower())}'
    if kind == 'REG_MULTI_SZ':
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', raw) or ([raw] if raw else [])
        return f'{label}={hexdata(7, "".join(utf16hex(i) + "0000" for i in items) + "0000")}'
    if kind == 'REG_NONE':
        return f'{label}=hex(0):'
    raise ValueError(kind)


def icon_reference(raw, icons):
    """RAW with an icon given by index ("shell32.dll,3") given by resource ID instead ("shell32.dll,-4").

    ICONS maps a DLL's name to its icon groups' IDs in order. Windows and Wine
    read an index as the position among the DLL's icon groups; Wine's own
    shell32, which 32-bit programs load, has named icon groups before its
    numbered ones, so Windows 7's indexes would pick other icons there. The
    IDs are the same in both."""
    m = re.match(r'(?i)^(.*?)([^\\]+\.dll),(\d+)$', raw)
    ids = icons.get(m.group(2).lower()) if m else None
    if not ids or int(m.group(3)) >= len(ids) or ids[int(m.group(3))] is None:
        return raw
    return f'{m.group(1)}{m.group(2)},-{ids[int(m.group(3))]}'


def entries(path):
    """(key, [(name, type, value)]) of a manifest: its registry keys, then its settings' defaults."""
    root = ET.parse(path).getroot()
    strings = {'string.' + s.get('id', ''): s.get('value', '') for s in root.iter(NS + 'string')}
    keys = [(key.get('keyName', ''), [(v.get('name', ''), v.get('valueType', ''), v.get('value', ''))
                                      for v in key.findall(NS + 'registryValue')])
            for key in root.iter(NS + 'registryKey')]
    # A setting names its key in wcm:handler="regkey('KEY')", its value in
    # wcm:legacyName and its type in wcm:legacyType, and holds the default: in
    # its default attribute or, as the Start menu's options of the explorer
    # component (StartPanel\...\DefaultValue), in wcm:default.
    settings = {}
    for element in root.iter(XSD + 'element'):
        m = re.match(r"regkey\('(.+)'\)$", element.get(WCM + 'handler', ''))
        default = element.get('default', element.get(WCM + 'default'))
        if m and default is not None and element.get(WCM + 'legacyType'):
            settings.setdefault(m.group(1), []).append(
                (element.get(WCM + 'legacyName', ''), element.get(WCM + 'legacyType'), default))
    return keys + list(settings.items()), strings


def convert(paths, icons=None):
    """The .reg text of the manifests PATHS, and what was left out.

    ICONS (a DLL's name -> its icon groups' IDs) turns icon indexes into IDs."""
    out = ['Windows Registry Editor Version 5.00', '']
    missing = set()
    for path in paths:
        keys, strings = entries(path)

        def resolve(text):
            def sub(m):
                name = m.group(1)
                if name in RUNTIME:
                    return RUNTIME[name]
                if name in strings:
                    return strings[name]
                raise KeyError(name)
            return re.sub(r'\$\(([^)]+)\)', sub, text)

        for name, values in keys:
            hive, _, rest = name.partition('\\')
            if hive == 'HKEY_USERS' and rest.upper().startswith('.DEFAULT'):
                hive, rest = 'HKEY_CURRENT_USER', rest[len('.DEFAULT'):].lstrip('\\')
            if hive not in HIVES:
                missing.add(f'key in {hive}')
                continue
            try:
                key = hive + ('\\' + resolve(rest) if rest else '')
            except KeyError as e:
                missing.add(f'variable {e}')
                continue
            lines = []
            for vname, kind, raw in values:
                try:
                    value = resolve(raw)
                    if icons and kind in ('REG_SZ', 'REG_EXPAND_SZ'):
                        value = icon_reference(value, icons)
                    lines.append(value_line(vname, kind, value))
                except KeyError as e:
                    missing.add(f'variable {e}')
                except ValueError:
                    missing.add(f'type {kind}')
            out += [f'[{key}]', *lines, '']
    return '\r\n'.join(out) + '\r\n', sorted(missing)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip())
    text, missing = convert(sys.argv[2:])
    with open(sys.argv[1], 'w', encoding='utf-16') as f:
        f.write(text)
    for item in missing:
        print('left out:', item, file=sys.stderr)
