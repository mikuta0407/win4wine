#!/usr/bin/env python3
"""Show the Linux desktop's applications in the XP Start menu.

Reads the desktop entries of the XDG data directories (freedesktop.org Desktop
Entry Specification) and keeps one shortcut per shown application in the
prefix's common Programs folder, sorted into XP-like folders by category and
named "NAME (Linux)". Each shortcut starts the program through
linux-launch.exe, under a name of its own (apps\\<desktop file ID>.exe, a hard
link): XP's Start menu counts the uses of a program by the executable its
shortcut runs, so with one launcher for all, every application would count as
one. Icons are converted from the icon theme. Only shortcuts
that this module made are changed or removed; their list is kept in
C:\\xp\\linux-apps\\state.json. With --watch it follows changes to the
application directories until it is stopped; --remove takes them all out.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import select
import shutil
import struct
import subprocess
import sys
import ctypes

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = 'drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs'
WINDOWS_PROGRAMS = r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs'
STATE = 'drive_c/xp/linux-apps'
WINDOWS_STATE = r'C:\xp\linux-apps'
ICON_SIZES = (16, 32, 48)
# XDG main categories to Start menu folders, as on XP where one exists
# (Japanese, other languages). The first category of an entry that is
# listed here decides; TerminalEmulator goes with XP's command prompt.
FOLDERS = (
    ('TerminalEmulator', ('アクセサリ', 'Accessories')),
    ('AudioVideo', (r'アクセサリ\エンターテイメント', r'Accessories\Entertainment')),
    ('Audio', (r'アクセサリ\エンターテイメント', r'Accessories\Entertainment')),
    ('Video', (r'アクセサリ\エンターテイメント', r'Accessories\Entertainment')),
    ('Development', ('開発', 'Development')),
    ('Education', ('教育', 'Education')),
    ('Game', ('ゲーム', 'Games')),
    ('Graphics', ('グラフィックス', 'Graphics')),
    ('Network', ('インターネット', 'Internet')),
    ('Office', ('オフィス', 'Office')),
    ('Science', ('科学', 'Science')),
    ('Settings', ('設定', 'Settings')),
    ('System', (r'アクセサリ\システム ツール', r'Accessories\System Tools')),
    ('Utility', ('アクセサリ', 'Accessories')),
)
INVALID = str.maketrans({c: '_' for c in '\\/:*?"<>|'} | {chr(c): None for c in range(32)})


def data_dirs():
    home = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local/share')
    rest = os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
    seen, dirs = set(), []
    for d in [home, *rest.split(':')]:
        if d and os.path.isabs(d) and d not in seen:
            seen.add(d)
            dirs.append(Path(d))
    return dirs


def unescape(value):
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == '\\' and i + 1 < len(value):
            i += 1
            out.append({'s': ' ', 'n': '\n', 't': '\t', 'r': '\r', '\\': '\\'}.get(value[i], '\\' + value[i]))
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def parse(path):
    """The [Desktop Entry] group as {key: value}, with locale keys like Name[ja]."""
    entry, group = {}, None
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('['):
            group = line
            continue
        if group == '[Desktop Entry]' and '=' in line:
            key, value = line.split('=', 1)
            entry.setdefault(key.strip(), value.strip())
    return entry


def locale_names():
    """Locale keys to try, best first (lang_COUNTRY@MODIFIER, lang_COUNTRY, lang@MODIFIER, lang)."""
    value = next((os.environ[k] for k in ('LC_ALL', 'LC_MESSAGES', 'LANG') if os.environ.get(k)), 'C')
    value, _, modifier = value.partition('@')
    value = value.split('.')[0]
    lang, _, country = value.partition('_')
    if lang in ('C', 'POSIX', ''):
        return []
    names = []
    if country and modifier:
        names.append(f'{lang}_{country}@{modifier}')
    if country:
        names.append(f'{lang}_{country}')
    if modifier:
        names.append(f'{lang}@{modifier}')
    names.append(lang)
    return names


def localized(entry, key, locales):
    for name in locales:
        if f'{key}[{name}]' in entry:
            return unescape(entry[f'{key}[{name}]'])
    return unescape(entry[key]) if key in entry else None


def boolean(entry, key):
    return entry.get(key, '').strip().lower() == 'true'


def strings(entry, key):
    return [s for s in unescape(entry.get(key, '')).split(';') if s]


def find_program(name):
    if os.path.isabs(name):
        return name if os.access(name, os.X_OK) and os.path.isfile(name) else None
    return shutil.which(name)


def shown(entry):
    if entry.get('Type') != 'Application' or not entry.get('Exec'):
        return False
    if boolean(entry, 'NoDisplay') or boolean(entry, 'Hidden'):
        return False
    desktops = [d for d in os.environ.get('XDG_CURRENT_DESKTOP', '').split(':') if d]
    only = strings(entry, 'OnlyShowIn')
    if only and not set(only) & set(desktops):
        return False
    if set(strings(entry, 'NotShowIn')) & set(desktops):
        return False
    if entry.get('TryExec') and not find_program(unescape(entry['TryExec'])):
        return False
    return True


def split_exec(value):
    """Exec's arguments: double quotes group, and inside them a backslash escapes " ` $ \\."""
    args, current, quoted, started, i = [], [], False, False, 0
    while i < len(value):
        c = value[i]
        if quoted:
            if c == '\\' and i + 1 < len(value) and value[i+1] in '"`$\\':
                i += 1
                current.append(value[i])
            elif c == '"':
                quoted = False
            else:
                current.append(c)
        elif c == '"':
            quoted = started = True
        elif c in ' \t':
            if started:
                args.append(''.join(current))
                current, started = [], False
        else:
            current.append(c)
            started = True
        i += 1
    if quoted:
        raise ValueError('unterminated quote')
    if started:
        args.append(''.join(current))
    return args


