#!/usr/bin/env python3
"""
Short vertical (1080x1920) animado con monigotes (stickman), estilo vídeo
explicativo: voz neuronal gratuita (edge-tts), escenas dibujadas con código,
subtítulos palabra a palabra y un "whoosh" suave en cada cambio de escena.

Uso:
    python3 stickman_short.py spec.json

spec.json:
{
  "out": "salida/mi_short.mp4",
  "voice": "es-ES-AlvaroNeural",          (opcional)
  "rate": "+8%", "pitch": "-3Hz",         (opcional; velocidad y tono de la voz)
  "tts": "flow" | "lines",                 (opcional; flow = todo el guion en una toma, con
                                           silencios recortados y tiempos reales por palabra)
  "theme": "light" | "dark" | "8bit" | "mg" | "pixel" | "toon",  (opcional; mg = motion graphics,
                                          pixel = mg en pixel art, toon = mascota de dibujos + tarjeta)
  "lines": [
    {"text": "Las seis de la mañana.", "scene": "sleep", "alarm": true},
    {"text": "Uno se levanta.", "scene": "split",
     "top":    {"scene": "sleep", "label": "EL RESTO"},
     "bottom": {"scene": "run",   "label": "TÚ"}}
  ]
}

Escenas con monigote: stand, walk, sad, run, sleep, phone, think, climb, lift,
work, money, push, read, crowd, graph, clock, split.
Escenas de motion graphics sin personajes (tema "mg"): title (texto grande palabra
a palabra, *dorado*), icons (emojis con rótulo, strike/check), versus (EL RESTO / TÚ
con barras), chart (gráfica con área), flow (pasos con flechas), drain (algo que se
vacía, bar_label) y question (gran interrogación).
Tema "toon": cada línea pinta su escena de motion graphics dentro de una tarjeta arriba y la
mascota del canal abajo, que habla con la voz y parpadea. Opciones: pose (idle, up, celebrate,
wave, point, think, facepalm, shrug, thumbs, cross), face (happy, sad, shock, serious, smirk) y
label EL RESTO (sudadera gris) / TÚ (sudadera dorada), que sale como chapa en el pecho.  Opciones comunes por línea:
"label" (cartel arriba), "hook" (texto gancho de 2-4 palabras en grande durante
los primeros 2,4 s; ponlo en la primera línea, nunca repite palabras del título), "face" (happy, sad, neutral, determined, tired,
shock), "gold" (monigote dorado).  Ver cada función scene_* para el resto.

Requisitos: ffmpeg con libass, Pillow, numpy y `pip install edge-tts`.
"""
import json
import math
import random
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_short import FONT, FONT_DIR, duration, run, tts  # noqa: E402

W, H, FPS, SS = 1080, 1920, 30, 2
GROUND = 1360

THEMES = {
    "light": dict(bg=(245, 241, 232), ink=(22, 22, 24), gold=(214, 160, 30), grey=(160, 158, 152),
                  red=(205, 60, 50), soft=(225, 219, 205), glow=(255, 236, 160), box=(22, 22, 24)),
    # Pixel art: las escenas de motion graphics pixeladas a 16 colores (los emojis se
    # convierten en sprites), cajas negras de videojuego y letra pixel.
    "pixel": dict(bg=(29, 43, 83), ink=(255, 241, 232), gold=(255, 236, 39), grey=(131, 118, 156),
                  red=(255, 0, 77), soft=(0, 0, 0), glow=(255, 204, 170), box=(0, 0, 0), grid=(29, 43, 83),
                  pixel=6, font="PixelifySans.ttf", fscale=0.85, sfx="blip",
                  sub_font="Pixelify Sans", sub_size=96, hi="&H27ECFF&"),
    # Dibujos: mascota del canal en ilustración plana + gráfico en tarjeta (como los
    # explicadores animados con personaje). Subtítulos entre la tarjeta y el personaje.
    "toon": dict(bg=(15, 15, 21), ink=(246, 243, 236), gold=(236, 178, 62), grey=(128, 128, 140),
                 red=(232, 72, 72), soft=(26, 26, 34), glow=(70, 60, 30), box=(0, 0, 0), grid=(15, 15, 21),
                 toon=True, sub_y=900, sub_size=100),
    # Motion graphics sin personajes: fondo casi negro con rejilla, oro y blanco.
    "mg": dict(bg=(13, 13, 17), ink=(246, 243, 236), gold=(236, 191, 88), grey=(128, 128, 140),
               red=(232, 72, 72), soft=(28, 28, 36), glow=(70, 60, 30), box=(0, 0, 0), grid=(22, 22, 29)),
    "dark": dict(bg=(16, 16, 19), ink=(238, 236, 230), gold=(232, 197, 120), grey=(95, 95, 100),
                 red=(225, 80, 70), soft=(40, 40, 46), glow=(90, 80, 40), box=(0, 0, 0)),
    # Estilo videojuego de 8 bits: paleta fija de 16 colores, píxeles de 6x6, letra pixel,
    # líneas de barrido tipo CRT y "blips" chiptune en los cortes.
    "8bit": dict(bg=(29, 43, 83), ink=(255, 241, 232), gold=(255, 236, 39), grey=(131, 118, 156),
                 red=(255, 0, 77), soft=(95, 87, 79), glow=(255, 204, 170), box=(0, 0, 0),
                 pixel=6, font="PixelifySans.ttf", fscale=0.75, sfx="blip",
                 sub_font="Pixelify Sans", sub_size=96, hi="&H27ECFF&"),
}
PALETTE_8BIT = [(0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81), (171, 82, 54), (95, 87, 79),
                (194, 195, 199), (255, 241, 232), (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54),
                (41, 173, 255), (131, 118, 156), (255, 119, 168), (255, 204, 170)]
C = dict(THEMES["light"])


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def V(a):
    r = math.radians(a)
    return (math.sin(r), -math.cos(r))


def add(p, v, k=1.0):
    return (p[0] + v[0] * k, p[1] + v[1] * k)


_fonts = {}


def load_font(path, px):
    if (path, px) not in _fonts:
        f = ImageFont.truetype(str(path), px)
        try:
            f.set_variation_by_name("Bold")
        except (OSError, ValueError):
            pass
        _fonts[(path, px)] = f
    return _fonts[(path, px)]


def font(px):
    px = max(8, int(px * C.get("fscale", 1)))
    return load_font(FONT_DIR / C["font"] if C.get("font") else FONT, px)


_pal = None


def pixelate(img):
    """Baja a una rejilla de bloques, ajusta a la paleta de 16 colores sin tramado,
    vuelve a escalar sin suavizar y oscurece la última fila de cada bloque (efecto CRT)."""
    global _pal
    p = C["pixel"]
    if _pal is None:
        _pal = Image.new("P", (1, 1))
        _pal.putpalette([v for c in PALETTE_8BIT for v in c] + [0] * (768 - 48))
    small = img.resize((W // p, H // p), Image.BOX).quantize(palette=_pal, dither=Image.Dither.NONE)
    big = np.asarray(small.convert("RGB").resize((W, H), Image.NEAREST)).copy()
    big[p - 1::p] = (big[p - 1::p] * 0.78).astype(np.uint8)
    return Image.fromarray(big)


class Cv:
    """Lienzo con supermuestreo y una cámara simple (zoom alrededor de un punto)."""

    def __init__(self, z=1.0, cx=540, cy=1000):
        self.img = Image.new("RGB", (W * SS, H * SS), C["bg"])
        self.d = ImageDraw.Draw(self.img)
        self.z, self.cx, self.cy = z, cx, cy
        self.texts = []  # en pixel art el texto se dibuja nítido después de pixelar

    ox = oy = 0

    def P(self, p):
        return (((p[0] - self.cx) * self.z + self.cx + self.ox) * SS,
                ((p[1] - self.cy) * self.z + self.cy + self.oy) * SS)

    def S(self, w):
        return max(1, int(round(w * self.z * SS)))

    def line(self, a, b, w, c):
        pa, pb = self.P(a), self.P(b)
        ww = self.S(w)
        self.d.line([pa, pb], fill=c, width=ww)
        r = ww / 2
        for p in (pa, pb):
            self.d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=c)

    def path(self, pts, w, c):
        for a, b in zip(pts, pts[1:]):
            self.line(a, b, w, c)

    def circle(self, c, r, fill=None, outline=None, w=0):
        x, y = self.P(c)
        rr = r * self.z * SS
        self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill, outline=outline,
                       width=self.S(w) if outline else 0)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=0, rad=0):
        a, b = self.P((x0, y0)), self.P((x1, y1))
        self.d.rounded_rectangle([a, b], radius=rad * self.z * SS, fill=fill, outline=outline,
                                 width=self.S(w) if outline else 0)

    def poly(self, pts, fill):
        self.d.polygon([self.P(p) for p in pts], fill=fill)

    def text(self, p, s, size, c, anchor="mm", stroke=0, stroke_c=None):
        if C.get("pixel"):
            x, y = self.P(p)
            self.texts.append((x / SS, y / SS, s, size * self.z, c, anchor))
            return
        self.d.text(self.P(p), s, font=font(size * self.z * SS), fill=c, anchor=anchor,
                    stroke_width=self.S(stroke) if stroke else 0, stroke_fill=stroke_c)

    def final(self):
        img = self.img.reduce(SS)
        if not C.get("pixel"):
            return img
        img = pixelate(img)
        d = ImageDraw.Draw(img)
        for x, y, s, size, c, anchor in self.texts:
            px = max(24, int(size * C.get("fscale", 1) / 6) * 6)
            f = load_font(FONT_DIR / C["font"], px)
            d.text((x + 6, y + 6), s, font=f, fill=(0, 0, 0), anchor=anchor)  # sombra de 1 píxel
            d.text((x, y), s, font=f, fill=c, anchor=anchor)
        return img


