#!/usr/bin/env python3
"""A LightDM greeter that looks like ReactOS's logon screen.

LightDM and PAM log the user in; this program only draws ReactOS's msgina
dialogs (greeter/rosdialog.py) from ReactOS's files that greeter/install.sh
copies: "Press Ctrl-Alt-Delete to begin", then the Logon dialog (user name,
password, Shut Down). When those files, GTK or LightDM's GObject bindings
are missing, it starts the usual greeter instead
(/etc/win4wine/reactos-greeter.json "fallback", lightdm-gtk-greeter by default).
"""
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CARET_BLINK = 530      # ms, the default caret blink time


def log(message):
    print(f'reactos-greeter: {message}', file=sys.stderr, flush=True)


def fallback(reason):
    """Hand the greeter's place to the usual greeter (before talking to LightDM)."""
    try:
        name = json.loads(Path('/etc/win4wine/reactos-greeter.json').read_text()).get('fallback')
    except (OSError, ValueError):
        name = None
    name = name or 'lightdm-gtk-greeter'
    command = [name]
    try:
        for line in (Path('/usr/share/xgreeters') / f'{name}.desktop').read_text().splitlines():
            if line.startswith('Exec='):
                command = line[5:].split()
                break
    except OSError:
        pass
    search = os.pathsep.join((os.environ.get('PATH', ''), '/usr/local/sbin', '/usr/sbin', '/sbin'))
    program = shutil.which(command[0], path=search) or command[0]
    log(f'{reason}; starting {" ".join(command)}')
    os.execv(program, command)


