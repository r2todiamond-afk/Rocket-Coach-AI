const COLORES_TIPO = {
  acierto: "var(--c-acierto)",
  error: "var(--c-error)",
  jugada_dudosa: "var(--c-dudosa)",
  mecanica_sugerida: "var(--c-sugerida)",
  mecanica_de_mas: "var(--c-demas)",
};

const NOMBRES_TIPO = {
  acierto: "Acierto",
  error: "Error",
  jugada_dudosa: "Jugada dudosa",
  mecanica_sugerida: "Mecánica sugerida",
  mecanica_de_mas: "Mecánica de más",
};

const video = document.getElementById("video");
const videoEmpty = document.getElementById("video-empty");
const btnVideo = document.getElementById("btn-video");
const btnAnalisis = document.getElementById("btn-analisis");
const btnConfig = document.getElementById("btn-config");
const lista = document.getElementById("lista");
const contador = document.getElementById("contador");
const filtrosEl = document.getElementById("filtros");
const timeline = document.getElementById("timeline");
const timelineTicks = document.getElementById("timeline-ticks");
const timelineCursor = document.getElementById("timeline-cursor");

const modalConfig = document.getElementById("modal-config");
const btnElegirScript = document.getElementById("btn-elegir-script");
const modalContexto = document.getElementById("modal-contexto");
const inputContexto = document.getElementById("input-contexto");
const btnCancelarContexto = document.getElementById("btn-cancelar-contexto");
const btnConfirmarContexto = document.getElementById("btn-confirmar-contexto");
const modalProgreso = document.getElementById("modal-progreso");
const progresoLog = document.getElementById("progreso-log");
const progresoError = document.getElementById("progreso-error");
const btnCerrarProgreso = document.getElementById("btn-cerrar-progreso");

const modalExplicacion = document.getElementById("modal-explicacion");
const explicacionObsTitulo = document.getElementById("explicacion-obs-titulo");
const inputExplicacion = document.getElementById("input-explicacion");
const btnCancelarExplicacion = document.getElementById("btn-cancelar-explicacion");
const btnConfirmarExplicacion = document.getElementById("btn-confirmar-explicacion");

let observaciones = [];
let duracionTotal = 0;
let filtroActivo = "todos";
let tarjetasPorIndice = {};
let rutaScript = null;
let videoPendiente = null;
let rutaArchivoActual = null;
let indiceEnEdicion = null;

// -----------------------------------------------------------------------
// Configuración inicial: recordar dónde está rl_coach.py
// -----------------------------------------------------------------------

(async function iniciar() {
  const config = await window.api.obtenerConfig();
  if (config && config.rutaScript) rutaScript = config.rutaScript;
})();

btnConfig.addEventListener("click", async () => {
  const nueva = await window.api.elegirScript();
  if (nueva) rutaScript = nueva;
});

// -----------------------------------------------------------------------
// Carga de archivos
// -----------------------------------------------------------------------

btnVideo.addEventListener("click", async () => {
  const videoSeleccionado = await window.api.elegirVideo();
  if (!videoSeleccionado) return;

  cargarVideoEnReproductor(videoSeleccionado.videoUrl);
  videoPendiente = videoSeleccionado.videoPath;

  if (!rutaScript) {
    modalConfig.classList.remove("oculto");
    return;
  }

  abrirModalContexto();
});

function cargarVideoEnReproductor(videoUrl) {
  video.src = videoUrl;
  videoEmpty.style.display = "none";

  video.addEventListener(
    "loadedmetadata",
    () => {
      duracionTotal = video.duration || duracionTotal;
      renderTicks();
    },
    { once: true }
  );
}

// -----------------------------------------------------------------------
// Modal: elegir ubicación del script (primera vez)
// -----------------------------------------------------------------------

btnElegirScript.addEventListener("click", async () => {
  const script = await window.api.elegirScript();
  if (!script) return;
  rutaScript = script;
  modalConfig.classList.add("oculto");
  abrirModalContexto();
});

// -----------------------------------------------------------------------
// Modal: contexto opcional antes de analizar
// -----------------------------------------------------------------------

function abrirModalContexto() {
  inputContexto.value = "";
  modalContexto.classList.remove("oculto");
  inputContexto.focus();
}

btnCancelarContexto.addEventListener("click", () => {
  modalContexto.classList.add("oculto");
});

btnConfirmarContexto.addEventListener("click", () => {
  modalContexto.classList.add("oculto");
  iniciarAnalisisAutomatico(videoPendiente, inputContexto.value.trim());
});

inputContexto.addEventListener("keydown", (e) => {
  if (e.key === "Enter") btnConfirmarContexto.click();
});