# ---------------------------------------------------------------- monigote
STAND = dict(lean=0, head=0, aL1=-10, aL2=-6, aR1=10, aR2=6, lL1=-7, lL2=-3, lR1=7, lR2=3)


def figure(cv, hip, pose=None, h=520, col=None, face="neutral", facing=1, rot=0, ground=None):
    """Dibuja un monigote. Ángulos de extremidad: 0 = hacia abajo, + = hacia delante
    (hacia donde mira). lean: inclinación del tronco. rot: gira toda la figura."""
    p = dict(STAND)
    p.update(pose or {})
    f = -1 if facing < 0 else 1
    col = col or C["ink"]
    T, nk, r = 0.30 * h, 0.035 * h, 0.085 * h
    ua, fa, th, sh = 0.16 * h, 0.15 * h, 0.21 * h, 0.21 * h
    lw = 0.03 * h

    def limb(o):
        return 180 - f * o + rot

    tor = f * p["lean"] + rot
    neck = add(hip, V(tor), T)
    sho = add(hip, V(tor), 0.88 * T)
    hd = add(neck, V(tor + f * p["head"]), nk + r)
    eL = add(sho, V(limb(p["aL1"])), ua)
    hL = add(eL, V(limb(p["aL2"])), fa)
    eR = add(sho, V(limb(p["aR1"])), ua)
    hR = add(eR, V(limb(p["aR2"])), fa)
    kL = add(hip, V(limb(p["lL1"])), th)
    fL = add(kL, V(limb(p["lL2"])), sh)
    kR = add(hip, V(limb(p["lR1"])), th)
    fR = add(kR, V(limb(p["lR2"])), sh)
    J = dict(hip=hip, neck=neck, sho=sho, head=hd, eL=eL, hL=hL, eR=eR, hR=hR, kL=kL, fL=fL, kR=kR, fR=fR)
    if ground is not None:
        low = max(fL[1], fR[1], kL[1], kR[1], hip[1], hd[1] + r) + lw / 2
        J = {k: (v[0], v[1] + ground - low) for k, v in J.items()}
    for a, b, c in (("hip", "kL", "fL"), ("hip", "kR", "fR"), ("sho", "eL", "hL"), ("sho", "eR", "hR")):
        cv.path([J[a], J[b], J[c]], lw, col)
    cv.line(J["hip"], J["neck"], lw, col)
    cv.circle(J["head"], r, fill=C["bg"], outline=col, w=lw)
    draw_face(cv, J["head"], r, tor + f * p["head"], face, 0 if facing == 0 else f, col, lw)
    J["r"], J["lw"], J["f"] = r, lw, f
    return J


def draw_face(cv, c, r, ang, face, f, col, lw):
    if face in (None, "none"):
        return
    up, right = V(ang), V(ang + 90)

    def L(x, y):
        return (c[0] + (x * right[0] + y * up[0]) * r, c[1] + (x * right[1] + y * up[1]) * r)

    eyes = [(-0.32, 0.15), (0.32, 0.15)] if f == 0 else [(f * 0.12, 0.15), (f * 0.52, 0.15)]
    mx = 0 if f == 0 else f * 0.3
    for ex, ey in eyes:
        if face == "tired":
            cv.line(L(ex - 0.1, ey), L(ex + 0.1, ey), lw * 0.45, col)
        else:
            cv.circle(L(ex, ey), r * 0.09, fill=col)
        if face == "determined":
            inner = 1 if (ex - mx) < 0 else -1
            cv.line(L(ex - 0.13, ey + 0.28 + 0.06 * inner), L(ex + 0.13, ey + 0.28 - 0.06 * inner), lw * 0.4, col)
        if face == "sad":
            inner = 1 if (ex - mx) < 0 else -1
            cv.line(L(ex - 0.13, ey + 0.26 - 0.07 * inner), L(ex + 0.13, ey + 0.26 + 0.07 * inner), lw * 0.4, col)
    if face == "shock":
        cv.circle(L(mx, -0.4), r * 0.13, outline=col, w=lw * 0.4)
        return
    k = {"happy": 1, "sad": -1}.get(face, 0)
    pts = []
    for i in range(7):
        x = -0.24 + 0.48 * i / 6
        pts.append(L(mx + x, -0.38 + k * 0.16 * ((x / 0.24) ** 2 - 1)))
    cv.path(pts, lw * 0.45, col)


def walk_pose(ph, amp=26, knee=34, arm=24, lean=4):
    s = math.sin(ph)
    pose = dict(lean=lean)
    for leg, q in (("lL", ph), ("lR", ph + math.pi)):
        a = amp * math.sin(q)
        pose[leg + "1"] = a
        pose[leg + "2"] = a - knee * max(0.0, math.cos(q))
    pose["aL1"], pose["aL2"] = -arm * s, -arm * s + arm * 0.9
    pose["aR1"], pose["aR2"] = arm * s, arm * s + arm * 0.9
    return pose


def run_pose(ph):
    p = walk_pose(ph, amp=44, knee=75, arm=55, lean=14)
    p["aL2"] = p["aL1"] + 85
    p["aR2"] = p["aR1"] + 85
    return p


SIT = dict(lL1=82, lL2=4, lR1=88, lR2=8)


# ---------------------------------------------------------------- props
def ground(cv, y=GROUND, x0=90, x1=990):
    cv.line((x0, y), (x1, y), 7, C["ink"])


def coin(cv, c, r, rot=0.0):
    sq = abs(math.cos(rot))
    x, y = cv.P(c)
    rr = r * cv.z * SS
    cv.d.ellipse([x - rr * max(sq, 0.12), y - rr, x + rr * max(sq, 0.12), y + rr], fill=C["gold"],
                 outline=mix(C["gold"], (0, 0, 0), 0.35), width=cv.S(r * 0.12))
    if sq > 0.45:
        cv.text(c, "$", r * 1.3, mix(C["gold"], (0, 0, 0), 0.45))


def cloud(cv, c, s=1.0, col=None):
    col = col or C["grey"]
    for dx, dy, r in ((-70, 10, 55), (0, -20, 75), (75, 5, 58), (30, 30, 50), (-30, 30, 50)):
        cv.circle((c[0] + dx * s, c[1] + dy * s), r * s, fill=col)


def rain(cv, c, t, s=1.0):
    rnd = random.Random(7)
    for i in range(14):
        x = c[0] + rnd.uniform(-110, 110) * s
        y0 = c[1] + 40 * s
        y = y0 + ((t * 700 + rnd.uniform(0, 400)) % 420) * s
        cv.line((x, y), (x - 6, y + 34 * s), 5, mix(C["grey"], (60, 90, 160), 0.5))


def bubble(cv, c, txt, size=120, anchor_pt=None):
    if anchor_pt:
        for k, rr in ((0.25, 12), (0.5, 20)):
            cv.circle((anchor_pt[0] + (c[0] - anchor_pt[0]) * k, anchor_pt[1] + (c[1] - anchor_pt[1]) * k), rr,
                      fill=C["bg"], outline=C["ink"], w=5)
    for dx, dy, r in ((-90, 0, 85), (0, -35, 100), (90, 0, 85), (0, 40, 85)):
        cv.circle((c[0] + dx, c[1] + dy), r + 6, fill=C["ink"])
    for dx, dy, r in ((-90, 0, 85), (0, -35, 100), (90, 0, 85), (0, 40, 85)):
        cv.circle((c[0] + dx, c[1] + dy), r, fill=C["bg"])
    cv.text((c[0], c[1] + 5), txt, size, C["ink"])


def clock(cv, c, R, minutes, col=None):
    col = col or C["ink"]
    cv.circle(c, R, fill=C["bg"], outline=col, w=R * 0.08)
    for i in range(12):
        a = i * 30
        cv.line(add(c, V(a), R * 0.78), add(c, V(a), R * 0.88), R * 0.05, col)
    cv.line(c, add(c, V(minutes / 720 * 360), R * 0.5), R * 0.08, col)
    cv.line(c, add(c, V(minutes % 60 * 6), R * 0.75), R * 0.05, C["red"])
    cv.circle(c, R * 0.07, fill=col)


