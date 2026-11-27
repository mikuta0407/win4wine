"""Draw XP's Welcome screen with cairo and Pango from the user's XP files.

Images and strings come from the user's logonui.exe, msgina.dll and
winlogon.exe at run time. The layout below is XP's at 96 DPI; the numbers
were measured on the reference XP (stage 9). At other DPI settings (Screen's
dpi) XP scales the layout, the fonts and most images with the DPI (stage 10).
"""
import os
from pathlib import Path
import struct
import sys
import unicodedata

import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

from xpres import Resources

CONFIG = Path('/etc/win4wine/greeter.json')
# What the screen needs from extract/extract.py's output; without these the usual greeter is used.
REQUIRED = ('system32/logonui.exe', 'system32/msgina.dll', 'system32/winlogon.exe', 'fonts/msgothic.ttc')

TOP, BOTTOM = 80, 96            # top band; bottom band (2 divider + 20 + 26 + 2 + 26 + 20)
BOTTOM_PARTS = (2, 20, 26, 2, 26, 20)  # each scaled on its own above 96 DPI (122px at 120 DPI)
PANEL = 384                     # width of the left and the right panel
BACKGROUND = (90, 126, 220)
TOP_COLOR = (0, 48, 156)
BOTTOM_LEFT, BOTTOM_RIGHT = (57, 52, 173), (0, 48, 156)
TEXT = (239, 247, 255)
SHADOW = (49, 81, 181)
STATUS = (0, 48, 156)
ITEM = 80                       # height of one account
INSET = 2                       # DirectUI draws text 2px in from its element's left and right edges
MESSAGE = 320                   # where the left panel's message wraps, at every DPI
# The shutdown dialog: its template is in DLUs. The base units of its font at 96 DPI,
# by the template's face and size: Japanese XP's MS UI Gothic 9pt is 7x12, English
# XP's MS Shell Dlg 8pt (Microsoft Sans Serif) 6x13 (the dialog is 313x199 there).
BASE_UNITS = {('ms ui gothic', 9): (7, 12), ('ms shell dlg', 8): (6, 13)}
# The font of tooltips and balloons (SPI's status font) by the language of logonui:
# Japanese XP's MS UI Gothic 9pt, English XP's Tahoma 8pt.
SYSTEM_FONTS = {0x411: ('MS UI Gothic', 9), 0x409: ('Tahoma', 8)}
# The faded screen behind the shutdown dialog: an affine fit per channel of XP's final state
# (mean error under 1, at most 11).
DIM = ((0.1435, 0.6198, 0.1571, -4.37), (0.0952, 0.6789, 0.1426, -3.11), (0.0722, 0.6450, 0.1985, -3.15))
BLEND = {}


def setup(cache, assets=None):
    """The configuration and Assets, with fontconfig pointed at the XP fonts (before any text is drawn).

    Without the greeter's configuration (greeter/install.sh), ASSETS, the
    output of extract/extract.py, stands for it. Raises an exception when
    anything the screen needs is missing."""
    import json
    if CONFIG.is_file() or not assets:
        config = json.loads(CONFIG.read_text())
    else:
        config = {'assets': str(assets)}
    root = Path(config['assets'])
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError('missing ' + ', '.join(missing))
    use_fonts(root, cache)
    return config, Assets(root)


def use_fonts(root, cache):
    """Point fontconfig at the XP fonts in ROOT (extract/extract.py's output), before any text is drawn."""
    english = english_media(root)
    if english:
        # GDI's TrueType hinting, as FreeType's older interpreter does it: XP's
        # Arial and Tahoma get their 2px stems at the Welcome screen's sizes.
        # FreeType reads this once, when it draws the first text.
        os.environ.setdefault('FREETYPE_PROPERTIES', 'truetype:interpreter-version=35')
    os.environ['FONTCONFIG_FILE'] = str(fontconfig(Path(root) / 'fonts', Path(cache), english))


def english_media(root):
    """Whether the Welcome screen's files are English XP's (logonui's strings are not in
    Japanese: XP in other languages is set up as English XP)."""
    return 0x411 not in Resources(Path(root) / 'system32/logonui.exe').languages(6)


def config_dpi(config):
    """The Welcome screen's DPI: "dpi" in greeter.json (XP's machine-wide setting), 96 by default."""
    try:
        value = int(config.get('dpi', 96))
    except (TypeError, ValueError):
        return 96
    return value if 19 <= value <= 480 else 96


def login_session(saved, installed, default):
    """The session to start for a user: the one they last used (SAVED), or the
    greeter's own (DEFAULT, LightDM's user-session). These screens have no
    session menu, so a saved session that cannot have been chosen here is not
    kept: one that is no longer installed (LightDM would refuse to start it),
    and LightDM's "lightdm-xsession" (the system's default X session, which
    LightDM records for a user who logged in through its usual greeter before
    this one was installed: on a system without a desktop that is a lone
    terminal, and the user could never get to the shell)."""
    if saved and saved in installed and saved not in ('lightdm-xsession', 'default'):
        return saved
    return default


def default_picture(config, assets):
    """The picture of users without their own: XP's beach.bmp, as the XP prefix gives them."""
    return assets.pictures / config.get('picture', 'beach.bmp')


def points(pt, dpi=96):
    """Pixel height of a font of PT points at DPI, rounded as MulDiv does."""
    return (pt * dpi + 36) // 72


