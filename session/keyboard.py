#!/usr/bin/env python3
"""The session's keyboard layout, as XP's Regional and Language Options set it.

XP keeps the user's input languages in HKCU\\Keyboard Layout\\Preload (in
order, with Substitutes for variants such as French (Canada)) and the key
that switches them in HKCU\\Keyboard Layout\\Toggle; XP's Text Services and
Input Languages (input.dll) writes them, and Wine patch 0043 gives them to
Windows programs. The keys themselves follow the session's XKB layout, so the
session sets XKB from the same list: labwc's environment file in the Wayland
session, setxkbmap in the X11 session. A prefix first takes the Linux
system's layout (localectl) as its input language.

  keyboard.py seed PREFIX --wine WINE    the system's layout as XP's, once
  keyboard.py env PREFIX                 XKB_DEFAULT_* lines for labwc
  keyboard.py apply PREFIX               set XKB from the prefix's choice
  keyboard.py apply --klids 0000040c,00000409 [--toggle 1]
                                         set XKB from these (keyboard-watch.exe)
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

# Windows keyboard layout identifiers (KLIDs) and the XKB layout and variant
# that type the same characters. A KLID's low word is its language.
LAYOUTS = {
    '00000409': ('us', ''), '00010409': ('us', 'dvorak'), '00020409': ('us', 'intl'),
    '00030409': ('us', 'dvorak-l'), '00040409': ('us', 'dvorak-r'), '00000809': ('gb', ''),
    '00001809': ('ie', ''), '00000c09': ('au', ''), '00001009': ('ca', 'fr'),
    '0000040c': ('fr', ''), '0000080c': ('be', ''), '0001080c': ('be', ''), '00000c0c': ('ca', 'fr-legacy'),
    '0000100c': ('ch', 'fr'), '0000140c': ('fr', ''), '0000180c': ('fr', ''),
    '00000407': ('de', ''), '00010407': ('de', ''), '00000807': ('ch', ''), '00000c07': ('at', ''),
    '00001007': ('de', ''), '00001407': ('de', ''), '00000410': ('it', ''), '00010410': ('it', ''),
    '00000810': ('ch', ''), '0000040a': ('es', ''), '0001040a': ('es', ''), '0000080a': ('latam', ''),
    '00000816': ('pt', ''), '00000416': ('br', ''), '00010416': ('br', ''), '00000413': ('nl', ''),
    '00000813': ('be', ''), '00000406': ('dk', ''), '0000040b': ('fi', ''), '00000414': ('no', ''),
    '0000041d': ('se', ''), '0000040f': ('is', ''), '00000405': ('cz', ''), '00010405': ('cz', 'qwerty'),
    '0000041b': ('sk', ''), '0000040e': ('hu', ''), '00000415': ('pl', ''), '00010415': ('pl', ''),
    '00000418': ('ro', ''), '0000041a': ('hr', ''), '00000424': ('si', ''), '00000c1a': ('rs', ''),
    '0000081a': ('rs', 'latin'), '00000402': ('bg', ''), '00000419': ('ru', ''), '00000422': ('ua', ''),
    '00000423': ('by', ''), '00000408': ('gr', ''), '0000041f': ('tr', ''), '0001041f': ('tr', 'f'),
    '00000425': ('ee', ''), '00000426': ('lv', ''), '00000427': ('lt', ''), '0000040d': ('il', ''),
    '00000401': ('ara', ''), '00000429': ('ir', ''), '0000041e': ('th', ''), '0000042a': ('vn', ''),
    '00000411': ('jp', ''), 'e0010411': ('jp', ''), '00000412': ('kr', ''), 'e0010412': ('kr', ''),
    '00000437': ('ge', ''), '0000042b': ('am', ''), '0000042f': ('mk', ''), '0000041c': ('al', ''),
    '00000439': ('in', ''), '00000438': ('fo', ''), '0000043f': ('kz', ''),
}
# XP's switching key (Toggle\Hotkey) as an XKB option: 1 Left Alt+Shift
# (XP's default), 2 Ctrl+Shift, 3 none, 4 the grave accent.
TOGGLES = {'1': 'grp:lalt_lshift_toggle', '2': 'grp:ctrl_shift_toggle', '3': '', '4': 'grp:tilde_toggle'}
MARKER = r'HKCU\Software\Win4Wine\Profile'


def system():
    """The Linux system's XKB settings (localectl), as a dict."""
    settings = {'layout': 'us', 'model': '', 'variant': '', 'options': ''}
    try:
        out = subprocess.run(['localectl', 'status'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ''
    for key, name in (('layout', 'X11 Layout'), ('model', 'X11 Model'), ('variant', 'X11 Variant'),
                      ('options', 'X11 Options')):
        m = re.search(rf'^\s*{name}:\s*(\S+)', out, re.MULTILINE)
        if m and m.group(1) != '(unset)':  # localectl's word for a setting the system does not have
            settings[key] = m.group(1)
    return settings


def klids_for(settings):
    """The KLIDs of the system's layouts, for the prefix's Preload."""
    layouts = settings['layout'].split(',')
    variants = (settings['variant'].split(',') + [''] * len(layouts))[:len(layouts)]
    klids = []
    for layout, variant in zip(layouts, variants):
        exact = [k for k, v in LAYOUTS.items() if v == (layout, variant)]
        loose = [k for k, v in LAYOUTS.items() if v[0] == layout and not v[1]]
        klid = (exact or loose or [None])[0]
        if klid and klid not in klids:
            klids.append(klid)
    return klids or ['00000409']


def registry_values(prefix, key):
    """The values of an HKCU key in the prefix's user.reg (Wine's text format)."""
    header = '[' + key.replace('\\', '\\\\') + ']'
    values, inside = {}, False
    try:
        lines = (prefix / 'user.reg').read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return values
    for line in lines:
        if line.startswith('['):
            # "[Key\\Path] time"; the key itself may have spaces (Keyboard Layout)
            inside = line.lower() == header.lower() or line.lower().startswith(header.lower() + ' ')
        elif inside:
            m = re.match(r'"([^"]*)"="([^"]*)"', line)
            if m:
                values[m.group(1)] = m.group(2)
    return values


def preload(prefix):
    """The prefix's input languages (Substitutes applied) and its switching key."""
    order = registry_values(prefix, r'Keyboard Layout\Preload')
    substitutes = {k.lower(): v for k, v in registry_values(prefix, r'Keyboard Layout\Substitutes').items()}
    klids = [substitutes.get(order[n].lower(), order[n]) for n in sorted(order, key=lambda n: int(n) if n.isdigit() else 99)]
    toggle = registry_values(prefix, r'Keyboard Layout\Toggle').get('Hotkey', '1')
    return [k.lower() for k in klids], toggle


def xkb(klids, toggle, base=None):
    """XKB settings for the input languages KLIDS: the system's model and
    options, and its variant where it has the same layout (fr's azerty)."""
    base = base or system()
    system_layouts = base['layout'].split(',')
    system_variants = (base['variant'].split(',') + [''] * len(system_layouts))[:len(system_layouts)]
    layouts, variants = [], []
    for klid in klids:
        layout, variant = LAYOUTS.get(klid.lower(), (None, ''))
        if not layout or (layout, variant) in zip(layouts, variants):
            continue
        if not variant and layout in system_layouts:
            variant = system_variants[system_layouts.index(layout)]
        layouts.append(layout)
        variants.append(variant)
    if not layouts:
        return dict(base)
    options = [o for o in base['options'].split(',') if o and not o.startswith('grp:')]
    if len(layouts) > 1 and TOGGLES.get(toggle, TOGGLES['1']):
        options.append(TOGGLES.get(toggle, TOGGLES['1']))
    return {'layout': ','.join(layouts), 'model': base['model'],
            'variant': ','.join(variants) if any(variants) else '', 'options': ','.join(options)}


def prefix_settings(prefix):
    """The XKB settings of the prefix's input languages; the system's own while
    the prefix has none, or only those that seed() could give a system whose
    layout has no KLID (US English stands for it until the user chooses)."""
    klids, toggle = preload(prefix)
    base = system()
    known = {layout for layout, _ in LAYOUTS.values()}
    stand_in = klids == klids_for(base) and any(layout not in known for layout in base['layout'].split(','))
    return xkb(klids, toggle, base) if klids and not stand_in else base


def environment(settings):
    return ''.join(f'XKB_DEFAULT_{key.upper()}={settings[key]}\n'
                   for key in ('layout', 'model', 'variant', 'options'))


def apply(settings):
    """Set the session's layout: labwc's environment file and a reconfigure
    (Wayland; Xwayland and Wine follow), or setxkbmap (X11)."""
    env_file = os.environ.get('WIN4WINE_LABWC_ENV')
    if env_file:
        temporary = Path(env_file + '.tmp')
        temporary.write_text(environment(settings))
        temporary.replace(env_file)
        pid = os.environ.get('LABWC_PID')
        if pid and pid.isdigit():
            try:
                os.kill(int(pid), signal.SIGHUP)
            except OSError:
                pass
        return True
    if os.environ.get('DISPLAY') and shutil.which('setxkbmap'):
        command = ['setxkbmap', '-layout', settings['layout'], '-variant', settings['variant'], '-option', '']
        if settings['model']:
            command += ['-model', settings['model']]
        if settings['options']:
            command += ['-option', settings['options']]
        return subprocess.run(command, check=False, timeout=10).returncode == 0
    return False


def seed(prefix, wine):
    """Once per prefix: the system's layouts become XP's input languages."""
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEDEBUG='-all')
    env.pop('WINEARCH', None)

    def reg(*args):
        return subprocess.run([wine, 'reg', *args], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=120).returncode == 0
    if reg('query', MARKER, '/v', 'KeyboardLayout'):
        return
    klids = klids_for(system())
    reg('delete', r'HKCU\Keyboard Layout\Preload', '/f')
    for number, klid in enumerate(klids, 1):
        reg('add', r'HKCU\Keyboard Layout\Preload', '/v', str(number), '/d', klid, '/f')
    reg('add', MARKER, '/v', 'KeyboardLayout', '/t', 'REG_DWORD', '/d', '1', '/f')
    print('Input languages:', ', '.join(klids))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('seed', 'env', 'apply'))
    parser.add_argument('prefix', type=Path, nargs='?')
    parser.add_argument('--wine', default=os.environ.get('WINE', 'wine'))
    parser.add_argument('--klids', help='comma-separated KLIDs (keyboard-watch.exe)')
    parser.add_argument('--toggle', default='1')
    args = parser.parse_args()
    if args.action == 'apply' and args.klids:
        apply(xkb(args.klids.split(','), args.toggle))
        raise SystemExit
    if not args.prefix:
        parser.error('the prefix is needed')
    prefix = args.prefix.resolve(strict=True)
    if args.action == 'seed':
        seed(prefix, args.wine)
    else:
        settings = prefix_settings(prefix)
        if args.action == 'env':
            print(environment(settings), end='')
        else:
            apply(settings)
