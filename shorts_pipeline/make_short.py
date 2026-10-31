#!/usr/bin/env python3
"""
Genera un Short vertical (1080x1920) a partir de un guion en JSON:
voz neuronal gratuita (edge-tts), fotos con zoom/paneo, transiciones
suaves y subtítulos palabra a palabra.

Uso:
    python3 make_short.py spec.json

spec.json:
{
  "out": "salida/mi_short.mp4",
  "voice": "es-ES-AlvaroNeural",        (opcional)
  "lines": [
    {"text": "Las cinco de la mañana.", "image": "img/1.jpg", "label": ""},
    {"text": "El motivado, la pospone.", "image": "img/2.jpg", "label": "MOTIVADO"}
  ]
}

Requisitos: ffmpeg con libass, Python 3 y `pip install edge-tts`.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "fonts"
FONT = FONT_DIR / "Anton-Regular.ttf"
FPS = 30
XF = 0.35  # duración de cada transición


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def duration(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def tts(text, voice, mp3):
    cmd = ["edge-tts", "--voice", voice, "--rate=+4%", "--pitch=-3Hz", "--text", text, "--write-media", str(mp3)]
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        cmd[1:1] = ["--proxy", proxy]
    run(cmd, capture_output=True)


def main(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    base = Path(spec_path).resolve().parent
    out = (base / spec["out"]).resolve()
    work = out.parent / (out.stem + "_work")
    work.mkdir(parents=True, exist_ok=True)
    voice = spec.get("voice", "es-ES-AlvaroNeural")
    lines = spec["lines"]

    # 1. Voz por frase, sin silencios al principio ni al final
    segs, words, t = [], [], 0.0
    for i, ln in enumerate(lines):
        mp3, wav = work / f"l{i}.mp3", work / f"l{i}.wav"
        tts(ln["text"], voice, mp3)
        trim = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af", trim, "-ar", "44100", "-ac", "1", str(wav)])
        d = duration(wav)
        pause = 0.28 if ln["text"].rstrip().endswith((".", ":", "?", "!")) else 0.12
        # tiempos por palabra, proporcionales a su longitud
        ws = ln["text"].split()
        weight = [len(re.sub(r"\W", "", w)) + 1.5 for w in ws]
        c = t
        for w, wt in zip(ws, weight):
            wd = d * wt / sum(weight)
            words.append((c, c + wd, w))
            c += wd
        segs.append({"wav": wav, "dur": d + pause, "image": (base / ln["image"]).resolve(), "label": ln.get("label", "")})
        t += d + pause

    # 2. Pista de voz continua y normalizada
    inputs, fc = [], ""
    for i, s in enumerate(segs):
        inputs += ["-i", str(s["wav"])]
        fc += f"[{i}:a]apad=whole_dur={s['dur']:.3f}[a{i}];"
    fc += "".join(f"[a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1,loudnorm=I=-14:TP=-1.5[a]"
    voz = work / "voz.wav"
    run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", fc, "-map", "[a]", str(voz)])

    # 3. Un clip por imagen con movimiento de cámara y etiqueta opcional
    moves = [
        "z='min(zoom+0.0016,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='1.15':x='(iw-iw/zoom)*on/{F}':y='ih/2-(ih/zoom/2)'",
        "z='if(eq(on,0),1.2,max(zoom-0.0016,1.02))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='1.15':x='(iw-iw/zoom)*(1-on/{F})':y='ih/2-(ih/zoom/2)'",
    ]
    clips = []
    for i, s in enumerate(segs):
        D = s["dur"] + XF
        F = int(D * FPS) + 1
        vf = (f"scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
              f"zoompan={moves[i % 4].replace('{F}', str(F))}:d={F}:s=1080x1920:fps={FPS},"
              f"eq=brightness=-0.06:saturation=0.9:contrast=1.05,vignette=PI/4")
        if s["label"]:
            vf += (f",drawbox=x=(iw-760)/2:y=300:w=760:h=150:color=black@0.55:t=fill,"
                   f"drawtext=fontfile={FONT}:text='{s['label']}':fontsize=110:fontcolor=0xE8C578:"
                   f"x=(w-text_w)/2:y=318")
        clip = work / f"v{i}.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(s["image"]), "-vf", vf + ",format=yuv420p",
             "-frames:v", str(F), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(clip)])
        clips.append((clip, D))

    # 4. Subtítulos ASS: bloques de 3 palabras, la palabra actual en amarillo
    def ts(x):
        return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"

    ass = ["[Script Info]", "PlayResX: 1080", "PlayResY: 1920", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding",
           "Style: W,Anton,138,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,6,2,5,60,60,0,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.,:;?!]$", w[2]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    for ch in chunks:
        for k, (s, e, _) in enumerate(ch):
            end = ch[k + 1][0] if k + 1 < len(ch) else e + 0.05
            txt = " ".join(("{\\c&H00D7FF&}" + x[2].upper() + "{\\c&HFFFFFF&}") if j == k else x[2].upper()
                           for j, x in enumerate(ch))
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            ass.append(f"Dialogue: 0,{ts(s)},{ts(end)},W,,0,0,0,,{{\\pos(540,1180)}}{pop}{txt}")
    subs = work / "subs.ass"
    subs.write_text("\n".join(ass), encoding="utf-8")

    # 5. Encadenar con transiciones, quemar subtítulos y añadir la voz
    inputs, fc, prev, off = [], "", "[0:v]", 0.0
    for clip, _ in clips:
        inputs += ["-i", str(clip)]
    for i in range(1, len(clips)):
        off += clips[i - 1][1] - XF
        tr = ["fade", "smoothleft", "fadeblack", "smoothup"][i % 4]
        fc += f"{prev}[{i}:v]xfade=transition={tr}:duration={XF}:offset={off:.3f}[x{i}];"
        prev = f"[x{i}]"
    fc += f"{prev}subtitles={subs}:fontsdir={FONT_DIR}[vout]"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-i", str(voz), "-filter_complex", fc,
         "-map", "[vout]", "-map", f"{len(clips)}:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)])
    print(f"OK {out} ({t:.1f} s)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python3 make_short.py spec.json")
    main(sys.argv[1])