// -----------------------------------------------------------------------
// Modal: progreso del análisis en vivo
// -----------------------------------------------------------------------

function iniciarAnalisisAutomatico(rutaVideo, contexto) {
  progresoLog.textContent = "";
  progresoError.classList.add("oculto");
  progresoError.textContent = "";
  btnCerrarProgreso.classList.add("oculto");
  modalProgreso.querySelector("h3").textContent = "Analizando tu partida...";
  modalProgreso.querySelector(".spinner").classList.remove("oculto");
  modalProgreso.classList.remove("oculto");

  window.api.iniciarAnalisis({ videoPath: rutaVideo, contexto, rutaScript });
}

window.api.onProgreso((linea) => {
  progresoLog.textContent += linea + "\n";
  progresoLog.scrollTop = progresoLog.scrollHeight;
});

window.api.onCompleto(({ rutaArchivo, datos }) => {
  rutaArchivoActual = rutaArchivo;
  observaciones = (datos.observaciones || []).slice().sort(
    (a, b) => (a.timestamp_segundos || 0) - (b.timestamp_segundos || 0)
  );
  if (datos.duracion_segundos) duracionTotal = datos.duracion_segundos;

  renderLista();
  renderTicks();
  modalProgreso.classList.add("oculto");
});

window.api.onError((mensaje) => {
  modalProgreso.querySelector("h3").textContent = "Algo salió mal";
  modalProgreso.querySelector(".spinner").classList.add("oculto");
  progresoError.textContent = mensaje;
  progresoError.classList.remove("oculto");
  btnCerrarProgreso.classList.remove("oculto");
});

btnCerrarProgreso.addEventListener("click", () => {
  modalProgreso.classList.add("oculto");
});

btnAnalisis.addEventListener("click", async () => {
  const resultado = await window.api.elegirAnalisis();
  if (!resultado) return;

  if (resultado.error) {
    alert(resultado.error);
    return;
  }

  const datos = resultado.datos;
  rutaArchivoActual = resultado.rutaArchivo;
  observaciones = (datos.observaciones || []).slice().sort(
    (a, b) => (a.timestamp_segundos || 0) - (b.timestamp_segundos || 0)
  );
  if (datos.duracion_segundos) duracionTotal = datos.duracion_segundos;

  renderLista();
  renderTicks();
});

// -----------------------------------------------------------------------
// Render de la lista de observaciones
// -----------------------------------------------------------------------

