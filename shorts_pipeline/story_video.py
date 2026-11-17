"""Vídeo vertical de "historia en segunda persona": una ilustración por frase con zoom/paneo suave
(efecto Ken Burns), voz con edge-tts y subtítulos palabra a palabra.

Uso: python story_video.py story.json carpeta_imagenes salida.mp4 [voz] [rate] [pitch]
story.json: {"hook": ["LÍNEA 1", "LÍNEA 2"], "lines": [{"text": "..."}, ...]}; imágenes 00.png, 01.png...
"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
story, imgdir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
voice = sys.argv[4] if len(sys.argv) > 4 else "es-MX-JorgeNeural"
rate = sys.argv[5] if len(sys.argv) > 5 else "+10%"
pitch = sys.argv[6] if len(sys.argv) > 6 else "+0Hz"
d = json.loads(story.read_text(encoding="utf-8"))
work = out.parent / (out.stem + "_work"); work.mkdir(parents=True, exist_ok=True)
text = " ".join(l["text"] for l in d["lines"])
(work / "texto.txt").write_text(text, encoding="utf-8")
subprocess.run([sys.executable if False else "python3", str(HERE / "tts_words.py"), str(work / "texto.txt"), voice,
                str(work / "voz.mp3"), str(work / "palabras.json"), rate, pitch], check=True)
words = json.loads((work / "palabras.json").read_text(encoding="utf-8"))
total = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(work / "voz.mp3")])) + 0.4
# inicio de cada frase según el recuento de palabras
starts, idx = [], 0
for l in d["lines"]:
    starts.append(words[min(idx, len(words) - 1)][0] if idx else 0.0)
    idx += len(re.findall(r"\w+", l["text"]))
starts.append(total)
FPS = 30
clips = []
for i in range(len(d["lines"])):
    dur = starts[i + 1] - starts[i]
    n = max(2, int(round(dur * FPS)))
    zin = i % 2 == 0
    z = f"1.0+0.12*on/{n}" if zin else f"1.12-0.12*on/{n}"
    px = f"(iw-iw/zoom)/2+{'1' if i % 3 else '-1'}*40*on/{n}"
    fn = work / f"c{i:02d}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(imgdir / f"{i:02d}.png"), "-vf",
                    f"scale=2160:3840:force_original_aspect_ratio=increase:flags=lanczos,crop=2160:3840,zoompan=z='{z}':x='{px}':y='(ih-ih/zoom)/2':d={n}:s=1080x1920:fps={FPS},"
                    f"unsharp=5:5:0.6", "-frames:v", str(n), "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", str(fn)], check=True)
    clips.append(fn)
(work / "lista.txt").write_text("".join(f"file '{c}'\n" for c in clips))
def ts(x): return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"
ass = ["[Script Info]", "PlayResX: 1080", "PlayResY: 1920", "", "[V4+ Styles]",
       "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
       "Style: W,Anton,108,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,9,3,5,60,60,0,1",
       "Style: H,Anton,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,3,20,0,5,40,40,0,1",
       "Style: R,Anton,100,&H00FFFFFF,&H00FFFFFF,&H002A2AD8,&H002A2AD8,0,0,0,0,100,100,1,0,3,20,0,5,40,40,0,1",
       "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
if d.get("hook"):
    hd = d.get("hook_dur", 2.6)
    shake = "".join(f"\\t({i*70},{i*70+70},\\frz{3 if i % 2 else -3})" for i in range(int(hd * 1000 / 70)))
    pop = "{\\fscx135\\fscy135\\t(0,120,\\fscx100\\fscy100)}"
    ass += [f"Dialogue: 1,{ts(0)},{ts(hd)},H,,0,0,0,,{{\\pos(540,300){shake}}}{pop}{d['hook'][0]}",
            f"Dialogue: 1,{ts(0)},{ts(hd)},R,,0,0,0,,{{\\pos(540,440){shake}}}{pop}{d['hook'][1]}"]
chunks, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) == 3 or re.search(r"[.,:;?!]$", w[2]):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
for ci, ch in enumerate(chunks):
    nxt = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else total
    for k, (s, e, _) in enumerate(ch):
        end = ch[k + 1][0] if k + 1 < len(ch) else min(e + 0.3, nxt)
        txt = " ".join(("{\\c&H00D7FF&}" + x[2].upper() + "{\\c&HFFFFFF&}") if j == k else x[2].upper() for j, x in enumerate(ch))
        p = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
        ass.append(f"Dialogue: 0,{ts(s)},{ts(end)},W,,0,0,0,,{{\\pos(540,1520)}}{p}{txt}")
(work / "subs.ass").write_text("\n".join(ass), encoding="utf-8")
hd = d.get("hook_dur", 2.6)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "lista.txt"), "-i", str(work / "voz.mp3"),
                "-filter_complex",
                f"[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=0xE8343C@0.95:t=24:enable='lt(t,{hd})*lt(mod(t,0.4),0.2)',"
                f"subtitles={work / 'subs.ass'}:fontsdir={FONTS}[v];[1:a]loudnorm=I=-14:TP=-1.5,aresample=48000,apad[a]",
                "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", str(out)], check=True)
print("OK", out, round(total, 1), "s")
