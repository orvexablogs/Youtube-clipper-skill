#!/usr/bin/env python3
"""Narra un texto entero de una vez con edge-tts y guarda los tiempos de cada palabra.

Uso: python tts_words.py texto.txt voz salida.mp3 salida.json [rate] [pitch]
(se ejecuta con el Python que tenga instalado edge-tts)."""
import asyncio
import json
import os
import sys

import edge_tts


async def main(txt, voice, mp3, js, rate="+4%", pitch="-3Hz"):
    text = open(txt, encoding="utf-8").read()
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary",
                               proxy=os.environ.get("HTTPS_PROXY"))
    words = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append([ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]])
    json.dump(words, open(js, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
