#!/usr/bin/env python3
"""
Rocket League AI Coach — pipeline con la API de Anthropic
============================================================

Dos modos de uso:

1) APRENDER de videos de referencia (freestyle, mecánicas, pros):
   python3 rl_coach.py aprender --video clip_pro_1.mp4 --contexto "1v1 aereo contra defensa"
   -> Extrae frames, le pide a Claude que analice la jugada, y GUARDA
      las conclusiones en knowledge_base.md (se va acumulando con cada video).

2) ANALIZAR tus propias partidas, usando todo lo aprendido como contexto:
   python3 rl_coach.py analizar --video mi_partida_1.mp4 --contexto "gol en contra por mal challenge"
   -> Extrae frames, le pasa a Claude la knowledge_base.md acumulada + los
      frames de tu jugada, y te devuelve feedback concreto. Se guarda en
      analisis/<nombre_del_video>.md

Requisitos:
    pip install anthropic --break-system-packages
    ffmpeg instalado y en el PATH (ya lo tenés si esto corre en este entorno,
    si lo corrés en tu compu propia instalalo: https://ffmpeg.org/download.html)

La API key la toma de la variable de entorno ANTHROPIC_API_KEY.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import anthropic

# Forzamos UTF-8 en la salida: cuando este script corre como subproceso silencioso
# (ej. lanzado desde la app de Electron) Windows a veces usa una codificación vieja
# (cp1252) que no soporta emojis como ✅ o ⚠️, y el script se rompe. Esto lo evita
# sin importar quién lo esté ejecutando.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MODEL = "claude-sonnet-4-6"

# --------------------------------------------------------------------------
# Prompts base — los podés editar libremente para ajustar el estilo del coach
# --------------------------------------------------------------------------

SYSTEM_APRENDER = """Sos un coach de altísimo nivel de Rocket League, con ojo entrenado \
para leer mecánicas y freestyle a partir de secuencias de fotogramas (no video real, \
así que no necesitás ser preciso con tiempos exactos ni distancias exactas — enfocate \
en la LECTURA de la jugada: qué mecánica se está ejecutando, en qué momento/contexto \
tiene sentido usarla, qué la hace efectiva o riesgosa, y qué principios generales se \
pueden sacar de ahí para aplicar en otras situaciones.

Te voy a pasar una secuencia ordenada de frames de un clip (freestyle o jugada de \
profesional). Quiero que:
1. Describas brevemente qué mecánica(s) ves (aéreo, doble toque, flip reset, ceiling \
shot, half-flip, fast aerial, wave dash, musty flick, etc. — lo que corresponda).
2. Expliques el contexto/situación en la que tiene sentido usarla (defensa, ataque, \
tiempo restante, posición en cancha, etc. — a nivel conceptual, sin inventar datos que \
no se ven).
3. Saques 2-4 principios/lecciones generales y reutilizables para un jugador que quiera \
aplicar algo similar.

Sé conciso y priorizá sabiduría práctica por sobre la descripción literal de cada frame."""

SYSTEM_APRENDER_TRAMO = """Sos un analista táctico de Rocket League. Te paso una secuencia \
de frames de UN TRAMO de un partido completo de jugadores profesionales (no un clip de \
mecánica aislada). En este tramo puede pasar cualquier cosa: rotaciones, gestión de boost, \
challenges, defensas, transición ataque/defensa, decisiones de cuándo NO hacer algo, etc.

No necesitás precisión de distancias/tiempos exactos. Enfocate en TOMA DE DECISIONES: \
- ¿Qué decisión tomó cada jugador (rotar, quedarse, challengear, esperar, ir por boost)?
- ¿Por qué esa decisión tiene sentido en ese contexto (posición de la pelota, de los \
compañeros, boost disponible, tiempo)?
- ¿Qué patrón de posicionamiento o rotación se puede identificar?

Respondé en 3-6 bullets cortos y concretos, tipo notas de análisis. No hace falta \
introducción ni conclusión, directo a los puntos observados en este tramo."""

SYSTEM_SINTESIS_APRENDER = """Tenés una serie de notas de análisis tomadas tramo por tramo \
de uno o varios partidos profesionales de Rocket League. Tu trabajo es CONSOLIDAR esas \
notas en principios generales y reutilizables (no repitas las notas tal cual, sintetizá).

Organizá la respuesta en estas secciones:
**Patrones de rotación y posicionamiento**
**Gestión de boost**
**Toma de decisiones en challenges (cuándo ir y cuándo no)**
**Transición ataque/defensa**
**Otros patrones notables**

Cada sección con 2-5 bullets de principios accionables. Priorizá lo que se repite entre \
varias notas (eso indica que es un patrón real, no un caso aislado)."""

CONOCIMIENTO_BASE = """CONOCIMIENTO BASE DE ROCKET LEAGUE (aplicá esto SIEMPRE, además de \
lo que haya en la base de conocimiento acumulada — esto no depende de qué videos se \
cargaron, son fundamentos del juego):

- Respetá el modo indicado en el contexto del usuario. En 1v1 no existe un compañero: no \
recomiendes que un teammate cubra, rote o apoye; enfocá el consejo en la posición y las \
opciones del propio jugador frente al rival. No supongas compañeros si el modo no los confirma.
- Los kickoffs (y en general los desafíos 50/50: dos jugadores yendo por la misma pelota) \
son intrínsecamente probabilísticos — el resultado depende también de la decisión del \
rival, no solo de la ejecución propia. NUNCA marques como "error" el simple hecho de no \
ganar posesión limpia en un kickoff o un 50/50, salvo que haya un error TÉCNICO \
identificable de verdad (mala elección de boost pad, no comprometerse con una dirección, \
llegar visiblemente tarde por una decisión de rotación previa evitable).
- No deduzcas que faltó un speedflip ni que se ejecutó mal solo porque el jugador tenga \
poco boost o no llegue primero al kickoff. No presentes el speedflip como requisito \
universal. Solo recomendá practicarlo si los frames muestran evidencia clara de una llegada \
lenta o de un problema mecánico; si no alcanza la evidencia, no inventes la causa.
- Analizá por separado la intención de disputar el kickoff, el contacto y el resultado. Estar \
orientado hacia la pelota o acercarse no demuestra que hubo contacto: afirmá que hubo toque \
solo si se ve el impacto o un cambio de trayectoria atribuible al jugador. Si el muestreo no \
permite confirmarlo, escribí que el contacto no se puede confirmar en los frames disponibles.
- Si el jugador parece cancelar la disputa o dejar que el rival toque primero, considerá un \
fake kickoff como posibilidad y describí la conducta observable; no afirmes la intención como \
hecho si no es clara. Un fake kickoff no es automáticamente un error: evaluá si cedió una \
ventaja real según la posición del compañero y el control que obtuvo el rival.
- En el modo estándar de Rocket League, cada kickoff reinicia el boost de todos los jugadores \
a 33, también después de un gol. No asumas que se conserva el boost de la jugada anterior. No \
clasifiques 33 como bajo por sí solo durante el reinicio o la salida inicial del kickoff, ni \
recomiendes recoger pads durante la celebración o el reseteo para llegar al saque con más \
boost. Esta regla solo aplica a ese contexto: en un aéreo u otra jugada, 33 puede ser poco si \
no alcanza para la acción necesaria. Evaluá siempre la cantidad según la jugada, la amenaza y \
las opciones disponibles.
- Gastar boost durante el kickoff y quedar con poco después del primer toque o 50/50 es NORMAL \
y no es un error por sí mismo — solo es señal de algo a corregir si aparece junto con una mala \
decisión posterior o un patrón repetido de recuperación deficiente.
- Después de una jugada aérea, no concluyas que faltó un plan de recuperación mirando solo \
un frame con poco boost. Evaluá la secuencia: inercia y dirección del auto, tiempo para \
maniobrar, ubicación y amenaza de la pelota, posición de rivales/compañero, pads disponibles \
y si la ruta permite volver a defender o seguir la jugada. Ir por un boost grande puede ser \
correcto si el rival está lejos y no se abandona una amenaza urgente; no lo marques error solo \
por alejarse momentáneamente de la pelota o por tener que esperar a controlar el auto.
- No uses reglas absolutas como "nunca persigas la pelota sin boost". Compará opciones según \
el peligro inmediato y la cobertura: a veces conviene recuperar boost; otras, disputar o cubrir \
el arco con el boost disponible. Si los frames no muestran suficiente contexto temporal para \
decidir, expresá incertidumbre o no generes una observación de error.
- Diferenciá un air dribble de un tiro aislado observando la secuencia: en un air dribble el \
jugador busca el primer toque para levantar o mantener la pelota cerca y seguirla en el aire, \
posiblemente con varios toques controlados. No llames "disparo" a todo el approach solo porque \
la pelota va hacia el arco o aparece el aviso "DISPARO +10"; ese aviso puede señalar un tiro \
dentro de una secuencia más amplia, como un air dribble que culmina en remate. Describí ambas \
fases si están respaldadas por los frames.
- No deduzcas la intención de tirar ni la mecánica de air dribble a partir de un solo frame. \
Si el muestreo no muestra los toques o la continuación, expresá la incertidumbre y no presentes \
un setup aéreo como un tiro confirmado. Tampoco recomiendes reservar boost para un segundo \
remate si no hay evidencia de que la jugada terminó en un tiro aislado y necesitaba seguimiento.
- Usá "jugada_dudosa" cuando la calidad de una decisión dependa de información que no podés \
confirmar (por ejemplo, si el jugador oyó al rival, anticipó su ruta o tuvo una razón táctica) \
y los frames no permitan distinguir una decisión informada de una casualidad. Separá lo que \
se observa de lo que no se sabe; no atribuyas intención ni conocimiento como hechos. Explicá \
escenarios condicionales concretos (si el rival estaba lejos, recuperar boost podía ser válido; \
si volvía rápido, disputar o cubrir podía ser mejor). No juzgues una decisión solo por el \
resultado posterior: un gol recibido no prueba por sí mismo que la decisión previa fuera mala. \
Si recomendás escuchar el juego, plantealo como información útil, no como prueba de que el \
jugador no prestó atención.
- Distinguí siempre entre: (a) una jugada que salió mal por mala suerte/50-50 perdido \
(no es un error del jugador), (b) un error de EJECUCIÓN de una mecánica que el jugador \
ya intentó pero le falta pulir, y (c) un error de DECISIÓN (eligió mal qué hacer, \
independientemente de si la ejecución fue buena). El consejo que des tiene que ser \
específico a cuál de estos tres es."""

REGLA_IDENTIDAD_JUGADOR = """No se proporciona el nickname del usuario. No asumas que el \
nombre que aparece en un anuncio de gol pertenece al usuario: el anuncio solo identifica al \
anotador. Atribuí un gol, una asistencia o una decisión al usuario solo si los frames vinculan \
claramente esa acción con el auto que controla la cámara. Si no podés confirmarlo, describí el \
hecho de forma neutral (por ejemplo, "LAFRITANGA231 anotó") y no lo marques como acierto o \
error del usuario. Tampoco digas que la presión previa del usuario causó el gol sin evidencia \
clara de su participación. No infieras causalidad solo porque ambas cosas ocurren cerca en el \
tiempo; ante duda, omití la atribución personal."""

SYSTEM_ANALIZAR_TRAMO_JSON = """Sos un coach de Rocket League analizando UN TRAMO de una \
partida real de tu jugador, junto con una base de conocimiento de patrones aprendidos de \
profesionales. Te paso una secuencia de frames, cada uno etiquetado con su tiempo real \
dentro del video (ej. "[tiempo: 00:47]").

""" + CONOCIMIENTO_BASE + "\n\n" + REGLA_IDENTIDAD_JUGADOR + """

Identificá observaciones puntuales dignas de mencionar: errores, aciertos, jugadas dudosas, \
mecánicas que \
hubieran servido, o mecánicas de más. Para cada observación que encuentres, asociala al \
tiempo del frame (o frames) donde ocurre — usá el tiempo exacto que te dieron en las \
etiquetas, no inventes uno.

En kickoffs, no confundas aproximación con contacto ni atribuyas un toque que los frames no \
confirman. Si el jugador no disputa la pelota, describí lo que se ve y considerá si pudo ser \
un fake kickoff antes de juzgarlo; con muestreo escaso, expresá la incertidumbre u omití la \
observación. No diagnostiques falta de speedflip basándote solo en el boost visible.

No llames "desafío aéreo" a una jugada solo porque el auto aparece suspendido en un frame. \
Para clasificarla como desafío aéreo, los frames deben mostrar que el jugador despegó y fue a \
disputar la pelota en el aire antes del contacto. Si el auto queda en el aire después de un \
choque o fifty, describí ese estado como consecuencia del contacto, no como la mecánica que \
lo inició. Si la secuencia no permite distinguirlo, usá una descripción neutral y no inventes \
la mecánica. Respetá también el contexto del modo: en 1v1 no des consejos sobre compañeros.

Al analizar una jugada aérea, diferenciá el setup/los toques de un air dribble del posible \
remate final. El aviso "DISPARO +10" por sí solo no demuestra que todo el approach haya sido \
un tiro aislado ni descarta que antes hubiera un air dribble. Si faltan frames para observar \
la secuencia de contactos, no afirmes una mecánica ni bases un error de gestión de boost en \
esa suposición.

RESPONDÉ ÚNICAMENTE con un array JSON válido, sin texto antes ni después, sin backticks \
de markdown. Cada elemento del array debe tener EXACTAMENTE estos campos:

[
  {
    "timestamp_segundos": <int, el tiempo del frame más relevante para esta observación>,
    "tipo": "<uno de: acierto, error, jugada_dudosa, mecanica_sugerida, mecanica_de_mas>",
    "titulo": "<título corto, 4-8 palabras>",
    "descripcion": "<explicación concreta, 1-3 oraciones, por qué es relevante>",
    "consejo": "<OBLIGATORIO. Qué hacer distinto la próxima vez, concreto y accionable. \
Si es un error de ejecución, decí qué practicar. Si es un error de decisión, decí qué \
decisión tomar en su lugar. Si es un acierto, decí cómo reforzarlo o repetirlo. Nunca \
dejes este campo vacío ni genérico tipo 'mejorar' — tiene que ser específico.>",
    "contexto_segundos_antes": <int, cuántos segundos antes del timestamp conviene que \
arranque a verse el replay para entender el contexto completo (típicamente 2-5)>
  }
]

Si no hay nada relevante en este tramo, respondé exactamente: []

No inventes distancias ni tiempos que no estén en las etiquetas de los frames."""

SYSTEM_CORREGIR_OBSERVACION = """Sos un coach de Rocket League revisando una observación \
que ya hiciste sobre la partida de tu jugador, después de que el jugador te dio contexto \
adicional sobre qué pasó realmente en la jugada — contexto que no podías ver solo con las \
imágenes (por ejemplo, que fue un 50/50 real contra el rival, una decisión del compañero, \
etc.).

""" + CONOCIMIENTO_BASE + "\n\n" + REGLA_IDENTIDAD_JUGADOR + """

Te doy la observación original (en JSON) y la explicación del jugador. Tu trabajo:
1. Si la explicación cambia genuinamente la interpretación de la jugada, REVISÁ la \
observación — puede cambiar de "error" a "acierto", o dejar de ser relevante del todo.
2. Si la explicación NO cambia la naturaleza del error (ej. el jugador se justifica pero \
el error de fondo persiste), mantené la observación, pero podés afinar el consejo con el \
contexto nuevo.
3. Sé honesto: no le des la razón al jugador solo por quedar bien. Si el error real \
persiste a pesar del contexto que dio, decilo con respeto pero sin rodeos.

RESPONDÉ ÚNICAMENTE con un objeto JSON (no un array), sin texto antes ni después, sin \
backticks de markdown, con EXACTAMENTE estos campos:

{
    "tipo": "<uno de: acierto, error, jugada_dudosa, mecanica_sugerida, mecanica_de_mas, o 'sin_observacion' \
si con el contexto dado esta observación ya no amerita mencionarse>",
  "titulo": "<título corto, 4-8 palabras>",
  "descripcion": "<explicación concreta actualizada, 1-3 oraciones>",
  "consejo": "<consejo concreto y accionable actualizado, igual de específico que antes>",
  "nota_revision": "<1-2 líneas dirigidas al jugador explicando qué cambió (o por qué se \
mantiene) a partir de lo que contó>"
}"""

SYSTEM_ANALIZAR_TRAMO = """Sos un coach de Rocket League. Te paso una secuencia de frames \
de UN TRAMO de una partida real de tu jugador (no un clip de mecánica aislada), junto con \
una base de conocimiento de patrones aprendidos de profesionales.

""" + CONOCIMIENTO_BASE + """

Para este tramo, identificá SOLO cosas dignas de mencionar (no comentes cada frame si no \
pasa nada relevante):
- Decisiones de rotación/posicionamiento buenas o malas
- Gestión de boost buena o mala
- Challenges tomados de más o evitados quedebieron tomarse
- Cualquier error de lectura de juego comparado con los patrones de la base de conocimiento

Si en este tramo no pasa nada relevante para comentar, respondé solamente: "Sin observaciones \
relevantes en este tramo." Si hay algo, respondé en 2-5 bullets cortos. Cada bullet que \
señale un error DEBE terminar con un consejo concreto de qué hacer distinto (no alcanza \
con describir el error)."""

SYSTEM_SINTESIS_ANALIZAR = """Tenés una serie de notas de análisis tramo por tramo de una \
partida real de un jugador de Rocket League (algunas pueden decir "sin observaciones \
relevantes", ignorá esas). Consolidá todo en un informe final con esta estructura:

**Resumen general de la partida:** (2-3 líneas)
**Patrones positivos que se repitieron:** (con qué frecuencia/contexto)
**Errores que se repitieron:** (con qué frecuencia/contexto — esto es lo más importante \
del informe)
**Top 3 cosas a corregir primero:** (priorizadas por impacto, no por orden de aparición)
**Top 2 cosas a potenciar:** (lo que ya funciona y conviene reforzar)

Sé directo, como un coach dando feedback post-partido. Priorizá patrones que se repiten \
por sobre errores puntuales de una sola vez."""

SYSTEM_ANALIZAR = """Sos un coach de Rocket League analizando la partida de tu jugador. \
Te voy a dar dos cosas:
1. Una BASE DE CONOCIMIENTO con principios y mecánicas que ya aprendiste de videos de \
freestyle y de jugadores profesionales.
2. Una secuencia de frames de una jugada REAL del jugador que estás entrenando.

""" + CONOCIMIENTO_BASE + """

Usando la base de conocimiento como referencia, analizá la jugada del usuario y \
respondé con esta estructura:

**Qué hizo bien:** (con por qué funcionó, y cómo reforzarlo)
**Qué hizo mal / se puede mejorar:** (con por qué no funcionó o fue subóptimo — distinguí \
si es error de ejecución, de decisión, o simplemente un 50/50 perdido)
**Mecánica que hubiera servido acá:** (si aplica — y por qué, referenciando lo que \
sabés de la base de conocimiento)
**Mecánica de más / sobreactuada:** (si el jugador se complicó con algo innecesario \
cuando una opción más simple era mejor)
**Consejo concreto para la próxima vez:** (1-2 líneas, accionable — qué practicar o qué \
decidir distinto, no solo qué evitar)

No inventes distancias ni tiempos exactos — hablá en términos de lectura de juego, \
timing relativo y toma de decisiones. Sé directo y constructivo, como un coach real."""


# --------------------------------------------------------------------------
# Utilidad: duración del video
# --------------------------------------------------------------------------

def obtener_duracion(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error de ffprobe:", result.stderr, file=sys.stderr)
        sys.exit(1)
    return float(result.stdout.strip())


def extraer_frames_tramo(video_path: str, out_dir: str, inicio: float, duracion: float,
                          fps: float, max_dim: int) -> list[str]:
    """Igual que extraer_frames pero solo para una ventana [inicio, inicio+duracion) del video."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    pattern = os.path.join(out_dir, "frame_%04d.jpg")
    vf = f"fps={fps},scale='if(gt(iw,ih),{max_dim},-2)':'if(gt(iw,ih),-2,{max_dim})'"
    cmd = [
        "ffmpeg", "-y", "-ss", str(inicio), "-i", video_path, "-t", str(duracion),
        "-vf", vf, "-q:v", "3", pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error de ffmpeg:", result.stderr, file=sys.stderr)
        sys.exit(1)
    return [str(f) for f in sorted(Path(out_dir).glob("frame_*.jpg"))]


# --------------------------------------------------------------------------
# Extracción de frames
# --------------------------------------------------------------------------

def extraer_frames(video_path: str, out_dir: str, fps: float, max_dim: int) -> list[str]:
    """Extrae frames de un video con ffmpeg a intervalos regulares (fps),
    redimensionados para no gastar tokens de más, y devuelve las rutas ordenadas."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    pattern = os.path.join(out_dir, "frame_%04d.jpg")

    # scale=... 'if(gt(iw,ih),min(max_dim,iw),-2)' mantiene el lado largo <= max_dim
    vf = f"fps={fps},scale='if(gt(iw,ih),{max_dim},-2)':'if(gt(iw,ih),-2,{max_dim})'"

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-q:v", "3",  # calidad jpg (2-5 es buen rango, menor = mejor calidad)
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error de ffmpeg:", result.stderr, file=sys.stderr)
        sys.exit(1)

    frames = sorted(Path(out_dir).glob("frame_*.jpg"))
    if not frames:
        print("No se extrajo ningún frame. Revisá la ruta del video.", file=sys.stderr)
        sys.exit(1)
    return [str(f) for f in frames]


def frames_a_bloques_imagen(frame_paths: list[str], max_frames: int) -> list[dict]:
    """Convierte una lista de rutas de imagen a bloques de contenido para la API.
    Si hay más frames que max_frames, los muestrea parejo para no pasarse de costo."""
    if len(frame_paths) > max_frames:
        step = len(frame_paths) / max_frames
        frame_paths = [frame_paths[int(i * step)] for i in range(max_frames)]

    bloques = []
    for i, path in enumerate(frame_paths):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        bloques.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })
        bloques.append({
            "type": "text",
            "text": f"[frame {i + 1}/{len(frame_paths)}]",
        })
    return bloques


def frames_a_bloques_imagen_con_tiempo(frame_paths: list[str], max_frames: int,
                                        tiempo_inicio: float, fps: float) -> list[dict]:
    """Igual que frames_a_bloques_imagen, pero etiqueta cada frame con su tiempo REAL
    dentro del video completo (tiempo_inicio del tramo + índice/fps), para que Claude
    pueda referenciar timestamps exactos en vez de inventarlos."""
    tiempos = [tiempo_inicio + i / fps for i in range(len(frame_paths))]

    if len(frame_paths) > max_frames:
        step = len(frame_paths) / max_frames
        idx = [int(i * step) for i in range(max_frames)]
        frame_paths = [frame_paths[i] for i in idx]
        tiempos = [tiempos[i] for i in idx]

    bloques = []
    for path, t in zip(frame_paths, tiempos):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        mm, ss = divmod(int(t), 60)
        bloques.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })
        bloques.append({
            "type": "text",
            "text": f"[tiempo: {mm:02d}:{ss:02d}]",
        })
    return bloques


def parsear_json_claude(texto: str) -> list:
    """Parsea la respuesta de Claude como JSON, tolerando backticks de markdown
    que a veces se cuelan igual. Devuelve [] y avisa si no se puede parsear."""
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1]
        if limpio.startswith("json"):
            limpio = limpio[4:]
    limpio = limpio.strip()
    try:
        data = json.loads(limpio)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print(f"\n⚠️  No se pudo parsear como JSON, se descarta este tramo: {texto[:200]}")
        return []


def parsear_json_objeto_claude(texto: str) -> dict:
    """Igual que parsear_json_claude pero espera un objeto {} en vez de un array []."""
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1]
        if limpio.startswith("json"):
            limpio = limpio[4:]
    limpio = limpio.strip()
    try:
        data = json.loads(limpio)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        print(f"\n⚠️  No se pudo parsear como JSON: {texto[:200]}")
        return {}


# --------------------------------------------------------------------------
# Llamadas a la API
# --------------------------------------------------------------------------

def llamar_claude(client: anthropic.Anthropic, system: str, bloques_imagen: list[dict],
                   instruccion_final: str) -> str:
    content = bloques_imagen + [{"type": "text", "text": instruccion_final}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------

def cmd_aprender(args):
    client = anthropic.Anthropic()
    tmp_dir = tempfile.mkdtemp(prefix="rl_frames_")
    try:
        print(f"Extrayendo frames de {args.video} a {args.fps} fps...")
        frames = extraer_frames(args.video, tmp_dir, args.fps, args.max_dim)
        print(f"  {len(frames)} frames extraídos.")

        bloques = frames_a_bloques_imagen(frames, args.max_frames)
        instruccion = f"Contexto que me diste sobre el clip: {args.contexto or '(sin contexto adicional)'}"

        print("Consultando a Claude...")
        analisis = llamar_claude(client, SYSTEM_APRENDER, bloques, instruccion)

        kb_path = Path(args.knowledge_base)
        encabezado = f"\n\n---\n### {Path(args.video).name} — {datetime.now():%Y-%m-%d %H:%M}\n"
        if args.contexto:
            encabezado += f"_Contexto: {args.contexto}_\n\n"
        with open(kb_path, "a", encoding="utf-8") as f:
            f.write(encabezado + analisis + "\n")

        print(f"\n✅ Análisis agregado a {kb_path}\n")
        print(analisis)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def cmd_analizar(args):
    client = anthropic.Anthropic()

    kb_path = Path(args.knowledge_base)
    knowledge_base = kb_path.read_text(encoding="utf-8") if kb_path.exists() else ""
    if not knowledge_base.strip():
        print("⚠️  No hay base de conocimiento todavía (corré 'aprender' con algunos "
              "clips de referencia antes para mejores resultados). Sigo igual...")

    tmp_dir = tempfile.mkdtemp(prefix="rl_frames_")
    try:
        print(f"Extrayendo frames de {args.video} a {args.fps} fps...")
        frames = extraer_frames(args.video, tmp_dir, args.fps, args.max_dim)
        print(f"  {len(frames)} frames extraídos.")

        bloques = frames_a_bloques_imagen(frames, args.max_frames)

        instruccion = "BASE DE CONOCIMIENTO ACUMULADA:\n" + (knowledge_base or "(vacía)")
        instruccion += f"\n\n---\nContexto que me diste sobre esta jugada: {args.contexto or '(sin contexto adicional)'}"
        instruccion += "\n\nAhora analizá la secuencia de frames que te pasé de MI jugada."

        print("Consultando a Claude...")
        analisis = llamar_claude(client, SYSTEM_ANALIZAR, bloques, instruccion)

        out_dir = Path("analisis")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{Path(args.video).stem}_{datetime.now():%Y%m%d_%H%M%S}.md"
        out_path.write_text(analisis, encoding="utf-8")

        print(f"\n✅ Análisis guardado en {out_path}\n")
        print(analisis)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def cmd_aprender_partido(args):
    client = anthropic.Anthropic()
    duracion_total = obtener_duracion(args.video)
    n_tramos = max(1, int(duracion_total // args.chunk_seconds) + (1 if duracion_total % args.chunk_seconds else 0))
    print(f"Video de {duracion_total:.0f}s dividido en {n_tramos} tramos de ~{args.chunk_seconds:.0f}s")

    notas = []
    tmp_dir = tempfile.mkdtemp(prefix="rl_frames_")
    try:
        for i in range(n_tramos):
            inicio = i * args.chunk_seconds
            dur = min(args.chunk_seconds, duracion_total - inicio)
            print(f"  Tramo {i + 1}/{n_tramos} ({inicio:.0f}s - {inicio + dur:.0f}s)...", end=" ", flush=True)

            chunk_dir = os.path.join(tmp_dir, f"tramo_{i}")
            frames = extraer_frames_tramo(args.video, chunk_dir, inicio, dur, args.fps, args.max_dim)
            if not frames:
                print("sin frames, salteado.")
                continue
            bloques = frames_a_bloques_imagen(frames, args.max_frames_por_tramo)
            nota = llamar_claude(client, SYSTEM_APRENDER_TRAMO, bloques,
                                  "Analizá este tramo del partido.")
            notas.append(f"[{inicio:.0f}s-{inicio + dur:.0f}s]\n{nota}")
            print("ok")
            shutil.rmtree(chunk_dir, ignore_errors=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("Sintetizando patrones generales...")
    texto_notas = "\n\n".join(notas)
    sintesis = llamar_claude(
        client, SYSTEM_SINTESIS_APRENDER, [],
        f"Notas tramo por tramo del partido {Path(args.video).name}:\n\n{texto_notas}"
    )

    kb_path = Path(args.knowledge_base)
    encabezado = f"\n\n---\n### PARTIDO: {Path(args.video).name} — {datetime.now():%Y-%m-%d %H:%M}\n"
    if args.contexto:
        encabezado += f"_Contexto: {args.contexto}_\n\n"
    with open(kb_path, "a", encoding="utf-8") as f:
        f.write(encabezado + sintesis + "\n")

    print(f"\n✅ Síntesis agregada a {kb_path}\n")
    print(sintesis)


def cmd_analizar_partido(args):
    client = anthropic.Anthropic()

    kb_path = Path(args.knowledge_base)
    knowledge_base = kb_path.read_text(encoding="utf-8") if kb_path.exists() else ""
    if not knowledge_base.strip():
        print("⚠️  No hay base de conocimiento todavía (corré 'aprender-partido' con algún "
              "partido de referencia antes para mejores resultados). Sigo igual...")

    duracion_total = obtener_duracion(args.video)
    n_tramos = max(1, int(duracion_total // args.chunk_seconds) + (1 if duracion_total % args.chunk_seconds else 0))
    print(f"Video de {duracion_total:.0f}s dividido en {n_tramos} tramos de ~{args.chunk_seconds:.0f}s")

    notas = []
    tmp_dir = tempfile.mkdtemp(prefix="rl_frames_")
    try:
        for i in range(n_tramos):
            inicio = i * args.chunk_seconds
            dur = min(args.chunk_seconds, duracion_total - inicio)
            print(f"  Tramo {i + 1}/{n_tramos} ({inicio:.0f}s - {inicio + dur:.0f}s)...", end=" ", flush=True)

            chunk_dir = os.path.join(tmp_dir, f"tramo_{i}")
            frames = extraer_frames_tramo(args.video, chunk_dir, inicio, dur, args.fps, args.max_dim)
            if not frames:
                print("sin frames, salteado.")
                continue
            bloques = frames_a_bloques_imagen(frames, args.max_frames_por_tramo)
            instruccion = ("BASE DE CONOCIMIENTO:\n" + (knowledge_base or "(vacía)") +
                            "\n\n---\nAnalizá este tramo de MI partida.")
            nota = llamar_claude(client, SYSTEM_ANALIZAR_TRAMO, bloques, instruccion)
            if "sin observaciones relevantes" not in nota.lower():
                notas.append(f"[{inicio:.0f}s-{inicio + dur:.0f}s]\n{nota}")
                print("ok (con observaciones)")
            else:
                print("ok (sin observaciones)")
            shutil.rmtree(chunk_dir, ignore_errors=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not notas:
        print("\nNo se encontraron observaciones relevantes en ningún tramo. "
              "Probá bajar --chunk-seconds o subir --fps para más detalle.")
        return

    print("Generando informe final...")
    texto_notas = "\n\n".join(notas)
    informe = llamar_claude(
        client, SYSTEM_SINTESIS_ANALIZAR, [],
        f"Notas tramo por tramo de mi partida {Path(args.video).name}:\n\n{texto_notas}"
    )

    out_dir = Path("analisis")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"PARTIDO_{Path(args.video).stem}_{datetime.now():%Y%m%d_%H%M%S}.md"
    out_path.write_text(informe, encoding="utf-8")

    print(f"\n✅ Informe guardado en {out_path}\n")
    print(informe)


def cmd_analizar_app(args):
    """Motor pensado para la futura app con reproductor: analiza el partido por tramos
    y devuelve observaciones estructuradas en JSON con timestamp exacto, listas para
    que una interfaz las muestre como lista clickeable que salta el video al momento
    correcto."""
    client = anthropic.Anthropic()

    kb_path = Path(args.knowledge_base)
    knowledge_base = kb_path.read_text(encoding="utf-8") if kb_path.exists() else ""
    if not knowledge_base.strip():
        print("⚠️  No hay base de conocimiento todavía (corré 'aprender-partido' antes "
              "para mejores resultados). Sigo igual...")

    duracion_total = obtener_duracion(args.video)
    n_tramos = max(1, int(duracion_total // args.chunk_seconds) + (1 if duracion_total % args.chunk_seconds else 0))
    print(f"Video de {duracion_total:.0f}s dividido en {n_tramos} tramos de ~{args.chunk_seconds:.0f}s")

    observaciones = []
    tmp_dir = tempfile.mkdtemp(prefix="rl_frames_")
    try:
        for i in range(n_tramos):
            inicio = i * args.chunk_seconds
            dur = min(args.chunk_seconds, duracion_total - inicio)
            print(f"  Tramo {i + 1}/{n_tramos} ({inicio:.0f}s - {inicio + dur:.0f}s)...", end=" ", flush=True)

            chunk_dir = os.path.join(tmp_dir, f"tramo_{i}")
            frames = extraer_frames_tramo(args.video, chunk_dir, inicio, dur, args.fps, args.max_dim)
            if not frames:
                print("sin frames, salteado.")
                continue

            bloques = frames_a_bloques_imagen_con_tiempo(frames, args.max_frames_por_tramo, inicio, args.fps)
            instruccion = (
                "BASE DE CONOCIMIENTO:\n" + (knowledge_base or "(vacía)") +
                "\n\nCONTEXTO DE LA PARTIDA INDICADO POR EL USUARIO: " +
                (args.contexto or "(no especificado)") +
                "\n\nUsá este contexto para interpretar el modo y las relaciones entre jugadores. "
                "Analizá este tramo de MI partida y devolvé el JSON."
            )
            respuesta = llamar_claude(client, SYSTEM_ANALIZAR_TRAMO_JSON, bloques, instruccion)
            obs_tramo = parsear_json_claude(respuesta)
            observaciones.extend(obs_tramo)
            print(f"ok ({len(obs_tramo)} observaciones)")
            shutil.rmtree(chunk_dir, ignore_errors=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    observaciones.sort(key=lambda o: o.get("timestamp_segundos", 0))

    resultado = {
        "video": Path(args.video).name,
        "duracion_segundos": duracion_total,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "contexto": args.contexto,
        "total_observaciones": len(observaciones),
        "observaciones": observaciones,
    }

    out_dir = Path("analisis")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{Path(args.video).stem}_{datetime.now():%Y%m%d_%H%M%S}_data.json"
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(observaciones)} observaciones guardadas en {out_path}\n")
    for o in observaciones:
        t = o.get("timestamp_segundos", 0)
        mm, ss = divmod(int(t), 60)
        print(f"  [{mm:02d}:{ss:02d}] ({o.get('tipo', '?')}) {o.get('titulo', '(sin título)')}")


def cmd_corregir(args):
    """Revisa una observación puntual del JSON usando contexto adicional que da el jugador
    (ej. 'esto fue un 50/50 real, no un error de control'). Puede mantener, ajustar, o
    eliminar la observación según corresponda, y guarda el resultado en el mismo archivo."""
    client = anthropic.Anthropic()

    json_path = Path(args.json_path)
    datos = json.loads(json_path.read_text(encoding="utf-8"))
    obs_list = datos.get("observaciones", [])

    if args.indice < 0 or args.indice >= len(obs_list):
        print(f"Índice inválido: {args.indice} (hay {len(obs_list)} observaciones)", file=sys.stderr)
        sys.exit(1)

    original = obs_list[args.indice]

    instruccion = (
        "Observación original (JSON):\n" + json.dumps(original, ensure_ascii=False, indent=2) +
        "\n\nExplicación del jugador sobre qué pasó realmente en esta jugada:\n" + args.explicacion
    )

    print("Revisando observación con el contexto que diste...")
    respuesta = llamar_claude(client, SYSTEM_CORREGIR_OBSERVACION, [], instruccion)
    revisada = parsear_json_objeto_claude(respuesta)

    if not revisada:
        print("No se pudo interpretar la revisión de Claude.", file=sys.stderr)
        sys.exit(1)

    if revisada.get("tipo") == "sin_observacion":
        obs_list.pop(args.indice)
        print(f"✅ La observación se eliminó (con el contexto dado, ya no aplica): {revisada.get('nota_revision', '')}")
    else:
        obs_list[args.indice] = {
            "timestamp_segundos": original.get("timestamp_segundos"),
            "tipo": revisada.get("tipo", original.get("tipo")),
            "titulo": revisada.get("titulo", original.get("titulo")),
            "descripcion": revisada.get("descripcion", original.get("descripcion")),
            "consejo": revisada.get("consejo", original.get("consejo")),
            "contexto_segundos_antes": original.get("contexto_segundos_antes", 3),
            "revisado": True,
            "explicacion_usuario": args.explicacion,
            "nota_revision": revisada.get("nota_revision", ""),
        }
        print(f"✅ Observación revisada: {revisada.get('titulo', '')}")
        print(f"   {revisada.get('nota_revision', '')}")

    datos["observaciones"] = obs_list
    datos["total_observaciones"] = len(obs_list)
    json_path.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Guardado en {json_path}")


def main():
    parser = argparse.ArgumentParser(description="Coach de Rocket League con la API de Claude")
    sub = parser.add_subparsers(dest="comando", required=True)

    common = dict(
        fps=2.0, max_dim=768, max_frames=40,
        knowledge_base="knowledge_base.md",
    )

    p_aprender = sub.add_parser("aprender", help="Analiza un video de referencia (freestyle/pro) y suma al conocimiento")
    p_aprender.add_argument("--video", required=True, help="Ruta al video de referencia")
    p_aprender.add_argument("--contexto", default="", help="Descripción breve opcional del clip")
    p_aprender.add_argument("--fps", type=float, default=common["fps"], help="Frames por segundo a extraer (default 2)")
    p_aprender.add_argument("--max-dim", type=int, default=common["max_dim"], dest="max_dim", help="Lado largo máximo en px (default 768)")
    p_aprender.add_argument("--max-frames", type=int, default=common["max_frames"], dest="max_frames", help="Tope de frames a mandar a la API (default 40)")
    p_aprender.add_argument("--knowledge-base", default=common["knowledge_base"], dest="knowledge_base", help="Archivo donde acumular el conocimiento (default knowledge_base.md)")
    p_aprender.set_defaults(func=cmd_aprender)

    p_analizar = sub.add_parser("analizar", help="Analiza un video de tu propia partida usando lo aprendido")
    p_analizar.add_argument("--video", required=True, help="Ruta al video de tu jugada")
    p_analizar.add_argument("--contexto", default="", help="Descripción breve opcional de la jugada")
    p_analizar.add_argument("--fps", type=float, default=common["fps"], help="Frames por segundo a extraer (default 2)")
    p_analizar.add_argument("--max-dim", type=int, default=common["max_dim"], dest="max_dim", help="Lado largo máximo en px (default 768)")
    p_analizar.add_argument("--max-frames", type=int, default=common["max_frames"], dest="max_frames", help="Tope de frames a mandar a la API (default 40)")
    p_analizar.add_argument("--knowledge-base", default=common["knowledge_base"], dest="knowledge_base", help="Archivo de conocimiento a usar (default knowledge_base.md)")
    p_analizar.set_defaults(func=cmd_analizar)

    p_aprender_partido = sub.add_parser("aprender-partido", help="Analiza un partido COMPLETO de referencia (pro) por tramos y saca patrones de decisión")
    p_aprender_partido.add_argument("--video", required=True, help="Ruta al video del partido completo")
    p_aprender_partido.add_argument("--contexto", default="", help="Descripción breve opcional del partido")
    p_aprender_partido.add_argument("--fps", type=float, default=1.0, help="Frames por segundo dentro de cada tramo (default 1)")
    p_aprender_partido.add_argument("--max-dim", type=int, default=common["max_dim"], dest="max_dim")
    p_aprender_partido.add_argument("--chunk-seconds", type=float, default=60.0, dest="chunk_seconds", help="Duración de cada tramo en segundos (default 60)")
    p_aprender_partido.add_argument("--max-frames-por-tramo", type=int, default=30, dest="max_frames_por_tramo", help="Tope de frames por tramo (default 30)")
    p_aprender_partido.add_argument("--knowledge-base", default=common["knowledge_base"], dest="knowledge_base")
    p_aprender_partido.set_defaults(func=cmd_aprender_partido)

    p_analizar_partido = sub.add_parser("analizar-partido", help="Analiza un partido COMPLETO tuyo por tramos, usando la base de conocimiento")
    p_analizar_partido.add_argument("--video", required=True, help="Ruta al video de tu partido completo")
    p_analizar_partido.add_argument("--contexto", default="", help="Descripción breve opcional del partido")
    p_analizar_partido.add_argument("--fps", type=float, default=1.0, help="Frames por segundo dentro de cada tramo (default 1)")
    p_analizar_partido.add_argument("--max-dim", type=int, default=common["max_dim"], dest="max_dim")
    p_analizar_partido.add_argument("--chunk-seconds", type=float, default=60.0, dest="chunk_seconds", help="Duración de cada tramo en segundos (default 60)")
    p_analizar_partido.add_argument("--max-frames-por-tramo", type=int, default=30, dest="max_frames_por_tramo", help="Tope de frames por tramo (default 30)")
    p_analizar_partido.add_argument("--knowledge-base", default=common["knowledge_base"], dest="knowledge_base")
    p_analizar_partido.set_defaults(func=cmd_analizar_partido)

    p_analizar_app = sub.add_parser("analizar-app", help="Como analizar-partido, pero devuelve JSON con timestamps exactos (motor para la futura app con reproductor)")
    p_analizar_app.add_argument("--video", required=True, help="Ruta al video de tu partida")
    p_analizar_app.add_argument("--contexto", default="", help="Descripción breve opcional")
    p_analizar_app.add_argument("--fps", type=float, default=1.0, help="Frames por segundo dentro de cada tramo (default 1)")
    p_analizar_app.add_argument("--max-dim", type=int, default=common["max_dim"], dest="max_dim")
    p_analizar_app.add_argument("--chunk-seconds", type=float, default=60.0, dest="chunk_seconds", help="Duración de cada tramo en segundos (default 60)")
    p_analizar_app.add_argument("--max-frames-por-tramo", type=int, default=30, dest="max_frames_por_tramo")
    p_analizar_app.add_argument("--knowledge-base", default=common["knowledge_base"], dest="knowledge_base")
    p_analizar_app.set_defaults(func=cmd_analizar_app)

    p_corregir = sub.add_parser("corregir", help="Revisa una observación puntual del JSON con una explicación adicional del jugador")
    p_corregir.add_argument("--json", required=True, dest="json_path", help="Ruta al archivo *_data.json a corregir")
    p_corregir.add_argument("--indice", required=True, type=int, help="Índice (0-based) de la observación dentro del array")
    p_corregir.add_argument("--explicacion", required=True, help="Qué pasó realmente en la jugada, según el jugador")
    p_corregir.set_defaults(func=cmd_corregir)

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  No encontré la variable de entorno ANTHROPIC_API_KEY. Configurala con:\n"
              "   export ANTHROPIC_API_KEY='tu-api-key-aca'", file=sys.stderr)
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()