def command(entry, path, locales):
    """The argument list of an entry started without files or URLs, or None
    for one that cannot be started (an Exec that is not well formed, a
    program that is not there)."""
    args = []
    try:
        words = split_exec(unescape(entry['Exec']))
    except ValueError:
        # One desktop file with an unterminated quote must not end the menu
        # for all the others (the first pass and the watcher).
        return None
    for arg in words:
        if arg in ('%f', '%F', '%u', '%U', '%d', '%D', '%n', '%N', '%v', '%m'):
            continue
        if arg == '%i':
            if entry.get('Icon'):
                args += ['--icon', unescape(entry['Icon'])]
            continue
        out, i = [], 0
        while i < len(arg):
            if arg[i] == '%' and i + 1 < len(arg):
                code = arg[i+1]
                out.append({'%': '%', 'c': localized(entry, 'Name', locales) or '', 'k': str(path)}.get(code, ''))
                i += 2
            else:
                out.append(arg[i])
                i += 1
        args.append(''.join(out))
    if not args or not find_program(args[0]):
        return None
    if boolean(entry, 'Terminal'):
        terminal = 'x-terminal-emulator' if shutil.which('x-terminal-emulator') else 'xterm'
        args = [terminal, '-e', *args]
    return args


def folder(entry, japanese):
    categories = strings(entry, 'Categories')
    for category, names in FOLDERS:
        if category in categories:
            return names[0 if japanese else 1]
    return ''


def entries():
    """Shown desktop entries by desktop file ID; earlier data directories win."""
    found = {}
    for base in data_dirs():
        apps = base / 'applications'
        if not apps.is_dir():
            continue
        for directory, subdirs, files in os.walk(apps):
            relative = Path(directory).relative_to(apps)
            # Wine's own menu entries for Windows programs live in applications/wine.
            if relative == Path('.'):
                subdirs[:] = [d for d in subdirs if d != 'wine']
            subdirs.sort()
            for name in sorted(files):
                if not name.endswith('.desktop'):
                    continue
                file_id = '-'.join((*relative.parts, name)) if relative != Path('.') else name
                if file_id in found:
                    continue
                path = Path(directory) / name
                found[file_id] = (path, parse(path))
    return {k: v for k, v in found.items() if v[1] is not None and shown(v[1])}


# Icons: the icon theme lookup of the Icon Theme Specification, simplified to
# the directory sizes of each theme's index.theme.

