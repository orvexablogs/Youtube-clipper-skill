# Shorts diarios sin créditos

Pipeline gratuito para el canal **orvexa**: un Short vertical al día con fotos de Unsplash, voz
neuronal gratuita (edge-tts), subtítulos palabra a palabra y publicación en YouTube Shorts.

## Piezas

| Paso | Herramienta | Coste |
|---|---|---|
| Tema y guion | Búsqueda web + `voice.md` | 0 |
| Imágenes | Unsplash (conector) | 0 |
| Voz | `edge-tts`, voz `es-ES-AlvaroNeural` | 0 |
| Montaje | `make_short.py` (ffmpeg) | 0 |
| Alojar el MP4 con URL pública | Higgsfield `media_upload` + `media_confirm` | 0 créditos |
| Publicar en YouTube | Zapier `upload_video` (YouTubeV4CLIAPI) | 0 (plan gratis) |
| TikTok | Higgsfield `tiktok_prepare_publish` (el usuario confirma en el formulario) | 0 créditos |

## Preparar un servidor nuevo

```bash
pip install edge-tts
export SSL_CERT_FILE=/root/.ccr/ca-bundle.crt   # solo en los contenedores de Claude Code
```

`ffmpeg` debe tener `libass` (subtítulos). La fuente Anton (licencia OFL) va en `fonts/`.

## Crear un Short

1. Escribe el guion con el tono de `voice.md` (20–35 s, gancho en la primera frase, cierre en bucle).
2. Descarga una foto vertical por frase en una carpeta `img/`.
3. Crea `spec.json` (formato en la cabecera de `make_short.py`) y ejecuta:

```bash
python3 make_short.py spec.json
```

## Hora de publicación

18:37 hora de Ciudad de México (19:37 en Nueva York): la subida queda procesada justo antes del
pico de uso de 19:00–22:00 en México, Centroamérica y el público hispano de EE. UU.

## Shorts de monigotes (stickman)

`stickman_short.py` (temas `light`, `dark` y `8bit`) dibuja con código escenas animadas de monigotes (sin fotos ni licencias),
con la misma voz, los subtítulos palabra a palabra y un "whoosh" suave en cada corte.
Necesita Pillow y numpy además de lo anterior.

```bash
python3 stickman_short.py ejemplo_stickman.json     # vídeo completo
python3 stickman_short.py --preview carpeta/         # un fotograma de cada escena
```

Escenas: `stand`, `walk`, `sad`, `run`, `sleep`, `phone`, `think`, `climb`, `lift`, `work`,
`money`, `push`, `read`, `crowd`, `graph`, `clock` y `split` (dos paneles con `top`/`bottom`).
Opciones por línea: `label`, `face`, `gold`, `bubble`, `alarm`, `zoom`… (ver la cabecera del script).

## Estrategia y sistema de guion

`estrategia_orvexa.md` recoge las descripciones del canal, la identidad visual, la tabla de guion
en 4 columnas, las reglas de títulos y portada, y el embudo hacia orvexablogs.com.

### Motion graphics sin personajes

Con `"theme": "mg"` y las escenas `title`, `icons`, `versus`, `chart`, `flow`, `drain` y
`question`, el mismo generador hace vídeos de textos animados, iconos (Noto Color Emoji),
gráficas y comparaciones sobre fondo oscuro con oro. Ejemplo completo en `ejemplo_motion.json`.