def phone(cv, hand, glow=True, glow_r=95):
    x, y = hand
    if glow:
        cv.circle((x, y - 44), glow_r, fill=mix(C["bg"], C["glow"], 0.55))
    cv.rect(x - 26, y - 92, x + 26, y + 4, fill=C["ink"], rad=8)
    cv.rect(x - 20, y - 84, x + 20, y - 4, fill=C["glow"] if glow else C["grey"], rad=4)


def sofa(cv, x, y):
    cv.rect(x - 230, y - 150, x + 230, y + 60, fill=C["soft"], outline=C["ink"], w=7, rad=40)
    cv.rect(x - 270, y - 60, x - 190, y + 90, fill=C["soft"], outline=C["ink"], w=7, rad=30)
    cv.rect(x + 190, y - 60, x + 270, y + 90, fill=C["soft"], outline=C["ink"], w=7, rad=30)
    cv.line((x - 230, y + 90), (x + 230, y + 90), 7, C["ink"])


def chair(cv, x, seat):
    cv.line((x - 70, seat), (x + 70, seat), 9, C["ink"])
    cv.line((x - 70, seat), (x - 70, seat - 230), 9, C["ink"])
    cv.line((x - 60, seat), (x - 60, GROUND), 8, C["ink"])
    cv.line((x + 60, seat), (x + 60, GROUND), 8, C["ink"])


def window_night(cv, x, y, w=300, h=340):
    cv.rect(x, y, x + w, y + h, fill=mix(C["ink"], (20, 30, 70), 0.6), outline=C["ink"], w=9, rad=6)
    cv.line((x + w / 2, y), (x + w / 2, y + h), 7, C["ink"])
    cv.line((x, y + h / 2), (x + w, y + h / 2), 7, C["ink"])
    cv.circle((x + w * 0.72, y + h * 0.25), 34, fill=(245, 235, 200))
    cv.circle((x + w * 0.66, y + h * 0.21), 30, fill=mix(C["ink"], (20, 30, 70), 0.6))
    for sx, sy in ((0.2, 0.15), (0.3, 0.7), (0.8, 0.8), (0.15, 0.4)):
        cv.circle((x + w * sx, y + h * sy), 5, fill=(245, 245, 230))


# ---------------------------------------------------------------- escenas
def fig_col(o):
    return C["gold"] if o.get("gold") else None


def scene_stand(cv, t, D, o):
    ground(cv)
    b = math.sin(t * 2.4)
    figure(cv, (540, 0), dict(aL1=-10 - 3 * b, aR1=10 + 3 * b, head=2 * b), face=o.get("face", "neutral"),
           facing=o.get("facing", 0), ground=GROUND, col=fig_col(o))
    if o.get("bubble"):
        bubble(cv, (700, 560), o["bubble"], anchor_pt=(600, 820))


def scene_walk(cv, t, D, o):
    ground(cv)
    sad = o.get("sad") or o.get("scene") == "sad"
    speed = 0.9 if sad else 1.7
    x = 200 + 640 * ease(t / D) if not sad else 260 + 520 * (t / D)
    pose = walk_pose(t * speed * 2 * math.pi, amp=16 if sad else 26)
    if sad:
        pose.update(lean=12, head=22)
    J = figure(cv, (x, 0), pose, face=o.get("face", "sad" if sad else "neutral"), ground=GROUND, col=fig_col(o))
    if sad:
        cloud(cv, (J["head"][0], J["head"][1] - 230), 0.9)
        rain(cv, (J["head"][0], J["head"][1] - 230), t, 0.9)


def scene_run(cv, t, D, o):
    ground(cv)
    for i in range(6):
        x = 1000 - ((t * 900 + i * 180) % 1080)
        cv.line((x, GROUND + 40), (x + 70, GROUND + 40), 6, C["grey"])
    for i, yy in enumerate((980, 1060, 1140)):
        x = 330 - ((t * 600 + i * 60) % 120)
        cv.line((x - 110, yy), (x, yy), 6, C["grey"])
    J = figure(cv, (540, 0), run_pose(t * 2.6 * 2 * math.pi), face=o.get("face", "determined"), ground=GROUND,
               col=fig_col(o))
    if o.get("sweat", True) and int(t * 3) % 2 == 0:
        cv.circle((J["head"][0] - 70, J["head"][1] - 30), 10, fill=(90, 150, 220))


def scene_sleep(cv, t, D, o):
    ground(cv)
    cv.rect(180, 1180, 900, 1250, fill=C["soft"], outline=C["ink"], w=8, rad=12)
    cv.line((190, 1250), (190, GROUND), 10, C["ink"])
    cv.line((890, 1250), (890, GROUND), 10, C["ink"])
    cv.rect(160, 1020, 200, 1260, fill=C["ink"], rad=10)
    cv.rect(215, 1130, 345, 1185, fill=C["bg"], outline=C["ink"], w=6, rad=25)
    b = math.sin(t * 2.0) * 3
    figure(cv, (480, 1150 + b * 0.3), dict(lL1=2, lL2=0, lR1=-2, lR2=0, aL1=-4, aL2=0, aR1=4, aR2=0),
           rot=-90, face=o.get("face", "tired"), facing=0, col=fig_col(o))
    cv.poly([(380, 1110), (880, 1110), (880, 1195), (380, 1195)], mix(C["soft"], C["grey"], 0.5))
    cv.line((380, 1110), (880, 1110), 7, C["ink"])
    for i in range(3):
        k = (t * 0.6 + i / 3) % 1
        cv.text((330 + 90 * k + i * 15, 1060 - 260 * k), "Z", 60 + 40 * k, mix(C["ink"], C["bg"], k))
    if o.get("alarm"):
        sh = math.sin(t * 60) * 6 if int(t * 2) % 2 == 0 else 0
        cv.rect(930, 1180, 1040, 1360, fill=C["soft"], outline=C["ink"], w=6, rad=6)
        clock(cv, (985 + sh, 1105), 55, 6 * 60)
        if sh:
            cv.line((925, 1050), (900, 1030), 6, C["red"])
            cv.line((1045, 1050), (1070, 1030), 6, C["red"])


def scene_phone(cv, t, D, o):
    ground(cv)
    sofa(cv, 540, 1210)
    pose = dict(SIT, lean=-6, head=30, aR1=12, aR2=118 + 4 * math.sin(t * 9), aL1=6, aL2=112)
    J = figure(cv, (520, 1215), pose, face=o.get("face", "tired"), col=fig_col(o))
    phone(cv, (J["hR"][0] + 4, J["hR"][1] + 20), glow_r=55)
    rnd = random.Random(3)
    for i in range(4):
        k = (t * 0.7 + i / 4) % 1
        x = J["hR"][0] + rnd.uniform(-80, 140)
        y = J["hR"][1] - 120 - 380 * k
        col = mix(C["red"], C["bg"], k)
        cv.circle((x - 12, y), 16, fill=col)
        cv.circle((x + 12, y), 16, fill=col)
        cv.poly([(x - 27, y + 6), (x + 27, y + 6), (x, y + 34)], col)


def scene_think(cv, t, D, o):
    ground(cv)
    b = math.sin(t * 2)
    J = figure(cv, (430, 0), dict(aR1=62, aR2=200 + 3 * b, head=-8, aL1=-8, aL2=-4),
               face=o.get("face", "neutral"), ground=GROUND, col=fig_col(o))
    bubble(cv, (720, 640), o.get("bubble", "?"), size=o.get("size", 140), anchor_pt=(J["head"][0] + 60, J["head"][1] - 60))