function formatoTiempo(segundos) {
  const s = Math.max(0, Math.floor(segundos));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function renderLista() {
  tarjetasPorIndice = {};
  lista.innerHTML = "";

  const filtradas = observaciones.filter(
    (o) => filtroActivo === "todos" || o.tipo === filtroActivo
  );

  contador.textContent = `${filtradas.length} / ${observaciones.length}`;

  if (observaciones.length === 0) {
    lista.innerHTML = `
      <div class="lista-vacia">
        <p>Sin análisis cargado</p>
        <span>Elegí un archivo JSON generado con <code>analizar-app</code></span>
      </div>`;
    return;
  }

  if (filtradas.length === 0) {
    lista.innerHTML = `
      <div class="lista-vacia">
        <p>Nada en este filtro</p>
        <span>Probá con otra categoría</span>
      </div>`;
    return;
  }

  filtradas.forEach((obs) => {
    const idxReal = observaciones.indexOf(obs);
    const card = document.createElement("div");
    card.className = "obs-card";
    card.style.setProperty("--tipo-color", COLORES_TIPO[obs.tipo] || "var(--text-faint)");
    card.innerHTML = `
      <div class="obs-top">
        <span class="obs-time">${formatoTiempo(obs.timestamp_segundos)}</span>
        <span class="obs-tipo">${escapeHtml(NOMBRES_TIPO[obs.tipo] || obs.tipo)}</span>
        <button class="obs-corregir" title="Contarle a la IA qué pasó realmente">✎ Corregir</button>
      </div>
      <p class="obs-titulo">${escapeHtml(obs.titulo || "")}</p>
      <p class="obs-desc">${escapeHtml(obs.descripcion || "")}</p>
      ${obs.consejo ? `<p class="obs-consejo"><span class="obs-consejo-label">💡 Consejo</span>${escapeHtml(obs.consejo)}</p>` : ""}
      ${obs.nota_revision ? `<p class="obs-nota-revision">✎ ${escapeHtml(obs.nota_revision)}</p>` : ""}
    `;
    card.querySelector(".obs-corregir").addEventListener("click", (e) => {
      e.stopPropagation();
      abrirModalExplicacion(idxReal);
    });
    card.addEventListener("click", () => saltarAObservacion(obs));
    tarjetasPorIndice[idxReal] = card;
    lista.appendChild(card);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// -----------------------------------------------------------------------
// Timeline con marcas de eventos
// -----------------------------------------------------------------------

function renderTicks() {
  timelineTicks.innerHTML = "";
  if (!duracionTotal || observaciones.length === 0) return;

  observaciones.forEach((obs) => {
    const pct = Math.min(100, Math.max(0, (obs.timestamp_segundos / duracionTotal) * 100));
    const tick = document.createElement("div");
    tick.className = "tick";
    tick.style.left = pct + "%";
    tick.style.background = COLORES_TIPO[obs.tipo] || "var(--text-faint)";
    tick.title = `${formatoTiempo(obs.timestamp_segundos)} — ${obs.titulo || ""}`;
    tick.addEventListener("click", (e) => {
      e.stopPropagation();
      saltarAObservacion(obs);
    });
    timelineTicks.appendChild(tick);
  });
}

timeline.addEventListener("click", (e) => {
  if (!video.src || !duracionTotal) return;
  const rect = timeline.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  video.currentTime = pct * duracionTotal;
  video.play();
});

video.addEventListener("timeupdate", () => {
  if (!duracionTotal) return;
  const pct = (video.currentTime / duracionTotal) * 100;
  timelineCursor.style.left = pct + "%";
});

// -----------------------------------------------------------------------
// Saltar a una observación (con contexto previo) y marcarla activa
// -----------------------------------------------------------------------

function saltarAObservacion(obs) {
  if (!video.src) {
    alert("Primero cargá el video correspondiente a este análisis.");
    return;
  }
  const contexto = obs.contexto_segundos_antes || 0;
  const destino = Math.max(0, obs.timestamp_segundos - contexto);
  video.currentTime = destino;
  video.play();

  document.querySelectorAll(".obs-card.activa").forEach((c) => c.classList.remove("activa"));
  const idx = observaciones.indexOf(obs);
  const card = tarjetasPorIndice[idx];
  if (card) {
    card.classList.add("activa");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// -----------------------------------------------------------------------
// Filtros
// -----------------------------------------------------------------------

filtrosEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".filtro");
  if (!btn) return;
  filtrosEl.querySelectorAll(".filtro").forEach((b) => b.classList.remove("activo"));
  btn.classList.add("activo");
  filtroActivo = btn.dataset.tipo;
  renderLista();
});

// -----------------------------------------------------------------------
// Corregir una observación con contexto adicional del jugador
// -----------------------------------------------------------------------

function abrirModalExplicacion(idx) {
  if (!rutaScript || !rutaArchivoActual) {
    alert("Esta observación no se puede corregir todavía (falta el script o el archivo de análisis).");
    return;
  }
  indiceEnEdicion = idx;
  const obs = observaciones[idx];
  explicacionObsTitulo.textContent = `${formatoTiempo(obs.timestamp_segundos)} — ${obs.titulo || ""}`;
  inputExplicacion.value = "";
  modalExplicacion.classList.remove("oculto");
  inputExplicacion.focus();
}

btnCancelarExplicacion.addEventListener("click", () => {
  modalExplicacion.classList.add("oculto");
  indiceEnEdicion = null;
});

btnConfirmarExplicacion.addEventListener("click", () => {
  const explicacion = inputExplicacion.value.trim();
  if (!explicacion) return;

  modalExplicacion.classList.add("oculto");

  progresoLog.textContent = "";
  progresoError.classList.add("oculto");
  progresoError.textContent = "";
  btnCerrarProgreso.classList.add("oculto");
  modalProgreso.querySelector("h3").textContent = "Revisando observación...";
  modalProgreso.querySelector(".spinner").classList.remove("oculto");
  modalProgreso.classList.remove("oculto");

  window.api.iniciarCorreccion({
    rutaScript,
    rutaJson: rutaArchivoActual,
    indice: indiceEnEdicion,
    explicacion,
  });
});

window.api.onCorreccionCompleta(({ rutaArchivo, datos }) => {
  rutaArchivoActual = rutaArchivo;
  observaciones = (datos.observaciones || []).slice().sort(
    (a, b) => (a.timestamp_segundos || 0) - (b.timestamp_segundos || 0)
  );
  renderLista();
  renderTicks();
  modalProgreso.classList.add("oculto");
  indiceEnEdicion = null;
});

window.api.onCorreccionError((mensaje) => {
  modalProgreso.querySelector("h3").textContent = "Algo salió mal";
  modalProgreso.querySelector(".spinner").classList.add("oculto");
  progresoError.textContent = mensaje;
  progresoError.classList.remove("oculto");
  btnCerrarProgreso.classList.remove("oculto");
});