def fontconfig(fonts, directory, english=False):
    """Write a fonts.conf that adds the XP fonts and renders them as XP's standard smoothing does.

    XP follows each font's gasp table: MS UI Gothic is drawn without
    antialiasing (from its bitmaps) up to 24 pixels, Arial up to 17.
    English XP's fonts are fully hinted (with ENGLISH, see setup()).
    """
    directory = Path(directory).resolve()
    fonts = Path(fonts).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    rules = ''.join(f'''
  <match target="font">
    <test name="family"><string>{family}</string></test>
    <test name="pixelsize" compare="less_eq"><double>{size}</double></test>
    <edit name="antialias" mode="assign"><bool>false</bool></edit>
    <edit name="embeddedbitmap" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintfull</const></edit>
  </match>''' for family, size in (('MS UI Gothic', 24), ('Arial', 17)))
    if english:
        rules += ''.join(f'''
  <match target="font">
    <test name="family"><string>{family}</string></test>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="autohint" mode="assign"><bool>false</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintfull</const></edit>
    <edit name="rgba" mode="assign"><const>none</const></edit>
  </match>''' for family in ('Arial', 'Tahoma', 'Franklin Gothic Medium', 'Microsoft Sans Serif'))
    path = directory / 'fonts.conf'
    path.write_text(f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>{fonts}</dir>
  <cachedir>{directory / 'cache'}</cachedir>{rules}
</fontconfig>
''')
    return path


class Bitmap:
    """A DIB decoded to a premultiplied cairo surface."""

    def __init__(self, data, key=None, alpha=False, tint=None):
        if data[:2] == b'BM':
            data = data[14:]
        header, width, height, _, bits, compression, _, _, _, used = struct.unpack_from('<IiiHHIIiiI', data)
        bottom_up = height > 0
        height = abs(height)
        palette = []
        if bits <= 8:
            count = used or 1 << bits
            palette = [struct.unpack_from('<BBB', data, header + 4 * i)[::-1] for i in range(count)]
        pixels = data[header + 4 * len(palette) + (12 if compression == 3 and header == 40 else 0):]
        rows = []
        if compression == 1:
            indices = self.rle8(pixels, width, height)
            rows = [[palette[i] + (255,) for i in row] for row in indices]
        else:
            stride = (width * bits + 31) // 32 * 4
            step = bits // 8
            for y in range(height):
                line = pixels[y * stride:(y + 1) * stride]
                if bits == 8:
                    rows.append([palette[line[x]] + (255,) for x in range(width)])
                else:
                    rows.append([(line[x * step + 2], line[x * step + 1], line[x * step],
                                  line[x * step + 3] if alpha and step == 4 else 255) for x in range(width)])
        if bottom_up:
            rows.reverse()
        if key == 'corner':
            # DirectUI's content images (rcbmp mode 3) treat the top-left color as transparent.
            key = rows[0][0][:3]
        self.width, self.height = width, height
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, width)
        buffer = bytearray(stride * height)
        for y, row in enumerate(rows):
            for x, (r, g, b, a) in enumerate(row):
                if key is not None and (r, g, b) == key:
                    continue
                if tint:
                    r, g, b = tint((r, g, b))
                buffer[y * stride + 4 * x:y * stride + 4 * x + 4] = bytes(
                    (b * a // 255, g * a // 255, r * a // 255, a))
        self.surface = cairo.ImageSurface.create_for_data(buffer, cairo.FORMAT_ARGB32, width, height, stride)

    @staticmethod
    def rle8(data, width, height):
        rows, row, i = [], [], 0
        while len(rows) < height and i + 1 < len(data):
            count, value = data[i], data[i + 1]
            i += 2
            if count:
                row.extend([value] * count)
            elif value == 0:
                rows.append((row + [0] * width)[:width]); row = []
            elif value == 1:
                break
            elif value == 2:
                dx, dy = data[i], data[i + 1]; i += 2
                for _ in range(dy):
                    rows.append((row + [0] * width)[:width]); row = []
                row.extend([0] * dx)
            else:
                row.extend(data[i:i + value]); i += value + (value & 1)
        if row:
            rows.append((row + [0] * width)[:width])
        while len(rows) < height:
            rows.append([0] * width)
        return rows


def dim(color):
    r, g, b = color
    return tuple(max(0, min(255, round(x * r + y * g + z * b + k))) for x, y, z, k in DIM)


def scaled_picture(path, size, tint=None):
    """Any image GdkPixbuf reads, scaled to SIZE x SIZE, as a Bitmap-like object."""
    gi.require_version('GdkPixbuf', '2.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk, GdkPixbuf
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, False)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    surface.flush()
    if tint:
        data = surface.get_data()
        for i in range(0, len(data), 4):
            alpha = data[i + 3]
            if alpha:
                r, g, b = (data[i + 2 - k] * 255 // alpha for k in range(3))
                r, g, b = tint((r, g, b))
                data[i:i + 3] = bytes((b * alpha // 255, g * alpha // 255, r * alpha // 255))
        surface.mark_dirty()
    picture = Bitmap.__new__(Bitmap)
    picture.width = picture.height = size
    picture.surface = surface
    return picture


class Assets:
    """The user's XP files the greeter needs, as found by extract/extract.py."""

    def __init__(self, root):
        root = Path(root)
        self.root = root
        self.logonui = Resources(root / 'system32/logonui.exe')
        self.msgina = Resources(root / 'system32/msgina.dll')
        self.winlogon = Resources(root / 'system32/winlogon.exe')
        self.fonts = root / 'fonts'
        self.pictures = root / 'pictures'
        self.cache = {}
        theme = root / 'themes/Luna/luna.msstyles'
        self.luna = Resources(theme) if theme.is_file() else None
        # The faces logonui's UI file names: rcstr(1) for the left panel, rcstr(2)
        # for the bottom band, rcstr(3) for the accounts (all MS UI Gothic on
        # Japanese XP; arial, tahoma and tahoma on English XP).
        self.face = self.logonui.string(1) or 'MS UI Gothic'
        self.bottom_face = self.logonui.string(2) or self.face
        self.account_face = self.logonui.string(3) or self.face
        languages = self.logonui.languages(6)
        self.system_font = SYSTEM_FONTS[0x411 if not languages or languages[0] == 0x411 else 0x409]
        self.dialog = self.template(self.msgina.find(5, 20100))

    def bitmap(self, module, number, key=None, alpha=False, dimmed=False):
        name = (module, number, dimmed)
        if name not in self.cache:
            resources = {'logonui': self.logonui, 'msgina': self.msgina, 'luna': self.luna}[module]
            self.cache[name] = Bitmap(resources.bitmap(number), key, alpha, dim if dimmed else None)
        return self.cache[name]

    def picture(self, path, dimmed=False):
        """A user picture at XP's 48x48: BMP as is, other formats scaled."""
        name = ('picture', str(path), dimmed)
        if name not in self.cache:
            data = Path(path).read_bytes()
            if data[:2] == b'BM':
                picture = Bitmap(data, tint=dim if dimmed else None)
            else:
                picture = scaled_picture(path, 48, dim if dimmed else None)
            self.cache[name] = picture
        return self.cache[name]

    def string(self, module, number):
        return {'logonui': self.logonui, 'msgina': self.msgina, 'winlogon': self.winlogon}[module].string(number) or ''

    @staticmethod
    def template(data):
        """The controls of a DIALOGEX template: {id: (text, x, y, cx, cy)} in DLUs, plus its size."""
        def text(offset):
            if struct.unpack_from('<H', data, offset)[0] == 0xffff:
                return '', offset + 4
            end = offset
            while struct.unpack_from('<H', data, end)[0]:
                end += 2
            return data[offset:end].decode('utf-16-le'), end + 2
        style, count, _, _, cx, cy = struct.unpack_from('<8xIHhhhh', data, 4)
        offset = 26
        for _ in range(3):
            _, offset = text(offset)
        font = None
        if style & 0x40:
            size = struct.unpack_from('<H', data, offset)[0]
            face, offset = text(offset + 6)
            font = (face, size)
        controls = {'size': (cx, cy), 'font': font}
        for _ in range(count):
            offset = (offset + 3) & ~3
            x, y, w, h, number = struct.unpack_from('<12xhhhhI', data, offset)
            _, offset = text(offset + 24)
            caption, offset = text(offset)
            offset += 2 + struct.unpack_from('<H', data, offset)[0]
            controls[number] = (caption, x, y, w, h)
        return controls


# The XP fonts by family (in lower case, as GDI matches names): file and index in a collection.
FONT_FILES = {'ms ui gothic': ('msgothic.ttc', 2), 'arial': ('arial.ttf', 0), 'tahoma': ('tahoma.ttf', 0),
              'franklin gothic medium': ('framd.ttf', 0), 'microsoft sans serif': ('micross.ttf', 0)}
# Their own bold and italic faces, by (family, bold, italic). English XP media has
# them; where a face is missing, GDI simulates the style from the regular one.
STYLE_FILES = {('arial', True, False): 'arialbd.ttf', ('arial', False, True): 'ariali.ttf',
               ('arial', True, True): 'arialbi.ttf', ('tahoma', True, False): 'tahomabd.ttf',
               ('franklin gothic medium', False, True): 'framdit.ttf'}
# Names GDI draws with another family: XP's font substitute for MS Shell Dlg, and the
# family XP's font mapper picks for msgina's "Franklin Gothic" (seen on English XP).
SUBSTITUTES = {'ms shell dlg': 'microsoft sans serif', 'franklin gothic': 'franklin gothic medium'}


def font_family(name):
    """NAME as the family it is drawn with, in lower case if it is one of the XP fonts."""
    key = SUBSTITUTES.get(name.lower(), name.lower())
    return key if key in FONT_FILES else name


def win_metrics(path, index):
    """GDI's line metrics of a TrueType font: winAscent, winDescent, unitsPerEm and the underline."""
    data = Path(path).read_bytes()
    offset = 0
    if data[:4] == b'ttcf':
        offset = struct.unpack_from('>I', data, 12 + 4 * index)[0]
    tables = {}
    for i in range(struct.unpack_from('>H', data, offset + 4)[0]):
        tag, _, start, _ = struct.unpack_from('>4sIII', data, offset + 12 + 16 * i)
        tables[tag] = start
    em = struct.unpack_from('>H', data, tables[b'head'] + 18)[0]
    ascent, descent = struct.unpack_from('>HH', data, tables[b'OS/2'] + 74)
    position, thickness = struct.unpack_from('>hh', data, tables[b'post'] + 8)
    return ascent, descent, em, position, thickness


def scale(value, px, em):
    """VALUE font units at PX pixels per em, rounded half away from zero."""
    scaled = (abs(value) * px * 2 + em) // (2 * em)
    return scaled if value >= 0 else -scaled


def wide(ch):
    return unicodedata.east_asian_width(ch) in ('W', 'F')


class Block:
    """Laid out text: lines of runs, each run a Pango layout of one width class."""

    def __init__(self, lines, metrics, bold, shear, underline, box, align):
        self.lines, self.win, self.bold, self.shear = lines, metrics, bold, shear
        self.underline, self.box, self.align = underline, box, align


class Text:
    """Text placed and simulated as GDI's DrawText does it.

    Lines are tmHeight apart with baselines tmAscent below the top. The XP
    fonts have no bold or italic faces: GDI draws bold by striking each glyph
    again 1px to the right and widening every advance by 1px, and slants
    italic by 1/3 about the baseline. Underlines follow the font's post table.
    MS UI Gothic has a BASE table, which Pango uses to move Latin text off the
    baseline of Japanese text; GDI keeps one baseline, so each run of wide or
    narrow characters is laid out on its own and placed on the line's baseline.
    """

    def __init__(self, assets):
        self.assets = assets
        self.fontmap = PangoCairo.FontMap.get_default()
        self.context = self.fontmap.create_context()
        PangoCairo.context_set_resolution(self.context, 96)
        options = cairo.FontOptions()
        options.set_hint_metrics(cairo.HINT_METRICS_ON)
        PangoCairo.context_set_font_options(self.context, options)
        self.metrics = {}

    def style_file(self, family, bold, italic):
        """The file of FAMILY's own bold/italic face, if the XP media has it."""
        name = STYLE_FILES.get((family, bold, italic))
        return name if name and (self.assets.fonts / name).is_file() else None

    def win(self, family, style=None):
        """win_metrics() of FAMILY's regular face, or of its STYLE file; None for other fonts."""
        key = style or family
        if key not in self.metrics:
            name, index = (style, 0) if style else FONT_FILES.get(family, (None, 0))
            path = self.assets.fonts / name if name else None
            self.metrics[key] = win_metrics(path, index) if path and path.is_file() else None
        return self.metrics[key]

    def font_metrics(self, family, px, style=None):
        metrics = self.win(family, style)
        if metrics is None:
            ascent = round(px * 0.86)
            return ascent, px - ascent, 1, 1
        ascent, descent, em, position, thickness = metrics
        return (scale(ascent, px, em), scale(descent, px, em), -scale(position, px, em),
                max(1, scale(thickness, px, em)))

    def run(self, text, font, bold):
        layout = Pango.Layout.new(self.context)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        if bold:
            attributes = Pango.AttrList()
            attributes.insert(Pango.attr_letter_spacing_new(Pango.SCALE))
            layout.set_attributes(attributes)
        _, logical = layout.get_extents()
        # Pango spaces bold letters between them only; GDI widens every advance.
        return layout, (logical.width + Pango.SCALE - 1) // Pango.SCALE + bold

    def layout(self, text, px, bold=False, italic=False, underline=False, family=None, width=None,
               align='left', mnemonic=False):
        family = font_family(family or self.assets.face)
        style = self.style_file(family, bold, italic) if bold or italic else None
        simulated = family in FONT_FILES and not style
        # Set, not parsed: from_string() takes the "Medium" of Franklin Gothic Medium for a weight.
        font = Pango.FontDescription()
        font.set_family(family)
        font.set_absolute_size(px * Pango.SCALE)
        if bold and not simulated:
            font.set_weight(Pango.Weight.BOLD)
        if italic and not simulated:
            font.set_style(Pango.Style.ITALIC)
        bold = 1 if bold and simulated else 0
        marks = set()
        if mnemonic:
            # Windows' "&S": underline the character, drop the ampersand.
            plain, i = '', 0
            while i < len(text):
                if text[i] == '&' and i + 1 < len(text):
                    marks.add(len(plain))
                    plain += text[i + 1]
                    i += 2
                else:
                    plain += text[i]
                    i += 1
            text = plain
        elif underline:
            marks = set(range(len(text)))
        lines = []
        for paragraph in text.split('\n'):
            lines.extend(self.wrap(paragraph, font, bold, width))
        laid = []
        position = 0
        for line in lines:
            runs, x = [], 0
            for chunk in self.chunks(line):
                layout, advance = self.run(chunk, font, bold)
                spans = [(self.char_x(layout, chunk, k) + bold, self.char_x(layout, chunk, k + 1) + bold)
                         for k in range(len(chunk)) if position + k in marks]
                runs.append((layout, x, spans))
                x += advance
                position += len(chunk)
            laid.append((runs, x))
            position += 1 if line is not lines[-1] else 0
        return Block(laid, self.font_metrics(family, px, style), bold, 1 / 3 if italic and simulated else 0,
                     marks, width, align)

    @staticmethod
    def char_x(layout, text, k):
        index = len(text[:k].encode())
        return layout.index_to_pos(index).x // Pango.SCALE if k < len(text) else \
            layout.get_pixel_extents()[1].width

    @staticmethod
    def chunks(line):
        """Runs of wide or narrow characters; spaces stay with the run before them."""
        chunks, kinds = [], []
        for ch in line:
            if chunks and (ch == ' ' or wide(ch) == kinds[-1]):
                chunks[-1] += ch
            else:
                chunks.append(ch)
                kinds.append(wide(ch))
        return chunks

    def wrap(self, paragraph, font, bold, width):
        if width is None or not paragraph:
            return [paragraph]
        lines, line = [], ''
        for ch in paragraph:
            if line and sum(self.run(c, font, bold)[1] for c in self.chunks(line + ch)) > width:
                lines.append(line)
                line = ch.lstrip()
            else:
                line += ch
        return lines + [line]

    def offsets(self, block):
        """The x offset of each line; DT_CENTER and DT_RIGHT round down as GDI does."""
        result = []
        for _, width in block.lines:
            offset = 0
            if block.box is not None and block.align != 'left':
                offset = block.box - width
                if block.align == 'center':
                    offset //= 2
            result.append(offset)
        return result

    def draw(self, cr, block, x, y, color):
        ascent, descent, under, thickness = block.win
        cr.save()
        cr.set_source_rgb(*(c / 255 for c in color))
        PangoCairo.update_context(cr, self.context)
        for row, ((runs, _), offset) in enumerate(zip(block.lines, self.offsets(block))):
            baseline = y + ascent + row * (ascent + descent)
            cr.save()
            if block.shear:
                cr.transform(cairo.Matrix(1, 0, -block.shear, 1, block.shear * baseline, 0))
            for layout, left, spans in runs:
                line = layout.get_line_readonly(0)
                for strike in range(1 + block.bold):
                    cr.move_to(x + offset + left + strike, baseline)
                    PangoCairo.show_layout_line(cr, line)
                for start, end in spans:
                    cr.rectangle(x + offset + left + start, baseline + under, end - start, thickness)
                    cr.fill()
            cr.restore()
        cr.restore()

    def size(self, block):
        ascent, descent = block.win[:2]
        return max(width for _, width in block.lines), len(block.lines) * (ascent + descent)


def escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


class User:
    def __init__(self, name, display=None, picture=None, password=True):
        self.name, self.display, self.picture, self.password = name, display or name, picture, password


class Screen:
    """The Welcome screen's state; draw() paints it for a WIDTH x HEIGHT screen.

    mode: 'list' (choose an account, maybe with the password box of the
    selected one), 'logon' (Welcome, after a successful password), 'welcome'
    (the big "welcome" alone, as XP shows while the session starts) or
    'status' (centered logo and one line, for "Logging off..." and the like).
    """

    def __init__(self, assets, users, dpi=96):
        self.assets = assets
        self.dpi = dpi
        self.text = Text(assets)
        self.users = users
        self.mode = 'list'
        self.hover = None          # index of the account under the pointer
        self.selected = None       # index of the account showing its password box
        self.password = ''
        self.prompt = True         # whether the selected account shows its password box
        self.error = False
        self.status = ''
        self.power_hover = False
        self.dialog = False        # the "Turn off computer" dialog
        self.dialog_hover = None   # 'standby' | 'off' | 'restart' | 'cancel'
        self.dialog_pressed = None
        self.dialog_focus = 'off'
        self.tooltip = None        # (button, pointer x, pointer y) over the shutdown dialog
        self.layers = {}           # the screen behind the dialog, plain and faded
        self.can_standby = False
        self.caret = True

    # Geometry -------------------------------------------------------

    def px(self, value):
        """VALUE pixels at 96 DPI scaled to the screen's DPI, rounded as MulDiv does."""
        return (value * self.dpi + 48) // 96

    def bottom(self):
        """The bottom band's height: its parts scaled one by one (XP: 122 pixels at 120 DPI)."""
        return sum(self.px(part) for part in BOTTOM_PARTS)

    def pt(self, points_):
        return points(points_, self.dpi)

    def geometry(self, width, height):
        g = {}
        px = self.px
        top_band, bottom_band, panel = px(TOP), self.bottom(), px(PANEL)
        g['content'] = (top_band, height - bottom_band)
        center = (top_band + height - bottom_band) // 2
        g['center'] = center
        if self.mode == 'status':
            left = (width - panel) // 2
        else:
            # XP: the divider of the right panel is at width/2 - 2 at every size (96 DPI); above,
            # it moves left by half of what the panel grew (measured at 120 and 144 DPI).
            left = width // 2 - 2 - panel - (panel - PANEL) // 2
        g['left'] = left
        g['divider'] = left + panel
        if self.mode == 'welcome':
            shown = []
        else:
            shown = [self.selected] if self.mode == 'logon' else range(len(self.users))
        g['shown'] = list(shown)
        top = center - px(ITEM) * len(g['shown']) // 2
        g['items'] = {i: top + px(ITEM) * k for k, i in enumerate(g['shown'])}
        g['list_x'] = g['divider'] + px(1 + 26)
        return g

    def item_at(self, width, height, x, y):
        g = self.geometry(width, height)
        if self.mode != 'list' or self.dialog:
            return None
        px = self.px
        for i, top in g['items'].items():
            right = g['divider'] + px(PANEL)
            if g['list_x'] <= x < right and top <= y < top + px(ITEM):
                if i == self.selected and y >= top + px(5 + 2 + 58 + 2):
                    return None
                # Only the picture and the name take the pointer, as in XP.
                if x < g['list_x'] + px(7 + 58 + 7) + self.name_width(i) or i == self.selected:
                    return i
        return None

    def name_width(self, i):
        return self.text.size(self.name_layout(self.users[i].display))[0]

    def name_layout(self, name):
        """An account's name: logonui's account face at its size rcint(45)."""
        return self.text.layout(name, self.pt(int(self.assets.string('logonui', 45) or 12)),
                                family=self.assets.account_face)

    def power_rect(self, width, height):
        layout = self.power_layout()
        px = self.px
        return (px(25), height - self.bottom() + px(2) + px(20), px(26 + 2) + self.text.size(layout)[0], px(26))

    def power_layout(self, underline=False):
        """"Turn off computer": the bottom band's face at the buttons' size rcint(42)."""
        a = self.assets
        return self.text.layout(a.string('logonui', 11), self.pt(int(a.string('logonui', 42) or 12)),
                                underline=underline, family=a.bottom_face)

    def password_rects(self, width, height):
        g = self.geometry(width, height)
        top = g['items'][self.selected]
        px = self.px
        x = g['list_x'] + px(71)
        # The edit is as tall as its Arial 16pt line and borders; the empty keyboard element and
        # the go button each keep a 5px margin. Above 96 DPI XP's edit is a pixel lower than 29
        # scaled (35 at 120 DPI, 43 at 144), its bottom where it is at 96 DPI.
        height = px(29) - (self.dpi > 96)
        row = top + px(ITEM) - height
        return {'edit': (x, row, px(163), height), 'go': (x + px(163) + 2 * px(5), row + px(1), px(26), px(26))}

    def dialog_rects(self, width, height):
        controls = self.assets.dialog
        cx, cy = controls['size']
        base_x, base_y = self.base_units()
        w, h = self.dlu(cx, base_x, 4), self.dlu(cy, base_y, 8)
        # The 1px frame sits at (width - client) / 2 and one third down (XP at 800x600 and 1280x800).
        x = (width - w) // 2 + 1
        y = (height - h - 2) // 3 + 2
        rects = {'frame': (x - 1, y - 1, w + 2, h + 2), 'client': (x, y, w, h)}
        for name, number in (('cancel', 2), ('flag', 20101), ('title', 20102), ('standby', 20104),
                             ('off', 20103), ('restart', 20105), ('standby_label', 20108),
                             ('off_label', 20107), ('restart_label', 20109)):
            # As CreateDialog: x, y, cx and cy are each converted from DLUs.
            _, dx, dy, dw, dh = controls[number]
            rects[name] = (x + self.dlu(dx, base_x, 4), y + self.dlu(dy, base_y, 8),
                           self.dlu(dw, base_x, 4), self.dlu(dh, base_y, 8))
        return rects

    def dialog_font(self):
        """The shutdown dialog template's face and point size."""
        return self.assets.dialog['font'] or (self.assets.face, 9)

    def base_units(self):
        """The dialog's base units: its font as GdiGetCharDimensions measures it (BASE_UNITS at 96 DPI)."""
        face, size = self.dialog_font()
        if self.dpi == 96 and (face.lower(), size) in BASE_UNITS:
            return BASE_UNITS[face.lower(), size]
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        width, height = self.text.size(self.text.layout(letters, self.pt(size), family=face))
        return (width // 26 + 1) // 2, height

    @staticmethod
    def dlu(value, base, divisor):
        return (value * base + divisor // 2) // divisor

    # Drawing --------------------------------------------------------

    def draw(self, cr, width, height, dimmed=None, dialog=True):
        self.size = (width, height)
        if dimmed is None:
            dimmed = self.dialog
        tint = dim if dimmed else (lambda c: c)
        g = self.geometry(width, height)
        a = self.assets

        def fill(color, x, y, w, h):
            cr.set_source_rgb(*(c / 255 for c in tint(color)))
            cr.rectangle(x, y, w, h)
            cr.fill()

        def blit(bitmap, x, y, w=None, h=None, alpha=1.0, nearest=True):
            w = bitmap.width if w is None else w
            h = bitmap.height if h is None else h
            cr.save()
            cr.rectangle(x, y, w, h)
            cr.clip()
            cr.translate(x, y)
            cr.scale(w / bitmap.width, h / bitmap.height)
            cr.set_source_surface(bitmap.surface, 0, 0)
            if nearest:
                cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint_with_alpha(alpha)
            cr.restore()

        px = self.px
        top_band, bottom_band, panel = px(TOP), self.bottom(), px(PANEL)
        # Above 96 DPI XP stretches the pictures smoothly.
        smooth = self.dpi != 96

        # Bands.
        fill(TOP_COLOR, 0, 0, width, top_band)
        blit(a.bitmap('logonui', 125, dimmed=dimmed), 0, top_band - px(2), width, px(2))
        fill(BACKGROUND, 0, top_band, width, height - bottom_band - top_band)
        # GradientFill steps each channel in 12.20 fixed point (matches XP at 800, 1024 and 1280 wide).
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_RGB24, width)
        row = bytearray(stride)
        steps = [((c1 - c0) << 20) // width for c0, c1 in zip(BOTTOM_LEFT, BOTTOM_RIGHT)]
        for x in range(width):
            color = tint(tuple(((c0 << 20) + x * step) >> 20 for c0, step in zip(BOTTOM_LEFT, steps)))
            row[4 * x:4 * x + 3] = bytes(color[::-1])
        gradient = cairo.ImageSurface.create_for_data(row, cairo.FORMAT_RGB24, width, 1, stride)
        cr.save()
        cr.rectangle(0, height - bottom_band, width, bottom_band)
        cr.clip()
        cr.translate(0, height - bottom_band)
        cr.scale(1, bottom_band)
        cr.set_source_surface(gradient, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
        blit(a.bitmap('logonui', 126, dimmed=dimmed), 0, height - bottom_band, width, px(2))
        glow = a.bitmap('logonui', 100, dimmed=dimmed)
        blit(glow, 0, top_band, px(glow.width), px(glow.height), nearest=not smooth)

        # Left panel.
        right = g['left'] + panel
        if self.mode == 'welcome':
            # The word alone, a little right of the middle (measured on XP's screen:
            # it starts about 44 pixels left of the middle at 96 DPI).
            words = a.string('logonui', 7)
            size = self.pt(int(a.string('logonui', 44) or 32))
            layout = self.text.layout(words, size, bold=True, italic=True)
            w, h = self.text.size(layout)
            y = g['center'] - (h + px(3)) // 2
            x = width // 2 - px(44)
            self.text.draw(cr, layout, x + px(2), y + px(3), tint(SHADOW))
            self.text.draw(cr, layout, x, y, tint(TEXT))
        elif self.mode == 'logon':
            words = a.string('logonui', 7)
            size = self.pt(int(a.string('logonui', 44) or 32))
            layout = self.text.layout(words, size, bold=True, italic=True)
            w, h = self.text.size(layout)
            y = g['center'] - (h + px(3)) // 2
            # GDI's extent of the emboldened, slanted line reaches 7px past its last advance (measured).
            x = right - px(22) - w - px(7)
            self.text.draw(cr, layout, x + px(2), y + px(3), tint(SHADOW))
            self.text.draw(cr, layout, x, y, tint(TEXT))
        else:
            # The logo keeps its size at every DPI.
            logo = a.bitmap('logonui', 123, key='corner', dimmed=dimmed)
            message = self.status if self.mode == 'status' else a.string('logonui', 22)
            # The message wraps at the same width at every DPI: between 313 and 326 pixels on
            # XP at 120 and 144 DPI (at 96 DPI it fits on one line).
            layout = self.text.layout(message, self.pt(int(a.string('logonui', 45) or 12)),
                                      width=MESSAGE, align='right')
            w, h = self.text.size(layout)
            top = g['center'] - (logo.height + px(20) + h) // 2
            blit(logo, right - px(20) - logo.width, top)
            self.text.draw(cr, layout, right - px(40) - MESSAGE - px(INSET), top + logo.height + px(20),
                           tint(TEXT))

        # Right panel.
        if self.mode not in ('status', 'welcome'):
            blit(a.bitmap('logonui', 124, dimmed=dimmed), g['divider'], top_band, px(1), height - bottom_band - top_band)
            for i, top in g['items'].items():
                self.draw_user(cr, g, i, top, tint, blit, dimmed)

        # Bottom band.
        if self.mode == 'list':
            x, y, w, h = self.power_rect(width, height)
            blit(a.bitmap('logonui', 107, key='corner', dimmed=dimmed), x, y, px(26), px(26), nearest=not smooth)
            layout = self.power_layout(self.power_hover)
            self.text.draw(cr, layout, x + px(28 + INSET), y, tint((255, 255, 255)))
            layout = self.text.layout(a.string('logonui', 25).replace('\\n', '\n'),
                                      self.pt(int(a.string('logonui', 43) or 9)), width=px(325 - 18),
                                      family=a.bottom_face)
            self.text.draw(cr, layout, width - px(25 + 325 - 18) + INSET, y, tint((255, 255, 255)))

        if self.dialog and dialog:
            self.draw_dialog(cr, width, height, blit)

    def draw_user(self, cr, g, i, top, tint, blit, dimmed):
        a = self.assets
        px = self.px
        user = self.users[i]
        x = g['list_x']
        hot = self.mode == 'list' and (self.hover is not None or self.selected is not None)
        lit = self.mode == 'logon' or i in (self.hover, self.selected) or not hot
        alpha = 1.0 if lit else 96 / 255
        selected = i == self.selected
        if selected and self.mode == 'list':
            bar = a.bitmap('logonui', 112, key=(255, 0, 255), dimmed=dimmed)
            # The list keeps 5px free on its right.
            self.nine(cr, bar, x, top, g['divider'] + px(PANEL) - px(5) - x, px(72), (8, 8, 0, 8))
        lit_frame = self.mode == 'list' and (selected or i == self.hover)
        frame = a.bitmap('logonui', 119 if lit_frame else 113, alpha=True, dimmed=dimmed)
        # The picture's frame keeps its 7px offset at every DPI (measured at 144 DPI).
        fx, fy = x + 5 + 2, top + 5 + 2
        if alpha < 1:
            target = cr.get_target()
            area = (x, top, g['divider'] + px(PANEL) - x, px(ITEM))
            under = self.capture(target, area)
        blit(frame, fx, fy, px(frame.width), px(frame.height), nearest=self.dpi == 96)
        if user.picture:
            try:
                picture = a.picture(user.picture, dimmed)
            except Exception as e:  # An unreadable picture leaves the frame empty.
                print(f'cannot read {user.picture}: {e}', file=sys.stderr)
                user.picture = None
            else:
                blit(picture, fx + px(5), fy + px(5), px(48), px(48), nearest=False)
        name = self.name_layout(user.display)
        name_x = x + px(5 + 2 + 58 + 7) + INSET
        self.text.draw(cr, name, name_x, fy, tint(TEXT))
        if self.mode == 'logon' and self.status:
            layout = self.text.layout(self.status, self.pt(int(a.string('logonui', 46) or 9)), bold=True,
                                      family=a.account_face)
            self.text.draw(cr, layout, name_x, fy + self.text.size(name)[1], tint(STATUS))
        if alpha < 1:
            self.fade(target, area, under, 96)
        if selected and self.mode == 'list' and (self.prompt or self.error):
            self.draw_password(cr, g, top, tint, blit, dimmed)

    @staticmethod
    def capture(target, area):
        x, y, w, h = area
        target.flush()
        data, stride = target.get_data(), target.get_stride()
        return [bytes(data[(y + r) * stride + 4 * x:(y + r) * stride + 4 * (x + w)]) for r in range(h)]

    def fade(self, target, area, under, alpha):
        """Blend what was drawn over AREA with what was there, as AlphaBlend with a constant alpha."""
        if alpha not in BLEND:
            BLEND[alpha] = bytes((new * alpha + old * (255 - alpha) + 127) // 255
                                 for new in range(256) for old in range(256))
        table = BLEND[alpha]
        x, y, w, h = area
        target.flush()
        data, stride = target.get_data(), target.get_stride()
        for r in range(h):
            start = (y + r) * stride + 4 * x
            new = data[start:start + 4 * w]
            data[start:start + 4 * w] = bytes(table[n << 8 | o] for n, o in zip(new, under[r]))
        target.mark_dirty()

    def draw_password(self, cr, g, top, tint, blit, dimmed):
        a = self.assets
        rects = self.password_rects(*self.size)
        x, y, w, h = rects['edit']
        px = self.px
        label = self.text.layout(a.string('logonui', 6), self.pt(int(a.string('logonui', 47) or 9)),
                                 family=a.string('logonui', 48) or None)
        lw, lh = self.text.size(label)
        self.text.draw(cr, label, x + px(3 + INSET), y - px(3) - lh, tint((255, 255, 255)))
        edit = a.bitmap('logonui', 102, key=(255, 0, 255), dimmed=dimmed)
        self.nine(cr, edit, x, y, w, h, (3, 3, 5, 5))
        # The edit's formatting rectangle starts inside the 3px border; the EDIT control
        # leaves 6px before the first character of Arial 16pt (measured).
        dots = self.text.layout('\u25cf' * len(self.password), self.pt(16), family='Arial')
        tx, ty = x + px(3 + 6), y + px(3)
        cr.save()
        cr.rectangle(x + px(3), y + px(3), w - px(8), h - px(8))
        cr.clip()
        if self.password:
            self.text.draw(cr, dots, tx, ty, tint((0, 0, 0)))
        if self.caret and not self.dialog:
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(tx + (self.text.size(dots)[0] if self.password else 0), ty, 1, dots.win[0] + dots.win[1])
            cr.fill()
        cr.restore()
        gx, gy, gw, gh = rects['go']
        blit(a.bitmap('logonui', 103, key='corner', dimmed=dimmed), gx, gy, gw, gh)
        if self.error and not self.dialog:
            self.draw_balloon(cr, x + w // 2 - 1, y + h // 2)

    def nine(self, cr, bitmap, x, y, w, h, border):
        """Stretch BITMAP over the rectangle keeping its borders (left, top, right, bottom)."""
        left, top, right, bottom = border
        bw, bh = bitmap.width, bitmap.height
        columns = ((0, left, x, left), (left, bw - left - right, x + left, w - left - right),
                   (bw - right, right, x + w - right, right))
        rows = ((0, top, y, top), (top, bh - top - bottom, y + top, h - top - bottom),
                (bh - bottom, bottom, y + h - bottom, bottom))
        for sx, sw, dx, dw in columns:
            for sy, sh, dy, dh in rows:
                if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
                    continue
                cr.save()
                cr.rectangle(dx, dy, dw, dh)
                cr.clip()
                cr.translate(dx, dy)
                cr.scale(dw / sw, dh / sh)
                cr.set_source_surface(bitmap.surface, -sx, -sy)
                cr.get_source().set_filter(cairo.FILTER_NEAREST)
                cr.paint()
                cr.restore()

    def draw_balloon(self, cr, tip_x, tip_y, title=None, body=None, icon=True, wrap=None):
        """A balloon tip, as XP shows under the password box and over the shutdown buttons.

        The body starts 16px left of the stem and 19px below its tip; its corners
        and outline follow the pixels of XP's rounded region (measured). XP keeps the
        balloon's text and size at every DPI; only its error icon grows (to about 32px
        at 144 DPI, not reproduced).
        """
        a = self.assets
        face, size = a.system_font
        title = self.text.layout(title or a.string('logonui', 10), points(size), bold=True, family=face)
        body = self.text.layout(body or a.string('logonui', 8).replace('\\n', '\n'), points(size), width=wrap,
                                family=face)
        tw, th = self.text.size(title)
        bw, bh = self.text.size(body)
        left, top = tip_x - 16, tip_y + 19
        title_left, body_top = (36, 30) if icon else (12, 38)
        width = max(title_left + tw, 12 + bw) + 13
        height = body_top + bh + 10
        inset = (5, 3, 2, 1, 1)
        rows = {}
        for r in range(tip_y, top):
            rows[r] = (tip_x, tip_x + r - tip_y + 1)
        for r in range(height):
            edge = inset[min(r, height - 1 - r)] if min(r, height - 1 - r) < len(inset) else 0
            span = (left + edge, left + width - edge)
            if top + r in rows:
                span = (min(span[0], rows[top + r][0]), max(span[1], rows[top + r][1]))
            rows[top + r] = span

        def inside(x, y):
            return y in rows and rows[y][0] <= x < rows[y][1]
        cr.save()
        for y, (x0, x1) in rows.items():
            cr.set_source_rgb(1, 1, 225 / 255)
            cr.rectangle(x0, y, x1 - x0, 1)
            cr.fill()
            cr.set_source_rgb(0, 0, 0)
            for x in range(x0, x1):
                if not all(inside(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    cr.rectangle(x, y, 1, 1)
            cr.fill()
        if not icon:
            self.text.draw(cr, title, left + title_left, top + 11, (0, 0, 0))
            self.text.draw(cr, body, left + 12, top + body_top, (0, 0, 0))
            return
        # The error icon is drawn, not taken from user32.
        ix, iy = left + 11, top + 9
        cr.arc(ix + 7.5, iy + 7.5, 7, 0, 6.2832)
        cr.set_source_rgb(0.86, 0.1, 0.1)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(2)
        cr.move_to(ix + 4.5, iy + 4.5); cr.line_to(ix + 10.5, iy + 10.5)
        cr.move_to(ix + 10.5, iy + 4.5); cr.line_to(ix + 4.5, iy + 10.5)
        cr.stroke()
        cr.restore()
        self.text.draw(cr, title, left + 36, top + 11, (0, 0, 0))
        self.text.draw(cr, body, left + 12, top + 30, (0, 0, 0))

    def draw_dialog(self, cr, width, height, blit):
        a = self.assets
        r = self.dialog_rects(width, height)
        x, y, w, h = r['frame']
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x, y, w, h)
        cr.fill()
        blit(a.bitmap('msgina', 20142), *r['client'])
        flag = a.bitmap('msgina', 20143)
        fx, fy, fw, fh = r['flag']
        blit(flag, fx + int((fw - flag.width) / 2), fy + int((fh - flag.height) / 2))
        title = a.dialog[20102][0]
        layout = self.text.layout(title, self.pt(int(a.string('msgina', 20126) or 14)),
                                  family=a.string('msgina', 20125) or None)
        tx, ty, tw, th = r['title']
        self.text.draw(cr, layout, tx, ty + (th - self.text.size(layout)[1]) // 2, (255, 255, 255))
        strip = a.bitmap('msgina', 20150, key=(255, 0, 255))
        for name, base, number in (('standby', 3, 20104), ('off', 0, 20103), ('restart', 6, 20105)):
            bx, by, bw, bh = r[name]
            enabled = name != 'standby' or self.can_standby
            state = 0
            if not enabled:
                index = 9
            else:
                # Each button has normal, pressed and lit images; the focused one is lit too.
                if self.dialog_pressed == name:
                    state = 1
                elif name in (self.dialog_hover, self.dialog_focus):
                    state = 2
                index = base + state
            cr.save()
            cr.rectangle(bx, by, bw, bh)
            cr.clip()
            cr.translate(bx, by)
            cr.scale(bw / 32, bh / 32)
            cr.set_source_surface(strip.surface, 0, -32 * index)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
            cr.restore()
            lx, ly, lw, lh = r[name + '_label']
            layout = self.text.layout(a.dialog[number][0], self.pt(int(a.string('msgina', 20128) or 9)),
                                      bold=True, mnemonic=True, width=lw, align='center',
                                      family=a.string('msgina', 20127) or None)
            self.text.draw(cr, layout, lx, ly, (255, 255, 255) if enabled else (160, 160, 160))
        self.draw_button(cr, r['cancel'], a.dialog[2][0])
        if self.tooltip:
            name, x, y = self.tooltip
            number = {'standby': 20104, 'off': 20103, 'restart': 20105}[name]
            text = {'standby': 20130, 'off': 20129, 'restart': 20132}[name]
            # Below the pointer by half a cursor (SM_CYCURSOR 32), at most 300px of text wide.
            self.draw_balloon(cr, x, y + 16, a.dialog[number][0].replace('&', ''), a.string('msgina', text),
                              icon=False, wrap=300)

    def draw_button(self, cr, rect, caption):
        """A push button as Luna draws it: Blue\\button.bmp, five states, sizing margins 8, 8, 9, 9."""
        x, y, w, h = rect
        if self.assets.luna:
            image = self.assets.bitmap('luna', 'BLUE_BUTTON_BMP', alpha=True)
            states = 5
            state = 2 if self.dialog_pressed == 'cancel' else 1 if self.dialog_hover == 'cancel' else 0
            part = image.height // states
            cell = Bitmap.__new__(Bitmap)
            cell.width, cell.height = image.width, part
            cell.surface = image.surface.create_for_rectangle(0, part * state, image.width, part)
            self.nine(cr, cell, x, y, w, h, (8, 9, 8, 9))
        else:
            cr.set_source_rgb(0, 60 / 255, 116 / 255)
            cr.rectangle(x, y, w, h)
            cr.fill()
            cr.set_source_rgb(243 / 255, 243 / 255, 239 / 255)
            cr.rectangle(x + 1, y + 1, w - 2, h - 2)
            cr.fill()
        face, size = self.dialog_font()
        layout = self.text.layout(caption, self.pt(size), width=w, align='center', family=face)
        self.text.draw(cr, layout, x, y + (h - self.text.size(layout)[1]) // 2, (0, 0, 0))

    def render(self, width, height, fade=1.0):
        """The whole screen. While the shutdown dialog fades the screen, FADE runs from 0 to 1.

        Behind the dialog nothing changes, so both versions of the screen are kept
        in self.layers until it is cleared (when the dialog opens)."""
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
        cr = cairo.Context(surface)
        if self.dialog:
            if fade < 1:
                cr.set_source_surface(self.render_layer(width, height, False), 0, 0)
                cr.paint()
            if fade > 0:
                cr.set_source_surface(self.render_layer(width, height, True), 0, 0)
                cr.paint_with_alpha(fade)
            self.draw_dialog_only(cr, width, height)
        else:
            self.draw(cr, width, height)
        surface.flush()
        return surface

    def render_layer(self, width, height, dimmed):
        key = (width, height, dimmed)
        if key not in self.layers:
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
            self.draw(cairo.Context(surface), width, height, dimmed=dimmed, dialog=False)
            surface.flush()
            self.layers[key] = surface
        return self.layers[key]

    def draw_dialog_only(self, cr, width, height):
        def blit(bitmap, x, y, w=None, h=None, alpha=1.0, nearest=True):
            w = bitmap.width if w is None else w
            h = bitmap.height if h is None else h
            cr.save()
            cr.rectangle(x, y, w, h)
            cr.clip()
            cr.translate(x, y)
            cr.scale(w / bitmap.width, h / bitmap.height)
            cr.set_source_surface(bitmap.surface, 0, 0)
            if nearest:
                cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint_with_alpha(alpha)
            cr.restore()
        self.size = (width, height)
        self.draw_dialog(cr, width, height, blit)
