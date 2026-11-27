# Installation

[日本語](../../INSTALL.md) · **English**

> [!WARNING]
> - Obtain the Windows XP ISO yourself, and use this at your own risk (see [Caution in the README](README.en.md#caution)).
> - This is an experimental project. It has only been tested on a **freshly installed Debian 13** set up with `scripts/setup.sh`;
>   installing it on a system already in use has not been tried. The script installs packages and may change LightDM's
>   settings (see "2. What the script does"). A virtual machine or a spare machine is recommended.

## Requirements

- A **Debian 13 (trixie) amd64** machine (real or virtual). No desktop environment is needed.
  On Arch Linux and its derivatives (CachyOS, ...), `scripts/setup.sh` installs the same packages with pacman
  and keeps the display manager in use (untested beyond the package step). The checkout path must not contain spaces.
- A **Windows XP Professional SP3 (x86) ISO** (or an XP Windows directory), **Japanese or English**; which one is
  detected from the ISO.
- Network access (packages and the Wine source) and **about 40 GB of free space** (Wine's source and build).
- A user who can use sudo.

## 1. Set everything up

Run it as the user who will use the XP shell (not as root). It uses sudo for packages and system files.

```sh
git clone https://github.com/mikuta0407/win4wine.git ~/win4wine
cd ~/win4wine
scripts/setup.sh --media /path/to/WindowsXPSP3.iso --greeter
```

| Option | Meaning |
|---|---|
| `--media PATH` | the XP ISO or Windows directory (required); with `--shell win7`, a Windows 7 SP1 x64 ISO |
| `--greeter` | make the login screen XP's Welcome screen (LightDM becomes the display manager) |
| `--no-greeter` | keep the current login screen (default); only XP's cursors are installed |
| `--theme luna\|classic` | `luna` (default: XP's "Windows XP" theme, the XP-style Start menu, the Bliss wallpaper) or `classic` (XP's "Windows Classic" theme, the classic Start menu, no wallpaper) |
| `--dpi N` | the screen's DPI (XP's "DPI setting"): 96 (normal), 120 (large) or any value from 19 to 480; for the XP shell, the Linux applications in its session and the Welcome screen |
| `--wayland` | also install the Wayland session "XP Shell (Wine, Wayland)" (builds labwc and wlroots): a scale per monitor, scales such as 125% or 150%, XP frames for Wayland applications; with `--greeter` it becomes the Welcome screen's default session. **Even more experimental than the X11 session** (tested less, with known limits; [docs/wayland.md](../../docs/wayland.md)) |
| `--wine-install DIR` | use a Wine built on another Debian 13 machine (a copy of its `.local/wine-install`) instead of building it here |
| `--jobs N` | parallel jobs for the Wine build (default: the number of CPUs) |
| `--no-shadowfb` | on a virtual machine, leave the way X draws as it is (step 8 of "2. What the script does") |
| `--shell reactos` | set up ReactOS's shell instead of XP's (no `--media`; see "The ReactOS shell" below) |
| `--shell win7` | set up Windows 7's shell (experimental); `--media` is a Windows 7 ISO (see "The Windows 7 shell" below) |
| `--lang ja\|en` | the ReactOS shell's language (default: `ja` if the current locale is Japanese, else `en`) |

If it fails, just run it again: finished steps are skipped. Everything it builds stays in `.local/` of this checkout.

## 2. What the script does

1. Installs packages (Wine's build dependencies, Xorg, python3-xlib, fcitx5 + Mozc, …), and LightDM if there is no display manager.
2. Fetches Wine 11.0, applies the patches and builds it (`.local/wine-install`; about 90 minutes on 4 cores; log in `.local/wine-build.log`).
   While it builds, only the step, the number and share of files compiled, an estimate of the time left and the last few lines of output are shown.
3. Builds the bridge (the WM and the proxy windows).
4. Extracts only the needed files from the ISO (`.local/assets`), and finds out the XP's language (Japanese or English).
5. Generates the locale of that language (`ja_JP.UTF-8` or `en_US.UTF-8`).
6. Creates the XP prefix (`.local/prefix`), with that XP's fonts and settings (see "English XP" below).
7. Writes `~/.config/win4wine/session.json` and registers the session "XP Shell (Wine, X11)".
8. On a virtual machine whose virtual graphics card is slow to read back from (QEMU's standard VGA, Hyper-V, VirtualBox's
   VBoxVGA and VBoxSVGA), makes X draw in memory first (`/etc/X11/xorg.conf.d/20-win4wine-shadowfb.conf`, modesetting's
   ShadowFB). Moving windows then costs the X server about half or less. It applies to every X session of the machine.
   `--no-shadowfb` skips it; virtio-gpu and VMware's virtual cards are left as they are.
9. With `--greeter`, installs XP's Welcome screen.
10. With `--wayland`, builds labwc and wlroots with their patches (`.local/labwc-install`; log in `.local/labwc-build.log`)
   and registers the session "XP Shell (Wine, Wayland)" too.

## English XP

Give an English XP SP3 ISO to `--media` and the setup follows English XP; the options are the same.

- The locale is `en_US.UTF-8`. Japanese input (fcitx5) is not set up (`session.json` gets no `input_method`).
- The fonts are English XP's: with Luna, Trebuchet MS in title bars and Tahoma 8 pt elsewhere, Franklin Gothic Medium for
  the Start button and the user name in the Start menu; with the classic theme, Tahoma 8 pt. Linux applications get Tahoma.
- The command prompt uses the raster font Terminal (8×12), as on English XP.
- The Welcome screen has English XP's text and fonts (Arial, Tahoma, Franklin Gothic Medium).
- The font files come from the ISO (Franklin Gothic, Arial bold and italic, Microsoft Sans Serif and Terminal of the English ISO).
- Mixing Japanese and English XP on one machine is not intended. There is one Welcome screen per machine: the last one set
  up with `--greeter`.
- XP in languages other than Japanese and English is set up the same way as English XP (with the locale `en_US.UTF-8`).
  It has not been tested at all, so `setup.sh` warns (and goes on).

To switch from Japanese to English XP (or back), move the extracted files and the prefix away and run `setup.sh` again with
the other ISO: `setup.sh` does not make them again while they exist. The Wine build is reused, and `setup.sh` updates the
locale and the input method in `session.json`. Log off, and on the text console (Ctrl+Alt+F2) or over SSH:

```sh
cd ~/win4wine
mv .local/assets .local/assets-ja
mv .local/prefix .local/prefix-ja
scripts/setup.sh --media /path/to/English-XP.iso --greeter
```

Once it works, you can delete the `-ja` folders.

## The ReactOS shell

Without an XP ISO, set up ReactOS's shell (classic look):

```sh
scripts/setup.sh --shell reactos --lang en
```

- It downloads the ReactOS 0.4.16 release (about 200 MB) from GitHub, checks its SHA-256 and extracts only the shell's files into
  `.local/assets-reactos`; the zip stays in `.local/dl`.
- The prefix is `.local/prefix-reactos`, the settings `~/.config/win4wine/reactos-session.json` and the session
  "**ReactOS Shell (Wine, X11)**". The XP shell's settings and session are left alone, so both can be set up (Wine and the bridge are shared).
- With `--greeter`, the login screen becomes ReactOS's logon screen.
- `--theme` is `classic` (the default, a Windows 2000-like classic look) or one of ReactOS's themes, `lautus`, `lunar` or
  `mizu`; run setup.sh again with `--theme` to change it later.
- With `--wayland`, the Wayland session "ReactOS Shell (Wine, Wayland)" is installed too (even more experimental than X11).
- Details: [docs/reactos.md](../../docs/reactos.md) (Japanese).

## The Windows 7 shell (experimental)

With a Windows 7 SP1 x64 ISO, Windows 7's shell (the Windows 7 Basic look) can be set up:

```sh
scripts/setup.sh --shell win7 --media /path/to/Windows7SP1x64.iso
```

- Only the shell's files and the MUI files of the ISO's language are extracted from its `sources/install.wim` into
  `.local/assets-win7` (the Professional edition's image, else the last one). The ISO decides the language.
- The prefix is `.local/prefix-win7`, the settings `~/.config/win4wine/win7-session.json` and the session
  "**Windows 7 Shell (Wine, X11)**". It can be set up beside the XP and ReactOS shells (they share Wine and the bridge).
- Windows 7's Aero cursors are installed; with `--greeter` the login screen is Windows 7's logon screen too.
- `--theme` and `--wayland` are not available for it yet; `--dpi` is.
- Tested with Japanese Windows 7 Professional SP1. English was tried with that media's strings (MUI) replaced by those of the English language pack (KB2483139); English installation media itself has not been tried yet. The language follows the media, and English Windows 7 is set up with the English locale (`en_US.UTF-8`). Details: [docs/windows7.md](../../docs/windows7.md) (Japanese).

## 3. Log in

Restart the display manager (or reboot).

- With `--greeter`: choose your user on XP's Welcome screen and type the password.
- Otherwise: choose the session "**XP Shell (Wine, X11)**" (with `--wayland`, also "**XP Shell (Wine, Wayland)**") on the login screen.

## Usage

| To | Do |
|---|---|
| toggle Japanese input | Ctrl+Space or Zenkaku/Hankaku, or click the icon in the notification area |
| start a Linux application | Start → All Programs (names end in "(Linux)") |
| install a Windows application | `wine setup.exe` in a terminal; the session's `PATH` starts with this Wine |
| start a Windows application from outside the session (ssh, another desktop) | `win4wine-wine setup.exe` (`~/.local/bin`): it runs with the session's prefix, Wine and settings, and looks as in the session. With more than one shell set up, choose with `--shell xp`, `reactos` or `win7`. Plain `wine` uses `~/.wine` and Wine's own look |
| open the Start menu | the Windows key, Ctrl+Esc |
| Run / Explorer | Win+R / Win+E |
| log off or shut down | Start → Log Off / Turn Off Computer |

## Settings (`~/.config/win4wine/session.json`)

| Key | Default | Meaning |
|---|---|---|
| `wine`, `prefix` | (written by setup.sh) | absolute paths of the Wine and prefix to use |
| `locale` | `ja_JP.UTF-8` (`en_US.UTF-8` for English XP) | the session's locale |
| `input_method` | `fcitx5` (none for English XP) | the input method; leave it out to start none |
| `linux_font` | `MS UI Gothic` (`Tahoma` for English XP and for the ReactOS and Windows 7 shells in English) | font of Linux applications; `null` leaves it alone |
| `linux_menu` | `true` | list Linux applications in the Start menu |
| `welcome_screen` | `true` | show XP's screens after login and while logging off (Windows 7's "Welcome", "Logging off" and so on for the Windows 7 shell) |
| `cursor_theme` | `win4wine-xp` | cursor theme; `null` for none |
| `shutdown_command`, `reboot_command` | `systemctl poweroff` / `reboot` | commands run by Turn Off Computer |
| `outputs` | (none) | the Wayland session's settings per output, e.g. `{"HDMI-A-1": {"scale": 1.5}, "DP-1": {"scale": 1, "position": "2560,0"}}` (`mode` too; `wlr-randr` lists the names) |
| `shell` | `xp` | `reactos` for ReactOS's shell (setup.sh writes it into `reactos-session.json`), `win7` for Windows 7's (`win7-session.json`) |
| `primary` | the leftmost output | the output the Wayland session makes Win32's primary monitor; XP's desktop and taskbar are on it |
| `composite` | `true` | the X server keeps the contents of Wine's windows (Composite's automatic redirection): moving or closing a window no longer shows the Wine windows below black until they repaint. `false` turns it off |
| `window_snap` | `false` | `true` lets windows snap to half of the screen (like Windows 7's Aero Snap; XP has no such thing): Win+Left/Right for the left or right half, Win+Up to maximize, Win+Down to restore or minimize; dragging a title bar to the left or right edge of the screen snaps it to that half, to the top edge maximizes it; dragging a maximized window's title bar restores it. Takes effect at the next login |

## Changing the look and the text size

Display Properties (right-click the desktop → Properties) do not open in the XP shell or the ReactOS shell (their parts are
not installed: XP shows an error, ReactOS nothing). The theme (the look), the DPI (the size of text and screen elements) and the font smoothing (ClearType) are changed with `setup.sh`, while the
session's Wine is not running: log off first.

1. Start → Log Off, back to the login screen.
2. Press Ctrl+Alt+F2 for a text console and log in as the same user (or log in over SSH from another machine).
3. Run one of these:

   ```sh
   cd ~/win4wine
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --theme classic   # XP's "Windows Classic"; --theme luna goes back
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --dpi 120          # text size; 96 is normal (XP's "Normal size")
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --font-smoothing cleartype   # ClearType; --font-smoothing standard goes back
   scripts/setup.sh --shell reactos --theme lautus                      # the ReactOS shell: classic, lautus, lunar or mizu
   ```

4. Log out of the console with `exit`, press Ctrl+Alt+F7 for the login screen and log in again.

- A theme brings its wallpaper, as choosing a theme on XP does (none for classic, Bliss for luna).
- Steps already done are skipped, so later runs are quick (Wine is rebuilt only where its patches changed).
- A higher DPI makes text and metrics larger while icons stay 32×32, as on XP. Linux applications get the same DPI for their
  text (GTK also doubles its widgets from 192).
- `--font-smoothing cleartype` is what choosing ClearType under XP's "Use the following method to smooth edges of screen fonts"
  does (the default is XP's Standard). As on XP, MS UI Gothic's small text (menus and the like, up to 22 pixels) stays a bitmap,
  while Tahoma, Arial and other text and large text become ClearType. Linux applications draw their text in the screen's RGB
  subpixel order too (in the X11 session).

In the Wayland session Linux applications draw at each output's scale (`scale` in `outputs`) and the XP shell at its DPI,
crisp on every output; set the DPI to the scale of the output you mostly use (144 for 1.5). See [docs/wayland.md](../../docs/wayland.md) (Japanese).

## Troubleshooting

- Session logs: `~/.local/state/win4wine/` (the previous run's in `*.log.1`).
- If the XP shell keeps crashing, the session switches to Wine's own explorer and an xterm.
- Before 2026-10-13, `setup.sh` could fail while setting a new prefix's look (`Setting the theme failed`).
  Update, then run `scripts/setup.sh --media ISO --theme luna` (or `classic`) again.
- If the Welcome screen does not appear: `/var/log/lightdm/seat0-greeter.log`. When something it needs is missing, it falls back to LightDM's usual greeter.

## Uninstall

```sh
greeter/install.sh --remove                     # stop using the Welcome screen (back to LightDM's previous greeter)
sudo rm /usr/share/xsessions/xp-shell.desktop /usr/local/bin/xp-shell-session   # unregister the session
sudo rm /usr/share/wayland-sessions/xp-shell-wayland.desktop /usr/local/bin/xp-shell-wayland-session   # and the Wayland one
sudo rm /usr/share/xsessions/reactos-shell.desktop /usr/local/bin/reactos-shell-session   # and the ReactOS shell's
sudo rm /usr/share/wayland-sessions/reactos-shell-wayland.desktop /usr/local/bin/reactos-shell-wayland-session
sudo rm /usr/share/xsessions/windows7-shell.desktop /usr/local/bin/windows7-shell-session   # and the Windows 7 shell's
python3 session/linux_apps.py .local/prefix --wine .local/wine-install/bin/wine --remove   # remove the Start menu entries it made
sudo rm -f /etc/X11/xorg.conf.d/20-win4wine-shadowfb.conf   # remove the virtual machine's X setting (from the next start of X)
```

The builds, extracted files and prefix go away with `.local/` of this checkout.
Packages the script installed (LightDM included) and the switch of display manager are not undone.
