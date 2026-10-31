const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const { extractAnalysisPath, resolveAnalysisPath, videoPathToFileUrl } = require("./app-utils");

let mainWindow;

function crearVentana() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 650,
    backgroundColor: "#0B0E14",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  crearVentana();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) crearVentana();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// -----------------------------------------------------------------------
// IPC: diálogos de selección de archivos
// -----------------------------------------------------------------------

ipcMain.handle("elegir-video", async () => {
  const resultado = await dialog.showOpenDialog(mainWindow, {
    title: "Elegí el video de tu partida",
    properties: ["openFile"],
    filters: [
      { name: "Videos", extensions: ["mp4", "mkv", "mov", "avi", "webm"] },
    ],
  });
  if (resultado.canceled || resultado.filePaths.length === 0) return null;
  const videoPath = resultado.filePaths[0];
  return { videoPath, videoUrl: videoPathToFileUrl(videoPath) };
});

ipcMain.handle("elegir-analisis", async () => {
  const resultado = await dialog.showOpenDialog(mainWindow, {
    title: "Elegí el archivo de análisis (JSON generado por rl_coach.py)",
    properties: ["openFile"],
    filters: [{ name: "Análisis JSON", extensions: ["json"] }],
  });
  if (resultado.canceled || resultado.filePaths.length === 0) return null;

  try {
    const contenido = fs.readFileSync(resultado.filePaths[0], "utf-8");
    const datos = JSON.parse(contenido);
    return { rutaArchivo: resultado.filePaths[0], datos };
  } catch (err) {
    return { error: `No se pudo leer o interpretar el archivo: ${err.message}` };
  }
});

// -----------------------------------------------------------------------
// Configuración persistente (dónde está rl_coach.py en la máquina del usuario)
// -----------------------------------------------------------------------

function rutaConfig() {
  return path.join(app.getPath("userData"), "config.json");
}

ipcMain.handle("obtener-config", async () => {
  try {
    return JSON.parse(fs.readFileSync(rutaConfig(), "utf-8"));
  } catch {
    return {};
  }
});

ipcMain.handle("elegir-script", async () => {
  const resultado = await dialog.showOpenDialog(mainWindow, {
    title: "Elegí tu archivo rl_coach.py",
    properties: ["openFile"],
    filters: [{ name: "Script Python", extensions: ["py"] }],
  });
  if (resultado.canceled || resultado.filePaths.length === 0) return null;

  const rutaScript = resultado.filePaths[0];
  try {
    fs.writeFileSync(rutaConfig(), JSON.stringify({ rutaScript }));
  } catch (err) {
    // si falla el guardado igual devolvemos la ruta para usar en esta sesión
  }
  return rutaScript;
});

// -----------------------------------------------------------------------
// Ejecutar rl_coach.py analizar-app y transmitir el progreso en vivo
// -----------------------------------------------------------------------

ipcMain.on("iniciar-analisis", (event, { videoPath, contexto, rutaScript }) => {
  const scriptDir = path.dirname(rutaScript);
  const nombreScript = path.basename(rutaScript);
  const args = ["-u", nombreScript, "analizar-app", "--video", videoPath];
  if (contexto) args.push("--contexto", contexto);

  const proceso = spawn("python", args, {
    cwd: scriptDir,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  let buffer = "";
  let rutaJsonGenerado = null;
  let falloAlIniciar = false;

  const emitirLineas = (chunk) => {
    buffer += chunk.toString();
    const lineas = buffer.split(/\r?\n/);
    buffer = lineas.pop();
    lineas.forEach((linea) => {
      if (!linea.trim()) return;
      const rutaInformada = extractAnalysisPath(linea);
      if (rutaInformada) rutaJsonGenerado = resolveAnalysisPath(scriptDir, rutaInformada);
      event.sender.send("analisis-progreso", linea);
    });
  };

  proceso.stdout.on("data", emitirLineas);
  proceso.stderr.on("data", emitirLineas);

  proceso.on("error", (err) => {
    falloAlIniciar = true;
    event.sender.send(
      "analisis-error",
      `No se pudo iniciar Python ("${err.message}"). Verificá que Python esté instalado y accesible como "python" desde la terminal.`
    );
  });

  proceso.on("close", (code) => {
    if (falloAlIniciar) return;
    if (code !== 0) {
      event.sender.send("analisis-error", `El script terminó con un error (código ${code}). Revisá el log de arriba.`);
      return;
    }

    try {
      if (!rutaJsonGenerado) {
        event.sender.send("analisis-error", "El análisis terminó, pero el script no informó la ruta del JSON generado.");
        return;
      }

      const datos = JSON.parse(fs.readFileSync(rutaJsonGenerado, "utf-8"));
      event.sender.send("analisis-completo", { rutaArchivo: rutaJsonGenerado, datos });
    } catch (err) {
      event.sender.send("analisis-error", `Error leyendo el resultado: ${err.message}`);
    }
  });
});

// -----------------------------------------------------------------------
// Corregir una observación puntual con contexto adicional del usuario
// -----------------------------------------------------------------------

ipcMain.on("iniciar-correccion", (event, { rutaScript, rutaJson, indice, explicacion }) => {
  const scriptDir = path.dirname(rutaScript);
  const nombreScript = path.basename(rutaScript);
  const args = [
    "-u", nombreScript, "corregir",
    "--json", rutaJson,
    "--indice", String(indice),
    "--explicacion", explicacion,
  ];

  const proceso = spawn("python", args, {
    cwd: scriptDir,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  let buffer = "";
  let falloAlIniciar = false;

  const emitirLineas = (chunk) => {
    buffer += chunk.toString();
    const lineas = buffer.split(/\r?\n/);
    buffer = lineas.pop();
    lineas.forEach((linea) => {
      if (linea.trim()) event.sender.send("analisis-progreso", linea);
    });
  };

  proceso.stdout.on("data", emitirLineas);
  proceso.stderr.on("data", emitirLineas);

  proceso.on("error", (err) => {
    falloAlIniciar = true;
    event.sender.send("correccion-error", `No se pudo iniciar Python ("${err.message}").`);
  });

  proceso.on("close", (code) => {
    if (falloAlIniciar) return;
    if (code !== 0) {
      event.sender.send("correccion-error", `El script terminó con un error (código ${code}). Revisá el log de arriba.`);
      return;
    }
    try {
      const datos = JSON.parse(fs.readFileSync(rutaJson, "utf-8"));
      event.sender.send("correccion-completa", { rutaArchivo: rutaJson, datos });
    } catch (err) {
      event.sender.send("correccion-error", `Error leyendo el resultado: ${err.message}`);
    }
  });
});
