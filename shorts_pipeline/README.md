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
