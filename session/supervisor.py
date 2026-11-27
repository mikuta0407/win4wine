#!/usr/bin/env python3
"""Session supervisor with shell readiness checks and bounded recovery.

In the X11 session it starts bridge-wm; in the Wayland session
(xp-shell-wayland-session) win4wine's labwc is the window manager, runs
this as its session command and gives the IPC directory in WIN4WINE_IPC."""
import argparse
from collections import deque
import glob
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape
from Xlib import X, display, error

import dpi
from wineenv import SHELLS, environment

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path.home() / '.config/win4wine/session.json'
# Seconds the shut-down screen waits for the system to end the session (compositor)
POWER_OFF_WAIT = 60
IM_VARIABLES = ('XMODIFIERS', 'GTK_IM_MODULE', 'QT_IM_MODULE', 'SDL_IM_MODULE', 'CLUTTER_IM_MODULE')


class Session:
    def __init__(self, config):
        self.wine = str(Path(config['wine']).resolve(strict=True))
        self.prefix = Path(config['prefix']).resolve(strict=True)
        # The shell: XP's explorer from the user's media, or (opt-in, experimental)
        # ReactOS's explorer in a prefix made for it.
        self.shell = SHELLS.get(config.get('shell', 'xp'))
        if not self.shell:
            raise SystemExit('Unsupported shell')
        if not (self.prefix / self.shell['marker']).is_file():
            raise SystemExit(f'Expected a dedicated prefix with {self.shell["marker"]}')
        self.proxy = ROOT / '.local/bridge/proxy.exe'
        if not self.proxy.is_file():
            raise SystemExit('Build bridge-wm first')
        self.state = Path(config.get('state', str(Path.home() / '.local/state/win4wine')))
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        # The logs only grow while a session runs (Wine's debug channels and
        # restarts append). Each session starts them anew and keeps the
        # previous session's as NAME.log.1.
        for log in self.state.glob('*.log'):
            log.replace(log.with_name(log.name + '.1'))
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
        # Under win4wine's labwc the compositor is the window manager and owns the IPC directory.
        self.compositor = bool(os.environ.get('WIN4WINE_IPC') and os.environ.get('WAYLAND_DISPLAY'))
        if self.compositor:
            self.ipc = Path(os.environ['WIN4WINE_IPC']).resolve(strict=True)
        else:
            self.ipc = Path(tempfile.mkdtemp(prefix=f'win4wine-{os.getuid()}-', dir=runtime))
        # Wine's errors, with the time, but not its fixmes: every program of the
        # session inherits this and writes to the shell's or the proxy's log.
        # (+seh logged each window message call of a 32-bit process, several
        # MB within minutes.) session.json's "debug" sets other channels.
        self.env = environment(dict(os.environ, WINEDEBUG=config.get('debug', '+timestamp,fixme-all')),
                               config, self.shell)
        # Under the compositor, layered windows' translucent pixels are blended
        # by it; Wine leaves them as they are (Windows 7's Start button, patch 0123).
        if self.compositor:
            self.env['WIN4WINE_COMPOSITED'] = '1'
        # Opt-in: the proxy snaps windows to half of the screen (Win+arrows, dragging to an edge).
        if config.get('window_snap'):
            self.env['WIN4WINE_WINDOW_SNAP'] = '1'
        self.input_method = config.get('input_method')
        if self.input_method not in (None, 'fcitx5'):
            raise SystemExit('Unsupported input_method')
        if self.input_method:
            # An input method framework already chosen for this login (for
            # example by im-config from Xsession) keeps its variables.
            if not any(os.environ.get(name) for name in IM_VARIABLES):
                self.env.update(XMODIFIERS='@im=fcitx', QT_IM_MODULE='fcitx', SDL_IM_MODULE='fcitx')
                # On Wayland GTK talks to fcitx5 through the compositor (text-input-v3).
                if not self.compositor:
                    self.env.update(GTK_IM_MODULE='fcitx')
        # Linux applications take the XP shell's DPI (LogPixels) and ClearType too.
        self.dpi = dpi.prefix_dpi(self.prefix)
        self.cleartype = dpi.prefix_cleartype(self.prefix)
        self.env.update(dpi.environment(self.dpi, wayland=self.compositor))
        # Wayland: each output's scale, and the one Win32 takes as its primary monitor.
        self.outputs = config.get('outputs', {})
        self.primary = config.get('primary')
        # XP's cursors (greeter/install.sh installs them as an X cursor theme): winex11
        # shows Windows' standard cursors through the theme, Linux applications use it too.
        self.cursor_theme = config.get('cursor_theme', 'win4wine-xp')
        if self.cursor_theme and self.find_cursor_theme(self.cursor_theme):
            self.env.update(XCURSOR_THEME=self.cursor_theme)
        else:
            self.cursor_theme = None
        # Linux applications take the XP shell's UI font: MS UI Gothic on
        # Japanese XP, Tahoma on English XP (the prefix's "language").
        self.linux_font = config.get('linux_font', 'Tahoma' if self.language() == 'en' else 'MS UI Gothic')
        self.linux_menu = config.get('linux_menu', True)
        self.composite = config.get('composite', True)
        # Wine's ExitWindowsEx records log off / shut down / restart here,
        # so that the shell's exit ends the session instead of restarting it.
        self.request = self.state / 'session-request'
        self.env['WIN4WINE_SESSION_REQUEST'] = 'Z:' + str(self.request.resolve()).replace('/', '\\')
        self.power_commands = {'shutdown': config.get('shutdown_command', ['systemctl', 'poweroff']),
                               'reboot': config.get('reboot_command', ['systemctl', 'reboot'])}
        self.processes = []
        # XP's Welcome screen covers the shell's start and the session's end (greeter/xp-splash.py).
        self.welcome_screen = config.get('welcome_screen', True) and self.shell['welcome']
        self.welcome = None
        self.powering_off = False
        self.wine_envs = [self.env]
        self.logs = []
        self.stopping = False
        self.readiness_timeout = float(config.get('readiness_timeout', 30))
        self.failures = int(config.get('failures', 3))
        if self.failures < 1 or self.readiness_timeout <= 0:
            raise SystemExit('Invalid recovery limits')
        self.d = display.Display()
        dpi.set_xft(self.d, self.dpi, self.cleartype)
        self.class_atom = self.d.intern_atom('_WIN4WINE_CLASS')
        # The supervisor sleeps until a top-level window changes, a child
        # exits or a signal comes; signal handlers write to this pipe.
        self.d.screen().root.change_attributes(event_mask=X.SubstructureNotifyMask)
        self.wakeup = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self.pidfds = {}
        self.tray_window = None
        if self.linux_font:
            self.env['FONTCONFIG_FILE'] = str(self.font_config())
        self.status('starting')

    def language(self):
        """The language of the prefix's media: "language" in the XP prefix's marker
        (prefix/create.py; Japanese before English was supported), "lang" in the
        ReactOS and Windows 7 prefixes' (prefix/reactos.py, prefix/win7.py)."""
        try:
            marker = json.loads((self.prefix / self.shell['marker']).read_text())
        except (OSError, ValueError):
            return 'ja'
        return marker.get('language') or marker.get('lang') or 'ja'

    @staticmethod
    def find_cursor_theme(name):
        directories = [Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'icons',
                       Path.home() / '.icons', Path('/usr/share/icons')]
        return any((d / name / 'cursors/left_ptr').is_file() for d in directories)

    def font_config(self):
        """Prefer one family for Linux applications' sans-serif text.

        The prefix's Fonts directory is added so that the XP shell's own
        fonts, such as MS UI Gothic, serve Linux applications too. The
        system configuration, and through it the user's, still applies.
        With XP's ClearType, fonts are drawn in its RGB subpixel order."""
        directory = self.state / 'fontconfig'
        directory.mkdir(mode=0o700, exist_ok=True)
        family = escape(self.linux_font)
        aliases = ''.join(f'  <alias binding="strong"><family>{generic}</family>'
                          f'<prefer><family>{family}</family></prefer></alias>\n'
                          for generic in ('sans-serif', 'Sans', 'system-ui'))
        text = ('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n<fontconfig>\n'
                '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
                f'  <dir>{escape(str(self.prefix / "drive_c/windows/Fonts"))}</dir>\n'
                f'{aliases}'
                + ('' if self.compositor else
                   '  <match target="pattern"><edit name="dpi" mode="assign">'
                   f'<double>{self.dpi}</double></edit></match>\n')
                + ('  <match target="font"><edit name="rgba" mode="assign"><const>rgb</const></edit>'
                   '<edit name="lcdfilter" mode="assign"><const>lcddefault</const></edit></match>\n'
                   if self.cleartype else '')
                + '</fontconfig>\n')
        target = directory / 'fonts.conf'
        tmp = directory / 'fonts.tmp'
        tmp.write_text(text)
        tmp.replace(target)
        return target

    def xim_server(self, name):
        """Whether an XIM server of this name is already registered on the display."""
        servers = self.d.screen().root.get_full_property(self.d.intern_atom('XIM_SERVERS'), X.AnyPropertyType)
        wanted = '@server=' + name
        return bool(servers) and any(self.d.get_atom_name(atom) == wanted for atom in servers.value)

    def fcitx_defaults(self):
        """XP's IME shows its mode in the taskbar, not beside the caret.

        fcitx5 shows the input method's name at the caret when it changes or
        a window gets the focus; for XIM clients (Wine) it then leaves that
        window black until it hides it. The tray icon already shows the mode.
        Options that the user set in fcitx5's configuration are kept."""
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'fcitx5'
        self.fcitx_option(base / 'config', '[Behavior]',
                          {'ShowInputMethodInformation': 'False', 'showInputMethodInformationWhenFocusIn': 'False'})
        # Japanese input shows the text being converted in the text box itself
        # (on-the-spot); fcitx5 offers XIM clients only over-the-spot otherwise,
        # which shows it in the candidate window. Wine gives the caret's place.
        self.fcitx_option(base / 'conf/xim.conf', None, {'UseOnTheSpot': 'True'})

    @staticmethod
    def fcitx_option(config, section, wanted):
        """Add the options of WANTED that CONFIG does not set, under SECTION."""
        try:
            lines = config.read_text().splitlines()
        except FileNotFoundError:
            lines = []
        keys = {line.split('=', 1)[0].strip() for line in lines if '=' in line}
        missing = [f'{key}={value}' for key, value in wanted.items() if key not in keys]
        if not missing:
            return
        if section is None:
            lines = missing + lines
        elif section in lines:
            index = lines.index(section) + 1
            lines[index:index] = missing
        else:
            lines += [section, *missing]
        config.parent.mkdir(parents=True, exist_ok=True)
        temporary = config.with_name(config.name + '.win4wine')
        temporary.write_text('\n'.join(lines) + '\n')
        temporary.replace(config)

    @staticmethod
    def missing_frontends():
        """Installed Qt versions without fcitx5's input context plugin.

        Without it, Qt applications ignore QT_IM_MODULE=fcitx silently and
        take only the keyboard's own characters."""
        missing = []
        libraries = [Path(d) for d in glob.glob('/usr/lib/*-linux-gnu') + ['/usr/lib']]
        for version, core in (('qt5', 'libQt5Core.so.5'), ('qt6', 'libQt6Core.so.6')):
            if not any((d / core).exists() for d in libraries):
                continue
            plugins = [d / version / 'plugins/platforminputcontexts' for d in libraries]
            if not any(any(p.glob('libfcitx5platforminputcontextplugin*')) for p in plugins):
                missing.append(f'fcitx5-frontend-{version}')
        return missing

    def start_input_method(self):
        if not self.input_method or self.xim_server('fcitx'):
            return None  # Not configured, or started by the login already.
        missing = self.missing_frontends()
        if missing:
            with (self.state / 'fcitx5.log').open('a') as log:
                for package in missing:
                    print(f'{package} is not installed: Qt applications get no input method', file=log)
        self.fcitx_defaults()
        return self.spawn(['fcitx5'], 'fcitx5')

    def start_linux_menu(self):
        """Put the Linux applications into the Start menu, then follow changes.

        The first pass ends before the shell starts, so that its Start menu
        has them from the beginning. A failure only leaves the menu as it was."""
        menu = [sys.executable, str(ROOT / 'session/linux_apps.py'), str(self.prefix), '--wine', self.wine]
        with (self.state / 'linux-apps.log').open('ab') as log:
            log.write(f'\n--- sync {time.time()} ---\n'.encode())
            log.flush()
            try:
                subprocess.run(menu, env=self.env, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False)
            except subprocess.TimeoutExpired:
                print('Linux menu sync timed out; see linux-apps.log', file=sys.stderr)
        self.pin_recent()
        # Wine's desktop process keeps the environment of the program that
        # started it; let the shell start it with the session's own.
        self.stop_wine()
        self.spawn([*menu, '--watch'], 'linux-apps')

    def play_sound(self, event):
        """An event of XP's sound scheme (the XP shell only), as XP plays it."""
        player = ROOT / '.local/bridge/playsound.exe'
        if self.shell['marker'] != 'xp-shell.json' or not player.is_file():
            return None
        return self.spawn([self.wine, str(player), event], 'sounds')

    def keyboard(self):
        """The session's keyboard layout from XP's input languages (Wine patch
        0043), or the Linux system's while the prefix has none."""
        if self.shell['marker'] != 'xp-shell.json':
            return
        with (self.state / 'keyboard.log').open('ab') as log:
            subprocess.run([sys.executable, str(ROOT / 'session/keyboard.py'), 'apply', str(self.prefix)],
                           env=self.env, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=False)

    def keyboard_watch(self):
        """Follow the input languages that XP's Regional and Language Options set."""
        watch = ROOT / '.local/bridge/keyboard-watch.exe'
        if self.shell['marker'] == 'xp-shell.json' and watch.is_file():
            self.spawn([self.wine, str(watch), str(ROOT / 'session/keyboard.py')], 'keyboard')

    def pin_recent(self):
        """Pin the most used programs in the Start menu's left column.

        XP's own list of them stays empty under Wine; XP Explorer's
        startmenu.exe (prefix/extras.py) counts them from XP's usage data
        before the shell starts, as XP Explorer's xpstart.exe does."""
        helper = self.prefix / 'drive_c/xp/bin/startmenu.exe'
        if self.shell['marker'] != 'xp-shell.json' or not helper.is_file():
            return
        with (self.state / 'startmenu.log').open('ab') as log:
            try:
                subprocess.run([self.wine, r'C:\xp\bin\startmenu.exe', 'recent'], env=self.env, stdout=log,
                               stderr=subprocess.STDOUT, timeout=60, check=False)
            except subprocess.TimeoutExpired:
                print('startmenu.exe recent timed out', file=sys.stderr)

    def status(self, state, **extra):
        record = dict(state=state, time=time.time(), **extra)
        target = self.state / 'status.json'
        tmp = self.state / 'status.tmp'
        tmp.write_text(json.dumps(record, indent=2) + '\n')
        tmp.replace(target)

    def spawn(self, args, name, env=None):
        log = (self.state / f'{name}.log').open('ab', buffering=0)
        log.write(f'\n--- start {time.time()} ---\n'.encode())
        process = subprocess.Popen(args, env=env or self.env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        self.logs.append(log)
        self.processes.append(process)
        return process

    def xp_assets(self):
        """The XP files the prefix was made from (xp-shell.json), or this checkout's."""
        try:
            return Path(json.loads((self.prefix / 'xp-shell.json').read_text())['assets'])
        except (OSError, ValueError, KeyError):
            return ROOT / '.local/assets'

    def show_welcome(self, mode):
        if not self.welcome_screen:
            return
        self.hide_welcome()
        log = (self.state / 'welcome.log').open('ab', buffering=0)
        self.logs.append(log)
        extra = ['--assets', str(self.xp_assets())] if self.welcome_screen == 'greeter/xp-splash.py' else []
        self.welcome = subprocess.Popen([sys.executable, str(ROOT / self.welcome_screen), mode,
                                         '--dpi', str(self.dpi), *extra],
                                        stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)

    def wait_welcome(self, timeout=5):
        """Wait until the screen is up (it names its window), so that the session's
        end, shut down at once by a fast machine, does not take it away unseen."""
        end = time.monotonic() + timeout
        while self.welcome and self.welcome.poll() is None and time.monotonic() < end:
            try:
                for w in self.d.screen().root.query_tree().children:
                    if w.get_wm_name() == 'win4wine-splash' and w.get_attributes().map_state == X.IsViewable:
                        return
            except error.XError:
                pass
            time.sleep(0.05)

    def tell_welcome(self, word):
        """Change the line of the log-off screen ('saving', 'shutdown')."""
        if self.welcome and self.welcome.poll() is None:
            try:
                self.welcome.stdin.write(word.encode() + b'\n')
                self.welcome.stdin.flush()
            except OSError:
                pass

    def hide_welcome(self):
        if self.welcome:
            self.halt(self.welcome)
            self.welcome.stdin.close()
            self.welcome = None

    def tray(self):
        # The taskbar found last time is checked first; a full search asks
        # the X server about every top-level window.
        windows = self.d.screen().root.query_tree().children if self.tray_window is None else [self.tray_window]
        for w in windows:
            try:
                p = w.get_full_property(self.class_atom, X.AnyPropertyType)
                if p and bytes(p.value).rstrip(b'\0').lower() == b'shell_traywnd' and w.get_attributes().map_state == X.IsViewable:
                    self.tray_window = w
                    geometry = w.get_geometry()
                    # Along the screen's edge it is docked to: Windows 7's taskbar
                    # properties (and dragging an unlocked taskbar) dock it left or
                    # right too, where it is narrow and tall.
                    return (max(geometry.width, geometry.height) >= 200 and
                            min(geometry.width, geometry.height) >= 20)
            except error.XError:
                pass
        if self.tray_window is not None:
            self.tray_window = None
            return self.tray()
        return False

    def wait(self, processes, timeout=None):
        """Sleep until a window changes, one of the processes exits, a signal comes or the timeout passes."""
        fds = [self.d.fileno(), self.wakeup[0]]
        for process in processes:
            if process and process.poll() is None:
                if process not in self.pidfds:
                    self.pidfds[process] = os.pidfd_open(process.pid)
                fds.append(self.pidfds[process])
        for process in [p for p in self.pidfds if p.poll() is not None]:
            os.close(self.pidfds.pop(process))
        while True:
            ready = []
            if not self.d.pending_events() and not self.stopping:
                ready = select.select(fds, [], [], timeout)[0]
            try:
                os.read(self.wakeup[0], 512)
            except BlockingIOError:
                pass
            moves = True
            while self.d.pending_events():
                moves = self.d.next_event().type == X.ConfigureNotify and moves
            # Without a timeout the taskbar is up: windows that only move
            # or change size (each step of a drag) need no check.
            if timeout is not None or not moves or self.stopping or set(ready) - {self.d.fileno()}:
                return

    def halt(self, *processes):
        """End the processes' groups: SIGTERM together, then SIGKILL after three seconds.

        At the end of a login the display manager kills what is left soon;
        waiting for each group in turn could leave the later ones running."""
        running = []
        for process in processes:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    running.append(process)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 3
        for process in running:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
            try:
                # Children that ignore SIGTERM, such as Wine's start.exe
                # waiting for its program, go with the group.
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def stop_wine(self):
        server = Path(self.wine).with_name('wineserver')
        for env in self.wine_envs:
            subprocess.run([str(server), '-k'], env=env, timeout=10, check=False)
            subprocess.run([str(server), '-w'], env=env, timeout=10, check=False)

    def configure_outputs(self):
        """Wayland: the outputs' scale and place (wlr-randr), and Win32's primary monitor.

        The compositor puts the primary output first for Xwayland and
        makes it RandR's primary; Wine puts Win32's 0,0 at its top-left.
        Without "primary" in the configuration it is the leftmost output."""
        if self.primary:
            temporary = self.ipc / 'primary.tmp'
            temporary.write_text(str(self.primary) + '\n')
            temporary.replace(self.ipc / 'primary')
        names = []
        try:
            listing = subprocess.run(['wlr-randr', '--json'], env=self.env, capture_output=True,
                                     text=True, timeout=10, check=True).stdout
            names = [o['name'] for o in json.loads(listing) if o.get('enabled', True)]
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            print('wlr-randr is not available: outputs keep their settings', file=sys.stderr)
        command = ['wlr-randr']
        for name, settings in self.outputs.items():
            if name not in names:
                continue
            # One call for all outputs: one at a time, the compositor would
            # move the others out of the way in between.
            command += ['--output', name]
            if 'mode' in settings:
                command += ['--mode', str(settings['mode'])]
            if 'custom_mode' in settings:
                command += ['--custom-mode', str(settings['custom_mode'])]
            if 'position' in settings:
                command += ['--pos', str(settings['position'])]
            if 'scale' in settings:
                command += ['--scale', str(settings['scale'])]
        if len(command) > 1:
            subprocess.run(command, env=self.env, timeout=10, check=False)

    def run(self):
        if self.compositor:
            # win4wine's labwc manages the windows; it ends the session when this exits.
            wm = None
            self.configure_outputs()
        self.show_welcome('logon')
        if not self.compositor:
            wm = self.spawn(['python3', str(ROOT / 'bridge-wm/wm.py'), '--ipc', str(self.ipc)] +
                            ([] if self.composite else ['--no-composite']), 'wm')
            time.sleep(.5)
            if wm.poll() is not None:
                raise RuntimeError('WM failed; see wm.log')
        if self.cursor_theme and shutil.which('xsetroot') and not self.compositor:
            # The WM's root cursor comes from the core cursor font; xsetroot takes the theme's.
            subprocess.run(['xsetroot', '-cursor_name', 'left_ptr'], env=self.env, check=False)
        # Linux tray icons (StatusNotifierItem) reach the XP notification
        # area through the proxy; the input method shows its mode there.
        self.spawn(['python3', str(ROOT / 'bridge-wm/tray.py'), '--ipc', str(self.ipc)], 'tray')
        im = self.start_input_method()
        im_restarts = deque()
        # Install only the shell family in this dedicated prefix. Runtime overrides select them.
        script, *command = self.shell['stage']
        subprocess.run(['python3', str(ROOT / script), *command, str(self.prefix), '--wine', self.wine], check=True)
        self.keyboard()
        if self.linux_menu:
            self.start_linux_menu()
        else:
            self.pin_recent()
            self.stop_wine()
        crashes = deque()
        attempt = 0
        while not self.stopping:
            if wm and wm.poll() is not None:
                raise RuntimeError('WM exited during session')
            attempt += 1
            self.request.unlink(missing_ok=True)
            ipc_win = 'Z:' + str(self.ipc).replace('/', '\\')
            proxy = self.spawn([self.wine, str(self.proxy), ipc_win], 'proxy')
            self.keyboard_watch()
            shell = self.spawn([self.wine, self.shell['command']], 'xp-shell')
            started = time.monotonic()
            ready = False
            while not self.stopping:
                if wm and wm.poll() is not None:
                    raise RuntimeError('WM exited during session')
                if im and im.poll() is not None:
                    im = self.restart_input_method(im_restarts)
                has_tray = self.tray()
                if has_tray and not ready:
                    ready = True
                    self.status('xp-shell', attempt=attempt)
                    self.hide_welcome()
                    if attempt == 1:
                        self.play_sound('SystemStart')
                if ready and not has_tray:
                    break
                if not ready and (time.monotonic()-started > self.readiness_timeout or shell.poll() is not None):
                    break
                if proxy.poll() is not None:
                    break
                # While the shell starts, its taskbar may get its class or
                # size without an event this client sees; check every second.
                self.wait((wm, im, proxy, shell), None if ready else 1)
            if self.stopping:
                break
            if self.end_requested(shell):
                return
            self.halt(shell)
            self.halt(proxy)
            # Release the prior desktop manager too; environment is inherited at its creation.
            self.stop_wine()
            now = time.monotonic()
            crashes.append(now)
            while crashes and now-crashes[0] > 120:
                crashes.popleft()
            self.status('retry', attempt=attempt, failures=len(crashes))
            if len(crashes) >= self.failures:
                self.fallback(wm)
                return
            time.sleep(1)

    def restart_input_method(self, restarts):
        """Restart an input method that exited, at most three times in two minutes."""
        now = time.monotonic()
        restarts.append(now)
        while restarts and now-restarts[0] > 120:
            restarts.popleft()
        if len(restarts) > 3:
            print('input method keeps exiting; see fcitx5.log', file=sys.stderr)
            return None
        return self.start_input_method()

    def end_requested(self, shell):
        """Finish the session after an XP log off, shut down or restart."""
        try:
            request = self.request.read_text().strip()
        except OSError:
            return False
        if request not in ('logoff', 'shutdown', 'reboot'):
            return False
        self.show_welcome('logoff')
        self.wait_welcome()
        sound = self.play_sound('WindowsLogoff')
        try:
            shell.wait(timeout=30)  # let wineboot end the applications first
        except subprocess.TimeoutExpired:
            pass
        if sound:
            try:
                sound.wait(timeout=10)  # XP's log off sound ends before the session
            except subprocess.TimeoutExpired:
                pass
        self.status('ending', request=request)
        self.tell_welcome('saving')
        self.stopping = True
        command = self.power_commands.get(request)
        if command:
            self.tell_welcome('shutdown')
            time.sleep(0.5)  # for the screen to show the line
            self.powering_off = True
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        return True

    def fallback(self, wm):
        self.hide_welcome()
        env = dict(self.env)
        env.pop('WIN4WINE_EXTERNAL_SHELL', None)
        env.pop('WIN4WINE_SHELL', None)
        # Native shell COM registrations can also affect builtin explorer. Keep
        # recovery independent of both the XP files and their registry entries.
        env['WINEPREFIX'] = str(self.prefix / 'recovery')
        env['WINEDLLOVERRIDES'] = 'explorer,shell32,shdocvw,browseui,shlwapi,comctl32,uxtheme=b;mscoree,mshtml='
        self.wine_envs.append(env)
        self.status('fallback')
        # A Wine desktop plus file browser and a native terminal gives an escape route.
        home = 'Z:' + str(Path.home()).replace('/', '\\')
        fallback = self.spawn([self.wine, 'explorer', home], 'fallback', env)
        terminal = self.spawn(['xterm', '-title', 'XP shell recovery'], 'recovery-terminal', env)
        while not self.stopping:
            if wm and wm.poll() is not None:
                raise RuntimeError('WM exited during fallback')
            if fallback.poll() is not None and terminal.poll() is not None:
                break
            self.wait((wm, fallback, terminal))

    def close(self):
        self.stopping = True
        self.halt(*reversed(self.processes))
        try:
            self.stop_wine()
            if self.powering_off and self.compositor and self.welcome and self.welcome.poll() is None:
                # The compositor ends with this process, and the shut-down screen with it
                # (on X11 it stays as the root window's background): keep it until the
                # system ends the session, as Windows shows it until the power goes off.
                select.select([self.wakeup[0]], [], [], POWER_OFF_WAIT)
        finally:
            # The log-off screen leaves its last image as the root window's background.
            self.hide_welcome()
            for f in self.logs:
                f.close()
            try:
                self.d.close()
            except (error.ConnectionClosedError, OSError):
                pass  # The X server ended first, as when the display manager restarts.
            shutil.rmtree(self.ipc, ignore_errors=True)
            self.status('stopped')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    session = Session(json.loads(args.config.read_text()))
    signal.set_wakeup_fd(session.wakeup[1])
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: setattr(session, 'stopping', True))
    try:
        session.run()
    finally:
        session.close()