def icon_theme():
    for settings in (Path.home() / '.config/gtk-3.0/settings.ini', Path('/etc/gtk-3.0/settings.ini')):
        try:
            for line in settings.read_text().splitlines():
                key, _, value = line.partition('=')
                if key.strip() == 'gtk-icon-theme-name' and value.strip():
                    return value.strip()
        except OSError:
            pass
    return 'Adwaita'


def theme_dirs(theme, bases):
    """(directory, nominal size, scalable) for a theme, from its index.theme."""
    for base in bases:
        index = base / theme / 'index.theme'
        if not index.is_file():
            continue
        groups, group = {}, None
        for line in index.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line.startswith('['):
                group = groups.setdefault(line[1:-1], {})
            elif group is not None and '=' in line:
                key, value = line.split('=', 1)
                group[key.strip()] = value.strip()
        main = groups.get('Icon Theme', {})
        result = []
        for name in main.get('Directories', '').split(','):
            info = groups.get(name.strip())
            if not info or info.get('Scale', '1') != '1':
                continue
            try:
                size = int(info.get('Size', '0'))
            except ValueError:
                continue
            result.append((name.strip(), size, info.get('Type', 'Threshold') == 'Scalable'))
        return result, [t.strip() for t in main.get('Inherits', '').split(',') if t.strip()]
    return [], []


def icon_files(name):
    """Candidate (size, scalable, path) files for an icon name, from the first theme that has it."""
    if os.path.isabs(name):
        return [(0, name.endswith('.svg'), Path(name))] if os.path.isfile(name) else []
    bases = [d / 'icons' for d in data_dirs()]
    bases.insert(0, Path.home() / '.icons')
    # The user's theme and the themes it inherits, then hicolor.
    queue, seen = [icon_theme()], set()
    while queue:
        theme = queue.pop(0)
        if theme in seen:
            continue
        seen.add(theme)
        directories, inherits = theme_dirs(theme, bases)
        found = []
        for directory, size, scalable in directories:
            for base in bases:
                for extension in ('png', 'svg', 'xpm'):
                    path = base / theme / directory / f'{name}.{extension}'
                    if path.is_file():
                        found.append((size, scalable or extension == 'svg', path))
        if found:
            return found
        queue += [t for t in inherits if t != 'hicolor']
        if not queue and 'hicolor' not in seen:
            queue.append('hicolor')
    for extension in ('png', 'svg', 'xpm'):
        path = Path('/usr/share/pixmaps') / f'{name}.{extension}'
        if path.is_file():
            return [(0, extension == 'svg', path)]
    return []


def pixbuf_module():
    try:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        return GdkPixbuf
    except (ImportError, ValueError):
        return None


def icon_image(GdkPixbuf, candidates, size):
    """BGRA rows (top first) of one icon size, or None."""
    def rank(candidate):
        nominal, scalable, _ = candidate
        if nominal == size:
            return (0, 0)
        if scalable:
            return (1, 0)
        # Prefer scaling down from the nearest larger image.
        return (2, nominal - size) if nominal > size else (3, size - nominal)
    for _, scalable, path in sorted(candidates, key=rank):
        try:
            if scalable:
                image = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), size, size)
            else:
                image = GdkPixbuf.Pixbuf.new_from_file(str(path))
                if image.get_width() != size or image.get_height() != size:
                    scale = size / max(image.get_width(), image.get_height())
                    image = image.scale_simple(max(1, round(image.get_width() * scale)),
                                               max(1, round(image.get_height() * scale)),
                                               GdkPixbuf.InterpType.HYPER)
        except Exception:  # GLib.Error for unreadable or unsupported files
            continue
        if not image.get_has_alpha():
            image = image.add_alpha(False, 0, 0, 0)
        width, height = image.get_width(), image.get_height()
        canvas = bytearray(size * size * 4)
        data, stride = image.get_pixels(), image.get_rowstride()
        left, top = (size - width) // 2, (size - height) // 2
        for y in range(height):
            for x in range(width):
                r, g, b, a = data[y*stride + x*4:y*stride + x*4 + 4]
                offset = ((top + y) * size + left + x) * 4
                canvas[offset:offset+4] = bytes((b, g, r, a))
        return bytes(canvas)
    return None


