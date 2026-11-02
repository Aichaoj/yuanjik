# -*- coding: utf-8 -*-
"""Self-drawn clean placeholder cards (no external assets).

Design: 800x800, soft tinted background, thin rounded frame, light disc,
minimal line icon, Chinese product name, small "测试占位图 / TEST PLACEHOLDER" tag.
"""
import os
from PIL import Image, ImageDraw, ImageFont

S = 800
INK = (154, 164, 178)
INK_D = (47, 55, 66)
SUB = (168, 176, 187)

TINTS = [(247, 248, 250), (246, 249, 247), (248, 247, 250), (246, 248, 251)]


def _font(size, bold=False):
    for p in ([r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"] if bold
              else [r"C:\Windows\Fonts\msyh.ttc"]):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    for p in [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\arial.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _w(d, xy, width, fill=None):
    d.line(xy, fill=fill or INK, width=width, joint="curve")


def icon(d, kind, cx, cy, R, w):
    """Draw a minimal line icon inside a box of half-size R centred at (cx,cy)."""
    r = R * 0.62
    def P(x, y):
        return (cx + x * r, cy + y * r)

    if kind == "pills":                      # round tablet with score line
        d.ellipse([cx - r * .75, cy - r * .75, cx + r * .75, cy + r * .75], outline=INK, width=w)
        _w(d, [P(-.75, 0), P(.75, 0)], w)
    elif kind == "capsule":                  # two capsules
        d.rounded_rectangle([cx - r * .95, cy - r * .38, cx + r * .25, cy + r * .38],
                            radius=r * .38, outline=INK, width=w)
        d.rounded_rectangle([cx + r * .05, cy - r * .10, cx + r * 1.05, cy + r * .66],
                            radius=r * .38, outline=INK, width=w)
    elif kind == "softgel":                  # three softgels
        for dx, dy in ((-.45, -.35), (.45, -.35), (0, .5)):
            d.ellipse([cx + dx * r - r * .42, cy + dy * r - r * .28,
                       cx + dx * r + r * .42, cy + dy * r + r * .28], outline=INK, width=w)
    elif kind == "powder":                   # jar with lid + scoop
        d.rounded_rectangle([cx - r * .68, cy - r * .35, cx + r * .68, cy + r * .85],
                            radius=r * .16, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .42, cy - r * .72, cx + r * .42, cy - r * .35],
                            radius=r * .1, outline=INK, width=w)
        _w(d, [P(-.68, .1), P(.68, .1)], w)
        _w(d, [P(-.3, .45), P(.3, .45)], max(2, w - 3))
        d.ellipse([cx + r * .78, cy + r * .38, cx + r * 1.22, cy + r * .82], outline=INK, width=w)
        _w(d, [P(.92, .78), P(.66, 1.02)], w)
    elif kind == "berry":                    # berry cluster + leaf
        for dx, dy in ((-.42, .20), (.0, .34), (.42, .20), (-.21, -.30), (.21, -.30)):
            d.ellipse([cx + dx * r - r * .27, cy + dy * r - r * .27,
                       cx + dx * r + r * .27, cy + dy * r + r * .27], outline=INK, width=w)
        d.arc([cx - r * .1, cy - r * 1.05, cx + r * .95, cy - r * .05], 150, 320, fill=INK, width=w)
    elif kind == "moxa":                     # moxa stick + smoke curls
        d.rounded_rectangle([cx - r * .30, cy - r * .05, cx + r * .30, cy + r * .92],
                            radius=r * .12, outline=INK, width=w)
        _w(d, [P(-.30, .18), P(.30, .18)], max(2, w - 3))
        _w(d, [P(-.30, .42), P(.30, .42)], max(2, w - 3))
        d.arc([cx - r * .42, cy - r * .62, cx + r * .18, cy - r * .02], 250, 90, fill=INK, width=w)
        d.arc([cx - r * .12, cy - r * 1.05, cx + r * .48, cy - r * .45], 250, 90, fill=INK, width=w)
    elif kind == "gelatin":                  # stacked blocks
        d.rounded_rectangle([cx - r * .8, cy - r * .1, cx + r * .1, cy + r * .7],
                            radius=r * .1, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .1, cy - r * .7, cx + r * .8, cy + r * .1],
                            radius=r * .1, outline=INK, width=w)
    elif kind == "root":                     # ginseng root with legs and hairs
        d.ellipse([cx - r * .34, cy - r * .78, cx + r * .34, cy - r * .02], outline=INK, width=w)
        _w(d, [P(-.16, -.02), P(-.46, .62)], w)
        _w(d, [P(.16, -.02), P(.46, .62)], w)
        _w(d, [P(0, -.02), P(0, .82)], w)
        for dy in (-.62, -.42, -.22):
            _w(d, [P(-.30, dy), P(-.60, dy - .12)], max(2, w - 3))
            _w(d, [P(.30, dy), P(.60, dy - .12)], max(2, w - 3))
        _w(d, [P(-.46, .62), P(-.62, .92)], max(2, w - 3))
        _w(d, [P(.46, .62), P(.62, .92)], max(2, w - 3))
    elif kind == "band":                     # wrist band
        d.rounded_rectangle([cx - r * .85, cy - r * .45, cx + r * .85, cy + r * .45],
                            radius=r * .45, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .34, cy - r * .30, cx + r * .34, cy + r * .30],
                            radius=r * .12, outline=INK, width=w)
    elif kind == "bpmonitor":                # monitor + cuff
        d.rounded_rectangle([cx - r * .85, cy - r * .75, cx + r * .45, cy + r * .5],
                            radius=r * .14, outline=INK, width=w)
        d.ellipse([cx - r * .55, cy - r * .5, cx - r * .05, cy], outline=INK, width=w)
        d.rounded_rectangle([cx + r * .18, cy - r * .1, cx + r * .95, cy + r * .62],
                            radius=r * .2, outline=INK, width=w)
    elif kind == "scale":                    # bathroom scale
        d.rounded_rectangle([cx - r * .8, cy - r * .62, cx + r * .8, cy + r * .62],
                            radius=r * .16, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .36, cy - r * .3, cx + r * .36, cy + r * .12],
                            radius=r * .08, outline=INK, width=w)
    elif kind == "dumbbell":
        _w(d, [P(-.55, 0), P(.55, 0)], w)
        for dx in (-.85, -.55, .55, .85):
            _w(d, [P(dx, -.5), P(dx, .5)], w)
    elif kind == "mat":                      # rolled mat
        d.ellipse([cx - r * .8, cy - r * .35, cx + r * .3, cy + r * .75], outline=INK, width=w)
        d.ellipse([cx - r * .5, cy - r * .05, cx + r * .0, cy + r * .45], outline=INK, width=w)
        d.rounded_rectangle([cx - r * .25, cy - r * .35, cx + r * .85, cy + r * .75],
                            radius=r * .2, outline=INK, width=w)
    elif kind == "kneebrace":                # brace around a knee
        d.arc([cx - r * .6, cy - r * .8, cx + r * .6, cy + r * .8], 200, 340, fill=INK, width=w)
        d.arc([cx - r * .6, cy - r * .8, cx + r * .6, cy + r * .8], 20, 160, fill=INK, width=w)
        d.ellipse([cx - r * .18, cy - r * .18, cx + r * .18, cy + r * .18], outline=INK, width=w)
    elif kind == "massagegun":
        d.rounded_rectangle([cx - r * .9, cy - r * .3, cx + r * .25, cy + r * .3],
                            radius=r * .28, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .35, cy + r * .1, cx + r * .05, cy + r * .95],
                            radius=r * .18, outline=INK, width=w)
        d.ellipse([cx + r * .2, cy - r * .32, cx + r * .58, cy + r * .06], outline=INK, width=w)
    elif kind == "grains":                   # bowl with grains
        d.arc([cx - r * .85, cy - r * .5, cx + r * .85, cy + r * .95], 0, 180, fill=INK, width=w)
        _w(d, [P(-.85, -.02), P(.85, -.02)], w)
        for dx, dy in ((-.4, -.3), (0, -.42), (.4, -.3), (-.2, -.14), (.2, -.14)):
            d.ellipse([cx + dx * r - r * .09, cy + dy * r - r * .09,
                       cx + dx * r + r * .09, cy + dy * r + r * .09], outline=INK, width=max(2, w - 4))
    elif kind == "shake":                    # shaker cup + straw
        d.polygon([P(-.5, -.6), P(.5, -.6), P(.36, .9), P(-.36, .9)], outline=INK, width=w)
        _w(d, [P(-.5, -.6), P(.5, -.6)], w)
        _w(d, [P(.12, -.6), P(.3, -1.0)], w)
    elif kind == "tea":                      # cup + saucer
        d.arc([cx - r * .62, cy - r * .4, cx + r * .42, cy + r * .5], 0, 180, fill=INK, width=w)
        _w(d, [P(-.62, -.02), P(.42, -.02)], w)
        d.arc([cx + r * .28, cy - r * .3, cx + r * .78, cy + r * .16], 270, 90, fill=INK, width=w)
        _w(d, [P(-.85, .55), P(.85, .55)], w)
        d.arc([cx - r * .25, cy - r * .95, cx + r * .15, cy - r * .45], 200, 340, fill=INK, width=w)
    elif kind == "bread":                    # loaf with slices
        d.rounded_rectangle([cx - r * .85, cy - r * .3, cx + r * .85, cy + r * .7],
                            radius=r * .3, outline=INK, width=w)
        for dx in (-.45, 0, .45):
            _w(d, [P(dx, -.05), P(dx, .6)], max(2, w - 3))
    elif kind == "tubes":                    # two test tubes in a rack
        for dx in (-.35, .35):
            d.rounded_rectangle([cx + dx * r - r * .2, cy - r * .8,
                                 cx + dx * r + r * .2, cy + r * .5],
                                radius=r * .2, outline=INK, width=w)
            _w(d, [P(dx - .2, 0), P(dx + .2, 0)], w)
        _w(d, [P(-.75, .5), P(.75, .5)], w)
    elif kind == "herbs":                    # leaf sprig
        _w(d, [P(0, .95), P(0, -.55)], w)
        for dy in (-.45, -.05, .35):
            d.arc([cx - r * .75, cy + dy * r - r * .3, cx + r * .05, cy + dy * r + r * .3],
                  90, 270, fill=INK, width=w)
            d.arc([cx - r * .05, cy + dy * r - r * .3, cx + r * .75, cy + dy * r + r * .3],
                  270, 90, fill=INK, width=w)
    elif kind == "couch":                    # armchair
        d.rounded_rectangle([cx - r * .8, cy - r * .55, cx + r * .8, cy + r * .35],
                            radius=r * .18, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .95, cy - r * .1, cx - r * .55, cy + r * .55],
                            radius=r * .12, outline=INK, width=w)
        d.rounded_rectangle([cx + r * .55, cy - r * .1, cx + r * .95, cy + r * .55],
                            radius=r * .12, outline=INK, width=w)
        d.rounded_rectangle([cx - r * .8, cy + r * .25, cx + r * .8, cy + r * .62],
                            radius=r * .12, outline=INK, width=w)
    elif kind == "table":                    # massage table
        d.rounded_rectangle([cx - r * .95, cy - r * .35, cx + r * .95, cy + r * .05],
                            radius=r * .12, outline=INK, width=w)
        for dx in (-.7, .7):
            _w(d, [P(dx, .05), P(dx * 1.1, .9)], w)
        d.ellipse([cx - r * .8, cy - r * .62, cx - r * .35, cy - r * .3], outline=INK, width=w)
    else:                                    # fallback: capsule
        d.rounded_rectangle([cx - r * .8, cy - r * .34, cx + r * .8, cy + r * .34],
                            radius=r * .34, outline=INK, width=w)
        _w(d, [P(0, -.34), P(0, .34)], w)


