"""Original artwork for Mare Save Sync: the starry banner and the pixel floppy-and-moon icon.

Needs Pillow. The app falls back to a plain gradient if Pillow is missing.
Regenerate the icons with:  python -m mss.ui.theme_art
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..paths import ASSETS

TITLE_FONT = ASSETS / "title_font.ttf"


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _sparkle(d: ImageDraw.ImageDraw, x, y, r, color):
    """Four-point star."""
    w = max(1, r // 4)
    d.polygon([(x, y - r), (x + w, y - w), (x + r, y), (x + w, y + w),
               (x, y + r), (x - w, y + w), (x - r, y), (x - w, y - w)], fill=color)


def _crescent_mask(size, r, cut_dx, cut_dy, cut_r):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    c = size / 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=255)
    d.ellipse([c - cut_r + cut_dx, c - cut_r + cut_dy, c + cut_r + cut_dx, c + cut_r + cut_dy], fill=0)
    return m


def render_banner(w: int, h: int, title: str, left="#0d0b70", right="#2f64d6", scale: float = 1.0):
    """Night-sky banner with stars, a glowing crescent moon and a pixel-font title."""
    w, h = max(w, 50), max(h, 40)
    a, b = _hex(left), _hex(right)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        col = _lerp(a, b, (x / w) ** 1.3)
        for y in range(h):
            px[x, y] = col

    rnd = random.Random(20131011)
    d = ImageDraw.Draw(img)
    for _ in range(w * h // 700):
        x, y = rnd.randrange(w), rnd.randrange(h)
        v = rnd.randint(120, 255)
        d.point((x, y), fill=(v, v, min(255, v + 20)))
    for _ in range(max(4, w // 140)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        _sparkle(d, x, y, rnd.randint(2, 4), (235, 240, 255))

    # title
    fsize = int(h * 0.36)
    try:
        font = ImageFont.truetype(str(TITLE_FONT), fsize)
        try:
            font.set_variation_by_name("Bold")
        except Exception:
            pass
    except OSError:
        font = ImageFont.load_default()
    tb = d.textbbox((0, 0), title, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tx, ty = (w - tw) // 2 - tb[0], int(h * 0.36) - th // 2 - tb[1]

    # crescent moon with halo, left of the title
    ms = int(h * 0.62)
    mx, my = (w - tw) // 2 - ms - int(h * 0.18), int(h * 0.36) - ms // 2
    pad = ms // 2
    mask = _crescent_mask(ms + 2 * pad, ms * 0.40, ms * 0.17, -ms * 0.10, ms * 0.34)
    halo = mask.filter(ImageFilter.GaussianBlur(ms * 0.12)).point(lambda v: int(v * 0.65))
    img.paste((255, 236, 170), (mx - pad, my - pad), halo)
    img.paste((255, 247, 214), (mx - pad, my - pad), mask)

    d = ImageDraw.Draw(img)
    sh = max(2, fsize // 14)
    d.text((tx + sh, ty + sh), title, font=font, fill=(6, 6, 52))
    d.text((tx, ty), title, font=font, fill=(255, 255, 255))
    _sparkle(d, tx + tw + int(h * 0.16), int(h * 0.24), max(4, int(h * 0.09)), (255, 240, 170))
    _sparkle(d, tx + tw + int(h * 0.30), int(h * 0.48), max(3, int(h * 0.05)), (220, 230, 255))
    return img


# ------------------------------------------------------------------- library art
def _font(size, bold=True):
    try:
        f = ImageFont.truetype(str(TITLE_FONT), size)
        if bold:
            try:
                f.set_variation_by_name("Bold")
            except Exception:
                pass
        return f
    except OSError:
        return ImageFont.load_default()


def _wrap(d, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def night_sky(w: int, h: int) -> Image.Image:
    a, b = _hex("#0d0b70"), _hex("#3a5fc8")
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for x in range(w):
        d.line([(x, 0), (x, h)], fill=_lerp(a, b, (x / w) ** 1.3))
    rnd = random.Random(7)
    for _ in range(w * h // 600):
        v = rnd.randint(120, 255)
        d.point((rnd.randrange(w), rnd.randrange(h)), fill=(v, v, 255))
    ms = int(h * 0.55)
    pad = ms // 2
    mask = _crescent_mask(ms + 2 * pad, ms * 0.40, ms * 0.17, -ms * 0.10, ms * 0.34)
    halo = mask.filter(ImageFilter.GaussianBlur(ms * 0.12)).point(lambda v: int(v * 0.6))
    mx, my = int(w * 0.80) - ms // 2 - pad, int(h * 0.12) - pad
    img.paste((255, 236, 170), (mx, my), halo)
    img.paste((255, 247, 214), (mx, my), mask)
    d = ImageDraw.Draw(img)
    _sparkle(d, int(w * 0.70), int(h * 0.18), max(4, h // 22), (255, 240, 170))
    _sparkle(d, int(w * 0.90), int(h * 0.55), max(3, h // 34), (220, 230, 255))
    return img


def placeholder_cover(w: int, h: int, title: str) -> Image.Image:
    """A night-sky cover with the game's name, for games without SteamGridDB art."""
    rnd = random.Random(sum(map(ord, title)) or 1)
    top = (rnd.randint(8, 24), rnd.randint(6, 18), rnd.randint(70, 120))
    bot = (rnd.randint(40, 80), rnd.randint(60, 110), rnd.randint(170, 220))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=_lerp(top, bot, (y / h) ** 1.4))
    for _ in range(w * h // 260):
        v = rnd.randint(110, 255)
        d.point((rnd.randrange(w), rnd.randrange(int(h * 0.7))), fill=(v, v, 255))
    ms = int(w * 0.42)
    pad = ms // 2
    mask = _crescent_mask(ms + 2 * pad, ms * 0.40, ms * 0.17, -ms * 0.10, ms * 0.34)
    halo = mask.filter(ImageFilter.GaussianBlur(ms * 0.12)).point(lambda v: int(v * 0.6))
    mx, my = int(w * 0.52) - pad, int(h * 0.12) - pad
    img.paste((255, 236, 170), (mx, my), halo)
    img.paste((255, 247, 214), (mx, my), mask)
    d = ImageDraw.Draw(img)
    f = _font(max(12, w // 9))
    lines = _wrap(d, title, f, w - 20)[:4]
    lh = int(f.size * 1.15)
    y = int(h * 0.62) - lh * len(lines) // 2
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((w - tw) / 2 + 2, y + 2), ln, font=f, fill=(6, 6, 52))
        d.text(((w - tw) / 2, y), ln, font=f, fill=(255, 255, 255))
        y += lh
    _sparkle(d, int(w * 0.80), int(h * 0.10), max(3, w // 30), (255, 240, 170))
    return img


def cover_tile(path, w: int, h: int, title: str) -> Image.Image:
    if path:
        try:
            im = Image.open(path)
            im.seek(0)
            return ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.4))
        except Exception:
            pass
    return placeholder_cover(w, h, title)


def banner_tile(path, w: int, h: int) -> Image.Image:
    if path:
        try:
            return ImageOps.fit(Image.open(path).convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.35))
        except Exception:
            pass
    return night_sky(w, h)


def hero_image(hero_path, logo_path, w: int, h: int, title: str, bar: int = 62) -> Image.Image:
    """Wide banner for the details page: hero art (or night sky), the logo, and a dark bar at the bottom."""
    img = None
    if hero_path:
        try:
            img = ImageOps.fit(Image.open(hero_path).convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.35))
        except Exception:
            img = None
    if img is None:
        img = night_sky(w, h)
    img = img.convert("RGBA")
    logo_drawn = False
    if logo_path:
        try:
            lg = Image.open(logo_path).convert("RGBA")
            lg.thumbnail((int(w * 0.36), int((h - bar) * 0.70)), Image.LANCZOS)
            img.alpha_composite(lg, (int(w * 0.04), max(6, (h - bar - lg.height) // 2)))
            logo_drawn = True
        except Exception:
            pass
    if not logo_drawn:
        d = ImageDraw.Draw(img)
        f = _font(max(18, h // 7))
        y = (h - bar) // 2 - f.size // 2
        d.text((int(w * 0.04) + 3, y + 3), title, font=f, fill=(6, 6, 52))
        d.text((int(w * 0.04), y), title, font=f, fill=(255, 255, 255))
    shade = Image.new("RGBA", (w, bar + 30), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(bar + 30):
        a = int(200 * min(1, i / 30))
        sd.line([(0, i), (w, i)], fill=(8, 8, 40, a))
    img.alpha_composite(shade, (0, h - bar - 30))
    return img.convert("RGB")


# --------------------------------------------------------------------------- icon
def icon_image(n: int) -> Image.Image:
    """Pixel-art floppy disk with a crescent moon on its label, rendered on an n×n grid."""
    BG, BODY, BODYHI, SHUT, SLOT, LABEL, MOON, SPARK = range(8)
    pal = {BODY: (52, 46, 160), BODYHI: (96, 92, 214), SHUT: (200, 200, 208), SLOT: (40, 36, 120),
           LABEL: (240, 236, 255), MOON: (255, 214, 72), SPARK: (255, 255, 255)}

    def region(u, v):                     # u, v in 0..1
        inside = 0.09 <= u <= 0.91 and 0.09 <= v <= 0.91 and not (u - 0.78 > v - 0.09 and u > 0.78)
        if not inside:
            return BG
        if 0.28 <= u <= 0.70 and 0.09 <= v <= 0.36:
            if 0.53 <= u <= 0.62 and 0.14 <= v <= 0.30:
                return SLOT
            return SHUT
        if 0.19 <= u <= 0.81 and 0.47 <= v <= 0.91:
            cx, cy = 0.50, 0.69
            if math.hypot(u - cx, v - cy) <= 0.165 and math.hypot(u - cx - 0.08, v - cy + 0.05) > 0.14:
                return MOON
            return LABEL
        if (abs(u - 0.17) < 0.025 and abs(v - 0.20) < 0.07) or (abs(v - 0.20) < 0.025 and abs(u - 0.17) < 0.07):
            return SPARK
        return BODYHI if u < 0.15 else BODY

    grid = [[region((x + 0.5) / n, (y + 0.5) / n) for x in range(n)] for y in range(n)]
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    p = img.load()
    for y in range(n):
        for x in range(n):
            r = grid[y][x]
            if r == BG:
                continue
            edge = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                nb = grid[yy][xx] if 0 <= xx < n and 0 <= yy < n else BG
                if nb == BG or (r in (SHUT, LABEL) and nb in (BODY, BODYHI)):
                    edge = True
            if r == MOON:
                p[x, y] = pal[MOON] + (255,)
            elif edge:
                p[x, y] = (0, 0, 0, 255)
            else:
                p[x, y] = pal[r] + (255,)
    return img


def save_icons(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    big = icon_image(32).resize((256, 256), Image.NEAREST)
    sizes = {16: icon_image(16), 24: icon_image(24), 32: icon_image(32), 48: icon_image(48)}
    big.save(folder / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
             append_images=[sizes[16], sizes[24], sizes[32], sizes[48]])
    sizes[16].save(folder / "icon16.png")
    sizes[32].save(folder / "icon32.png")
    icon_image(32).resize((64, 64), Image.NEAREST).save(folder / "icon64.png")


if __name__ == "__main__":
    save_icons(ASSETS)
    render_banner(900, 96, "Mare Save Sync").save(ASSETS / "banner_preview.png")
