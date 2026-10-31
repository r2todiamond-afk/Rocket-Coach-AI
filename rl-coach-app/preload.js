const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  elegirVideo: () => ipcRenderer.invoke("elegir-video"),
  elegirAnalisis: () => ipcRenderer.invoke("elegir-analisis"),
  elegirScript: () => ipcRenderer.invoke("elegir-script"),
  obtenerConfig: () => ipcRenderer.invoke("obtener-config"),

  iniciarAnalisis: (payload) => ipcRenderer.send("iniciar-analisis", payload),
  onProgreso: (cb) => ipcRenderer.on("analisis-progreso", (_e, linea) => cb(linea)),
  onCompleto: (cb) => ipcRenderer.on("analisis-completo", (_e, data) => cb(data)),
  onError: (cb) => ipcRenderer.on("analisis-error", (_e, msg) => cb(msg)),

  iniciarCorreccion: (payload) => ipcRenderer.send("iniciar-correccion", payload),
  onCorreccionCompleta: (cb) => ipcRenderer.on("correccion-completa", (_e, data) => cb(data)),
  onCorreccionError: (cb) => ipcRenderer.on("correccion-error", (_e, msg) => cb(msg)),
});
