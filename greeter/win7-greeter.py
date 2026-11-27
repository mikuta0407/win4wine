#!/usr/bin/env python3
"""A LightDM greeter that looks like Windows 7's logon screen.

LightDM and PAM log the user in; this program only draws LogonUI's screen
(greeter/w7logon.py) from the Windows 7 files that greeter/install.sh --win7
copies: the users to choose from when there are several, the chosen user's
tile and password field (with Switch User back to the list), the Ease of
Access button, the edition's name and the shutdown button with its menu. When those files, GTK or
LightDM's GObject bindings are missing, it starts the usual greeter instead
(/etc/win4wine/win7-greeter.json "fallback", lightdm-gtk-greeter by default).
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
OPTIONS = ('accessibility', 'shutdown', 'more')


def log(message):
    print(f'win7-greeter: {message}', file=sys.stderr, flush=True)


def fallback(reason):
    """Hand the greeter's place to the usual greeter (before talking to LightDM)."""
    try:
        name = json.loads(Path('/etc/win4wine/win7-greeter.json').read_text()).get('fallback')
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
        import w7logon
        self.w = w7logon
        self.config = config
        self.lightdm = LightDM.Greeter()
        self.lightdm.connect('show-prompt', self.on_prompt)
        self.lightdm.connect('show-message', self.on_message)
        self.lightdm.connect('authentication-complete', self.on_complete)
        self.lightdm.connect_to_daemon_sync()
        # LogonUI lists the users in name order; LightDM's hint (a user to switch
        # to) goes to that user's tile directly.
        users = sorted(LightDM.UserList.get_instance().get_users(), key=lambda u: u.get_name().casefold())
        listed = [(u.get_name(), u.get_image()) for u in users]
        hint = self.lightdm.get_select_user_hint()
        name = hint if hint in dict(listed) else ''
        self.screen = w7logon.Screen(assets, name, dict(listed).get(name), users=listed or None)
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
                             Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.area.connect('draw', self.on_draw)
        self.area.connect('button-press-event', self.on_press)
        self.area.connect('button-release-event', self.on_release)
        self.area.connect('motion-notify-event', self.on_motion)
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
        if s.focus == 'password' and not s.message and not s.menu:
            s.caret = not s.caret
            self.refresh()
        return True

    # Authentication -------------------------------------------------

    def log_on(self):
        s = self.screen
        if not s.user or self.waiting:
            return
        self.waiting = s.busy = True
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
        # LogonUI: "The user name or password is incorrect." with OK, the password cleared.
        s.busy = False
        s.message = s.assets.string(self.w.IDS_WRONG)
        s.password = ''
        s.focus = 'ok'
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
            self.screen.busy = False
            self.refresh()

    # Input ----------------------------------------------------------

    def open_menu(self):
        s, w = self.screen, self.w
        a = s.assets
        items = [('restart', a.string(w.IDS_RESTART)), None]
        if LightDM.get_can_suspend():
            items.append(('suspend', a.string(w.IDS_SLEEP)))
        if LightDM.get_can_hibernate():
            items.append(('hibernate', a.string(w.IDS_HIBERNATE)))
        items.append(('shutdown', a.string(w.IDS_POWER_OFF)))
        s.menu, s.menu_hover = items, None

    def run_action(self, action):
        self.screen.menu = None
        try:
            {'restart': LightDM.restart, 'suspend': LightDM.suspend, 'hibernate': LightDM.hibernate,
             'shutdown': LightDM.shutdown}[action]()
        except GLib.Error as e:
            log(f'{action}: {e.message}')

    def focus_order(self):
        s = self.screen
        if s.listing:
            return ('tiles',) + OPTIONS
        return ('password', 'submit') + (('switch',) if len(s.users) > 1 else ()) + OPTIONS

    def cancel(self):
        if self.lightdm.get_in_authentication():
            self.lightdm.cancel_authentication()

    def activate(self, target):
        s = self.screen
        if target.startswith('tile:'):
            s.choose(int(target[5:]))
        elif target == 'tiles':
            s.choose(s.selected)
        elif target == 'switch':
            self.cancel()
            s.back_to_list()
        elif target == 'submit':
            self.log_on()
        elif target == 'ok':
            s.message = None
            s.focus = 'password'
        elif target == 'shutdown':
            self.run_action('shutdown')
        elif target == 'more':
            if s.menu:
                s.menu = None
            else:
                self.open_menu()
        # accessibility: Windows 7 opens its Ease of Access options; there are none here
        self.refresh()

    def on_motion(self, area, event):
        s = self.screen
        if s.menu:
            hover = s.menu_hit(self.width, self.height, event.x, event.y)
            if hover != s.menu_hover:
                s.menu_hover = hover
                self.refresh()
            return True
        hover = s.hit(self.width, self.height, event.x, event.y)
        if hover != s.hover:
            s.hover = hover
            self.refresh()
        return True

    def on_press(self, area, event):
        s = self.screen
        if event.button != 1 or self.waiting:
            return True
        if s.menu:
            index = s.menu_hit(self.width, self.height, event.x, event.y)
            if index is not None:
                self.run_action(s.menu[index][0])
            elif s.hit(self.width, self.height, event.x, event.y) != 'more':
                s.menu = None
            self.refresh()
            if index is not None or s.menu is None:
                return True
        target = s.hit(self.width, self.height, event.x, event.y)
        if target is not None and target.startswith('tile:'):
            s.focus, s.selected, s.pressed = 'tiles', int(target[5:]), target
        elif target is not None:
            s.focus = target if target != 'tile' else 'password'
            if target != 'password':
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
        s = self.screen
        key = Gdk.keyval_name(event.keyval) or ''
        state = event.state
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if self.waiting:
            return True
        if s.menu:
            choices = [i for i, item in enumerate(s.menu) if item is not None]
            if key == 'Escape':
                s.menu = None
            elif key in ('Up', 'Down'):
                current = choices.index(s.menu_hover) if s.menu_hover in choices else -1
                step = 1 if key == 'Down' else -1
                s.menu_hover = choices[(current + step) % len(choices)] if current >= 0 else choices[
                    0 if step > 0 else -1]
            elif key in ('Return', 'KP_Enter', 'space') and s.menu_hover is not None:
                self.run_action(s.menu[s.menu_hover][0])
            self.refresh()
            return True
        if s.message:
            if key in ('Return', 'KP_Enter', 'space', 'Escape'):
                self.activate('ok')
            return True
        order = self.focus_order()
        if key in ('Tab', 'ISO_Left_Tab'):
            step = -1 if key == 'ISO_Left_Tab' or state & Gdk.ModifierType.SHIFT_MASK else 1
            current = order.index(s.focus) if s.focus in order else 0
            s.focus = order[(current + step) % len(order)]
        elif s.listing and s.focus == 'tiles' and key in ('Left', 'Right', 'Up', 'Down', 'Home', 'End'):
            last = len(s.users) - 1
            s.selected = {'Left': max(0, s.selected - 1), 'Up': max(0, s.selected - 1), 'Home': 0,
                          'Right': min(last, s.selected + 1), 'Down': min(last, s.selected + 1),
                          'End': last}[key]
        elif s.listing and s.focus == 'tiles' and key in ('Return', 'KP_Enter', 'space'):
            self.activate('tiles')
            return True
        elif 'switch' in order and (key == 'Escape' or (state & Gdk.ModifierType.MOD1_MASK and key.lower() == 'w')):
            # Esc and Switch User's access key: back to the list, the password dropped
            self.activate('switch')
            return True
        elif key in ('Return', 'KP_Enter'):
            self.activate('submit' if s.focus in ('password', 'submit') else s.focus)
            return True
        elif key == 'space' and s.focus != 'password':
            self.activate(s.focus)
            return True
        elif key == 'Escape':
            s.password = ''
        elif s.focus == 'password':
            if key == 'BackSpace':
                s.password = s.password[:-1]
            else:
                code = Gdk.keyval_to_unicode(event.keyval)
                character = chr(code) if code else ''
                if character and character.isprintable() and not ctrl and len(s.password) < 127:
                    s.password += character
            s.caret = True
        self.refresh()
        return True


def main():
    try:
        import w7logon
        cache = Path(os.environ.get('HOME') or '/var/lib/lightdm') / '.cache/win7-greeter'
        config, assets = w7logon.setup(cache)
        theme = config.get('cursor_theme', 'win4wine-win7')
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