def ico(images):
    """An .ico file of 32-bit images {size: BGRA rows}, with an AND mask for alpha 0."""
    header = struct.pack('<HHH', 0, 1, len(images))
    directory, blobs = b'', b''
    offset = 6 + 16 * len(images)
    for size, pixels in sorted(images.items()):
        rows = [pixels[y*size*4:(y+1)*size*4] for y in range(size)]
        mask_stride = (size + 31) // 32 * 4
        mask = bytearray()
        for row in reversed(rows):
            bits = bytearray(mask_stride)
            for x in range(size):
                if row[x*4+3] == 0:
                    bits[x // 8] |= 0x80 >> (x % 8)
            mask += bits
        blob = (struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0, size * size * 4 + len(mask), 0, 0, 0, 0)
                + b''.join(reversed(rows)) + bytes(mask))
        directory += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    return header + directory + blobs


def make_icon(name, target):
    """Write TARGET from the theme icon NAME; returns whether it exists."""
    GdkPixbuf = pixbuf_module()
    candidates = icon_files(name) if name else []
    if not GdkPixbuf or not candidates:
        return False
    images = {}
    for size in ICON_SIZES:
        image = icon_image(GdkPixbuf, candidates, size)
        if image:
            images[size] = image
    if not images:
        return False
    temp = target.with_suffix('.tmp')
    temp.write_bytes(ico(images))
    temp.replace(target)
    return True


def windows_path(prefix, path):
    return 'C:\\' + str(path.relative_to(prefix / 'drive_c')).replace('/', '\\')


def quote(args):
    return subprocess.list2cmdline(args)