def make_card(path, name, icon_kind, variant=1, code=""):
    bg = TINTS[(variant - 1) % len(TINTS)]
    im = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(im)
    # subtle vignette / inner panel
    if variant == 2:
        for i in range(60):
            k = i / 60.0
            d.rounded_rectangle([20 + i, 20 + i, S - 20 - i, S - 20 - i], radius=48,
                                outline=(int(bg[0] - 6 * k), int(bg[1] - 6 * k), int(bg[2] - 5 * k)), width=1)
    d.rounded_rectangle([26, 26, S - 26, S - 26], radius=44, outline=(226, 230, 236), width=3)

    cy = 330 if variant != 4 else 350
    R = 190 if variant != 4 else 225
    if variant in (1, 3):
        d.ellipse([S/2 - R, cy - R, S/2 + R, cy + R], fill=(238, 241, 245))
    icon(d, icon_kind, S / 2, cy, R if variant != 4 else R * 0.92, 9 if variant != 4 else 10)

    if variant != 2:
        f = _font(52, bold=True)
        tw = d.textlength(name, font=f)
        while tw > S - 130 and f.size > 24:
            f = _font(f.size - 4, bold=True)
            tw = d.textlength(name, font=f)
        d.text(((S - tw) / 2, 620), name, fill=INK_D, font=f)
        fs = _font(22)
        tag = "测试占位图 · TEST PLACEHOLDER"
        d.text(((S - d.textlength(tag, font=fs)) / 2, 700), tag, fill=SUB, font=fs)
    else:
        fs = _font(24)
        tag = "测试占位图 · TEST PLACEHOLDER"
        d.text(((S - d.textlength(tag, font=fs)) / 2, 690), tag, fill=SUB, font=fs)
    if code and variant == 3:
        fc = _font(20)
        d.text((52, 52), code, fill=(196, 202, 210), font=fc)

    im.save(path, "JPEG", quality=80, optimize=True, progressive=True)
    return os.path.getsize(path)


if __name__ == "__main__":
    os.makedirs(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\ph_test", exist_ok=True)
    for k in ["pills", "capsule", "softgel", "powder", "berry", "moxa", "gelatin", "root", "band",
              "bpmonitor", "scale", "dumbbell", "mat", "kneebrace", "massagegun", "grains",
              "shake", "tea", "bread", "tubes", "herbs", "couch", "table"]:
        for v in (1, 2, 3, 4):
            make_card(rf"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\ph_test\{k}_{v}.jpg", "示例商品名", k, v, "001001")
    print("ok")
