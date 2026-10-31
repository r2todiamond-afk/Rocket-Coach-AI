# RL Coach — App

Interfaz de escritorio para ver el análisis generado por `rl_coach.py` (comando
`analizar-app`) junto al video de tu partida: reproductor + lista de
observaciones clickeables + línea de tiempo con marcas de color.

## Instalación

Necesitás [Node.js](https://nodejs.org/) instalado (con eso ya viene `npm`).

```bash
cd rl-coach-app
npm install
```

## Uso

```bash
npm start
```

Se abre la ventana de la app:

1. Click en **"Elegir video"** → seleccioná el `.mp4`/`.mkv` de tu partida.
2. **La primera vez**, te va a pedir la ubicación de tu `rl_coach.py` (el mismo
   script que ya usás desde la terminal) — lo elegís una sola vez y la app lo
   recuerda para siempre (se guarda en la configuración de la app, no en el
   proyecto).
3. Te pregunta si querés agregar contexto de la partida (opcional, ej. "ranked
   1v1") y arranca el análisis automáticamente: corre `rl_coach.py analizar-app`
   por vos, mostrando el progreso en vivo (tramo por tramo, igual que verías en
   la terminal).
4. Cuando termina, el análisis se carga solo — la lista de la derecha se llena
   y la línea de tiempo debajo del video muestra las marcas de color.
5. Click en cualquier observación de la lista (o en una marca de la línea de
   tiempo) y el video salta automáticamente al momento justo, con margen de
   contexto antes.
6. Los filtros arriba de la lista ("Aciertos", "Errores", etc.) te dejan ver
   solo un tipo de observación a la vez.
7. Si ya tenés un análisis generado previamente y solo querés cargarlo (sin
   volver a correr el script), usá **"Cargar análisis existente"**.
8. El ícono ⚙ en la esquina superior te deja cambiar la ubicación del script
   en cualquier momento (por si lo movés de carpeta).
9. **Si no estás de acuerdo con una observación** (ej. te marcó un kickoff
   perdido como "error" cuando en realidad fue un 50/50 legítimo), click en
   **"✎ Corregir"** dentro de esa tarjeta, contale a la IA qué pasó
   realmente, y la va a revisar: puede ajustar la descripción/consejo, o
   directamente eliminarla si el contexto que diste hace que ya no aplique.
   Las observaciones corregidas quedan marcadas con una nota en cursiva
   explicando qué cambió.

**Nota sobre Python**: la app ejecuta el comando `python` tal cual lo tengas
configurado en tu PATH — es el mismo que ya usás en PowerShell, así que si ahí
te funciona, en la app también.

## Generar el instalador (.exe)

Cuando quieras un instalador para no depender de correr `npm start` cada vez:

```bash
npm run dist
```

Esto genera un instalador en la carpeta `dist/` usando `electron-builder`,
configurado para Windows (target NSIS).

## Estructura del proyecto

```
rl-coach-app/
├── main.js           # proceso principal de Electron (ventana, diálogos de archivo)
├── preload.js        # puente seguro entre main y la interfaz
├── package.json
└── renderer/
    ├── index.html
    ├── styles.css     # identidad visual (paleta, tipografía, timeline)
    └── renderer.js    # lógica: carga de archivos, lista, timeline, sync con video
```

## Notas

- El video y el JSON de análisis deben corresponder al mismo partido — la app
  no valida automáticamente que coincidan, así que fijate de elegir el par
  correcto.
- Si el video no carga, confirmá que el formato es uno soportado por el
  reproductor HTML5 (mp4/H.264 anda siempre bien; algunos `.mkv` con codecs
  raros pueden no reproducirse — en ese caso convertilo con
  `ffmpeg -i original.mkv -c:v libx264 -c:a aac convertido.mp4`).