def stairs_y(x, x0=150, w=125, top=GROUND, h=110, n=6):
    k = int((x - x0) // w)
    k = max(0, min(n, k))
    return top - k * h


def scene_climb(cv, t, D, o):
    x0, w, h, n = 150, 125, 110, 6
    pts = [(60, GROUND), (x0, GROUND)]
    for k in range(n):
        y = GROUND - (k + 1) * h
        pts += [(x0 + k * w, y), (x0 + (k + 1) * w, y)]
    pts.append((1020, GROUND - n * h))
    cv.path(pts, 8, C["ink"])
    fx, fy = x0 + n * w + 40, GROUND - n * h
    cv.line((fx, fy), (fx, fy - 200), 7, C["ink"])
    cv.poly([(fx, fy - 200), (fx + 110, fy - 170), (fx, fy - 140)], C["gold"])
    p = min(1.0, t / (D * 0.92))
    x = 90 + (x0 + (n - 0.4) * w - 90) * p
    J = figure(cv, (x, 0), walk_pose(t * 1.8 * 2 * math.pi, amp=20, knee=45), ground=stairs_y(x + 15), face=o.get("face", "determined"),
               col=fig_col(o) or (C["gold"] if p > 0.97 else None))


def scene_lift(cv, t, D, o):
    ground(cv)
    s = (1 - math.cos(t * 1.4 * 2 * math.pi)) / 2
    pose = dict(lL1=-18, lL2=-12, lR1=18, lR2=12, aR1=95 + 75 * s, aR2=178, aL1=-(95 + 75 * s), aL2=-178)
    J = figure(cv, (540, 0), pose, face=o.get("face", "determined"), facing=0, ground=GROUND, col=fig_col(o))
    y = (J["hL"][1] + J["hR"][1]) / 2
    cv.line((J["hL"][0] - 170, y), (J["hR"][0] + 170, y), 12, C["ink"])
    for sx in (-1, 1):
        bx = (J["hR"][0] + 125) if sx > 0 else (J["hL"][0] - 125)
        cv.rect(bx - 20, y - 85, bx + 20, y + 85, fill=C["gold"], outline=C["ink"], w=5, rad=6)
        cv.rect(bx + sx * 25 - 15, y - 60, bx + sx * 25 + 15, y + 60, fill=C["gold"], outline=C["ink"], w=5, rad=6)
    if s > 0.6:
        cv.circle((J["head"][0] + 70, J["head"][1] - 10), 10, fill=(90, 150, 220))


def scene_work(cv, t, D, o):
    ground(cv)
    if o.get("night", True):
        window_night(cv, 120, 520)
    if o.get("time"):
        clock(cv, (860, 560), 90, o["time"])
    cv.rect(560, 1080, 960, 1105, fill=C["ink"], rad=6)
    cv.line((590, 1100), (590, GROUND), 9, C["ink"])
    cv.line((930, 1100), (930, GROUND), 9, C["ink"])
    cv.poly([(640, 1080), (800, 1080), (840, 930), (690, 930)], C["ink"])
    cv.circle((765, 1005), 16, fill=C["bg"])
    lamp_on = mix(C["bg"], C["glow"], 0.45)
    cv.circle((900, 900), 120, fill=lamp_on)
    cv.line((900, 1080), (900, 880), 7, C["ink"])
    cv.poly([(860, 880), (940, 880), (920, 830), (880, 830)], C["gold"])
    chair(cv, 400, 1150)
    tp = 3 * math.sin(t * 22)
    J = figure(cv, (420, 1145), dict(SIT, lean=8, head=6, aR1=58, aR2=98 + tp, aL1=50, aL2=92 - tp),
               face=o.get("face", "determined"), col=fig_col(o))


def scene_money(cv, t, D, o):
    ground(cv)
    rnd = random.Random(11)
    pile = 0
    for i in range(26):
        t0 = rnd.uniform(0, max(0.1, D - 0.4))
        x = rnd.uniform(120, 960)
        if t < t0:
            continue
        y = 300 + (t - t0) * 1100
        if y > GROUND - 32 - (i % 4) * 18:
            y = GROUND - 32 - (i % 4) * 18
            pile += 1
        coin(cv, (x, y), 32, rot=(t - t0) * 9 + i)
    j = abs(math.sin(t * 3.2)) * 40
    J = figure(cv, (540, 0), dict(aL1=-150, aL2=-165, aR1=150, aR2=165, lL1=-12, lR1=12),
               face=o.get("face", "happy"), facing=0, ground=GROUND - j,
           col=None if o.get("gold") is False else C["gold"])


def scene_push(cv, t, D, o):
    cv.poly([(0, 1560), (1080, 1000), (1080, 1920), (0, 1920)], C["soft"])
    cv.line((0, 1560), (1080, 1000), 8, C["ink"])
    p = t / D
    x = 300 + 160 * p + 6 * math.sin(t * 5)
    slope = (1560 - 1000) / 1080

    def gy(xx):
        return 1560 - xx * slope

    bx = x + 175
    cv.circle((bx, gy(bx) - 125), 125, fill=C["grey"], outline=C["ink"], w=8)
    pose = walk_pose(t * 1.1 * 2 * math.pi, amp=22, knee=40)
    pose.update(lean=42, head=-30, aL1=110, aL2=100, aR1=105, aR2=95)
    figure(cv, (x, 0), pose, face=o.get("face", "determined"), ground=gy(x) + 10, col=fig_col(o))


def scene_read(cv, t, D, o):
    ground(cv)
    chair(cv, 420, 1150)
    cv.rect(760, 1120, 900, 1140, fill=C["ink"], rad=4)
    cv.line((830, 1140), (830, GROUND), 8, C["ink"])
    cv.rect(790, 1060, 840, 1120, fill=C["bg"], outline=C["ink"], w=6, rad=6)
    for i in range(2):
        k = (t * 0.5 + i / 2) % 1
        cv.text((815 + 10 * math.sin(k * 6), 1030 - 100 * k), "~", 50, mix(C["grey"], C["bg"], k))
    J = figure(cv, (440, 1145), dict(SIT, lean=-4, head=20, aR1=40, aR2=140, aL1=30, aL2=135),
               face=o.get("face", "neutral"), col=fig_col(o))
    hx, hy = (J["hR"][0] + J["hL"][0]) / 2 + 10, (J["hR"][1] + J["hL"][1]) / 2 - 20
    flip = 6 * math.sin(t * 1.5)
    cv.poly([(hx, hy + 40), (hx - 70, hy + 10 + flip), (hx - 70, hy - 80 + flip), (hx, hy - 50)], C["bg"])
    cv.poly([(hx, hy + 40), (hx + 70, hy + 10), (hx + 70, hy - 80), (hx, hy - 50)], C["bg"])
    cv.path([(hx, hy + 40), (hx - 70, hy + 10 + flip), (hx - 70, hy - 80 + flip), (hx, hy - 50), (hx, hy + 40),
             (hx + 70, hy + 10), (hx + 70, hy - 80), (hx, hy - 50)], 6, C["gold"])


def scene_crowd(cv, t, D, o):
    ground(cv)
    n = 7
    for i in range(n):
        x = 110 + i * 143
        if i == n // 2:
            continue
        ph = t * 1.4 * 2 * math.pi + i
        if o.get("mode", "phones") == "phones":
            J = figure(cv, (x, 0), dict(head=26, lean=6, aR1=30, aR2=150, aL1=20, aL2=140), h=290,
                       col=C["grey"], face="tired", ground=GROUND)
            phone(cv, (J["hR"][0] + 4, J["hR"][1] + 8), glow=False)
        else:
            figure(cv, (x, 0), walk_pose(ph, amp=14), h=290, col=C["grey"], facing=-1, face="neutral", ground=GROUND)
    x = 110 + (n // 2) * 143
    figure(cv, (x, 0), walk_pose(t * 1.6 * 2 * math.pi, amp=22), h=330, col=C["gold"], face="determined",
           facing=1 if o.get("mode") == "phones" else 1, ground=GROUND)
    if o.get("arrow", True):
        k = ease(min(1, t / 0.6))
        cv.path([(x, 820 + 60 * (1 - k)), (x, 960)], 9, C["gold"])
        cv.poly([(x - 30, 950), (x + 30, 950), (x, 995)], C["gold"])


def scene_graph(cv, t, D, o):
    x0, y0, x1, y1 = 170, 1300, 960, 560
    cv.path([(x0, y1 - 40), (x0, y0), (x1 + 40, y0)], 8, C["ink"])
    cv.text(((x0 + x1) / 2, y0 + 55), o.get("x", "TIEMPO"), 52, C["ink"])
    p = min(1.0, t / (D * 0.85))
    N = 60
    if o.get("flat", True):
        cv.path([(x0 + (x1 - x0) * i / N, y0 - 60 - 25 * (i / N)) for i in range(int(N * p) + 1)], 9, C["grey"])
    pts = [(x0 + (x1 - x0) * i / N, y0 - 20 - (y0 - y1 - 20) * ((math.exp(3.2 * i / N) - 1) / (math.exp(3.2) - 1)))
           for i in range(int(N * p) + 1)]
    if len(pts) > 1:
        cv.path(pts, 11, C["gold"])
        cv.circle(pts[-1], 16, fill=C["gold"])
    if o.get("y"):
        cv.text((x0 + 20, y1 - 80), o["y"], 52, C["ink"], anchor="lm")
    if o.get("flat_label") and p > 0.6:
        cv.text((x1, y0 - 120), o["flat_label"], 44, C["grey"], anchor="rm")


def scene_clock(cv, t, D, o):
    ground(cv)
    clock(cv, (540, 700), 250, o.get("start", 6 * 60) + t * o.get("speed", 400))
    figure(cv, (540, 0), dict(head=-28, aL1=-12, aR1=12), h=380, face=o.get("face", "shock"), facing=0,
           ground=GROUND, col=fig_col(o))


# ---------------------------------------------------------------- motion graphics (sin personajes)
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_emoji = {}


def back(x):
    """Entrada con rebote (sobrepasa un poco y vuelve)."""
    x = max(0.0, min(1.0, x))
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def pop(t, delay=0.0, dur=0.32):
    return back((t - delay) / dur) if t > delay else 0.0


def emoji(cv, ch, c, size, k=1.0, alpha=1.0):
    """Pega un emoji a color (Noto Color Emoji) centrado en c, con escala k y opacidad."""
    if k <= 0.01 or alpha <= 0.01:
        return
    if ch not in _emoji:
        f = ImageFont.truetype(EMOJI_FONT, 109)
        im = Image.new("RGBA", (160, 160))
        ImageDraw.Draw(im).text((8, 8), ch, font=f, embedded_color=True)
        _emoji[ch] = im.crop(im.getbbox() or (0, 0, 160, 160))
    src = _emoji[ch]
    px = max(2, int(size * k * cv.z * SS))
    im = src.resize((px, int(px * src.height / src.width)), Image.LANCZOS)
    if alpha < 1:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im.putalpha(a)
    x, y = cv.P(c)
    cv.img.paste(im, (int(x - im.width / 2), int(y - im.height / 2)), im)


def rich_lines(txt, size, maxw=900):
    """Parte un texto en líneas; las palabras entre *asteriscos* van en dorado."""
    words, gold = [], False
    for w in txt.replace("\n", " \n ").split(" "):
        if not w:
            continue
        start = w.startswith("*")
        if start:
            gold = True
        words.append((w.replace("*", ""), gold))
        if w.rstrip(".,:;?!").endswith("*"):
            gold = False
    lines, cur = [], []
    for w, g in words:
        if w == "\n":
            lines.append(cur)
            cur = []
            continue
        test = " ".join(x for x, _ in cur + [(w, g)])
        if cur and font(size * SS).getlength(test.upper()) / SS > maxw:
            lines.append(cur)
            cur = []
        cur.append((w, g))
    if cur:
        lines.append(cur)
    return lines


def kinetic(cv, txt, t, y, size=140, step=0.11, maxw=900):
    """Texto grande que entra palabra a palabra con rebote."""
    lines = rich_lines(txt, size, maxw)
    lh = size * 1.12
    y0 = y - (len(lines) - 1) * lh / 2
    n = 0
    for li, ln in enumerate(lines):
        widths = [font(size * SS).getlength(w.upper()) / SS for w, _ in ln]
        sp = size * 0.28
        x = 540 - (sum(widths) + sp * (len(ln) - 1)) / 2
        for (w, g), wd in zip(ln, widths):
            k = pop(t, n * step, 0.3)
            if k > 0.02:
                cv.text((x + wd / 2, y0 + li * lh), w.upper(), size * k, C["gold"] if g else C["ink"])
            x += wd + sp
            n += 1


def mg_background(cv, t):
    """Fondo oscuro con rejilla tenue y partículas doradas que flotan."""
    if C["grid"] != C["bg"]:
        for x in range(0, 1081, 90):
            cv.line((x, 0), (x, 1920), 2, C["grid"])
        for y in range(0, 1921, 90):
            cv.line((0, y), (1080, y), 2, C["grid"])
    rnd = random.Random(21)
    for i in range(26):
        x = rnd.uniform(0, 1080)
        y = (rnd.uniform(0, 1920) - t * rnd.uniform(15, 45)) % 1920
        r = rnd.uniform(2, 6)
        cv.circle((x + 10 * math.sin(t + i), y), r, fill=mix(C["bg"], C["gold"], rnd.uniform(0.25, 0.6)))


def scene_title(cv, t, D, o):
    """Frase grande palabra a palabra. o: big (texto, *dorado*), icon (emoji opcional), size."""
    y = 1000
    if o.get("icon"):
        emoji(cv, o["icon"], (540, 640), 260, pop(t, 0, 0.35))
        y = 1060
    kinetic(cv, o.get("big", o.get("text", "")), t, y, o.get("size", 130), step=o.get("step", 0.11))


def scene_icons(cv, t, D, o):
    """Iconos que aparecen uno a uno con su rótulo. o: items [[emoji, texto]...], strike/check."""
    items = o.get("items", [])
    n = len(items)
    cols = 2 if n == 4 else n
    rows = 2 if n == 4 else 1
    for i, (ic, lab) in enumerate(items):
        cx = 540 + ((i % cols) - (cols - 1) / 2) * (330 if cols == 3 else 440)
        cy = 920 + ((i // cols) - (rows - 1) / 2) * 420
        k = pop(t, 0.15 + i * o.get("step", 0.35))
        cv.circle((cx, cy - 20), 135 * k, fill=C["soft"])
        emoji(cv, ic, (cx, cy - 20), 190 if cols < 3 else 160, k)
        if k > 0.5:
            cv.text((cx, cy + 170), lab.upper(), 62, C["ink"])
        end = 0.15 + n * o.get("step", 0.35) + 0.25 + i * 0.12
        if o.get("strike") and t > end:
            p = ease((t - end) / 0.2)
            cv.line((cx - 120, cy - 140), (cx - 120 + 240 * p, cy - 140 + 240 * p), 16, C["red"])
        if o.get("check") and t > end:
            emoji(cv, "✅", (cx + 110, cy - 120), 90, pop(t, end))


def scene_versus(cv, t, D, o):
    """Comparación arriba/abajo. o: top/bottom = {label, icon, text, bar (0-1)}."""
    for key, y0, col, delay in (("top", 470, C["grey"], 0.0), ("bottom", 990, C["gold"], 0.45)):
        p = o.get(key, {})
        k = ease((t - delay) / 0.35)
        if k <= 0:
            continue
        x_off = (1 - k) * (-700 if key == "top" else 700)
        cv.rect(70 + x_off, y0, 1010 + x_off, y0 + 460, fill=C["soft"], outline=col, w=6, rad=28)
        cv.text((130 + x_off, y0 + 70), p.get("label", "").upper(), 64, col, anchor="lm")
        emoji(cv, p.get("icon", "❔"), (230 + x_off, y0 + 245), 170, pop(t, delay + 0.15))
        lines = rich_lines(p.get("text", ""), 58, 560)
        for i, ln in enumerate(lines[:3]):
            cv.text((370 + x_off, y0 + 190 + i * 66), " ".join(w for w, _ in ln).upper(), 58, C["ink"], anchor="lm")
        if "bar" in p:
            v = p["bar"] * ease((t - delay - 0.3) / 0.9)
            cv.rect(130 + x_off, y0 + 375, 950 + x_off, y0 + 410, fill=C["grid"], rad=17)
            if v > 0.01:
                cv.rect(130 + x_off, y0 + 375, 130 + 820 * v + x_off, y0 + 410, fill=col, rad=17)


def scene_chart(cv, t, D, o):
    """Gráfica animada con área. o: y, x (rótulos), flat_label, end_label."""
    x0, y0, x1, y1 = 150, 1360, 960, 560
    cv.path([(x0, y1 - 40), (x0, y0), (x1 + 40, y0)], 6, C["grey"])
    cv.text(((x0 + x1) / 2, y0 + 60), o.get("x", "TIEMPO").upper(), 54, C["grey"])
    if o.get("y"):
        cv.text((x0 + 20, y1 - 80), o["y"].upper(), 54, C["grey"], anchor="lm")
    p = min(1.0, t / (D * 0.8))
    N = 60
    m = int(N * p) + 1
    if o.get("flat", True):
        cv.path([(x0 + (x1 - x0) * i / N, y0 - 70 - 30 * (i / N)) for i in range(m)], 8, C["grey"])
    pts = [(x0 + (x1 - x0) * i / N, y0 - 20 - (y0 - y1 - 20) * ((math.exp(3.2 * i / N) - 1) / (math.exp(3.2) - 1)))
           for i in range(m)]
    if len(pts) > 1:
        cv.poly(pts + [(pts[-1][0], y0), (x0, y0)], mix(C["bg"], C["gold"], 0.18))
        cv.path(pts, 12, C["gold"])
        cv.circle(pts[-1], 26, fill=mix(C["bg"], C["gold"], 0.4))
        cv.circle(pts[-1], 15, fill=C["gold"])
    if o.get("flat_label") and p > 0.5:
        cv.text((x1, y0 - 140), o["flat_label"].upper(), 50, C["grey"], anchor="rm")
    if o.get("end_label") and p >= 1:
        k = pop(t, D * 0.8)
        if k > 0.02:
            cv.text((pts[-1][0] - 40, pts[-1][1] - 70), o["end_label"].upper(), 64 * k, C["gold"], anchor="rm")


def scene_flow(cv, t, D, o):
    """Pasos en cadena de arriba abajo con flechas. o: steps [[emoji, texto]...]."""
    steps = o.get("steps", [])
    gap = min(300, 900 / max(1, len(steps) - 1)) if len(steps) > 1 else 0
    ytop = 1000 - gap * (len(steps) - 1) / 2
    for i, (ic, lab) in enumerate(steps):
        y = ytop + i * gap
        d = 0.1 + i * o.get("step", 0.45)
        k = pop(t, d)
        cv.circle((300, y), 105 * k, fill=C["soft"], outline=C["gold"] if i == len(steps) - 1 else C["grey"], w=5)
        emoji(cv, ic, (300, y), 130, k)
        if k > 0.3:
            col = C["gold"] if i == len(steps) - 1 else C["ink"]
            sz = 70
            while sz > 40 and font(sz * SS).getlength(lab.upper()) / SS > 580:
                sz -= 4
            cv.text((450, y), lab.upper(), sz, col, anchor="lm")
        if i < len(steps) - 1 and t > d + 0.25:
            a = ease((t - d - 0.25) / 0.2)
            cv.line((300, y + 120), (300, y + 120 + (gap - 240) * a), 9, C["grey"])
            if a >= 1:
                cv.poly([(280, y + gap - 135), (320, y + gap - 135), (300, y + gap - 112)], C["grey"])


def scene_drain(cv, t, D, o):
    """Algo que se vacía: icono grande, barra que baja y cosas que salen volando.
    o: icon, bar_label, out (lista de emojis), to (nivel final 0-1)."""
    k = pop(t, 0, 0.35)
    emoji(cv, o.get("icon", "👛"), (540, 760), 300, k)
    rnd = random.Random(5)
    outs = o.get("out", ["📱", "🚗", "🏠", "🛍️"])
    for i in range(10):
        t0 = 0.4 + i * (D - 0.8) / 10
        if t < t0:
            continue
        q = (t - t0) / 0.9
        if q > 1:
            continue
        ang = rnd.uniform(-1, 1)
        x = 540 + ang * 520 * q
        y = 760 - 380 * q + 520 * q * q
        emoji(cv, outs[i % len(outs)], (x, y), 110, 1, 1 - q * q)
    lvl = 1 - (1 - o.get("to", 0.06)) * ease((t - 0.3) / (D - 0.6))
    col = C["gold"] if lvl > 0.35 else C["red"]
    cv.text((540, 1090), o.get("bar_label", "SUELDO").upper(), 64, C["ink"])
    cv.rect(150, 1150, 930, 1210, fill=C["grid"], rad=30)
    cv.rect(150, 1150, 150 + max(60, 780 * lvl), 1210, fill=col, rad=30)


def scene_question(cv, t, D, o):
    """Gran interrogación dorada que late y una pregunta debajo. o: big."""
    k = (1 + 0.06 * math.sin(t * 5)) * pop(t, 0, 0.35)
    if k > 0.02:
        cv.text((540, 720), "?", 520 * k, C["gold"])
    kinetic(cv, o.get("big", ""), t, 1180, o.get("size", 96), step=0.09)


SCENES = {k[6:]: v for k, v in globals().items() if k.startswith("scene_")}
SCENES["sad"] = scene_walk


def label_box(cv, txt, y, size=96):
    w = font(size * SS).getlength(txt) / SS + 80
    cv.rect(540 - w / 2, y - size * 0.75, 540 + w / 2, y + size * 0.75, fill=C["box"], rad=14)
    cv.text((540, y), txt, size, C["gold"])


ZOOM = dict(title=1.0, icons=1.0, versus=1.0, chart=1.0, flow=1.0, drain=1.0, question=1.0, climb=1.0, graph=1.0, push=1.05, crowd=1.08, money=1.08, sleep=1.12, clock=1.0, lift=1.15)


def render(o, t, D, z=1.0):
    cv = Cv(z=z, cy=1060)
    if C.get("grid"):
        z0, cv.z = cv.z, 1.0
        mg_background(cv, t)
        cv.z = z0
    SCENES[o.get("scene", "stand")](cv, t, D, o)
    return cv


# ---------------------------------------------------------------- personaje de dibujos (tema "toon")
# Mascota propia del canal, en ilustración plana: busto abajo, gráfico en una tarjeta arriba.
# Habla con la voz (la boca se abre según el volumen), parpadea y cambia de pose y de cara.
AMP = None          # volumen de la voz por fotograma (0-1), lo rellena main()
CUR_T = 0.0         # tiempo global del vídeo en el fotograma actual
SKIN, SKIN_D = (238, 196, 158), (214, 164, 126)
HAIR = (38, 30, 34)
HOODIE = {"TÚ": ((222, 166, 44), (186, 134, 28)), "EL RESTO": ((112, 112, 128), (88, 88, 102))}
HOODIE_DEF = ((62, 92, 168), (46, 70, 134))


def amp_now():
    if AMP is None or len(AMP) == 0:
        return 0.0
    return float(AMP[min(len(AMP) - 1, int(CUR_T * FPS))])


def ellipse(cv, c, rx, ry, fill):
    x, y = cv.P(c)
    cv.d.ellipse([x - rx * cv.z * SS, y - ry * cv.z * SS, x + rx * cv.z * SS, y + ry * cv.z * SS], fill=fill)


ARM_POSES = {
    # (codo, mano, tipo de mano, delante de la cara) por brazo; None = brazo abajo, fuera de cuadro
    "idle": (None, None),
    "up": (((170, 1500), (195, 1170), "open", False), ((910, 1500), (885, 1170), "open", False)),
    "celebrate": (((170, 1480), (210, 1130), "fist", False), ((910, 1480), (870, 1130), "fist", False)),
    "wave": (None, ((905, 1480), (930, 1150), "open", False)),
    "point": (None, ((905, 1500), (895, 1090), "point", False)),
    "think": (None, ((770, 1760), (625, 1450), "fist", True)),
    "facepalm": (None, ((810, 1700), (600, 1110), "open", True)),
    "shrug": (((170, 1720), (105, 1545), "open", False), ((910, 1720), (975, 1545), "open", False)),
    "thumbs": (None, ((880, 1720), (860, 1470), "thumb", True)),
    "cross": (((250, 1820), (720, 1770), "fist", True), ((830, 1820), (360, 1750), "fist", True)),
}
POSE_FACE = {"up": "happy", "celebrate": "happy", "wave": "happy", "thumbs": "happy", "facepalm": "sad",
             "shrug": "serious", "think": "serious", "cross": "serious", "point": "happy"}


def draw_arm(cv, sh, el, hand, kind, col, t, wiggle=0.0):
    hx, hy = hand
    hx += wiggle
    cv.line(sh, el, 116, col[1])
    cv.line(el, (hx, hy), 112, col[1])
    cv.line(sh, el, 100, col[0])
    cv.line(el, (hx, hy), 96, col[0])
    cv.circle((hx, hy + 8), 64, fill=SKIN)
    if kind == "open":
        for i, dx in enumerate((-42, -14, 14, 42)):
            cv.line((hx + dx, hy - 10), (hx + dx * 1.15, hy - 78 + abs(dx) * 0.35), 30, SKIN)
        cv.line((hx - 50, hy + 20), (hx - 92, hy - 10), 30, SKIN)
    elif kind == "point":
        cv.line((hx - 10, hy - 20), (hx - 10, hy - 125), 30, SKIN)
    elif kind == "thumb":
        cv.line((hx, hy - 30), (hx, hy - 110), 34, SKIN)
    cv.circle((hx - 18, hy + 22), 10, fill=SKIN_D)


def mascot(cv, t, o):
    lab = o.get("label") or o.get("who")
    col = HOODIE.get((lab or "").upper(), HOODIE_DEF)
    pose = o.get("pose", "idle")
    a = amp_now()
    by = -10 * a + 5 * math.sin(CUR_T * 2.2)
    if pose == "celebrate":
        by -= 26 * abs(math.sin(t * 6))
    sx = 6 * math.sin(CUR_T * 1.3)
    face = o.get("face") or POSE_FACE.get(pose) or {"TÚ": "happy", "EL RESTO": "serious"}.get((lab or "").upper(), "happy")
    arms = ARM_POSES.get(pose, ARM_POSES["idle"])
    shoulders = ((330, 1650 + by), (750, 1650 + by))
    wig = 26 * math.sin(t * 11) if pose == "wave" else 0
    # torso
    cv.rect(190, 1560 + by, 890, 2100, fill=col[0], rad=200)
    ellipse(cv, (540, 1580 + by), 190, 70, col[1])
    cv.rect(475, 1430 + by, 605, 1590 + by, fill=SKIN_D, rad=30)
    cv.line((500, 1630 + by), (490, 1760 + by), 10, (245, 240, 230))
    cv.line((580, 1630 + by), (590, 1760 + by), 10, (245, 240, 230))
    # brazos detrás de la cabeza
    for side, arm in enumerate(arms):
        if arm and not arm[3]:
            draw_arm(cv, shoulders[side], arm[0], arm[1], arm[2], col, t, wig if side == 1 else 0)
    # cabeza
    hx, hy = 540 + sx, 1235 + by
    for s_ in (-1, 1):
        cv.circle((hx + s_ * 222, hy + 25), 50, fill=SKIN)
        cv.circle((hx + s_ * 226, hy + 25), 26, fill=SKIN_D)
    ellipse(cv, (hx, hy), 222, 248, SKIN)
    ellipse(cv, (hx, hy - 205), 228, 110, HAIR)
    for dx, dy, r in ((-175, -165, 78), (-95, -245, 82), (0, -262, 86), (95, -245, 82), (175, -165, 78),
                      (-205, -95, 44), (205, -95, 44)):
        cv.circle((hx + dx, hy + dy), r, fill=HAIR)
    cv.poly([(hx - 150, hy - 150), (hx - 40, hy - 150), (hx - 110, hy - 85)], HAIR)
    cv.poly([(hx - 50, hy - 160), (hx + 120, hy - 160), (hx + 20, hy - 92)], HAIR)
    # cejas
    br = {"sad": (-14, 14), "shock": (-26, -26), "serious": (10, -10), "smirk": (-4, -18)}.get(face, (0, 0))
    for s_, d in ((-1, br[0]), (1, br[1])):
        ex = hx + s_ * 95
        cv.line((ex - 46, hy - 98 + (d if s_ < 0 else -d) * 0.5 + (d * 0.5)), (ex + 46, hy - 98 - (d if s_ < 0 else -d) * 0.5 + (d * 0.5)), 20, HAIR)
    # ojos (parpadeo cada ~3,7 s)
    blink = (CUR_T % 3.7) < 0.12 or face == "closed" or pose == "facepalm"
    lx, ly = (0, -10) if pose in ("point", "think", "up") else (0, 0)
    for s_ in (-1, 1):
        ex, ey = hx + s_ * 95, hy - 22
        if blink:
            cv.line((ex - 34, ey + 6), (ex + 34, ey + 6), 12, HAIR)
            continue
        ellipse(cv, (ex, ey), 40, 48, (255, 255, 255))
        cv.circle((ex + lx, ey + 4 + ly), 23, fill=(28, 24, 30))
        cv.circle((ex + lx + 8, ey - 6 + ly), 8, fill=(255, 255, 255))
    # nariz y mejillas
    ellipse(cv, (hx, hy + 55), 24, 17, SKIN_D)
    for s_ in (-1, 1):
        ellipse(cv, (hx + s_ * 150, hy + 80), 40, 23, mix(SKIN, (240, 120, 120), 0.45))
    # boca: se abre con el volumen de la voz
    mx, my = hx, hy + 135
    op = min(1.0, a * 1.3)
    dark, tongue = (70, 22, 30), (226, 102, 112)
    if face in ("happy", "smirk"):
        h = 26 + 60 * op
        pts = [(mx - 70 + 140 * i / 16, my + h * math.sin(math.pi * i / 16)) for i in range(17)]
        cv.poly([(mx - 70, my)] + pts + [(mx + 70, my)], dark)
        cv.rect(mx - 52, my - 2, mx + 52, my + 14, fill=(255, 255, 255), rad=6)
        if h > 45:
            ellipse(cv, (mx, my + h * 0.75), 34, h * 0.22, tongue)
    elif face == "sad":
        h = 14 + 40 * op
        pts = [(mx - 55 + 110 * i / 16, my + 20 - h * math.sin(math.pi * i / 16)) for i in range(17)]
        cv.poly(pts, dark)
        cv.path(pts, 8, dark)
    elif face == "shock":
        ellipse(cv, (mx, my + 10), 34, 34 + 26 * op, dark)
    else:
        h = 10 + 46 * op
        cv.rect(mx - 48, my - h / 2 + 8, mx + 48, my + h / 2 + 8, fill=dark, rad=min(18, h / 2))
    # brazos delante de la cara
    for side, arm in enumerate(arms):
        if arm and arm[3]:
            draw_arm(cv, shoulders[side], arm[0], arm[1], arm[2], col, t)
    # etiqueta en el pecho
    if lab:
        label_box(cv, lab.upper(), 1755 + by, 64)


def toon_frame(o, t, D):
    cv = Cv()
    mg_background(cv, t)
    cv.rect(60, 120, 1020, 830, fill=C["soft"], outline=C["gold"], w=5, rad=44)
    if o.get("scene") and o["scene"] in SCENES:
        k = 0.62 * (1 + 0.04 * t / D)
        cv.z, cv.cx, cv.cy, cv.oy = k, 540, 960, 475 - 960
        SCENES[o["scene"]](cv, t, D, o)
        cv.z, cv.cx, cv.cy = 1.0, 540, 1000
    cv.oy = 110  # el personaje baja para dejar sitio a los subtítulos bajo la tarjeta
    mascot(cv, t, o)
    cv.oy = 0
    hook = o.get("hook") if o.get("hook") and t < o.get("hook_dur", 2.4) else None
    if hook:
        hook_text(cv, hook, t)
    return cv.final()


def frame(o, t, D):
    if C.get("toon"):
        return toon_frame(o, t, D)
    labels = []
    if o.get("scene") == "split":
        cv = Cv()
        band = (8 * SS, 590 * SS, 1072 * SS, 1420 * SS)
        ph, pw = 610, int(1064 * 610 / 830)
        for key, top in (("top", 220), ("bottom", 880)):
            sub = dict(o.get(key, {}))
            img = render(sub, t, D).img.crop(band).resize((pw * SS, ph * SS), Image.LANCZOS)
            x = (W - pw) // 2
            cv.img.paste(img, (x * SS, top * SS))
            cv.rect(x, top, x + pw, top + ph, outline=C["ink"], w=8, rad=4)
            if sub.get("label"):
                labels.append((sub["label"], top + 58, 60))
    else:
        z = ZOOM.get(o.get("scene", "stand"), 1.22) * o.get("zoom", 1)
        z *= 1 + 0.045 * t / D + (0.07 * (1 - t / 0.25) ** 2 if t < 0.25 else 0)
        cv = render(o, t, D, z)
    cv.z, cv.cx, cv.cy = 1.0, 540, 1000
    hook = o.get("hook") if o.get("hook") and t < o.get("hook_dur", 2.4) else None
    if not hook and o.get("label"):
        labels.append((o["label"], 300, 96))
    if C.get("pixel"):
        # En 8 bits los textos se dibujan después de pixelar, para que la letra pixel salga nítida.
        img = cv.final()
        d = ImageDraw.Draw(img)
        for txt, y, size in labels:
            pixel_box(d, [txt.upper()], y, 72 if size > 80 else 48)
        if hook and t > 0.04:
            pixel_box(d, wrap_words(hook.upper(), 108, 900), 330, 108, last_gold=True)
        return img
    for lab in labels:
        label_box(cv, *lab)
    if hook:
        hook_text(cv, hook, t)
    return cv.final()


def pixel_font(px):
    return load_font(FONT_DIR / THEMES["8bit"]["font"], px)


def wrap_words(txt, px, maxw):
    lines = []
    for w in txt.split():
        if lines and pixel_font(px).getlength(lines[-1] + " " + w) <= maxw:
            lines[-1] += " " + w
        else:
            lines.append(w)
    return lines


def pixel_box(d, lines, y, px, last_gold=False):
    """Cuadro de diálogo de videojuego: fondo negro, borde blanco de 6 px y letra pixel."""
    f, lh = pixel_font(px), px + px // 2
    w = max(f.getlength(ln) for ln in lines) + 2 * px
    h = lh * len(lines) + px // 2
    x0, y0 = 540 - w / 2, y - h / 2
    d.rectangle([x0 - 6, y0 - 6, x0 + w + 6, y0 + h + 6], fill=C["ink"])
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=(0, 0, 0))
    for i, ln in enumerate(lines):
        col = C["gold"] if (i == len(lines) - 1 or not last_gold) else C["ink"]
        d.text((540, y0 + px // 2 + lh * i + lh / 2 - px // 8), ln, font=f, fill=col, anchor="mm")


def hook_text(cv, txt, t, size=132):
    """Texto gancho grande (2-4 palabras) que entra con un golpe de escala en el
    primer segundo y medio: lo primero que se lee antes de deslizar."""
    words, lines = txt.upper().split(), []
    for w in words:
        if lines and font(size * SS).getlength(lines[-1] + " " + w) / SS < 900:
            lines[-1] += " " + w
        else:
            lines.append(w)
    k = 1 + 0.35 * (1 - ease(t / 0.18))
    cv.z, cv.cx, cv.cy = k, 540, 330
    y0 = 330 - (len(lines) - 1) * size * 0.62
    for i, ln in enumerate(lines):
        y = y0 + i * size * 1.24
        w = font(size * SS).getlength(ln) / SS + 70
        cv.rect(540 - w / 2, y - size * 0.68, 540 + w / 2, y + size * 0.68, fill=C["box"], rad=16)
        cv.text((540, y + 4), ln, size, C["gold"] if i == len(lines) - 1 else (255, 255, 255))
    cv.z, cv.cx, cv.cy = 1.0, 540, 1000


# ---------------------------------------------------------------- audio, subtítulos y montaje
def whoosh_track(cuts, total, path, sr=48000):
    rnd = np.random.default_rng(5)
    out = np.zeros(int((total + 1) * sr), dtype=np.float32)
    n = int(0.28 * sr)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    noise = rnd.standard_normal(n).astype(np.float32)
    k = 40
    smooth = np.convolve(noise, np.ones(k) / k, mode="same")
    w = (smooth * env * 0.9).astype(np.float32)
    for c in cuts:
        i = max(0, int((c - 0.12) * sr))
        out[i:i + n] += w[: len(out) - i]
    out = np.clip(out, -1, 1)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes((out * 32767).astype(np.int16).tobytes())


def blip_track(cuts, total, path, sr=48000):
    """Sonido chiptune: dos notas de onda cuadrada que suben en cada corte."""
    out = np.zeros(int((total + 1) * sr), dtype=np.float32)
    n = int(0.06 * sr)
    tt = np.arange(n) / sr
    env = np.linspace(1, 0, n) ** 1.5
    note = lambda f: (np.sign(np.sin(2 * np.pi * f * tt)) * env * 0.35).astype(np.float32)
    w = np.concatenate([note(660), note(990)])
    for c in cuts:
        i = max(0, int((c - 0.06) * sr))
        out[i:i + len(w)] += w[: len(out) - i]
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())


def norm(w):
    return re.sub(r"[^\w]", "", w).lower()


def narrate_flow(lines, voice, work, rate="+8%", pitch="-3Hz"):
    """Narra el guion entero en una sola toma (entonación y ritmo naturales entre frases)
    y usa los tiempos reales de cada palabra para cortar escenas y sincronizar subtítulos."""
    import shutil
    txt, mp3, js = work / "guion.txt", work / "voz.mp3", work / "palabras.json"
    txt.write_text(" ".join(ln["text"].strip() for ln in lines), encoding="utf-8")
    exe = shutil.which("edge-tts")
    py = str(Path(exe).resolve().parent / "python") if exe else sys.executable
    run([py, str(HERE / "tts_words.py"), str(txt), voice, str(mp3), str(js), rate, pitch], capture_output=True)
    bnd = json.loads(js.read_text(encoding="utf-8"))
    # recortar los silencios largos entre frases para un ritmo continuo de Short
    sr = 48000
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
                                   "-ar", str(sr), "-"])
    audio = np.frombuffer(raw, dtype=np.int16)
    maxgap, keep, shift, pos, out = 0.26, [], 0.0, 0, []
    for k, (s0, e0, w) in enumerate(bnd):
        if k > 0:
            gap = s0 - bnd[k - 1][1]
            if gap > maxgap:
                cut0 = int((bnd[k - 1][1] + maxgap * 0.5) * sr)
                cut1 = int((s0 - maxgap * 0.5) * sr)
                out.append(audio[pos:cut0])
                pos = cut1
                shift += (cut1 - cut0) / sr
        keep.append([s0 - shift, e0 - shift, w])
    out.append(audio[pos:])
    bnd = keep
    pcm = work / "voz_raw.wav"
    with wave.open(str(pcm), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(np.concatenate(out).tobytes())
    voz = work / "voz.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(pcm), "-af", "loudnorm=I=-14:TP=-1.5,aresample=48000",
         "-ac", "1", str(voz)])
    total = duration(voz) + 0.3
    # alinear cada palabra del guion con su marca de tiempo (tolerando signos sueltos)
    words, firsts, j = [], [], 0
    for ln in lines:
        first = None
        for w in ln["text"].split():
            key = norm(w)
            hit = None
            for k in range(j, min(j + 4, len(bnd))):
                if norm(bnd[k][2]) == key or (key and norm(bnd[k][2]).startswith(key[:4])):
                    hit = k
                    break
            if hit is not None:
                s0, e0 = bnd[hit][0], bnd[hit][1]
                j = hit + 1
            else:
                s0 = words[-1][1] if words else 0.0
                e0 = s0 + 0.2
            words.append((s0, e0, w))
            first = s0 if first is None else first
        firsts.append(first if first is not None else (words[-1][0] if words else 0.0))
    starts = [0.0] + [max(0.0, f - 0.12) for f in firsts[1:]]
    segs = []
    for i, ln in enumerate(lines):
        end = starts[i + 1] if i + 1 < len(lines) else total
        segs.append(dict(dur=max(0.4, end - starts[i]), start=starts[i], o=ln))
    # alargar cada palabra hasta la siguiente para que el subtítulo no parpadee
    words = [(s0, max(e0, words[k + 1][0]) if k + 1 < len(words) and words[k + 1][0] - e0 < 0.35 else e0, w)
             for k, (s0, e0, w) in enumerate(words)]
    return segs, words, total, voz


def narrate_lines(lines, voice, work):
    """Modo antiguo: una toma por frase con pausa fija entre frases."""
    segs, words, t = [], [], 0.0
    for i, ln in enumerate(lines):
        mp3, wav = work / f"l{i}.mp3", work / f"l{i}.wav"
        tts(ln["text"], voice, mp3)
        trim = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af", trim, "-ar", "44100", "-ac", "1", str(wav)])
        d = duration(wav)
        pause = ln.get("pause", 0.3 if ln["text"].rstrip().endswith((".", ":", "?", "!")) else 0.14)
        ws = ln["text"].split()
        weight = [len(re.sub(r"\W", "", w)) + 1.5 for w in ws]
        c = t
        for w, wt in zip(ws, weight):
            wd = d * wt / sum(weight)
            words.append((c, c + wd, w))
            c += wd
        segs.append(dict(wav=wav, dur=d + pause, start=t, o=ln))
        t += d + pause
    total = t

    inputs, fc = [], ""
    for i, s in enumerate(segs):
        inputs += ["-i", str(s["wav"])]
        fc += f"[{i}:a]apad=whole_dur={s['dur']:.3f}[a{i}];"
    fc += "".join(f"[a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1,loudnorm=I=-14:TP=-1.5,aresample=48000[a]"
    voz = work / "voz.wav"
    run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", fc, "-map", "[a]", str(voz)])
    return segs, words, total, voz


def main(spec_path):
    global AMP, CUR_T
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    C.update(THEMES[spec.get("theme", "light")])
    base = Path(spec_path).resolve().parent
    out = (base / spec["out"]).resolve()
    work = out.parent / (out.stem + "_work")
    work.mkdir(parents=True, exist_ok=True)
    voice = spec.get("voice", "es-ES-AlvaroNeural")
    lines = spec["lines"]

    if spec.get("tts", "flow") == "flow":
        segs, words, total, voz = narrate_flow(lines, voice, work, spec.get("rate", "+8%"), spec.get("pitch", "-3Hz"))
    else:
        segs, words, total, voz = narrate_lines(lines, voice, work)
    with wave.open(str(voz)) as wf:
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
        raw = raw.reshape(-1, wf.getnchannels()).mean(axis=1)
        spf = wf.getframerate() // FPS
    n = len(raw) // spf
    rms = np.sqrt((raw[: n * spf].reshape(n, spf) ** 2).mean(axis=1))
    AMP = np.clip(rms / (np.percentile(rms, 95) + 1e-6), 0, 1)
    AMP = np.convolve(AMP, [0.25, 0.5, 0.25], mode="same")
    sfx = work / "sfx.wav"
    (blip_track if C.get("sfx") == "blip" else whoosh_track)([s["start"] for s in segs[1:]], total, sfx)

    def ts(x):
        return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"

    ass = ["[Script Info]", "PlayResX: 1080", "PlayResY: 1920", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding",
           f"Style: W,{C.get('sub_font', 'Anton')},{C.get('sub_size', 124)},&H00FFFFFF,&H00FFFFFF,&H00000000,"
           f"&H64000000,0,0,0,0,100,100,1,0,1,{8 if C.get('pixel') else 7},{0 if C.get('pixel') else 2},"
           "5,60,60,0,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.,:;?!]$", w[2]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else 1e9
        for k, (s, e, _) in enumerate(ch):
            end = ch[k + 1][0] if k + 1 < len(ch) else min(e + 0.05, nxt)
            txt = " ".join(("{\\c" + C.get("hi", "&H00D7FF&") + "}" + x[2].upper() + "{\\c&HFFFFFF&}")
                           if j == k else x[2].upper()
                           for j, x in enumerate(ch))
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            ass.append(f"Dialogue: 0,{ts(s)},{ts(end)},W,,0,0,0,,{{\\pos(540,{C.get('sub_y', 1660)})}}{pop}{txt}")
    subs = work / "subs.ass"
    subs.write_text("\n".join(ass), encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(voz), "-i", str(sfx), "-filter_complex",
         f"[0:v]subtitles={subs}:fontsdir={FONT_DIR}[v];[2:a]volume=0.35[s];"
         f"[1:a][s]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    nframes = int(math.ceil(total * FPS))
    si = 0
    for n in range(nframes):
        tt = n / FPS
        while si + 1 < len(segs) and tt >= segs[si + 1]["start"]:
            si += 1
        s = segs[si]
        CUR_T = tt
        ff.stdin.write(frame(s["o"], tt - s["start"], s["dur"]).tobytes())
    ff.stdin.close()
    if ff.wait():
        sys.exit("ffmpeg falló")
    print(f"OK {out} ({total:.1f} s)")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--preview":
        # Vista rápida de todas las escenas sin voz: python3 stickman_short.py --preview carpeta
        dst = Path(sys.argv[2])
        dst.mkdir(parents=True, exist_ok=True)
        demo = {"split": {"scene": "split", "top": {"scene": "phone", "label": "EL RESTO"},
                          "bottom": {"scene": "work", "label": "TÚ"}},
                "think": {"scene": "think", "bubble": "¿Y SI...?", "size": 70},
                "graph": {"scene": "graph", "y": "RESULTADOS"}, "sleep": {"scene": "sleep", "alarm": True}}
        for name in list(SCENES) + ["split"]:
            o = demo.get(name, {"scene": name})
            frame(o, 1.3, 3.0).save(dst / f"{name}.jpg", quality=85)
        print("OK", dst)
    elif len(sys.argv) != 2:
        sys.exit("uso: python3 stickman_short.py spec.json")
    else:
        main(sys.argv[1])
