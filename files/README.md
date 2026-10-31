# Rocket League AI Coach

Pipeline que usa la API de Anthropic para analizar clips de Rocket League
(freestyle, jugadores profesionales, y tus propias partidas) y darte
feedback de coaching.

## Instalación

```bash
pip install anthropic --break-system-packages
```

Necesitás `ffmpeg` instalado y en el PATH:
- Windows: https://ffmpeg.org/download.html (o `winget install ffmpeg`)
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

Configurá tu API key:

```bash
export ANTHROPIC_API_KEY="tu-api-key-aca"
```

(En Windows PowerShell: `$env:ANTHROPIC_API_KEY="tu-api-key-aca"`)

## Uso

### 1. Fase de aprendizaje — clips de freestyle / pros

```bash
python3 rl_coach.py aprender --video clip1.mp4 --contexto "flip reset en freestyle"
python3 rl_coach.py aprender --video clip2.mp4 --contexto "aereo defensivo de jugador pro en 1v1"
python3 rl_coach.py aprender --video clip3.mp4
```

Cada corrida analiza el clip y **agrega** las conclusiones a `knowledge_base.md`
(se va acumulando con cada video que le pases — no lo borra).

Recomendación: usá clips cortos (5-15 segundos) recortados a la jugada
específica que te interesa, en vez de videos completos de 20 minutos.
Podés recortar con ffmpeg antes:

```bash
ffmpeg -i partido_completo.mp4 -ss 00:03:10 -to 00:03:25 -c copy clip_recortado.mp4
```

### 2. Fase de análisis — tus propias partidas

```bash
python3 rl_coach.py analizar --video mi_jugada.mp4 --contexto "intenté un doble toque y erré"
```

Esto usa TODO lo acumulado en `knowledge_base.md` como referencia, analiza
los frames de tu jugada, y guarda el feedback en `analisis/<nombre>_<fecha>.md`.

## Parámetros ajustables

- `--fps`: cuántos frames por segundo extraer (default 2). Para mecánicas muy
  rápidas (flip resets, doble toque) probá subir a 4-5. Para jugadas más
  lentas de posicionamiento, con 1-1.5 alcanza y ahorrás costo.
- `--max-dim`: resolución máxima del lado largo del frame (default 768px).
  Subilo si sentís que Claude no está leyendo bien detalles finos, bajalo
  para ahorrar costo.
- `--max-frames`: tope de frames por llamada a la API (default 40). Con
  clips de 5-15 segundos a 2fps rara vez lo vas a necesitar, pero si mandás
  un video largo esto samplea parejo para no pasarte de costo/límite.
- `--knowledge-base`: podés tener varias bases de conocimiento separadas por
  tema si querés (ej. `kb_aereos.md`, `kb_defensa.md`) y elegir cuál usar al
  analizar.

## Notas de costo

Cada frame de ~768px consume aproximadamente 300-800 tokens de imagen según
el tamaño final. Un clip de 10 segundos a 2fps son 20 frames (~10-15k tokens
de input) — bastante barato por análisis. Empezá con clips cortos y andá
ajustando `--fps` y `--max-dim` según qué tan bien lee las mecánicas.