class Menu:
    def __init__(self, prefix, wine):
        self.prefix, self.wine = prefix, wine
        self.programs = prefix / PROGRAMS
        self.state_dir = prefix / STATE
        self.state_file = self.state_dir / 'state.json'
        self.japanese = (locale_names() or ['C'])[-1] == 'ja'

    def load(self):
        try:
            state = json.loads(self.state_file.read_text())
            return state.get('links', {}), set(state.get('folders', []))
        except (OSError, ValueError):
            return {}, set()

    def save(self, links, folders):
        temp = self.state_file.with_suffix('.tmp')
        temp.write_text(json.dumps({'links': links, 'folders': sorted(folders)}, ensure_ascii=False, indent=1) + '\n')
        temp.replace(self.state_file)

    def save_relaunch(self, links):
        """relaunch.tsv: for the proxy, the application a Linux window belongs to,
        found by its WM_CLASS class or Wayland app_id (lower case): KEY, name,
        command (the shortcut's) and icon, each as Windows 7's taskbar takes them
        from a window (AppUserModel Relaunch*: the jump list's title, pinning).
        Keys in order of trust: StartupWMClass, the desktop file ID, the
        ID's last dotted part, the program's name."""
        locales = locale_names()
        found = entries()
        rows, keyed = [], {}
        for file_id, item in sorted(links.items()):
            path, entry = found.get(file_id, (None, None))
            name = entry and (localized(entry, 'Name', locales) or '').replace('\t', ' ').strip()
            args = entry and command(entry, path, locales)
            if not name or not args:
                continue
            launch = quote([f'{WINDOWS_STATE}\\linux-launch.exe']) + ' ' + item['arguments']
            icon = self.state_dir / 'icons' / f'{file_id}.ico'
            stem = file_id.removesuffix('.desktop')
            keys = (entry.get('StartupWMClass', ''), stem, stem.rsplit('.', 1)[-1], Path(args[0]).name)
            rows.append((keys, (name, launch, windows_path(self.prefix, icon) + ',0' if icon.is_file() else '')))
        for rank in range(4):
            for keys, row in rows:
                key = keys[rank].strip().lower()
                if key and '\t' not in key and key not in keyed:
                    keyed[key] = row
        text = ''.join('\t'.join((key, *row)) + '\n' for key, row in sorted(keyed.items()))
        target = self.state_dir / 'relaunch.tsv'
        try:
            if target.read_text(encoding='utf-8') == text:
                return
        except OSError:
            pass
        temp = target.with_suffix('.tmp')
        temp.write_text(text, encoding='utf-8')
        temp.replace(target)

    def install_launcher(self, launchers=()):
        source = ROOT / '.local/bridge/linux-launch.exe'
        target = self.state_dir / 'linux-launch.exe'
        if not target.is_file() or target.read_bytes() != source.read_bytes():
            temp = target.with_suffix('.tmp')
            shutil.copyfile(source, temp)
            temp.replace(target)
        # One name per application: hard links to the launcher (copies elsewhere).
        apps = self.state_dir / 'apps'
        apps.mkdir(exist_ok=True)
        wanted = set(launchers)
        for path in apps.glob('*.exe'):
            if path.name not in wanted or (not path.samefile(target) and path.read_bytes() != target.read_bytes()):
                path.unlink()
        for name in wanted:
            path = apps / name
            if not path.exists():
                try:
                    os.link(target, path)
                except OSError:
                    shutil.copyfile(target, path)

    def wanted(self):
        """{file ID: link description} for the current desktop entries."""
        locales = locale_names()
        result, used = {}, set()
        for file_id, (path, entry) in sorted(entries().items()):
            args = command(entry, path, locales)
            name = (localized(entry, 'Name', locales) or '').translate(INVALID).strip(' .')
            if not args or not name:
                continue
            directory = folder(entry, self.japanese)
            link = f'{name} (Linux)'
            number = 2
            while (directory, link.lower()) in used:
                link, number = f'{name} (Linux {number})', number + 1
            used.add((directory, link.lower()))
            work = unescape(entry.get('Path', ''))
            result[file_id] = dict(
                link=f'{directory}\\{link}.lnk' if directory else f'{link}.lnk',
                launcher=re.sub(r'[^A-Za-z0-9._-]', '_', file_id.removesuffix('.desktop')) + '.exe',
                arguments=quote(args),
                directory='Z:' + work.replace('/', '\\') if work.startswith('/') else '',
                description=(localized(entry, 'Comment', locales) or localized(entry, 'GenericName', locales)
                             or '').replace('\t', ' ').replace('\n', ' '),
                icon=unescape(entry.get('Icon', '')),
                source=str(path), mtime=path.stat().st_mtime_ns)
        return result

    def sync(self, remove=False):
        """Bring the shortcuts up to date, or with REMOVE take out all of them."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / 'icons').mkdir(exist_ok=True)
        old, folders = self.load()
        new = {} if remove else self.wanted()
        self.install_launcher(item['launcher'] for item in new.values())
        for file_id, item in new.items():
            item['hash'] = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
        # Remove the links that went away or moved, then the folders made for them.
        for file_id, item in old.items():
            if file_id not in new or new[file_id]['link'] != item['link']:
                (self.programs / item['link'].replace('\\', '/')).unlink(missing_ok=True)
                if file_id not in new:
                    (self.state_dir / 'icons' / f'{file_id}.ico').unlink(missing_ok=True)
        for directory in sorted(folders, key=len, reverse=True):
            path = self.programs / directory.replace('\\', '/')
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
            if not path.exists():
                folders.discard(directory)
        lines, done = [], {}
        for file_id, item in sorted(new.items()):
            link_path = self.programs / item['link'].replace('\\', '/')
            if file_id in old and old[file_id].get('hash') == item['hash'] and link_path.is_file():
                done[file_id] = item
                continue
            parts = item['link'].split('\\')[:-1]
            for i in range(1, len(parts) + 1):
                directory = '\\'.join(parts[:i])
                if not (self.programs / directory.replace('\\', '/')).exists():
                    folders.add(directory)
            icon = self.state_dir / 'icons' / f'{file_id}.ico'
            icon_location = windows_path(self.prefix, icon) if make_icon(item['icon'], icon) else ''
            lines.append('\t'.join((f'{WINDOWS_PROGRAMS}\\{item["link"]}', f'{WINDOWS_STATE}\\apps\\{item["launcher"]}',
                                    item['arguments'], item['directory'], icon_location, item['description'])))
            done[file_id] = None
        failed = set()
        if lines:
            env = dict(os.environ, WINEPREFIX=str(self.prefix))
            # Saving a link in Wine's shell32 would otherwise ask winemenubuilder
            # to make a Linux menu entry for it, which this module would read back.
            overrides = env.get('WINEDLLOVERRIDES', '')
            env['WINEDLLOVERRIDES'] = (overrides + ';' if overrides else '') + 'winemenubuilder.exe=d'
            env.pop('WINEARCH', None)
            result = subprocess.run([self.wine, str(ROOT / '.local/bridge/linux-links.exe')], env=env,
                                    input='\n'.join(lines) + '\n', capture_output=True, text=True,
                                    encoding='utf-8', timeout=120)
            for line in result.stdout.splitlines():
                if line.startswith('fail'):
                    print('linux-apps:', line, file=sys.stderr)
                    failed.add(line.split(' ', 2)[-1])
            if result.returncode and not failed:
                print('linux-apps: linux-links.exe failed', result.returncode, result.stderr[-2000:], file=sys.stderr)
                failed = {'*'}
        for file_id in list(done):
            if done[file_id] is None:
                item = new[file_id]
                ok = '*' not in failed and f'{WINDOWS_PROGRAMS}\\{item["link"]}' not in failed
                if ok:
                    done[file_id] = item
                else:
                    del done[file_id]
        self.save(done, folders)
        self.save_relaunch(done)
        return len(lines), len(old.keys() - new.keys())


IN_ATTRIB, IN_CLOSE_WRITE, IN_MOVED_FROM, IN_MOVED_TO = 0x4, 0x8, 0x40, 0x80
IN_CREATE, IN_DELETE, IN_DELETE_SELF, IN_MOVE_SELF = 0x100, 0x200, 0x400, 0x800
WATCH = IN_ATTRIB | IN_CLOSE_WRITE | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE | IN_DELETE_SELF | IN_MOVE_SELF


class Watcher:
    """inotify on the application directories, and on their nearest existing parents."""

    def __init__(self):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify')
        self.watches = {}

    def refresh(self):
        wanted = set()
        for base in data_dirs():
            apps = base / 'applications'
            if apps.is_dir():
                wanted.add(apps)
                for directory, subdirs, _ in os.walk(apps):
                    wanted.update(Path(directory) / d for d in subdirs)
            else:
                parent = apps
                while not parent.is_dir() and parent != parent.parent:
                    parent = parent.parent
                wanted.add(parent)
        for path in wanted - self.watches.keys():
            descriptor = self.libc.inotify_add_watch(self.fd, os.fsencode(path), WATCH)
            if descriptor >= 0:
                self.watches[path] = descriptor
        for path in self.watches.keys() - wanted:
            self.libc.inotify_rm_watch(self.fd, self.watches.pop(path))

    def drain(self):
        while True:
            try:
                if not os.read(self.fd, 65536):
                    return
            except BlockingIOError:
                return

    def wait(self, quiet):
        """Block until a change, then until QUIET seconds pass without another."""
        select.select([self.fd], [], [])
        self.drain()
        while select.select([self.fd], [], [], quiet)[0]:
            self.drain()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('prefix', type=Path, help='the dedicated XP prefix')
    parser.add_argument('--wine', default=os.environ.get('WINE', 'wine'))
    parser.add_argument('--watch', action='store_true', help='keep following changes until stopped')
    parser.add_argument('--remove', action='store_true', help='remove the shortcuts and folders made here')
    args = parser.parse_args()
    prefix = args.prefix.resolve(strict=True)
    if not any((prefix / marker).is_file() for marker in ('xp-shell.json', 'reactos-shell.json', 'win7-shell.json')):
        raise SystemExit('Expected a dedicated shell prefix')
    menu = Menu(prefix, args.wine)
    if args.remove:
        print(f'linux-apps: {menu.sync(remove=True)[1]} removed')
        return
    watcher = Watcher() if args.watch else None
    if watcher:
        watcher.refresh()
    while True:
        try:
            written, removed = menu.sync()
            if written or removed:
                print(f'linux-apps: {written} written, {removed} removed', flush=True)
        except (subprocess.SubprocessError, OSError) as failure:
            if not watcher:
                raise
            print('linux-apps:', failure, file=sys.stderr, flush=True)
        if not watcher:
            return
        # Package managers write several files; act once they are done.
        watcher.wait(2.0)
        watcher.refresh()


if __name__ == '__main__':
    main()