class Greeter:
    def __init__(self, config, assets):
        import rosdialog
        self.d = rosdialog
        self.config = config
        self.lightdm = LightDM.Greeter()
        self.lightdm.connect('show-prompt', self.on_prompt)
        self.lightdm.connect('show-message', self.on_message)
        self.lightdm.connect('authentication-complete', self.on_complete)
        self.lightdm.connect_to_daemon_sync()
        users = LightDM.UserList.get_instance().get_users()
        hint = self.lightdm.get_select_user_hint() or (users[0].get_name() if users else '')
        self.screen = rosdialog.Screen(assets, hint, LightDM.get_hostname() or '')
        if not config.get('ctrl_alt_del', True):
            self.screen.page = 'logon'
        if LightDM.get_can_suspend():
            self.screen.actions.append((rosdialog.IDS_SLEEP, rosdialog.IDS_SLEEP_DESC))
        self.waiting = False        # a password was given and LightDM checks it

        root = Gdk.get_default_root_window()
        self.width, self.height = root.get_width(), root.get_height()
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_app_paintable(True)
        self.window.move(0, 0)
        self.window.set_default_size(self.width, self.height)
        self.area = Gtk.DrawingArea()
        self.area.set_can_focus(True)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                             Gdk.EventMask.KEY_PRESS_MASK)
        self.area.connect('draw', self.on_draw)
        self.area.connect('button-press-event', self.on_press)
        self.area.connect('button-release-event', self.on_release)
        self.area.connect('key-press-event', self.on_key)
        self.window.add(self.area)
        self.frame = None
        self.window.show_all()
        self.window.get_window().set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default'))
        self.window.get_window().focus(Gdk.CURRENT_TIME)
        self.area.grab_focus()
        GLib.timeout_add(CARET_BLINK, self.blink)

    def refresh(self):
        self.frame = None
        self.area.queue_draw()

    def on_draw(self, area, cr):
        if self.frame is None:
            self.frame = self.screen.render(self.width, self.height)
        cr.set_source_surface(self.frame, 0, 0)
        cr.paint()
        return True

    def blink(self):
        s = self.screen
        if s.page == 'logon' and s.focus in (self.d.IDC_USERNAME, self.d.IDC_PASSWORD) and not s.message:
            s.caret = not s.caret
            self.refresh()
        return True

    # Authentication -------------------------------------------------

    def log_on(self):
        s = self.screen
        if not s.user or self.waiting:
            return
        self.waiting = True
        if self.lightdm.get_in_authentication():
            self.lightdm.cancel_authentication()
        self.lightdm.authenticate(s.user)

    def on_prompt(self, greeter, text, kind):
        if self.waiting and kind == LightDM.PromptType.SECRET:
            self.lightdm.respond(self.screen.password)
        else:
            log(f'unexpected prompt {text!r}')
            self.lightdm.cancel_authentication()

    def on_message(self, greeter, text, kind):
        log(f'message: {text}')

    def on_complete(self, greeter):
        if not self.waiting:
            return
        self.waiting = False
        s = self.screen
        if self.lightdm.get_is_authenticated():
            self.start_session()
            return
        # msgina: "The system could not log you on..." in a message box; the password is cleared.
        s.message = (self.screen.assets.string(self.d.IDS_LOGONTITLE),
                     self.screen.assets.string(self.d.IDS_WRONG))
        s.password = ''
        s.focus = self.d.IDC_PASSWORD
        self.refresh()

    def start_session(self):
        try:
            from Xlib import display
            import xdraw
            d = display.Display()
            xdraw.set_root_background(d, self.screen.background(self.width, self.height))
            d.close()
        except Exception:
            traceback.print_exc()
        user = LightDM.UserList.get_instance().get_user_by_name(self.screen.user)
        import welcome
        session = welcome.login_session(user.get_session() if user else None,
                                        {s.get_key() for s in LightDM.get_sessions()},
                                        self.lightdm.get_default_session_hint())
        try:
            self.lightdm.start_session_sync(session)
        except GLib.Error as e:
            log(f'cannot start session {session}: {e.message}')

    # Input ----------------------------------------------------------

    def activate(self, ident):
        s, d = self.screen, self.d
        if s.page == 'logon':
            if ident == 1:
                self.log_on()
            elif ident == 2:
                s.password = ''
                s.page = 'welcome' if self.config.get('ctrl_alt_del', True) else 'logon'
                s.focus = d.IDC_PASSWORD if s.user else d.IDC_USERNAME
            elif ident == d.IDC_SHUTDOWN:
                s.page, s.focus, s.action = 'shutdown', d.IDC_ACTION, 0
        elif s.page == 'shutdown':
            if ident == 1:
                action = s.actions[s.action][0]
                if action == d.IDS_SHUTDOWN:
                    LightDM.shutdown()
                elif action == d.IDS_RESTART:
                    LightDM.restart()
                else:
                    LightDM.suspend()
                    s.page, s.focus = 'logon', d.IDC_PASSWORD
            elif ident == 2:
                s.page, s.focus = 'logon', d.IDC_SHUTDOWN
        self.refresh()

    def on_press(self, area, event):
        s = self.screen
        if event.button != 1 or s.message or self.waiting or s.page == 'welcome':
            return True
        target = s.hit(self.width, self.height, event.x, event.y)
        if target is not None:
            s.focus = target
            if target not in (self.d.IDC_USERNAME, self.d.IDC_PASSWORD, self.d.IDC_DOMAIN, self.d.IDC_ACTION):
                s.pressed = target
        self.refresh()
        return True

    def on_release(self, area, event):
        s = self.screen
        if event.button != 1 or s.pressed is None:
            return True
        pressed, s.pressed = s.pressed, None
        if s.hit(self.width, self.height, event.x, event.y) == pressed:
            self.activate(pressed)
        self.refresh()
        return True

    def on_key(self, area, event):
        s, d = self.screen, self.d
        key = Gdk.keyval_name(event.keyval) or ''
        state = event.state
        ctrl, alt = state & Gdk.ModifierType.CONTROL_MASK, state & Gdk.ModifierType.MOD1_MASK
        if self.waiting:
            return True
        if s.message:
            if key in ('Return', 'KP_Enter', 'space', 'Escape'):
                s.message = None
                self.refresh()
            return True
        if s.page == 'welcome':
            if ctrl and alt and key in ('Delete', 'KP_Delete'):
                s.page = 'logon'
                s.focus = d.IDC_PASSWORD if s.user else d.IDC_USERNAME
                self.refresh()
            return True
        order = s.tab_order()
        if key in ('Tab', 'ISO_Left_Tab'):
            step = -1 if key == 'ISO_Left_Tab' or state & Gdk.ModifierType.SHIFT_MASK else 1
            current = order.index(s.focus) if s.focus in order else 0
            s.focus = order[(current + step) % len(order)]
        elif key in ('Return', 'KP_Enter'):
            # The default button (OK), unless another button has the focus.
            self.activate(s.focus if s.focus in (2, d.IDC_SHUTDOWN) else 1)
            return True
        elif key == 'Escape':
            self.activate(2)
            return True
        elif key == 'space' and s.focus in (1, 2, d.IDC_SHUTDOWN):
            self.activate(s.focus)
            return True
        elif s.page == 'shutdown' and key in ('Up', 'Down') and s.focus == d.IDC_ACTION:
            s.action = max(0, min(len(s.actions) - 1, s.action + (1 if key == 'Down' else -1)))
        elif s.page == 'logon' and alt and key.lower() == 's':
            self.activate(d.IDC_SHUTDOWN)
            return True
        elif s.page == 'logon' and s.focus in (d.IDC_USERNAME, d.IDC_PASSWORD):
            field = 'user' if s.focus == d.IDC_USERNAME else 'password'
            value = getattr(s, field)
            if key == 'BackSpace':
                value = value[:-1]
            else:
                code = Gdk.keyval_to_unicode(event.keyval)
                character = chr(code) if code else ''
                if character and character.isprintable() and not ctrl and len(value) < 127:
                    value += character
            setattr(s, field, value)
            s.caret = True
        self.refresh()
        return True


def main():
    try:
        import rosdialog
        cache = Path(os.environ.get('HOME') or '/var/lib/lightdm') / '.cache/reactos-greeter'
        config, assets = rosdialog.setup(cache)
        theme = config.get('cursor_theme', 'win4wine-reactos')
        if theme and (Path('/usr/share/icons') / theme / 'cursors/left_ptr').is_file():
            os.environ.update(XCURSOR_THEME=theme, XCURSOR_SIZE='32')
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('LightDM', '1')
        from gi.repository import Gdk as gdk, GLib as glib, Gtk as gtk, LightDM as lightdm
        globals().update(Gdk=gdk, GLib=glib, Gtk=gtk, LightDM=lightdm)
    except Exception as e:
        traceback.print_exc()
        fallback(f'the logon screen is not available ({e})')
    try:
        Greeter(config, assets)
    except Exception as e:
        traceback.print_exc()
        fallback(f'cannot start ({e})')
    Gtk.main()


if __name__ == '__main__':
    main()
