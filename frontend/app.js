// ============================================================
// Lineal — Smart City Planner  |  app.js v4.0
// Multi-Agent Urban Planning
// ============================================================

const API_BASE = "http://localhost:8001";

// ── State ────────────────────────────────────────────────────
let map, deckOverlay, drawingManager, drawnPolygon;
const _hiddenLayers = new Set(); // layer types toggled off by user
let currentLang = "es";

// ── Translations ──────────────────────────────────────────────
const T = {
  es: {
    lang_btn:           "EN",
    legend_title:       "Simbología",
    sim_group:          "Simulación",
    assets_group:       "Capas SIIMP",
    chat_placeholder:   "Escribe tu respuesta...",
    chat_title:         "Consultor",
    spinner:            "Analizando ciudad con IA...",
    status_active:      "AI ACTIVO",
    status_demo:        "MODO DEMO",
    status_offline:     "BACKEND DESCONECTADO",
    connecting:         "CONECTANDO...",
    map_init:           "INICIALIZANDO MOTOR ESPACIAL...",
    map_no_key:         "Configura GOOGLE_MAPS_API_KEY en el .env",
    import_pdfs:        "Importar PDFs",
    export_pdf:         "Exportar PDF",
    header_tag:         "Multi-Agente",
    search_placeholder: "Buscar ciudad o dirección...",
    view_proposal:      "Propuesta",
    draw:               "Dibujar",
    layers: {
      housing:        "Desarrollo Habitacional",
      green_space:    "Espacios Verdes",
      transport:      "Movilidad",
      flood:          "Gestión Hídrica",
      infrastructure: "Infraestructura",
      blocked:        "Bloqueadas",
    },
    siimp: {
      vialidades:              "Vialidades",
      contencion_urbana:       "Contención Urbana",
      zufos:                   "ZUFOs — Crecimiento",
      zonas_dinamica_especial: "Dinámica Especial",
      materiales_petreos:      "Materiales Pétreos",
    },
    opening_msg: "¡Hola! Soy **Lineal**, tu consultor de planeación urbana con IA para Aguascalientes. 🏙️\n\nCon 3 preguntas rápidas diseñaré el portafolio de desarrollo óptimo para tu zona.\n\n**¿Qué tipo de proyecto quieres desarrollar?**\n_(ej: vivienda residencial, vivienda social, comercial/retail, usos mixtos, parque urbano, transporte...)_",
    brief_ready: "Brief listo — iniciando análisis multi-agente...",
    chat_error:  "Error al conectar con el backend.",
    draw_zone:   "Marcar zona",
    draw_zone_hint: "Dibuja un polígono en el mapa para delimitar el área de proyecto, luego continúa la entrevista.",
    zone_active: "Zona activa ✓",
    zone_clear:  "Limpiar zona",
  },
  en: {
    lang_btn:           "ES",
    legend_title:       "Legend",
    sim_group:          "Simulation",
    assets_group:       "SIIMP Layers",
    chat_placeholder:   "Type your answer...",
    chat_title:         "Consultant",
    spinner:            "Analyzing city with AI...",
    status_active:      "AI ACTIVE",
    status_demo:        "DEMO MODE",
    status_offline:     "BACKEND OFFLINE",
    connecting:         "CONNECTING...",
    map_init:           "INITIALIZING SPATIAL ENGINE...",
    map_no_key:         "Set GOOGLE_MAPS_API_KEY in backend .env",
    import_pdfs:        "Import PDFs",
    export_pdf:         "Export PDF",
    header_tag:         "Multi-Agent",
    search_placeholder: "Search city or address...",
    view_proposal:      "Proposal",
    draw:               "Draw",
    layers: {
      housing:        "Residential Development",
      green_space:    "Green Spaces",
      transport:      "Mobility",
      flood:          "Water Management",
      infrastructure: "Infrastructure",
      blocked:        "Blocked",
    },
    siimp: {
      vialidades:              "Roads",
      contencion_urbana:       "Urban Boundary",
      zufos:                   "Growth Zones",
      zonas_dinamica_especial: "Special Dynamic Zones",
      materiales_petreos:      "Stone Material Areas",
    },
    opening_msg: "Hi! I'm **Lineal**, your AI urban planning consultant for Aguascalientes. 🏙️\n\nIn 3 quick questions I'll design the optimal development portfolio for your zone.\n\n**What type of project do you want to develop?**\n_(e.g., residential housing, social housing, commercial, mixed-use, urban park, transport...)_",
    brief_ready: "Brief ready — starting multi-agent analysis...",
    chat_error:  "Error connecting to backend.",
    draw_zone:   "Mark zone",
    draw_zone_hint: "Draw a polygon on the map to define the project area, then continue the interview.",
    zone_active: "Zone active ✓",
    zone_clear:  "Clear zone",
  },
};
const siimpDataLayers = {};
let _currentDeckLayers = [];
let is3D = true;
let currentSimulationData = null;
let currentViewMode = "optimized";
let stepInterval = null;
let currentStep = 0;
const STEP_DURATIONS = [9000, 11000, 7000, 6000];

// ── Color Palette (Construido: Azul, No construido: Gris, Verde: Verde) ──
const P = {
  housing: {
    tower:  [26,  115, 232, 248],   // #1a73e8 - Azul Google
    mid:    [66,  133, 244, 228],   // #4285f4 - Azul medio
    podium: [25,  103, 210, 200],   // #1967d2 - Azul profundo
    border: [100, 181, 246, 220],
    css: "#1a73e8",
    label: "Desarrollo Habitacional",
    desc: "Torres residenciales y conjuntos de vivienda de alta densidad"
  },
  green_space: {
    fill:   [52,  168, 83,  210],   // #34a853 - Verde Google
    tree:   null,
    border: [30,  142, 62,  160],
    css: "#34A853",
    label: "Espacio Verde / Parque",
    desc: "Parques, corredores ecológicos y áreas de biodiversidad urbana"
  },
  transport: {
    road:     [21,  82,  173, 255],  // Azul oscuro (calzada)
    lane:     [66,  133, 244, 200],  // Azul medio (carriles)
    sidewalk: [40,  70,  140, 160],  // Azul tenue (banqueta)
    css: "#1552ad",
    label: "Movilidad e Infraestructura Vial",
    desc: "Corredores de transporte, ciclovías y peatonalización"
  },
  flood: {
    outer: [154, 160, 166, 130],    // #9aa0a6 - Gris Google (No construido)
    inner: [128, 134, 139, 195],    // #80868b - Gris medio
    border:[189, 193, 198, 220],    // #bdc1c6 - Gris claro
    css: "#9aa0a6",
    label: "Gestión Hídrica y Resiliencia",
    desc: "Cuencas de retención, drenaje pluvial y zonas de amortiguamiento"
  },
  infrastructure: {
    main:   [30,  136, 229, 225],   // Azul material (equipamiento)
    accent: [66,  165, 245, 200],   // Azul claro
    border: [100, 181, 246, 200],
    css: "#1e88e5",
    label: "Infraestructura Urbana",
    desc: "Equipamiento público, servicios y redes de abastecimiento"
  },
  blocked: {
    fill:   [218, 30,  40,  80],
    border: [255, 70,  70,  200],
    css: "#DA1E28",
    label: "Intervención Bloqueada",
    desc: "No factible por normativa vigente o conflicto geoespacial"
  }
};

// ── Reference images served from /ui/ static folder ──────────
const TYPE_IMG = {
  housing:        "./img_housing.png",
  green_space:    "./img_green.png",
  transport:      "./img_transport.png",
  flood:          "./img_flood.png",
  infrastructure: "./img_infra.png",
};


// ── DOM Refs ─────────────────────────────────────────────────
let promptEl, generateBtn, drawBtn, spinner;
let proposedList, validatedList, analyzerReport;
let searchInput, searchBtn, viewToggle, viewToggleMode, exportBtn;
let sliderBlend;
let metricOverall, metricResilience, metricCO2, metricCost, metricPopulation, metricTimeline;
let recommendationBox, apiStatus, btnText, simBadge, mapTooltip, simLegend;
let pdfFileInput, importPdfBtn, exportReportBtn, pdfCountDisplay, pdfBadge;
let sessionCity, systemEstado;
let sidebarEl, sidebarToggleBtn;
let pdfCount = 0;

document.addEventListener("DOMContentLoaded", () => {
  promptEl         = document.getElementById("prompt");
  generateBtn      = document.getElementById("generate-btn");
  drawBtn          = document.getElementById("draw-btn");
  spinner          = document.getElementById("spinner");
  proposedList     = document.getElementById("proposed-list");
  validatedList    = document.getElementById("validated-list");
  analyzerReport   = document.getElementById("analyzer-report");
  searchInput      = document.getElementById("map-search-input");
  searchBtn        = document.getElementById("map-search-btn");
  viewToggle       = document.getElementById("view-toggle");
  viewToggleMode   = document.getElementById("view-toggle-mode");
  exportBtn        = document.getElementById("export-btn");
  apiStatus        = document.getElementById("api-status");
  btnText          = document.getElementById("btn-text");
  simBadge         = document.getElementById("sim-badge");
  mapTooltip       = document.getElementById("map-tooltip");
  simLegend        = document.getElementById("sim-legend");
  sliderBlend      = document.getElementById("slider-blend");

  metricOverall    = document.getElementById("metric-overall");
  metricResilience = document.getElementById("metric-resilience");
  metricCO2        = document.getElementById("metric-co2");
  metricCost       = document.getElementById("metric-cost");
  metricPopulation = document.getElementById("metric-population");
  metricTimeline   = document.getElementById("metric-timeline");
  recommendationBox = document.getElementById("recommendation-box");

  pdfFileInput     = document.getElementById("pdf-file-input");
  importPdfBtn     = document.getElementById("import-pdf-btn");
  pdfCountDisplay  = document.getElementById("pdf-count-display");
  pdfBadge         = document.getElementById("pdf-badge");
  sessionCity      = document.getElementById("session-city");
  systemEstado     = document.getElementById("system-estado");
  sidebarEl        = document.getElementById("sidebar");

  // Slider (hidden but functional)
  if (sliderBlend) sliderBlend.addEventListener("input", e => { updateBlend(e.target.value / 100); });

  // Vista toggle
  if (viewToggleMode) viewToggleMode.addEventListener("click", () => {
    currentViewMode = currentViewMode === "optimized" ? "current" : "optimized";
    const label = currentViewMode === "optimized" ? "Propuesta" : "Actual";
    const lbl = viewToggleMode.querySelector(".tool-label");
    if (lbl) lbl.textContent = label;
    viewToggleMode.classList.toggle("active", currentViewMode === "current");
    updateSimBadge();
    if (currentSimulationData) renderLayers(currentSimulationData);
  });

  if (drawBtn)    drawBtn.addEventListener("click", toggleDrawMode);
  if (viewToggle) viewToggle.addEventListener("click", toggle3D);
  if (searchBtn)  searchBtn.addEventListener("click", searchLocation);
  if (searchInput) searchInput.addEventListener("keyup", e => { if (e.key === "Enter") searchLocation(); });
  if (exportBtn)  exportBtn.addEventListener("click", exportResults);
  if (importPdfBtn) importPdfBtn.addEventListener("click", () => pdfFileInput.click());
  if (pdfFileInput) pdfFileInput.addEventListener("change", () => handlePdfUpload(pdfFileInput.files));

  initMap();
  checkApiHealth();
  initChatbot();
  initLayerToggles();
});

// ── PDF Upload ────────────────────────────────────────────────
async function handlePdfUpload(files) {
  if (!files || files.length === 0) return;
  const formData = new FormData();
  Array.from(files).forEach(f => formData.append("files", f));
  importPdfBtn.disabled = true;
  importPdfBtn.style.opacity = "0.6";
  try {
    const res  = await fetch(`${API_BASE}/upload-pdfs`, { method: "POST", body: formData });
    const data = await res.json();
    pdfCount += data.count ?? files.length;
  } catch {
    pdfCount += files.length; // optimistic — backend may not have the endpoint yet
  } finally {
    importPdfBtn.disabled = false;
    importPdfBtn.style.opacity = "";
    if (pdfCountDisplay) pdfCountDisplay.textContent = pdfCount;
    if (pdfBadge) { pdfBadge.textContent = pdfCount; pdfBadge.classList.remove("hidden"); }
    pdfFileInput.value = "";
  }
}

// ── API Health ────────────────────────────────────────────────

function setApiStatus(text, color) {
  // Preserve the Material icon span, only update the text node
  const icon = apiStatus.querySelector(".material-symbols-outlined");
  apiStatus.innerHTML = "";
  if (icon) apiStatus.appendChild(icon);
  apiStatus.appendChild(document.createTextNode(" " + text));
  apiStatus.style.color = color;
}

async function checkApiHealth() {
  try {
    const res  = await fetch(`${API_BASE}/`);
    const data = await res.json();
    const t = T[currentLang];
    setApiStatus(data.mode === "watsonx" ? t.status_active : t.status_demo,
                 data.mode === "watsonx" ? "#81c995" : "#fdd663");
  } catch {
    setApiStatus("BACKEND DESCONECTADO", "#f28b82");
  }
}

// ── Google Maps Dark — Custom Style Builder ───────────────────
// Descarga el estilo base de CartoDB y sobreescribe los colores
// para replicar la paleta oscura de Google Maps.

// GM kept only for SIIMP overlay colors (base map is now real Google Maps)
const GM = {
  building:     "#2b2b2b",
  buildingTop:  "#333333",
  hwyFill:      "#3c3c3c",
  park:         "#182522",
  wood:         "#1d2c21",
  mountain:     "#2c2c2c",
  commercial:   "#232323",
  industrial:   "#232323",
};

function loadGoogleMapsScript(key) {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.maps) { resolve(); return; }
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&libraries=drawing,geometry,places&language=es&region=MX`;
    s.async = true; s.defer = true;
    s.onload = resolve; s.onerror = reject;
    document.head.appendChild(s);
  });
}

// ── Map Init ──────────────────────────────────────────────────

async function initMap() {
  const loadingEl = document.getElementById("map-loading");

  let key = "";
  try {
    const r = await fetch(`${API_BASE}/maps/key`);
    const j = await r.json();
    key = j.key || "";
  } catch (e) { console.warn("maps/key failed:", e); }

  if (!key) {
    if (loadingEl) {
      loadingEl.innerHTML = `
        <span class="material-symbols-outlined" style="font-size:36px;color:#f28b82;opacity:0.7">map_off</span>
        <span style="font-size:0.85rem;letter-spacing:2px">GOOGLE_MAPS_API_KEY</span>
        <span style="font-size:0.72rem;color:var(--muted)">Configura la clave en el backend .env</span>
      `;
    }
    return;
  }

  await loadGoogleMapsScript(key);

  if (loadingEl) loadingEl.style.display = "none";

  map = new google.maps.Map(document.getElementById("map-container"), {
    center: { lat: 21.88, lng: -102.29 },
    zoom: 15,
    tilt: 0,
    heading: 0,
    mapId: "DEMO_MAP_ID",          // WebGL rendering + edificios 3D
    mapTypeId: "roadmap",
    gestureHandling: "greedy",
    disableDefaultUI: true,         // deshabilitamos los controles default
    zoomControl: false,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,
  });

  // Floating controls are siblings of #map-container inside .map-wrap,
  // positioned absolute via CSS — no map.controls push needed.

  // ── Places Autocomplete en el buscador ───────────────────────
  const autocomplete = new google.maps.places.Autocomplete(searchInput, {
    fields: ["geometry", "name", "formatted_address"],
    language: "es",
  });
  autocomplete.addListener("place_changed", () => {
    const place = autocomplete.getPlace();
    if (!place.geometry || !place.geometry.location) return;
    map.panTo(place.geometry.location);
    map.setZoom(15);
    if (sessionCity) sessionCity.textContent = place.name || place.formatted_address || "";
  });

  // Deck.gl overlay para Google Maps
  deckOverlay = new deck.GoogleMapsOverlay({
    layers: [],
    glOptions: { preserveDrawingBuffer: true },   // enables canvas.toDataURL() for PDF export
    getTooltip: ({ object }) => {
      if (!object || !object._meta) return null;
      return buildTooltip(object._meta);
    },
  });
  deckOverlay.setMap(map);

  // Drawing Manager (reemplaza MapboxDraw)
  drawingManager = new google.maps.drawing.DrawingManager({
    drawingMode: null,
    drawingControl: false,
    polygonOptions: {
      fillColor: "#4285f4", fillOpacity: 0.10,
      strokeColor: "#4285f4", strokeWeight: 2.5, editable: false,
    },
  });
  drawingManager.setMap(map);

  google.maps.event.addListener(drawingManager, "polygoncomplete", (polygon) => {
    if (drawnPolygon) drawnPolygon.setMap(null);
    drawnPolygon = polygon;
    drawingManager.setDrawingMode(null);
    if (drawBtn) { drawBtn.classList.remove("active"); const lbl = drawBtn.querySelector(".tool-label"); if (lbl) lbl.textContent = "Dibujar"; }
    updateDrawZoneBtn();
  });

  document.querySelector(".map-loading")?.remove();
  loadSiimpLayers();
}

// ── SIIMP Layers — SIIMP / ArcGIS API ────────────────────────
//
// Cada capa tiene su propio color basado en la paleta Google Maps
// dark + el significado urbano del dato:
//
//  vialidades           → línea gris (vías existentes)
//  contencion_urbana    → polígono gris azulado (límite urbano)
//  zufos                → polígono beige/ocre (expansión futura)
//  zonas_dinamica_especial → polígono verde tenue (zonas especiales)
//  materiales_petreos   → polígono café (extracción / industrial)
// ─────────────────────────────────────────────────────────────

const SIIMP_STYLES = {
  vialidades: {
    label: "Vialidades",
    color: "#4a4e56",        // GM.hwyFill — gris vías
    outline: null,
    fillOpacity: null,
    lineWidth: ["interpolate", ["linear"], ["zoom"], 10, 0.8, 14, 2, 18, 4],
    lineOpacity: 0.9,
  },
  contencion_urbana: {
    label: "Contención Urbana",
    color: "#3c4046",        // GM.building — gris urbano
    outline: "#5a606a",
    fillOpacity: 0.22,
    lineWidth: 1.5,
    lineOpacity: 0.8,
  },
  zufos: {
    label: "ZUFOs — Zonas de Crecimiento",
    color: "#2d2920",        // GM.commercial — ocre/beige oscuro
    outline: "#6b5a30",
    fillOpacity: 0.30,
    lineWidth: 1.2,
    lineOpacity: 0.75,
  },
  zonas_dinamica_especial: {
    label: "Zonas Dinámica Especial",
    color: "#182522",        // GM.park — verde Night
    outline: "#2e6048",
    fillOpacity: 0.28,
    lineWidth: 1.2,
    lineOpacity: 0.70,
  },
  materiales_petreos: {
    label: "Materiales Pétreos",
    color: "#362c22",        // GM.mountain — café / industrial
    outline: "#6b4428",
    fillOpacity: 0.38,
    lineWidth: 1.0,
    lineOpacity: 0.65,
  },
};

async function loadSiimpLayers() {
  const layerNames = Object.keys(SIIMP_STYLES);

  // Indicar carga en el sidebar
  const statusEl = document.getElementById("siimp-status");
  if (statusEl) statusEl.textContent = "Cargando...";

  let loaded = 0;

  try {
    const res = await fetch(`${API_BASE}/geo/multi`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layers: layerNames }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const allLayers = await res.json();

    for (const [name, geojson] of Object.entries(allLayers)) {
      const style = SIIMP_STYLES[name];
      if (!style) continue;

      if (!geojson || geojson.error || !Array.isArray(geojson.features)) {
        console.warn(`SIIMP '${name}' sin datos:`, geojson?.error ?? "vacío");
        continue;
      }

      // Create a google.maps.Data layer for this GeoJSON
      const dataLayer = new google.maps.Data();
      dataLayer.addGeoJson(geojson);
      dataLayer.setStyle({
        strokeColor:   style.outline ?? style.color,
        strokeWeight:  typeof style.lineWidth === "number" ? style.lineWidth : 1.5,
        strokeOpacity: style.lineOpacity ?? 0.8,
        fillColor:     style.color,
        fillOpacity:   style.fillOpacity ?? 0,
      });
      dataLayer.setMap(null);          // hidden until user enables it
      siimpDataLayers[name] = dataLayer;

      // Mark button as loaded but OFF (user must click to enable)
      const btn = document.querySelector(`.lt-btn[data-siimp="${name}"]`);
      if (btn) {
        btn.classList.remove("lt-loading");
        btn.classList.add("off");
      }
      renderLegend();

      loaded++;
    }

    if (statusEl) statusEl.textContent = `${loaded}/${layerNames.length} capas`;
  } catch (err) {
    console.warn("SIIMP layers no disponibles:", err.message);
    if (statusEl) statusEl.textContent = "Backend offline";
  }
}

function toggleSiimpLayer(name, visible) {
  const layer = siimpDataLayers[name];
  if (layer) layer.setMap(visible ? map : null);
}

// ── Map Utilities ─────────────────────────────────────────────

function updateBlend(opacity) {
  if (!deckOverlay || _currentDeckLayers.length === 0) return;
  deckOverlay.setProps({ layers: _currentDeckLayers.map(l => l.clone({ opacity })) });
}

async function searchLocation() {
  const q = searchInput.value.trim();
  if (!q) return;
  try {
    const res  = await fetch(`${API_BASE}/maps/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (data.lat && data.lng) {
      map.panTo({ lat: data.lat, lng: data.lng });
      map.setZoom(15);
      if (sessionCity) sessionCity.textContent = data.name;
    } else {
      alert("Ubicación no encontrada.");
    }
  } catch (e) { console.error("searchLocation error:", e); }
}

function updateDrawZoneBtn() {
  const t = T[currentLang];
  const btn = document.getElementById("draw-zone-btn");
  if (!btn) return;
  const lbl = btn.querySelector(".dz-label");
  const statusEl = document.getElementById("zone-status-label");
  const isDrawing = map && drawingManager && drawingManager.getDrawingMode() !== null;
  if (drawnPolygon) {
    btn.classList.add("zone-set");
    btn.classList.remove("zone-drawing");
    if (lbl) lbl.textContent = t.zone_clear;
    if (statusEl) { statusEl.textContent = t.zone_active; statusEl.style.display = ""; }
  } else if (isDrawing) {
    btn.classList.remove("zone-set");
    btn.classList.add("zone-drawing");
    if (lbl) lbl.textContent = "Cancelar";
    if (statusEl) statusEl.style.display = "none";
  } else {
    btn.classList.remove("zone-set", "zone-drawing");
    if (lbl) lbl.textContent = t.draw_zone;
    if (statusEl) statusEl.style.display = "none";
  }
}

function toggleDrawMode() {
  if (drawingManager.getDrawingMode() !== null) {
    drawingManager.setDrawingMode(null);
    if (drawBtn) { const lbl = drawBtn.querySelector(".tool-label"); if (lbl) lbl.textContent = "Dibujar"; drawBtn.classList.remove("active"); }
  } else {
    if (drawnPolygon) { drawnPolygon.setMap(null); drawnPolygon = null; }
    drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
    if (drawBtn) { const lbl = drawBtn.querySelector(".tool-label"); if (lbl) lbl.textContent = "Cancelar"; drawBtn.classList.add("active"); }
  }
  updateDrawZoneBtn();
}

function toggle3D() {
  is3D = !is3D;
  map.setTilt(is3D ? 45 : 0);
  if (!is3D) map.setZoom(Math.max(map.getZoom() - 2, 10));
  const lbl = viewToggle.querySelector(".tool-label");
  if (lbl) lbl.textContent = is3D ? "3D" : "2D";
  viewToggle.classList.toggle("active", is3D);
}

function updateSimBadge() {
  if (!currentSimulationData) return;
  simBadge.classList.remove("hidden");
  simBadge.className = `sim-badge ${currentViewMode}`;
  simBadge.textContent = currentViewMode === "optimized"
    ? "▲ SIMULACIÓN PROPUESTA — HORIZONTE 2030"
    : "◼ ESTADO URBANO ACTUAL";
}

// ── Geometry Helpers ──────────────────────────────────────────

function srand(seed) {
  const x = Math.sin(seed * 9301 + 49297) * 233280;
  return x - Math.floor(x);
}
function rect(cx, cy, hw, hh) {
  return [[cx-hw,cy-hh],[cx+hw,cy-hh],[cx+hw,cy+hh],[cx-hw,cy+hh],[cx-hw,cy-hh]];
}
function rotatePoly(poly, cx, cy, deg) {
  const r = deg * Math.PI / 180;
  return poly.map(([x,y]) => {
    const dx = x-cx, dy = y-cy;
    return [cx + dx*Math.cos(r) - dy*Math.sin(r), cy + dx*Math.sin(r) + dy*Math.cos(r)];
  });
}
function organicPoly(cx, cy, r, pts = 18, seed = 0) {
  const c = [];
  for (let i = 0; i < pts; i++) {
    const a = (i/pts)*Math.PI*2;
    const v = 1 + 0.20*Math.sin(a*3+seed) + 0.10*Math.sin(a*7+seed*2);
    c.push([cx + Math.cos(a)*r*v, cy + Math.sin(a)*r*v*0.88]);
  }
  c.push(c[0]);
  return c;
}

// ── Building Cluster Generator — city-block top-down 2D ──────
//
// Generates a realistic city-block layout: a grid of rectangular
// building footprints separated by alleys, exactly as seen in a
// top-down 2D map (Google Maps "buildings" layer style).
// ─────────────────────────────────────────────────────────────

function generateBuildingCluster(lng, lat, vp, isFeasible, meta) {
  const { building_count = 4, area_m2: rawArea = 8000 } = vp || {};
  const count = Math.min(Math.max(building_count, 2), 16);
  const seed  = lng * 1000 + lat * 1000;
  const pieces = [];

  // Block dimensions derived from area_m2 (at lat 21°N: 1°lng≈104600m, 1°lat≈111320m)
  const sideM  = Math.sqrt(rawArea);
  const blockW = sideM / 104600;           // total width in degrees longitude
  const blockH = sideM * 0.80 / 111320;   // total height in degrees latitude (0.80 aspect)

  // Grid: decide columns/rows to fit 'count' buildings
  const cols = count <= 4 ? 2 : count <= 9 ? 3 : 4;
  const rows = Math.ceil(count / cols);

  const alley  = blockW * 0.035;   // alley ~3.5% of block width (realistic ~5–7 m)
  const bldgW  = (blockW - alley * (cols + 1)) / cols;
  const bldgH  = (blockH - alley * (rows + 1)) / rows;

  // Block ground shadow (dark perimeter so towers appear elevated)
  pieces.push({
    polygon: rect(lng + blockW * 0.025, lat - blockH * 0.025, blockW * 0.54, blockH * 0.54),
    color:   isFeasible ? [8, 28, 70, 80] : [60, 15, 15, 60],
    border:  isFeasible ? [60, 120, 200, 40] : [160, 60, 60, 60],
    _meta:   meta,
  });
  pieces.push({
    polygon: rect(lng, lat, blockW * 0.52, blockH * 0.52),
    color:   isFeasible ? [15, 55, 130, 50] : [80, 20, 20, 45],
    border:  isFeasible ? [100, 181, 246, 55] : [200, 80, 80, 80],
    _meta:   meta,
  });

  const midCol = Math.floor(cols / 2);  // central column index

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const idx = r * cols + c;
      if (idx >= count) break;

      const isCentral = (c === midCol);   // central column = main tower

      const bx = (lng - blockW/2) + alley*(c+1) + bldgW*c + bldgW/2;
      const by = (lat - blockH/2) + alley*(r+1) + bldgH*r + bldgH/2;

      // Central tower: larger + deeper blue (like the reference's main facade)
      // Wing buildings: normal size + lighter steel-blue
      const sv = srand(seed + idx * 3.14);
      const sc = srand(seed + idx * 7.77);
      const sizeBoost = isCentral ? 1.08 : 1.0;
      const hw = bldgW/2 * (0.82 + sv * 0.16) * sizeBoost;
      const hh = bldgH/2 * (0.80 + sc * 0.18) * sizeBoost;

      const t  = srand(seed + idx * 2.33);
      // Central: deep blue-grey (tower); Wings: lighter steel-blue
      const towerR = isCentral ? 20  : P.housing.tower[0];
      const towerG = isCentral ? 80  : P.housing.tower[1];
      const towerB = isCentral ? 160 : P.housing.tower[2];
      const midR   = isCentral ? 45  : P.housing.mid[0];
      const midG   = isCentral ? 105 : P.housing.mid[1];
      const midB   = isCentral ? 190 : P.housing.mid[2];
      const baseR  = Math.round(towerR + t * (midR - towerR));
      const baseG  = Math.round(towerG + t * (midG - towerG));
      const baseB  = Math.round(towerB + t * (midB - towerB));

      pieces.push({
        polygon: rect(bx, by, hw, hh),
        color:   isFeasible ? [baseR, baseG, baseB, isCentral ? 248 : 225] : [...P.blocked.fill],
        border:  isFeasible ? [...P.housing.border] : [...P.blocked.border],
        _meta:   meta,
      });

      // Facade window grid — thin horizontal lines across building face
      if (isFeasible && hw > 0.00005) {
        const winColor = [baseR + 40, baseG + 40, baseB + 20, 90];
        const steps = isCentral ? 4 : 2;
        for (let wi = 1; wi <= steps; wi++) {
          const wy = by - hh + (hh * 2) * (wi / (steps + 1));
          pieces.push({
            polygon: rect(bx, wy, hw * 0.86, hh * (isCentral ? 0.055 : 0.07)),
            color:   winColor,
            border:  [baseR + 60, baseG + 60, baseB + 40, 60],
            _meta:   meta,
          });
        }
      }

      // Rooftop shadow inset (depth cue)
      if (isFeasible && hw > 0.00004 && hh > 0.00003) {
        pieces.push({
          polygon: rect(bx, by, hw * 0.52, hh * 0.52),
          color:   [Math.max(0, baseR - 25), Math.max(0, baseG - 25), baseB + 8, 70],
          border:  [100, 160, 240, 25],
          _meta:   meta,
        });
      }
    }
  }
  return pieces;
}

// ── Green Space Generator — realistic 2D park top-down ────────
//
// Generates a park as seen from above:
//  • Rectangular grass lawn (main polygon)
//  • Central hardscape plaza (lighter colour, circular)
//  • Two diagonal path polygons crossing the park
//  • Perimeter tree row (ScatterplotLayer dots)
//  • Interior tree clusters in the four quadrants
// ─────────────────────────────────────────────────────────────

function generateGreenData(lng, lat, vp, isFeasible, meta) {
  const area   = (vp && vp.area_m2) ? vp.area_m2 : 6500;
  // Correct degree-to-metre conversion at lat 21°N: 1°lng≈104600m, 1°lat≈111320m
  // hw/hh represent the half-side of a square with the given area_m2
  const hw     = Math.sqrt(area) * 0.00000478;  // half-width  in degrees longitude
  const hh     = Math.sqrt(area) * 0.00000449;  // half-height in degrees latitude
  const seed   = lng*1000 + lat*500;

  const fillC   = isFeasible ? [...P.green_space.fill]   : [...P.blocked.fill];
  const borderC = isFeasible ? [...P.green_space.border] : [...P.blocked.border];

  const base = [];

  // 1. Main lawn rectangle
  base.push({ polygon: rect(lng, lat, hw, hh), color: fillC, border: borderC, _meta: meta });

  if (!isFeasible) return { base, trees: [] };

  // 2. Two crossing paths (thin light-grey rectangles)
  const pathW = Math.max(hw * 0.07, 0.000012);
  const pathColor  = [185, 195, 175, 170];
  const pathBorder = [160, 175, 155, 80];
  base.push({ polygon: rect(lng, lat, hw, pathW),  color: pathColor, border: pathBorder, _meta: meta }); // horizontal
  base.push({ polygon: rect(lng, lat, pathW, hh),  color: pathColor, border: pathBorder, _meta: meta }); // vertical

  // 3. Central pond / water body (blue organic shape — inspired by isometric park reference)
  const pondR = Math.min(hw, hh) * 0.28;
  base.push({ polygon: organicPoly(lng, lat, pondR, 14, seed),          color: [45, 110, 185, 200], border: [80, 155, 220, 180], _meta: meta }); // pond body
  base.push({ polygon: organicPoly(lng, lat, pondR * 0.45, 10, seed+2), color: [90, 165, 240, 140], border: [120, 190, 255,  80], _meta: meta }); // sheen

  // 4. Trees ─────────────────────────────────────────────────
  const trees = [];

  // Perimeter row — evenly spaced along the edge
  const perimStepLng = hw * 2 / Math.ceil(hw * 2 / 0.000120);
  const perimStepLat = hh * 2 / Math.ceil(hh * 2 / 0.000095);
  let pi = 0;
  for (let x = lng - hw + perimStepLng*0.5; x < lng + hw; x += perimStepLng) {
    for (const y of [lat - hh * 0.93, lat + hh * 0.93]) {
      const s = srand(seed + pi * 4.1);
      trees.push({ position: [x, y], radius: 5 + s*3, color: [18+s*20, 110+s*55, 28+s*15, 220], _meta: meta });
      pi++;
    }
  }
  for (let y = lat - hh + perimStepLat*0.5; y < lat + hh; y += perimStepLat) {
    for (const x of [lng - hw * 0.93, lng + hw * 0.93]) {
      const s = srand(seed + pi * 3.7);
      trees.push({ position: [x, y], radius: 5 + s*3, color: [18+s*20, 110+s*55, 28+s*15, 220], _meta: meta });
      pi++;
    }
  }

  // Quadrant clusters — 4 groups of trees between the paths
  const quadrants = [
    [lng - hw*0.55, lat - hh*0.55],
    [lng + hw*0.55, lat - hh*0.55],
    [lng - hw*0.55, lat + hh*0.55],
    [lng + hw*0.55, lat + hh*0.55],
  ];
  let qi = 0;
  for (const [qx, qy] of quadrants) {
    const clusterCount = 3 + Math.round(srand(seed + qi * 9.1) * 4);
    for (let i = 0; i < clusterCount; i++) {
      const a  = srand(seed + qi*11 + i*7.31) * Math.PI * 2;
      const r  = srand(seed + qi*13 + i*3.17) * Math.min(hw, hh) * 0.35;
      const s1 = srand(seed + qi*17 + i*1.43);
      const s2 = srand(seed + qi*19 + i*2.89);
      const tx = qx + Math.cos(a)*r;
      const ty = qy + Math.sin(a)*r;
      // Don't place trees on the path strip
      if (Math.abs(tx - lng) < pathW*1.4 || Math.abs(ty - lat) < pathW*1.4) continue;
      trees.push({ position: [tx, ty], radius: 4 + s1*5, color: [18+s2*28, 120+s1*65, 30+s2*18, 215], _meta: meta });
    }
    qi++;
  }

  return { base, trees };
}

// ── Road / Transport Generator — 2D boulevard corridor ────────
//
// Renders a road segment as seen from above:
//   • Wide carriageway (dark blue rectangle)
//   • Two sidewalk strips (lighter, on both long sides)
//   • Dashed centre-line (PathLayer)
//   • Crosswalk at one end (zebra stripes)
// ─────────────────────────────────────────────────────────────

function generateRoadPaths(lng, lat, vp, isFeasible, meta) {
  const road    = isFeasible ? [...P.transport.road]     : [...P.blocked.fill.slice(0,3), 220];
  const lane    = isFeasible ? [...P.transport.lane]     : [180,60,60,120];
  const sidewalk = isFeasible ? [...P.transport.sidewalk] : [160,60,60,100];

  // Scale road length to area_m2 (corridor area = length × road width ≈ 14 m)
  // half-length in degrees longitude: area / (14m × 2) / 104600 m/deg
  const area_m2 = (vp && vp.area_m2) ? vp.area_m2 : 5000;
  const len  = Math.max(0.00050, area_m2 / 2928800);  // half-length (min ~52 m half)
  const hw   = 0.000065;   // half-carriageway width (~7 m) — fixed realistic
  const swW  = 0.000030;   // sidewalk half-width (~3 m)

  const paths = [];
  const polys = [];

  // Carriageway polygon (PolygonLayer via renderLayers returns PathLayer for transport —
  // we return a mixed object; renderLayers only uses paths for transport so we piggyback)
  const path = (p, width, color) => ({ path: p, width, color, _meta: meta });

  // Main carriageway
  paths.push(path([[lng - len, lat], [lng + len, lat]], hw * 2 * 111320, road));

  // Dashed centre divider
  const dashLen = 0.000080;
  for (let x = lng - len + dashLen; x < lng + len - dashLen; x += dashLen * 2.5) {
    paths.push(path([[x, lat], [x + dashLen, lat]], 1.2, lane));
  }

  // Sidewalk lines
  paths.push(path([[lng - len, lat + hw + swW], [lng + len, lat + hw + swW]], swW * 2 * 111320, sidewalk));
  paths.push(path([[lng - len, lat - hw - swW], [lng + len, lat - hw - swW]], swW * 2 * 111320, sidewalk));

  // Crosswalk stripes at western end
  const cwX   = lng - len * 0.82;
  const cwW   = 0.000020;
  const cwH   = hw + swW;
  const stripes = 5;
  for (let s = 0; s < stripes; s++) {
    const x0 = cwX + s * cwW * 2.4;
    paths.push(path([[x0, lat - cwH], [x0, lat + cwH]], cwW * 111320,
      isFeasible ? [220, 230, 245, 200] : [200, 140, 140, 150]));
  }

  return paths;
}

// ── Flood / Retention Generator — 2D basin top-down ──────────
//
// Renders a water-retention feature as seen from above:
//   • Grass buffer zone (green, outermost rectangle)
//   • Earthwork embankment (earth tone ring)
//   • Open water body (blue, irregular organic shape)
// ─────────────────────────────────────────────────────────────

function generateFloodData(lng, lat, vp, isFeasible, meta) {
  const area = (vp && vp.area_m2) ? vp.area_m2 : 8500;
  const hw   = Math.sqrt(area) * 0.00000540;  // half-width  degrees lng (~1.13× square)
  const hh   = Math.sqrt(area) * 0.00000449;  // half-height degrees lat
  const seed = lng * 500 + lat * 800;

  if (!isFeasible) {
    return { polys: [{ polygon: rect(lng, lat, hw, hh), color: [...P.blocked.fill], border: [...P.blocked.border], _meta: meta }], dots: [] };
  }

  const polys = [
    // 1. Outer green buffer
    { polygon: rect(lng, lat, hw * 1.30, hh * 1.30),
      color: [75, 112, 62, 140], border: [95, 135, 78, 110], _meta: meta },
    // 2. Earthwork embankment ring
    { polygon: rect(lng, lat, hw * 1.05, hh * 1.05),
      color: [105, 82, 52, 200], border: [128, 104, 68, 160], _meta: meta },
    // 3. Water channel — horizontal strip across the basin
    { polygon: rect(lng, lat - hh * 0.08, hw * 0.90, hh * 0.28),
      color: [35, 85, 160, 230], border: [65, 125, 210, 200], _meta: meta },
    // 4. Water sheen
    { polygon: rect(lng, lat - hh * 0.08, hw * 0.60, hh * 0.14),
      color: [75, 145, 215, 140], border: [110, 175, 240, 80], _meta: meta },
    // 5. Solar panel array (NE quadrant — small dark rectangles)
    { polygon: rect(lng + hw * 0.48, lat + hh * 0.45, hw * 0.22, hh * 0.14),
      color: [22, 50, 90, 240], border: [50, 100, 180, 200], _meta: meta },
    { polygon: rect(lng + hw * 0.48, lat + hh * 0.65, hw * 0.22, hh * 0.14),
      color: [22, 50, 90, 240], border: [50, 100, 180, 200], _meta: meta },
    // 6. Wind turbine base circle (NW quadrant)
    { polygon: organicPoly(lng - hw * 0.58, lat + hh * 0.55, hw * 0.075, 8, seed + 9),
      color: [200, 210, 220, 220], border: [160, 175, 190, 180], _meta: meta },
  ];

  // Wind turbine blades — 3 ScatterplotLayer dots in a triangle around hub
  const hubLng = lng - hw * 0.58;
  const hubLat = lat + hh * 0.55;
  const bR     = hw * 0.10 * 104600;  // blade reach in metres
  const dots = [
    { position: [hubLng,           hubLat + hw * 0.10, 0], radius: bR * 0.18, color: [210, 220, 230, 220] },
    { position: [hubLng - hw * 0.09, hubLat - hh * 0.08, 0], radius: bR * 0.18, color: [210, 220, 230, 220] },
    { position: [hubLng + hw * 0.09, hubLat - hh * 0.08, 0], radius: bR * 0.18, color: [210, 220, 230, 220] },
  ];

  return { polys, dots };
}

// ── Infrastructure Generator — institutional tower top-down ──────
//
// Inspired by reference: white/light institutional building with blue
// windows, flat roof with equipment, prominent shadow base.
//
// Top-down representation:
//  • Light grey building body (main rectangle)
//  • Slightly offset dark shadow perimeter (depth illusion)
//  • Blue window grid strips (horizontal bands)
//  • Roof equipment (small dark rectangle, centered top)
// ─────────────────────────────────────────────────────────────

function generateInfraData(lng, lat, vp, isFeasible, meta) {
  const area = (vp && vp.area_m2) ? vp.area_m2 : 4000;
  const hw   = Math.sqrt(area) * 0.00000478;
  const hh   = Math.sqrt(area) * 0.00000449;

  if (!isFeasible) {
    return [{ polygon: rect(lng, lat, hw, hh), color: [...P.blocked.fill], border: [...P.blocked.border], _meta: meta }];
  }

  return [
    // Shadow base (slightly larger, dark offset)
    { polygon: rect(lng + hw * 0.06, lat - hh * 0.06, hw * 1.04, hh * 1.04),
      color: [10, 18, 30, 160], border: [20, 30, 45, 80], _meta: meta },
    // Building body — light grey-white institutional
    { polygon: rect(lng, lat, hw, hh),
      color: [195, 205, 215, 240], border: [140, 155, 175, 220], _meta: meta },
    // Horizontal window bands (3 rows — blue glass)
    { polygon: rect(lng, lat + hh * 0.42, hw * 0.82, hh * 0.10),
      color: [55, 120, 210, 180], border: [80, 155, 245, 120], _meta: meta },
    { polygon: rect(lng, lat,            hw * 0.82, hh * 0.10),
      color: [55, 120, 210, 160], border: [80, 155, 245, 100], _meta: meta },
    { polygon: rect(lng, lat - hh * 0.42, hw * 0.82, hh * 0.10),
      color: [55, 120, 210, 180], border: [80, 155, 245, 120], _meta: meta },
    // Roof equipment block (HVAC / mechanical — dark centered rectangle)
    { polygon: rect(lng, lat + hh * 0.25, hw * 0.28, hh * 0.12),
      color: [80, 90, 100, 220], border: [110, 120, 135, 180], _meta: meta },
    // Entrance canopy (bottom edge — slightly protruding light strip)
    { polygon: rect(lng, lat - hh * 0.96, hw * 0.35, hh * 0.06),
      color: [220, 228, 238, 200], border: [160, 175, 200, 160], _meta: meta },
  ];
}

// ── Tooltip Builder ───────────────────────────────────────────

const TYPE_LABELS = {
  housing: "Vivienda", green_space: "Espacio Verde",
  transport: "Movilidad", flood_management: "Gestión Hídrica",
  infrastructure: "Infraestructura",
};

function buildTooltip(meta) {
  const { action, type, cost_usd, feasible, notes, pdf_sources } = meta;
  const typeLabel = TYPE_LABELS[type] || type || "Intervención";
  const statusCss = feasible ? "color:#24a148" : "color:#da1e28";
  const statusTxt = feasible ? "✓ Aprobado" : "✖ Bloqueado";
  const pdfs = (pdf_sources || [])
    .map(p => KNOWN_PDFS_SHORT[p] || p.replace(".pdf",""))
    .filter(Boolean).join(" · ");
  const truncNotes = notes ? notes.slice(0, 160) + (notes.length > 160 ? "…" : "") : "";

  return {
    html: `
      <div class="tt-header">
        <span class="tt-type">${typeLabel.toUpperCase()}</span>
        <span style="${statusCss}; font-weight:700">${statusTxt}</span>
      </div>
      <div class="tt-title">${action || "Sin nombre"}</div>
      ${cost_usd ? `<div class="tt-cost">💰 Inversión: $${cost_usd.toLocaleString()}</div>` : ""}
      ${truncNotes ? `<div class="tt-notes">${truncNotes}</div>` : ""}
      ${pdfs ? `<div class="tt-pdfs">📄 ${pdfs}</div>` : ""}`,
    style: {
      background: "rgba(5,5,10,0.95)",
      backdropFilter: "blur(12px)",
      border: "1px solid rgba(255,255,255,0.12)",
      borderRadius: "4px",
      padding: "10px 14px",
      maxWidth: "280px",
      fontFamily: "system-ui, sans-serif",
      fontSize: "12px",
      color: "#f4f4f4",
      lineHeight: "1.5",
      pointerEvents: "none",
    },
  };
}

// ── Dynamic Legend Builder ────────────────────────────────────

const KNOWN_PDFS_SHORT = {
  "04_02_1.2_PMDU2017_Guiametodologica.pdf": "PMDU 2017",
  "3-FASCCULOINUNDACIONES-ilovepdf-compressed.pdf": "Guía Inundaciones",
  "EDO-4-123.pdf": "EDO-4-123",
  "Manual_de_calles_2019.pdf": "Manual de Calles 2019",
  "NOM-001-SEDATU-2021.pdf": "NOM-001-SEDATU-2021",
};

function buildDynamicLegend(actions, validated) {
  if (!actions || actions.length === 0) return;

  const presentTypes = new Set();
  actions.forEach(a => {
    const type = String(a.type || "").toLowerCase();
    const name = String(a.action || "").toLowerCase();

    // Classification Logic (Must match renderLayers priority)
    const isHousing = type.includes("housing")||type.includes("residen")||name.includes("vivienda")||name.includes("habitac")||name.includes("edific");
    const isTraffic = type.includes("transport")||type.includes("road")||name.includes("vial")||name.includes("mobility")||name.includes("calle")||name.includes("avenida")||name.includes("ciclov");
    const isFlood   = type.includes("flood")||type.includes("water")||type.includes("retention")||name.includes("inundac")||name.includes("drenaje")||name.includes("pluvial")||name.includes("vaso")||name.includes("buffer")||name.includes("amortig")||name.includes("baldío")||name.includes("vacante")||name.includes("reserva");
    const isGreen   = type.includes("green")||type.includes("park")||name.includes("parque")||name.includes("verde")||name.includes("jardín")||name.includes("árbol")||name.includes("veget")||name.includes("bosque");

    if (isHousing) presentTypes.add("housing");
    else if (isTraffic) presentTypes.add("transport");
    else if (isFlood) presentTypes.add("flood_management");
    else if (isGreen) presentTypes.add("green_space");
    else presentTypes.add("infrastructure");
  });

  const hasBlocked = validated.some(v => !v.feasible);
  if (hasBlocked) presentTypes.add("blocked");

  const typeOrder = ["housing","green_space","transport","flood_management","infrastructure","blocked"];
  const typeToP   = {
    housing: P.housing, green_space: P.green_space, transport: P.transport,
    flood_management: P.flood, infrastructure: P.infrastructure, blocked: P.blocked
  };

  const items = typeOrder
    .filter(t => presentTypes.has(t))
    .map(t => {
      const tp = typeToP[t];
      return `
        <div class="legend-item">
          <div class="legend-swatch" style="background:${tp.css}"></div>
          <div class="legend-text">
            <div class="legend-type">${tp.label}</div>
            <div class="legend-desc">${tp.desc}</div>
          </div>
        </div>`;
    }).join("");

  simLegend.innerHTML = `
    <div class="hud-title">Simbología de la Simulación</div>
    <div class="legend-note">Pasa el cursor sobre los elementos del mapa para más detalle</div>
    ${items}`;
}

// ── Pipeline Progress ─────────────────────────────────────────

function startPipelineProgress() {}
function advanceStep() {}
function finishPipelineProgress() { if (stepInterval) clearTimeout(stepInterval); }

// ── RENDER RESULTS ────────────────────────────────────────────

function animateValue(el, endStr, duration = 900) {
  if (!el) return;
  const num = parseFloat(String(endStr).replace(/[^0-9.]/g,"")) || 0;
  const t0  = performance.now();
  (function step(now) {
    const p = Math.min((now-t0)/duration, 1);
    const e = 1-Math.pow(1-p,3);
    const v = num*e;
    const s = String(endStr);
    if (s.includes("$") && s.includes("M"))  el.textContent = `$${v.toFixed(1)}M`;
    else if (s.includes(" T"))               el.textContent = `${Math.round(v).toLocaleString()} T`;
    else if (s.includes("%"))                el.textContent = `${Math.round(v)}%`;
    else if (s.includes("mes"))              el.textContent = `${Math.round(v)} meses`;
    else                                     el.textContent = Math.round(v).toLocaleString();
    if (p < 1) requestAnimationFrame(step);
  })(performance.now());
}

function renderAccessibility(routesData) {
  const container = document.getElementById("accessibility-panel");
  if (!container) return;

  const routes = (routesData.routes || []).filter(r => r.status === "OK");
  if (routes.length === 0) {
    container.innerHTML = '<div class="empty-state">Sin datos de accesibilidad.</div>';
    return;
  }

  const modeLabel = { DRIVE: "Auto", WALK: "A pie", TRANSIT: "Transporte", BICYCLE: "Bici" };
  const mode = modeLabel[routesData.mode] || routesData.mode;

  const rows = routes.map(r => {
    const bar = Math.min(100, Math.round((r.duration_min / 30) * 100));
    const color = r.duration_min <= 10 ? "#34a853" : r.duration_min <= 20 ? "#fdd663" : "#f28b82";
    return `
      <div class="access-row">
        <div class="access-dest">${r.destination}</div>
        <div class="access-bar-wrap">
          <div class="access-bar" style="width:${bar}%;background:${color}"></div>
        </div>
        <div class="access-meta">${r.duration_min} min · ${r.distance_km} km</div>
      </div>`;
  }).join("");

  container.innerHTML = `
    <div class="access-mode-label">MODO: ${mode}</div>
    <div class="access-list">${rows}</div>`;
}

function renderResults(data) {
  currentSimulationData = data;
  const actions   = data.proposed_actions  || [];
  const validated = data.validated_actions || [];
  const metrics   = data.impact_metrics    || {};

  document.getElementById("proposed-count").textContent = actions.length;
  proposedList.innerHTML = actions.length === 0
    ? '<div class="empty-state">No se generaron intervenciones.</div>'
    : actions.map(a => `
        <div class="action-card">
          <div class="action-type-badge">${(a.type||"INFRA").toUpperCase()}</div>
          <div class="action-title">${a.action||"Sin título"}</div>
          ${a.description ? `<div class="action-desc">${a.description}</div>` : ""}
          <div class="action-cost">Inversión estimada: $${(a.cost_usd||0).toLocaleString()}</div>
        </div>`).join("");

  const feasibleCount = validated.filter(v=>v.feasible).length;
  document.getElementById("feasible-count").textContent = `${feasibleCount}/${validated.length} aprobadas`;
  validatedList.innerHTML = validated.length === 0
    ? '<div class="empty-state">Sin resultados de validación.</div>'
    : validated.map(v => `
          <div class="action-card ${v.feasible ? "card-approved" : "card-blocked"}">
            <div class="card-status ${v.feasible ? "status-ok":"status-blocked"}">
              ${v.feasible ? "✓ APROBADO — FACTIBLE" : "✖ BLOQUEADO — NO FACTIBLE"}
            </div>
            <div class="action-title" style="font-size:0.82rem">${v.action||"Desconocido"}</div>
            ${v.rejection_reason ? `<div class="card-reason">⚠ ${v.rejection_reason}</div>` : ""}
            ${v.notes ? `<div class="card-notes">${v.notes}</div>` : ""}
          </div>`).join("");

  animateValue(metricOverall,    `${metrics.overall_score||0}%`);
  animateValue(metricResilience, `${metrics.flood_reduction_percent||0}%`);
  animateValue(metricCO2,        `${(metrics.co2_reduction_tons_per_year||0).toLocaleString()} T`);
  animateValue(metricCost,       `$${((metrics.estimated_total_cost_usd||0)/1_000_000).toFixed(1)}M`);
  animateValue(metricPopulation, `${(metrics.affected_population||0).toLocaleString()}`);
  animateValue(metricTimeline,   `${metrics.implementation_timeline_months||0} meses`);

  if (metrics.recommendation) recommendationBox.innerHTML = `<strong>Diagnóstico:</strong><p>${metrics.recommendation}</p>`;
  
  if (data.final_analysis) {
    const parts = data.final_analysis.replace(/\*/g,"").split(/(\[[\w_]+\])/g);
    let html = "";
    parts.forEach(p => {
      if (/^\[[\w_]+\]$/.test(p)) html += `<div class="report-section-header">${p.replace(/[\[\]]/g,"").replace(/_/g," ")}</div>`;
      else if (p.trim()) html += `<p class="report-paragraph">${p.trim()}</p>`;
    });
    analyzerReport.innerHTML = `<div class="report-label">INFORME HOLÍSTICO DE CIUDAD</div><div class="report-body">${html}</div>`;     
  }

  const geminiPanel = document.getElementById("gemini-panel");
  if (geminiPanel) {
    const gr = data.gemini_ranking;
    if (gr && gr.top && gr.top.length > 0) {
      const items = gr.top.map(e =>
        `<div style="margin:0.4rem 0"><strong>#${e.rank} ${e.label || e.id}</strong><br><span style="opacity:0.7;font-size:0.78rem">${e.rationale || ""}</span></div>`
      ).join("");
      geminiPanel.innerHTML = `<span class="rec-label">GEMINI · PRIORIDAD</span>${items}`;
      geminiPanel.style.display = "";
    } else {
      geminiPanel.style.display = "none";
    }
  }

  buildDynamicLegend(actions, validated);
  updateSimBadge();
  renderLayers(data);
  narrateResultsInChat(data);
}

// ── Chatbot narration — structured result cards ───────────────
function narrateResultsInChat(data) {
  const actions   = data.proposed_actions  || [];
  const validated = data.validated_actions || [];
  const metrics   = data.impact_metrics    || {};
  const feasible  = validated.filter(v => v.feasible);
  const blocked   = validated.filter(v => !v.feasible);
  const zoneInfo  = data.zone_constraints  || {};

  const TYPE_COLOR = {
    housing: '#4285f4', green_space: '#34a853',
    transport: '#8ab4f8', flood_management: '#9aa0a6', infrastructure: '#1e88e5',
  };
  const TYPE_LABEL = {
    housing: 'Vivienda', green_space: 'Espacio Verde',
    transport: 'Movilidad', flood_management: 'Gestión Hídrica', infrastructure: 'Infraestructura',
  };
  const LAND_LABEL = { extension: 'Extensión', infill: 'Infill', urban_renewal: 'Renovación' };

  // Zone header
  const zoneHa  = zoneInfo.area_m2 > 0 ? `${(zoneInfo.area_m2/10000).toFixed(1)} ha` : '';
  const landLbl = LAND_LABEL[zoneInfo.land_use_status] || '';
  const zoneLine = [zoneHa, landLbl].filter(Boolean).join(' · ');

  // Action rows
  const actionRows = validated.map(v => {
    const a     = actions.find(x => x.id === v.id) || {};
    const color = TYPE_COLOR[a.type]  || '#8ab4f8';
    const lbl   = TYPE_LABEL[a.type] || (a.type || 'Intervención');
    const cost  = a.cost_usd ? `$${(a.cost_usd/1e6).toFixed(1)}M` : '';
    const name  = v.action || a.action || 'Intervención';
    if (v.feasible) {
      return `<div class="cr-action cr-ok">
        <span class="cr-dot" style="background:${color}"></span>
        <div class="cr-action-body">
          <span class="cr-action-name">${name}</span>
          <span class="cr-action-meta">${lbl}${cost ? ' · ' + cost : ''}</span>
        </div>
        <span class="cr-badge cr-badge-ok">✓</span>
      </div>`;
    } else {
      const reason = v.rejection_reason ? v.rejection_reason.substring(0, 72) + '…' : 'No factible por normativa';
      return `<div class="cr-action cr-blocked">
        <span class="cr-dot" style="background:#f28b82"></span>
        <div class="cr-action-body">
          <span class="cr-action-name">${name}</span>
          <span class="cr-action-meta cr-blocked-txt">${reason}</span>
        </div>
        <span class="cr-badge cr-badge-blocked">✗</span>
      </div>`;
    }
  }).join('');

  // Metrics strip
  const metricItems = [
    metrics.overall_score          ? `<div class="cr-metric"><span>Puntuación</span><strong>${metrics.overall_score}%</strong></div>` : '',
    metrics.co2_reduction_tons_per_year ? `<div class="cr-metric"><span>CO₂</span><strong>−${(metrics.co2_reduction_tons_per_year).toLocaleString()} t/yr</strong></div>` : '',
    metrics.estimated_total_cost_usd    ? `<div class="cr-metric"><span>Inversión</span><strong>$${(metrics.estimated_total_cost_usd/1e6).toFixed(1)}M</strong></div>` : '',
    metrics.affected_population         ? `<div class="cr-metric"><span>Población</span><strong>${metrics.affected_population.toLocaleString()}</strong></div>` : '',
    metrics.implementation_timeline_months ? `<div class="cr-metric"><span>Plazo</span><strong>${metrics.implementation_timeline_months} meses</strong></div>` : '',
  ].filter(Boolean).join('');

  // First sentence of final analysis
  let analysisSentence = '';
  if (data.final_analysis) {
    const clean = data.final_analysis.replace(/\*/g, '').replace(/\[[\w_]+\]/g, '').trim();
    const first = clean.split(/\.\s+/)[0];
    if (first && first.length > 30) analysisSentence = first + '.';
  }

  // Viability verdict
  const total = validated.length;
  const feasRatio = total > 0 ? feasible.length / total : 0;
  let viabClass = 'cr-viab-viable', viabLabel = 'VIABLE', viabIcon = '✓';
  if (feasRatio < 0.4 || feasible.length === 0) {
    viabClass = 'cr-viab-no'; viabLabel = 'NO VIABLE'; viabIcon = '✗';
  } else if (feasRatio < 0.8 || blocked.length > 0) {
    viabClass = 'cr-viab-cond'; viabLabel = 'CONDICIONADO'; viabIcon = '⚠';
  }

  const html = `<div class="cr-card">
    <div class="cr-header">
      <span class="cr-title">Análisis completado</span>
      ${zoneLine ? `<span class="cr-zone">${zoneLine}</span>` : ''}
    </div>
    <div class="cr-viability ${viabClass}">
      <span class="cr-viab-icon">${viabIcon}</span>
      <span class="cr-viab-label">${viabLabel}</span>
      <span class="cr-viab-sub">${feasible.length} de ${total} intervenciones aprobadas</span>
    </div>
    <div class="cr-summary">${feasible.length} aprobadas &nbsp;·&nbsp; ${blocked.length} bloqueadas</div>
    <div class="cr-actions">${actionRows || '<span class="cr-empty">Sin intervenciones generadas</span>'}</div>
    ${metricItems ? `<div class="cr-metrics">${metricItems}</div>` : ''}
    ${metrics.recommendation ? `<div class="cr-rec">${metrics.recommendation}</div>` : ''}
    ${analysisSentence ? `<div class="cr-analysis">${analysisSentence}</div>` : ''}
    <div class="cr-hint">Explora los polígonos en el mapa →</div>
  </div>`;

  const msgs = document.getElementById("chat-messages");
  if (!msgs) return;
  const div = document.createElement("div");
  div.className = "chat-msg bot";
  div.innerHTML = html;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function renderLayers(data) {
  const actions   = data.proposed_actions  || [];
  const validated = data.validated_actions || [];
  const geoCurrent = data.geojson_current;
  const layers      = [];
  const bounds      = new google.maps.LatLngBounds();
  const baseOpacity = sliderBlend ? sliderBlend.value/100 : 1;

  // Gemini rank lookup — empty when gemini_ranking absent (backward compatible)
  const rankedIds = (data.gemini_ranking && data.gemini_ranking.ranked_ids) || [];
  const rankMap   = {};
  rankedIds.forEach((id, i) => { rankMap[id] = i === 0 ? 1.0 : 0.85; });

  if (currentViewMode === "current") {
    // Fetch live SIIMP vialidades layer from the backend API
    if (!window._cachedVialidades) {
      fetch(`${API_BASE}/geo/layer/vialidades`)
        .then(r => r.json())
        .then(geojson => {
          window._cachedVialidades = geojson;
          renderLayers(data); // re-render with cached data
        })
        .catch(err => console.error("Failed to fetch vialidades layer:", err));
      // Show a temporary message while loading
      deckOverlay.setProps({ layers: [] });
      return;
    }
    const vialidadesData = window._cachedVialidades;
    if (vialidadesData && vialidadesData.features && vialidadesData.features.length > 0) {
      layers.push(new deck.GeoJsonLayer({
        id: "geojson-vialidades",
        data: vialidadesData,
        getFillColor: [15, 98, 254, 50],
        getLineColor: [15, 98, 254, 200],
        getLineWidth: 2,
        lineWidthMinPixels: 1.5,
        pickable: true,
        opacity: baseOpacity,
      }));
      // Also overlay the user's drawn zone if present
      if (geoCurrent && geoCurrent.features && geoCurrent.features.length > 0) {
        layers.push(new deck.GeoJsonLayer({ id: "geojson-zone", data: geoCurrent, getFillColor: [255, 255, 255, 20], getLineColor: [255, 255, 255, 120], getLineWidth: 1, lineWidthMinPixels: 1, opacity: baseOpacity }));
      }
    }
  } else {
    // Zone boundary always visible in proposal mode (blue outline)
    if (geoCurrent && geoCurrent.features && geoCurrent.features.length > 0) {
      layers.push(new deck.GeoJsonLayer({
        id: "zone-boundary-proposal",
        data: geoCurrent,
        getFillColor: [66, 133, 244, 18],
        getLineColor: [66, 133, 244, 210],
        getLineWidth: 4,
        lineWidthMinPixels: 2,
        opacity: 1,
      }));
    }

    actions.forEach(a => {
      const v         = validated.find(x => x.id === a.id);
      const feasible  = v ? v.feasible : true;
      const vp        = a.visual_params || {};
      const type      = String(a.type||"").toLowerCase();
      const name      = String(a.action||"").toLowerCase();
      const meta = { id: a.id, action: a.action, type: a.type, cost_usd: a.cost_usd, feasible, notes: v ? v.notes : "", pdf_sources: v ? (v.pdf_sources||[]) : [] };

      // Per-action opacity: Gemini rank multiplier when ranking is present, else 1.0
      const rankMult = rankedIds.length === 0 ? 1.0 : (rankMap[a.id] !== undefined ? rankMap[a.id] : 0.40);
      const opacity  = baseOpacity * rankMult;

      const isGreen   = type.includes("green")||type.includes("park")||name.includes("parque")||name.includes("verde");
      const isHousing = type.includes("housing")||type.includes("residen")||name.includes("vivienda");
      const isTraffic = type.includes("transport")||type.includes("road")||name.includes("vial")||name.includes("mobility");
      const isFlood   = type.includes("flood")||type.includes("water")||name.includes("retention")||name.includes("inundac");

      const effectiveType = !feasible ? "blocked"
        : isGreen   ? "green_space"
        : isHousing ? "housing"
        : isTraffic ? "transport"
        : isFlood   ? "flood"
        : "infrastructure";

      if (_hiddenLayers.has(effectiveType)) {
        // skip — toggled off by user

      } else if (!feasible) {
        // ── Blocked: red semi-transparent rectangle ───────────────
        const bArea = (vp && vp.area_m2) ? vp.area_m2 : 5000;
        const bw = Math.sqrt(bArea) * 0.00000478;
        const bh = Math.sqrt(bArea) * 0.00000449;
        layers.push(new deck.PolygonLayer({
          id: `blocked-${a.id}`,
          data: [{ polygon: rect(a.longitude, a.latitude, bw, bh), color: [...P.blocked.fill], border: [...P.blocked.border], _meta: meta }],
          getPolygon: d => d.polygon, getFillColor: d => d.color, getLineColor: d => d.border,
          lineWidthMinPixels: 2, extruded: false, pickable: true, opacity,
        }));

      } else {
        // ── Feasible: reference image placed at intervention footprint ──
        const iArea = (vp && vp.area_m2) ? vp.area_m2 : 10000;
        // Scale to map-readable footprint — cap at ~100m half-width
        const hw = Math.min(Math.sqrt(iArea) * 0.00000480, 0.00095);  // degrees lng
        const hh = Math.min(Math.sqrt(iArea) * 0.00000452, 0.00090);  // degrees lat

        // For roads: elongated corridor proportions (wider + longer)
        const roadLen = Math.min(Math.max(0.00060, iArea / 2000000), 0.00115);
        const imgMinLng = isTraffic ? a.longitude - roadLen : a.longitude - hw;
        const imgMaxLng = isTraffic ? a.longitude + roadLen : a.longitude + hw;
        const imgMinLat = isTraffic ? a.latitude - hw * 0.55 : a.latitude - hh;
        const imgMaxLat = isTraffic ? a.latitude + hw * 0.55 : a.latitude + hh;

        layers.push(new deck.BitmapLayer({
          id: `ref-${a.id}`,
          bounds: [imgMinLng, imgMinLat, imgMaxLng, imgMaxLat],
          image: TYPE_IMG[effectiveType],
          opacity: opacity * 0.92,
          pickable: true,
          // Pass meta for tooltip — BitmapLayer uses onClick/onHover not getTooltip directly
        }));

        // Thin outline border so the footprint is visible on the map
        layers.push(new deck.PolygonLayer({
          id: `ref-border-${a.id}`,
          data: [{ polygon: rect(a.longitude, a.latitude, (imgMaxLng-imgMinLng)/2, (imgMaxLat-imgMinLat)/2), _meta: meta }],
          getPolygon: d => d.polygon,
          getFillColor: [0, 0, 0, 0],
          getLineColor: isGreen   ? [52,168,83,180]
                      : isHousing ? [66,133,244,180]
                      : isTraffic ? [138,180,248,180]
                      : isFlood   ? [154,160,166,180]
                      : [30,136,229,180],
          lineWidthMinPixels: 2,
          extruded: false,
          pickable: false,
          opacity,
        }));
      }
      if (!isNaN(a.longitude) && !isNaN(a.latitude)) bounds.extend({ lat: a.latitude, lng: a.longitude });
    });

    // Rank-1 gold indicator dot (only when Gemini ranking is present)
    if (rankedIds.length > 0) {
      const topAction = actions.find(a => a.id === rankedIds[0]);
      if (topAction && !isNaN(topAction.longitude) && !isNaN(topAction.latitude)) {
        layers.push(new deck.ScatterplotLayer({
          id: "gemini-rank1",
          data: [{ position: [topAction.longitude, topAction.latitude] }],
          getPosition: d => d.position,
          getRadius: 12,
          getFillColor: [255, 200, 0, 220],
          radiusUnits: "meters",
          pickable: false,
          opacity: 1,
        }));
      }
    }
  }
  _currentDeckLayers = layers;
  deckOverlay.setProps({ layers });
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, 90);
    google.maps.event.addListenerOnce(map, "idle", () => {
      if (map.getZoom() > 16) map.setZoom(16);
    });
  }
}

// Build a styled "concept map" image from the deck.gl canvas.
// Uses a dark dot-grid background so the result looks intentional, not like a broken screenshot.
function _buildConceptMap(targetAR) {
  const dc = deckOverlay?.deck?.canvas;
  const container = document.getElementById("map-container");
  const srcW = (dc && dc.width  > 100) ? dc.width  : (container ? container.offsetWidth  * 2 : 1200);
  const srcH = (dc && dc.height > 100) ? dc.height : (container ? container.offsetHeight * 2 : 800);

  // ── Styled background canvas ────────────────────────────────
  const bg = document.createElement("canvas");
  bg.width = srcW; bg.height = srcH;
  const ctx = bg.getContext("2d");

  // Base gradient
  const grad = ctx.createLinearGradient(0, 0, srcW, srcH);
  grad.addColorStop(0,   "#080c18");
  grad.addColorStop(0.5, "#0a0e1e");
  grad.addColorStop(1,   "#060a14");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, srcW, srcH);

  // Dot-grid (looks like a professional planning diagram)
  const gs = Math.max(18, Math.round(srcW / 70));
  ctx.fillStyle = "rgba(66,133,244,0.14)";
  for (let x = gs; x < srcW; x += gs) {
    for (let y = gs; y < srcH; y += gs) {
      ctx.beginPath(); ctx.arc(x, y, 1.1, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Subtle radial vignette (darker at edges)
  const vgn = ctx.createRadialGradient(srcW/2, srcH/2, srcH*0.25, srcW/2, srcH/2, srcH*0.85);
  vgn.addColorStop(0, "rgba(0,0,0,0)");
  vgn.addColorStop(1, "rgba(0,0,0,0.55)");
  ctx.fillStyle = vgn;
  ctx.fillRect(0, 0, srcW, srcH);

  // Deck.gl intervention overlay (always readable — preserveDrawingBuffer: true)
  if (dc) { try { ctx.drawImage(dc, 0, 0, srcW, srcH); } catch (_) {} }

  // ── Crop to target aspect ratio ─────────────────────────────
  const canvasAR = srcW / srcH;
  let cropW = srcW, cropH = srcH, cropX = 0, cropY = 0;
  if (canvasAR > targetAR) {
    cropW = Math.round(srcH * targetAR);
    cropX = Math.round((srcW - cropW) / 2);
  } else {
    cropH = Math.round(srcW / targetAR);
    cropY = Math.round((srcH - cropH) / 2);
  }
  const out = document.createElement("canvas");
  out.width = cropW; out.height = cropH;
  out.getContext("2d").drawImage(bg, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);

  const d = out.toDataURL("image/png");
  return (d && d.length > 1000) ? d : null;
}

async function exportResults() {
  if (!currentSimulationData) { alert("Ejecuta primero una simulación."); return; }
  if (exportBtn) exportBtn.disabled = true;
  const exportLabel = exportBtn?.querySelector("span[data-i18n]");
  const origText = exportLabel?.textContent || "Exportar PDF";
  if (exportLabel) exportLabel.textContent = "Generando…";

  const data      = currentSimulationData;
  const actions   = data.proposed_actions  || [];
  const validated = data.validated_actions || [];
  const metrics   = data.impact_metrics    || {};
  const feasible  = validated.filter(v => v.feasible);
  const blocked   = validated.filter(v => !v.feasible);

  try {
    const { jsPDF } = window.jspdf;

    // ── Shared constants ──────────────────────────────────────────
    const doc    = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    const PW     = doc.internal.pageSize.getWidth();   // 297 mm
    const PH     = doc.internal.pageSize.getHeight();  // 210 mm
    const now    = new Date();
    const dateStr = `${now.toLocaleDateString("es-MX")} · ${now.toLocaleTimeString("es-MX",{hour:"2-digit",minute:"2-digit"})}`;

    // Color palette
    const C = {
      bg:      [8,  10,  18],
      bg2:     [14, 18,  30],
      panel:   [18, 22,  38],
      card:    [22, 28,  46],
      blue:    [66, 133, 244],
      green:   [52, 168, 83],
      yellow:  [251,188, 4],
      red:     [242,139, 130],
      white:   [230,235, 255],
      sub:     [138,180, 248],
      muted:   [90, 110, 155],
      divider: [35, 44,  70],
    };

    // Viability values (computed once, reused on both pages)
    const total    = validated.length;
    const feasRatio = total > 0 ? feasible.length / total : 0;
    let viabLabel, vClr;
    if (feasRatio >= 0.8 && blocked.length === 0) { viabLabel = "VIABLE";        vClr = C.green; }
    else if (feasible.length > 0)                 { viabLabel = "CONDICIONADO";  vClr = C.yellow; }
    else                                           { viabLabel = "NO VIABLE";     vClr = C.red; }

    const TYPE_LBL = { housing:"Vivienda", green_space:"Verde", transport:"Movilidad", flood_management:"Hídrica", infrastructure:"Infraestructura" };
    const TYPE_CLR = { housing:C.blue, green_space:C.green, transport:[138,180,248], flood_management:[154,160,166], infrastructure:[30,136,229] };

    // Helper to draw a full-page dark background
    function pageBg() {
      doc.setFillColor(...C.bg);
      doc.rect(0, 0, PW, PH, "F");
    }

    // Helper to draw the page header bar
    function pageHeader(title, subtitle) {
      doc.setFillColor(...C.bg2);
      doc.rect(0, 0, PW, 13, "F");
      doc.setFillColor(...C.blue);
      doc.rect(0, 0, PW, 0.5, "F");           // top accent line
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10); doc.setTextColor(...C.white);
      doc.text("LINEAL", 7, 8.5);
      doc.setTextColor(...C.muted);
      doc.setFontSize(7); doc.setFont("helvetica", "normal");
      doc.text("// CORE  ·  " + title, 22, 8.5);
      if (subtitle) { doc.setFontSize(6); doc.setTextColor(...C.muted); doc.text(subtitle, 22, 12); }
      doc.setFontSize(6.5); doc.setTextColor(...C.muted);
      doc.text(dateStr, PW - 7, 8.5, { align: "right" });
      // Bottom divider
      doc.setFillColor(...C.divider);
      doc.rect(0, 13, PW, 0.4, "F");
    }

    // Helper to draw page footer
    function pageFooter(pageNum, total_pages) {
      doc.setFillColor(...C.bg2);
      doc.rect(0, PH - 7, PW, 7, "F");
      doc.setFillColor(...C.divider);
      doc.rect(0, PH - 7, PW, 0.4, "F");
      doc.setFont("helvetica", "normal");
      doc.setFontSize(5.5); doc.setTextColor(...C.muted);
      doc.text("LINEAL — Sistema Multi-Agente de Planeación Urbana  ·  Aguascalientes, México", 7, PH - 3);
      doc.text(`${pageNum} / ${total_pages}`, PW - 7, PH - 3, { align: "right" });
    }

    // ════════════════════════════════════════════════════════════════
    // PAGE 1 — Concept Map + Summary Panel
    // ════════════════════════════════════════════════════════════════
    const HDR  = 13.4;
    const FTR  = 7;
    const CONTENT_TOP = HDR + 4;
    const CONTENT_BOT = PH - FTR - 2;
    const CONTENT_H   = CONTENT_BOT - CONTENT_TOP;

    const MAP_W   = 172;   // concept map width (mm)
    const INFO_X  = MAP_W + 4;
    const INFO_W  = PW - INFO_X - 5;

    pageBg();

    // ── Concept map area ──────────────────────────────────────────
    const mapImg = _buildConceptMap(MAP_W / PH);
    if (mapImg) {
      doc.addImage(mapImg, "PNG", 0, 0, MAP_W, PH);
    } else {
      // Fallback: styled placeholder
      doc.setFillColor(...C.bg2);
      doc.rect(0, 0, MAP_W, PH, "F");
      doc.setFontSize(7); doc.setTextColor(...C.muted);
      doc.text("Concepto de mapa no disponible", MAP_W / 2, PH / 2, { align: "center" });
    }

    // Semi-transparent gradient overlay on left edge of info panel (transition)
    doc.setFillColor(...C.bg);
    doc.rect(MAP_W, 0, INFO_W + 5, PH, "F");
    doc.setFillColor(...C.divider);
    doc.rect(MAP_W, 0, 0.5, PH, "F");

    // Map label badge (bottom-left of map)
    doc.setFillColor(8, 10, 18, 0.78);
    doc.roundedRect(4, PH - FTR - 14, 68, 8, 2, 2, "F");
    doc.setFontSize(5); doc.setTextColor(...C.muted);
    doc.setFont("helvetica", "bold");
    doc.text("MAPA CONCEPTUAL DE INTERVENCIONES", 8, PH - FTR - 8.5);
    doc.setFont("helvetica", "normal");
    const zc = data.zone_constraints || {};
    const zoneHint = zc.area_m2 > 0
      ? `Zona: ${(zc.area_m2/10000).toFixed(1)} ha · ${{"extension":"Extensión","infill":"Infill","urban_renewal":"Renovación"}[zc.land_use_status]||"Zona urbana"}`
      : "Aguascalientes, México";
    doc.setTextColor(...C.sub); doc.setFontSize(5.5);
    doc.text(zoneHint, 8, PH - FTR - 4.5);

    // Type legend (bottom-right of map area)
    const legendTypes = [...new Set(actions.map(a => a.type))].slice(0, 5);
    legendTypes.forEach((t, li) => {
      const lx = 4 + li * 32;
      if (lx + 30 > MAP_W) return;
      const clr = TYPE_CLR[t] || C.muted;
      doc.setFillColor(...clr);
      doc.circle(lx + 2, PH - FTR - 19, 1.5, "F");
      doc.setFontSize(5); doc.setTextColor(...C.white);
      doc.setFont("helvetica", "normal");
      doc.text(TYPE_LBL[t] || t, lx + 5.5, PH - FTR - 18);
    });

    pageHeader("Análisis Urbano Multi-Agente", null);
    pageFooter(1, 2);

    // ── Info panel ────────────────────────────────────────────────
    let cy = CONTENT_TOP;

    // Project description (from brief)
    const briefDesc = data.prompt || "";
    if (briefDesc) {
      doc.setFont("helvetica", "italic");
      doc.setFontSize(6.5); doc.setTextColor(...C.muted);
      const dLines = doc.splitTextToSize(`"${briefDesc.slice(0,100)}"`, INFO_W);
      doc.text(dLines.slice(0,2), INFO_X, cy);
      cy += dLines.slice(0,2).length * 3.5 + 3;
    }

    // Viability verdict — large accent card
    doc.setFillColor(...vClr.map(v => Math.round(v * 0.18)));
    doc.roundedRect(INFO_X, cy, INFO_W, 18, 2.5, 2.5, "F");
    doc.setFillColor(...vClr);
    doc.roundedRect(INFO_X, cy, 3.5, 18, 1, 1, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13); doc.setTextColor(...vClr);
    doc.text(viabLabel, INFO_X + 8, cy + 9.5);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(6); doc.setTextColor(...C.muted);
    doc.text("VEREDICTO DE VIABILIDAD", INFO_X + 8, cy + 14.5);
    doc.setTextColor(...C.sub);
    doc.text(`${feasible.length}/${total} aprobadas`, INFO_X + INFO_W - 2, cy + 9.5, { align: "right" });
    cy += 22;

    // Metrics grid 2×3
    const metDefs = [
      { k: "Puntuación",   v: metrics.overall_score                  ? `${metrics.overall_score}%`                              : "—" },
      { k: "Inversión",    v: metrics.estimated_total_cost_usd       ? `$${(metrics.estimated_total_cost_usd/1e6).toFixed(1)}M` : "—" },
      { k: "CO₂ evitado",  v: metrics.co2_reduction_tons_per_year    ? `${(metrics.co2_reduction_tons_per_year/1000).toFixed(1)}k t/yr` : "—" },
      { k: "Población",    v: metrics.affected_population             ? `${(metrics.affected_population/1000).toFixed(1)}k hab`  : "—" },
      { k: "Plazo",        v: metrics.implementation_timeline_months  ? `${metrics.implementation_timeline_months} meses`        : "—" },
      { k: "Aprobadas",    v: `${feasible.length} / ${total}` },
    ];
    const MCW = (INFO_W - 2) / 2;
    const MCH = 12;
    metDefs.forEach((m, i) => {
      const mx = INFO_X + (i % 2) * (MCW + 2);
      const my = cy + Math.floor(i / 2) * (MCH + 1.5);
      doc.setFillColor(...C.card);
      doc.roundedRect(mx, my, MCW, MCH, 2, 2, "F");
      doc.setFont("helvetica", "normal");
      doc.setFontSize(5); doc.setTextColor(...C.muted);
      doc.text(m.k.toUpperCase(), mx + MCW/2, my + 4.5, { align: "center" });
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9); doc.setTextColor(...C.white);
      doc.text(m.v, mx + MCW/2, my + 10, { align: "center" });
    });
    cy += 3 * (MCH + 1.5) + 5;

    // Section label
    doc.setFont("helvetica", "bold");
    doc.setFontSize(6); doc.setTextColor(...C.sub);
    doc.text("INTERVENCIONES GENERADAS", INFO_X, cy); cy += 4;

    // Intervention rows
    validated.forEach(v => {
      if (cy > CONTENT_BOT - 2) return;
      const a    = actions.find(x => x.id === v.id) || {};
      const clr  = TYPE_CLR[a.type] || C.muted;
      const nm   = (v.action || a.action || "Intervención").slice(0, 30);
      const cost = a.cost_usd ? `$${(a.cost_usd/1e6).toFixed(1)}M` : "";
      const lbl  = TYPE_LBL[a.type] || "Otro";

      // Row bg
      doc.setFillColor(...(v.feasible ? [18,26,46] : [28,18,20]));
      doc.roundedRect(INFO_X, cy - 1.5, INFO_W, 7.5, 1.5, 1.5, "F");
      // Type dot
      doc.setFillColor(...clr);
      doc.circle(INFO_X + 2.5, cy + 2, 1.6, "F");
      // Name
      doc.setFont("helvetica", "bold");
      doc.setFontSize(6); doc.setTextColor(...C.white);
      doc.text(nm, INFO_X + 6.5, cy + 2.5);
      // Meta
      doc.setFont("helvetica", "normal");
      doc.setFontSize(5); doc.setTextColor(...C.muted);
      doc.text(`${lbl}${cost ? "  ·  " + cost : ""}`, INFO_X + 6.5, cy + 5.5);
      // Status
      doc.setFontSize(6.5); doc.setTextColor(...(v.feasible ? C.green : C.red));
      doc.text(v.feasible ? "✓" : "✗", INFO_X + INFO_W - 2, cy + 2.5, { align: "right" });
      cy += 9;
    });

    // ════════════════════════════════════════════════════════════════
    // PAGE 2 — Analysis Interpretation
    // ════════════════════════════════════════════════════════════════
    doc.addPage();
    pageBg();
    pageHeader("Interpretación del Análisis", "Informe generado por agentes de IA");
    pageFooter(2, 2);

    // Extract section text helper
    function extractSection(text, key) {
      const m = text.match(new RegExp(`\\[${key}\\]([\\s\\S]*?)(?=\\[[A-Z_]+\\]|$)`, "i"));
      return m ? m[1].replace(/\*/g, "").trim() : "";
    }

    const analysisText = data.final_analysis || "";
    let ay = CONTENT_TOP;

    // ── Verdict banner (full width) ───────────────────────────────
    const bannerH = 16;
    doc.setFillColor(...vClr.map(v => Math.round(v * 0.25)));
    doc.roundedRect(5, ay, PW - 10, bannerH, 3, 3, "F");
    doc.setFillColor(...vClr);
    doc.roundedRect(5, ay, 5, bannerH, 2, 2, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(14); doc.setTextColor(...vClr);
    doc.text(viabLabel, 18, ay + 10.5);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7); doc.setTextColor(...C.muted);
    doc.text(
      `${feasible.length} intervenciones aprobadas  ·  ${blocked.length} condicionadas  ·  Puntuación global: ${metrics.overall_score || "—"}%`,
      18, ay + 14
    );
    // Score bar
    const scoreVal = (metrics.overall_score || 0) / 100;
    const barX = PW - 80, barY = ay + 6, barW = 70, barH2 = 4;
    doc.setFillColor(...C.bg);
    doc.roundedRect(barX, barY, barW, barH2, 2, 2, "F");
    doc.setFillColor(...vClr);
    doc.roundedRect(barX, barY, Math.max(2, barW * scoreVal), barH2, 2, 2, "F");
    doc.setFontSize(5); doc.setTextColor(...C.muted);
    doc.text("SCORE", barX, barY - 1);
    doc.setTextColor(...C.white); doc.setFont("helvetica", "bold");
    doc.text(`${metrics.overall_score || 0}%`, barX + barW + 1, barY + 3.5);
    ay += bannerH + 6;

    // ── Analysis sections (3 columns) ────────────────────────────
    const analysisSections = [
      { key:"CITY_STATE_SYNERGY",              label:"Sinergia Urbana",         icon:"01", clr:C.blue   },
      { key:"CRITICAL_RISK_ASSESSMENT",        label:"Evaluación de Riesgos",   icon:"02", clr:C.yellow },
      { key:"LONG_TERM_SUSTAINABILITY_VECTOR", label:"Sustentabilidad",         icon:"03", clr:C.green  },
    ];
    const colW3  = (PW - 16) / 3;
    const secBoxH = 48;

    analysisSections.forEach((sec, si) => {
      const sx   = 5 + si * (colW3 + 3);
      const text = extractSection(analysisText, sec.key)
        || (si === 0 ? `La zona presenta condiciones ${viabLabel === "VIABLE" ? "favorables" : "condicionadas"} para el desarrollo propuesto en Aguascalientes. El análisis multi-agente confirma la viabilidad técnica del proyecto.` : "—");

      // Card bg
      doc.setFillColor(...C.card);
      doc.roundedRect(sx, ay, colW3, secBoxH, 2.5, 2.5, "F");

      // Top accent bar with section color
      doc.setFillColor(...sec.clr);
      doc.roundedRect(sx, ay, colW3, 3, 2.5, 2.5, "F");
      doc.rect(sx, ay + 1, colW3, 2, "F");

      // Number badge
      doc.setFillColor(...sec.clr.map(v => Math.round(v * 0.25)));
      doc.roundedRect(sx + 3, ay + 6, 7, 7, 1.5, 1.5, "F");
      doc.setFont("helvetica", "bold");
      doc.setFontSize(5.5); doc.setTextColor(...sec.clr);
      doc.text(sec.icon, sx + 3 + 3.5, ay + 11.5, { align: "center" });

      // Label
      doc.setFontSize(7); doc.setTextColor(...C.white);
      doc.text(sec.label.toUpperCase(), sx + 13, ay + 11.5);

      // Body text
      doc.setFont("helvetica", "normal");
      doc.setFontSize(6.5); doc.setTextColor(...[185, 200, 230]);
      const bodyLines = doc.splitTextToSize(text, colW3 - 7);
      doc.text(bodyLines.slice(0, 7), sx + 3, ay + 18.5);
    });
    ay += secBoxH + 6;

    // ── Intervention detail cards ─────────────────────────────────
    doc.setFont("helvetica", "bold");
    doc.setFontSize(6.5); doc.setTextColor(...C.sub);
    doc.text("DETALLE DE INTERVENCIONES", 5, ay); ay += 5;

    const CARD_COLS = 3;
    const CARD_W = (PW - 16) / CARD_COLS;
    const CARD_H = 22;
    const CARD_GAP = 3;

    validated.forEach((v, vi) => {
      const col   = vi % CARD_COLS;
      const row   = Math.floor(vi / CARD_COLS);
      const cx2   = 5 + col * (CARD_W + CARD_GAP);
      const cy2   = ay + row * (CARD_H + CARD_GAP);
      if (cy2 + CARD_H > CONTENT_BOT) return;

      const a    = actions.find(x => x.id === v.id) || {};
      const clr  = TYPE_CLR[a.type] || C.muted;
      const nm   = (v.action || a.action || "Intervención").slice(0, 28);
      const lbl  = TYPE_LBL[a.type] || "Otro";
      const cost = a.cost_usd ? `$${(a.cost_usd/1e6).toFixed(1)}M USD` : "";
      const note = (v.notes || a.description || "").slice(0, 90);

      // Card
      doc.setFillColor(...C.card);
      doc.roundedRect(cx2, cy2, CARD_W, CARD_H, 2, 2, "F");

      // Left accent stripe
      doc.setFillColor(...clr);
      doc.roundedRect(cx2, cy2, 3, CARD_H, 1, 1, "F");

      // Type dot + label
      doc.setFontSize(5); doc.setTextColor(...clr);
      doc.setFont("helvetica", "bold");
      doc.text(lbl.toUpperCase(), cx2 + 6, cy2 + 5);

      // Name
      doc.setFontSize(6.5); doc.setTextColor(...C.white);
      doc.text(nm, cx2 + 6, cy2 + 9.5);

      // Note text
      doc.setFont("helvetica", "normal");
      doc.setFontSize(5.2); doc.setTextColor(...C.muted);
      const noteLines = doc.splitTextToSize(note, CARD_W - 9);
      doc.text(noteLines.slice(0, 2), cx2 + 6, cy2 + 13.5);

      // Cost + status row
      doc.setFontSize(5.5); doc.setTextColor(...C.sub);
      if (cost) doc.text(cost, cx2 + 6, cy2 + CARD_H - 3.5);
      doc.setTextColor(...(v.feasible ? C.green : C.red));
      doc.setFont("helvetica", "bold");
      doc.text(v.feasible ? "✓ Aprobada" : "✗ Condicionada", cx2 + CARD_W - 3, cy2 + CARD_H - 3.5, { align: "right" });
    });

    doc.save("lineal-propuesta-urbana.pdf");

  } catch (err) {
    console.error("PDF export error:", err);
    alert("Error al generar el PDF: " + (err.message || err));
  } finally {
    if (exportBtn) exportBtn.disabled = false;
    if (exportLabel) exportLabel.textContent = origText;
  }
}

// ── Chatbot (Orchestrator Agent 0) ───────────────────────────
let _chatSessionId = null;
let _chatDone      = false;
let _chatBrief     = null;   // full orchestrator_brief from completed interview
let _chatTurn      = 0;      // tracks which interview question we're on

function openChatbot() {}   // no-op: panel is always visible
function closeChatbot() {}  // no-op

// Quick-answer chips shown after each bot question (speeds up demos)
const _QUICK_CHIPS = {
  0: ["Vivienda Residencial", "Vivienda Social", "Comercial / Retail", "Usos Mixtos", "Parque Urbano"],
  1: ["Terreno Vacío / Baldío", "Ya tiene edificios", "Parcialmente construido"],
  2: ["$1–5M USD", "$5–15M USD", "$15–50M USD", "$50M+ USD"],
  3: ["Corto plazo (1–3 años)", "Mediano plazo (5 años)", "Largo plazo (10+ años)"],
  4: ["✓ Sí, confirmar", "Quisiera ajustar algo"],
};

function showQuickChips(turnIndex) {
  const opts = _QUICK_CHIPS[turnIndex];
  if (!opts) return;
  const msgs = document.getElementById("chat-messages");
  if (!msgs) return;
  msgs.querySelectorAll(".chat-quick-chips").forEach(el => el.remove());

  const wrap = document.createElement("div");
  wrap.className = "chat-quick-chips";

  const lbl = document.createElement("div");
  lbl.className = "chat-chips-label";
  lbl.textContent = "Sugerencias";
  wrap.appendChild(lbl);

  opts.forEach(opt => {
    const btn = document.createElement("button");
    btn.className = "chat-chip";
    btn.textContent = opt;
    btn.addEventListener("click", () => {
      msgs.querySelectorAll(".chat-quick-chips").forEach(el => el.remove());
      const inp = document.getElementById("chat-input");
      if (inp) { inp.value = opt; }
      sendChatMessage();
    });
    wrap.appendChild(btn);
  });
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
}

function appendChatMsg(role, text) {
  const msgs = document.getElementById("chat-messages");
  if (!msgs) return null;

  const htmlText = text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");

  if (role === "system") {
    const div = document.createElement("div");
    div.className = "chat-msg system";
    div.innerHTML = htmlText;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  const row = document.createElement("div");
  row.className = role === "bot" ? "chat-row bot-row" : "chat-row user-row";

  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.innerHTML = `<span class="material-symbols-outlined">smart_toy</span>`;
    row.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = `chat-msg ${role}`;
  bubble.innerHTML = htmlText;
  row.appendChild(bubble);

  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
  return bubble;
}

function showTyping() {
  const msgs = document.getElementById("chat-messages");
  if (!msgs) return null;
  const row = document.createElement("div");
  row.className = "chat-typing-row";
  row.id = "chat-typing-indicator";

  const avatar = document.createElement("div");
  avatar.className = "chat-avatar";
  avatar.innerHTML = `<span class="material-symbols-outlined">smart_toy</span>`;

  const bubble = document.createElement("div");
  bubble.className = "chat-typing";
  bubble.innerHTML = `<span class="chat-typing-label">Lineal</span><span></span><span></span><span></span>`;

  row.appendChild(avatar);
  row.appendChild(bubble);
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
  return row;
}

function hideTyping() {
  const el = document.getElementById("chat-typing-indicator");
  if (el) el.remove();
}

async function startChatSession() {
  _chatDone = false;
  _chatTurn = 0;
  const msgs = document.getElementById("chat-messages");
  if (msgs) msgs.innerHTML = "";
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  if (input) { input.disabled = true; input.value = ""; }
  if (sendBtn) sendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/orchestrator/start`, { method: "POST" });
    const data = await res.json();
    _chatSessionId = data.session_id;
    const msgs2 = document.getElementById("chat-messages");
    if (msgs2) msgs2.innerHTML = "";
    appendChatMsg("bot", data.reply);
    const firstMsg = document.getElementById("chat-messages")?.lastElementChild;
    if (firstMsg) firstMsg.id = "chat-opening-msg";
    showQuickChips(0);  // show project-type chips on opening

    const badge = document.getElementById("chat-mode-badge");
    if (badge) {
      fetch(`${API_BASE}/`).then(r => r.json()).then(d => {
        if (badge) {
          badge.textContent = d.mode === "watsonx" ? "AI" : "DEMO";
          badge.className = `status-badge ${d.mode === "watsonx" ? "badge-active" : "badge-stable"}`;
        }
      }).catch(() => {});
    }
  } catch (e) {
    appendChatMsg("system", "Error al conectar con el backend.");
  } finally {
    if (input) input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.focus();
  }
}

async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  if (!input || !_chatSessionId || _chatDone) return;

  const msg = input.value.trim();
  if (!msg) return;

  appendChatMsg("user", msg);
  input.value = "";
  input.disabled = true;
  if (sendBtn) sendBtn.disabled = true;

  showTyping();
  try {
    const t0 = Date.now();
    const res = await fetch(`${API_BASE}/orchestrator/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: _chatSessionId, message: msg }),
    });
    const data = await res.json();
    // Minimum 600ms typing feel so the bot doesn't feel instant/robotic
    const elapsed = Date.now() - t0;
    if (elapsed < 600) await new Promise(r => setTimeout(r, 600 - elapsed));
    hideTyping();
    appendChatMsg("bot", data.reply);
    _chatTurn++;

    if (data.done && data.brief) {
      _chatDone  = true;
      _chatBrief = data.brief;
      const desc = data.brief.project_description || "";
      appendChatMsg("system", T[currentLang].brief_ready);
      setTimeout(() => {
        closeChatbot();
        if (promptEl) promptEl.value = desc;
        generatePlan();
      }, 1200);
    } else {
      // Show relevant quick-chips for this turn
      showQuickChips(_chatTurn);
    }
  } catch (e) {
    hideTyping();
    appendChatMsg("system", T[currentLang].chat_error);
  } finally {
    if (!_chatDone) {
      if (input) { input.disabled = false; input.focus(); }
      if (sendBtn) sendBtn.disabled = false;
    }
  }
}

// Wire up chatbot (called after DOMContentLoaded)
// ── Language toggle ───────────────────────────────────────────
function applyLang(lang) {
  currentLang = lang;
  const t = T[lang];

  // 1. Sweep all data-i18n text nodes
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (t[key] !== undefined) el.textContent = t[key];
  });

  // 2. Sweep all data-i18n-placeholder inputs
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (t[key] !== undefined) el.placeholder = t[key];
  });

  // 3. Lang button label
  const langBtn = document.getElementById("lang-btn");
  if (langBtn) langBtn.textContent = t.lang_btn;

  // 4. Layer toggle tooltips
  document.querySelectorAll(".lt-btn[data-layer]").forEach(btn => {
    btn.title = t.layers[btn.dataset.layer] || btn.title;
  });
  document.querySelectorAll(".lt-btn[data-siimp]").forEach(btn => {
    btn.title = t.siimp[btn.dataset.siimp] || btn.title;
  });

  // 5. Opening chat message (dynamically injected, not in DOM at parse time)
  const openingEl = document.getElementById("chat-opening-msg");
  if (openingEl) {
    openingEl.innerHTML = t.opening_msg.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
  }

  // 6. Draw-zone button label (in chat panel)
  const dzBtn = document.getElementById("draw-zone-btn");
  if (dzBtn) {
    const lbl = dzBtn.querySelector(".dz-label");
    if (lbl) lbl.textContent = drawnPolygon ? t.zone_active : t.draw_zone;
    dzBtn.title = t.draw_zone_hint;
  }

  // 7. html lang attribute
  document.documentElement.lang = lang;

  renderLegend();
}

// ── Map legend — 2D icons ─────────────────────────────────────
const LEGEND_ICONS = {
  // Simulation layers — 2D top-down representations
  housing: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="1" y="3" width="9" height="12" fill="#4285f4" opacity="0.85" rx="1"/>
    <rect x="12" y="6" width="9" height="9" fill="#4285f4" opacity="0.65" rx="1"/>
    <line x1="3" y1="6.5" x2="8" y2="6.5" stroke="#fff" stroke-width="0.8" opacity="0.5"/>
    <line x1="3" y1="9"   x2="8" y2="9"   stroke="#fff" stroke-width="0.8" opacity="0.5"/>
    <line x1="3" y1="11.5" x2="8" y2="11.5" stroke="#fff" stroke-width="0.8" opacity="0.5"/>
    <line x1="14" y1="9" x2="19" y2="9" stroke="#fff" stroke-width="0.8" opacity="0.4"/>
    <line x1="14" y1="11.5" x2="19" y2="11.5" stroke="#fff" stroke-width="0.8" opacity="0.4"/>
  </svg>`,
  green_space: `<svg width="22" height="16" viewBox="0 0 22 16">
    <circle cx="6"  cy="9"  r="5"   fill="#34a853" opacity="0.85"/>
    <circle cx="15" cy="7"  r="4.5" fill="#34a853" opacity="0.7"/>
    <circle cx="14" cy="13" r="3"   fill="#34a853" opacity="0.6"/>
    <circle cx="6"  cy="9"  r="2.5" fill="#81c995" opacity="0.4"/>
    <circle cx="15" cy="7"  r="2"   fill="#81c995" opacity="0.35"/>
  </svg>`,
  transport: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="1" y="5" width="20" height="6" fill="#2a4a8a" rx="1"/>
    <line x1="1" y1="8" x2="21" y2="8" stroke="#8ab4f8" stroke-width="0.8" stroke-dasharray="3,2" opacity="0.7"/>
    <line x1="1" y1="6" x2="21" y2="6" stroke="#8ab4f8" stroke-width="0.6" opacity="0.4"/>
    <line x1="1" y1="10" x2="21" y2="10" stroke="#8ab4f8" stroke-width="0.6" opacity="0.4"/>
    <rect x="4"  y="5" width="3" height="6" fill="#4285f4" opacity="0.3"/>
    <rect x="10" y="5" width="3" height="6" fill="#4285f4" opacity="0.3"/>
    <rect x="16" y="5" width="3" height="6" fill="#4285f4" opacity="0.3"/>
  </svg>`,
  flood: `<svg width="22" height="16" viewBox="0 0 22 16">
    <ellipse cx="11" cy="11" rx="9" ry="4.5" fill="#9aa0a6" opacity="0.4" stroke="#bdc1c6" stroke-width="1"/>
    <path d="M3,9 Q6,5 11,9 Q16,13 19,9" fill="none" stroke="#9aa0a6" stroke-width="1.5" opacity="0.8"/>
    <path d="M5,11 Q8,8 11,11 Q14,14 17,11" fill="none" stroke="#bdc1c6" stroke-width="1" opacity="0.6"/>
    <circle cx="11" cy="4" r="1.5" fill="#8ab4f8" opacity="0.7"/>
    <path d="M11,2 L13,5.5 Q11,7 9,5.5 Z" fill="#8ab4f8" opacity="0.6"/>
  </svg>`,
  infrastructure: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="2" y="6" width="18" height="9" fill="#1e88e5" opacity="0.7" rx="1"/>
    <rect x="8" y="2" width="6" height="5" fill="#1e88e5" opacity="0.85" rx="1"/>
    <line x1="2" y1="10" x2="20" y2="10" stroke="#fff" stroke-width="0.7" opacity="0.35"/>
    <line x1="7" y1="6"  x2="7"  y2="15" stroke="#fff" stroke-width="0.7" opacity="0.25"/>
    <line x1="15" y1="6" x2="15" y2="15" stroke="#fff" stroke-width="0.7" opacity="0.25"/>
    <rect x="9" y="3" width="4" height="1" fill="#64b5f6" opacity="0.5"/>
  </svg>`,
  blocked: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="2" y="2" width="18" height="12" fill="#f28b82" opacity="0.2" rx="2" stroke="#f28b82" stroke-width="1.2"/>
    <line x1="5"  y1="4" x2="17" y2="12" stroke="#f28b82" stroke-width="2.2" stroke-linecap="round"/>
    <line x1="17" y1="4" x2="5"  y2="12" stroke="#f28b82" stroke-width="2.2" stroke-linecap="round"/>
  </svg>`,

  // SIIMP / ArcGIS overlay layers
  vialidades: `<svg width="22" height="16" viewBox="0 0 22 16">
    <line x1="1" y1="8" x2="21" y2="8" stroke="#4a4e56" stroke-width="4" stroke-linecap="round"/>
    <line x1="1" y1="8" x2="21" y2="8" stroke="#6e7280" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="5" y1="8" x2="8" y2="8"   stroke="#fff" stroke-width="0.8" opacity="0.4" stroke-dasharray="1.5,2"/>
    <line x1="12" y1="8" x2="16" y2="8" stroke="#fff" stroke-width="0.8" opacity="0.4" stroke-dasharray="1.5,2"/>
  </svg>`,
  contencion_urbana: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="2" y="2" width="18" height="12" fill="#3c4046" opacity="0.25" stroke="#5a606a" stroke-width="1.5" stroke-dasharray="3,2" rx="2"/>
    <line x1="2" y1="8" x2="20" y2="8" stroke="#5a606a" stroke-width="0.6" opacity="0.35"/>
  </svg>`,
  zufos: `<svg width="22" height="16" viewBox="0 0 22 16">
    <polygon points="11,2 20,14 2,14" fill="#2d2920" opacity="0.7" stroke="#6b5a30" stroke-width="1.4"/>
    <line x1="11" y1="6" x2="11" y2="12" stroke="#8b7a40" stroke-width="0.8" opacity="0.5"/>
    <line x1="8"  y1="10" x2="14" y2="10" stroke="#8b7a40" stroke-width="0.8" opacity="0.5"/>
  </svg>`,
  zonas_dinamica_especial: `<svg width="22" height="16" viewBox="0 0 22 16">
    <rect x="2" y="2" width="18" height="12" fill="#182522" opacity="0.8" stroke="#2e6048" stroke-width="1.4" rx="2"/>
    <line x1="6"  y1="8" x2="16" y2="8" stroke="#34a853" stroke-width="1.4"/>
    <line x1="11" y1="4" x2="11" y2="12" stroke="#34a853" stroke-width="1.4"/>
    <circle cx="11" cy="8" r="2" fill="#34a853" opacity="0.4"/>
  </svg>`,
  materiales_petreos: `<svg width="22" height="16" viewBox="0 0 22 16">
    <polygon points="11,2 19,7 16,14 6,14 3,7" fill="#362c22" opacity="0.85" stroke="#6b4428" stroke-width="1.4"/>
    <line x1="7" y1="10" x2="15" y2="10" stroke="#9b6438" stroke-width="0.8" opacity="0.5"/>
    <line x1="9" y1="7"  x2="13" y2="7"  stroke="#9b6438" stroke-width="0.8" opacity="0.5"/>
  </svg>`,
};

function renderLegend() {
  const body = document.getElementById("legend-body");
  if (!body) return;
  const t = T[currentLang];

  const SIM_KEYS  = ["housing","green_space","transport","flood","infrastructure","blocked"];
  const SIIMP_KEYS = ["vialidades","contencion_urbana","zufos","zonas_dinamica_especial","materiales_petreos"];

  let html = `<div class="legend-group-label">${t.sim_group}</div>`;
  for (const k of SIM_KEYS) {
    html += `<div class="legend-row"><span class="legend-icon">${LEGEND_ICONS[k]}</span>${t.layers[k]}</div>`;
  }
  html += `<div class="legend-sep-line"></div><div class="legend-group-label">${t.assets_group}</div>`;
  for (const k of SIIMP_KEYS) {
    const loaded = !!siimpDataLayers[k];
    html += `<div class="legend-row" style="opacity:${loaded ? 1 : 0.4}"><span class="legend-icon">${LEGEND_ICONS[k]}</span>${t.siimp[k]}</div>`;
  }
  body.innerHTML = html;
}

// ── Layer toggle buttons ──────────────────────────────────────
function initLayerToggles() {
  // Simulation layer toggles
  document.querySelectorAll(".lt-btn[data-layer]").forEach(btn => {
    btn.addEventListener("click", () => {
      const layer = btn.dataset.layer;
      if (_hiddenLayers.has(layer)) {
        _hiddenLayers.delete(layer);
        btn.classList.replace("off", "active");
      } else {
        _hiddenLayers.add(layer);
        btn.classList.replace("active", "off");
      }
      if (currentSimulationData) renderLayers(currentSimulationData);
    });
  });

  // SIIMP layer toggles (activated per-layer once loaded)
  document.querySelectorAll(".lt-btn[data-siimp]").forEach(btn => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.siimp;
      if (btn.classList.contains("active")) {
        toggleSiimpLayer(name, false);
        btn.classList.replace("active", "off");
      } else {
        toggleSiimpLayer(name, true);
        btn.classList.replace("off", "active");
      }
    });
  });

  // Legend collapse toggle
  const legendHdr = document.getElementById("legend-hdr");
  if (legendHdr) {
    legendHdr.addEventListener("click", () => {
      const body = document.getElementById("legend-body");
      const collapsed = body.classList.toggle("hidden");
      legendHdr.classList.toggle("collapsed", collapsed);
    });
  }

  // Language button
  const langBtn = document.getElementById("lang-btn");
  if (langBtn) langBtn.addEventListener("click", () => applyLang(currentLang === "es" ? "en" : "es"));

  renderLegend();
}

function initChatbot() {
  const input   = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");

  if (sendBtn) sendBtn.addEventListener("click", sendChatMessage);
  if (input) {
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
    });
  }

  // Draw-zone button — activates map drawing mode from chat panel
  const drawZoneBtn = document.getElementById("draw-zone-btn");
  if (drawZoneBtn) {
    drawZoneBtn.addEventListener("click", () => {
      if (drawnPolygon) {
        // Clear existing polygon
        drawnPolygon.setMap(null);
        drawnPolygon = null;
        updateDrawZoneBtn();
      } else {
        // Start drawing (map must be loaded)
        if (!map) return;
        toggleDrawMode();
        updateDrawZoneBtn();
      }
    });
  }

  // Auto-start session immediately
  startChatSession();
}

async function generatePlan() {
  const prompt = promptEl.value.trim();
  if (!prompt || prompt.length < 10) {
    alert("Por favor describe tu objetivo con más detalle (mínimo 10 caracteres).");
    return;
  }

  let zone = null;
  if (drawnPolygon) {
    const path = drawnPolygon.getPath();
    const coords = [];
    for (let i = 0; i < path.getLength(); i++) {
      const pt = path.getAt(i);
      coords.push([pt.lng(), pt.lat()]);
    }
    coords.push(coords[0]);
    zone = { type: "Polygon", coordinates: [coords] };
  }
  if (!zone) {
    const b  = map.getBounds();
    const ne = b.getNorthEast();
    const sw = b.getSouthWest();
    zone = { type:"Polygon", coordinates:[[[sw.lng(),sw.lat()],[ne.lng(),sw.lat()],[ne.lng(),ne.lat()],[sw.lng(),ne.lat()],[sw.lng(),sw.lat()]]] };
  }

  const _c = map.getCenter();
  const center = { lat: _c.lat(), lng: _c.lng() };
  spinner.classList.add("visible");
  btnText.textContent = "⌛ Procesando...";
  generateBtn.disabled = true;
  startPipelineProgress();

  try {
    const res = await fetch(`${API_BASE}/generate-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        center: { lat: center.lat, lng: center.lng },
        zone,
        brief: _chatBrief || null,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    finishPipelineProgress();
    renderResults(data);
  } catch (err) {
    finishPipelineProgress();
    console.error("Pipeline error:", err);
    if (recommendationBox) {
      recommendationBox.innerHTML = `<span class="rec-label" style="color:#f28b82">ERROR</span><p>${err.message || "Error en el pipeline. Verifica el backend."}</p>`;
    }
    const geminiPanel = document.getElementById("gemini-panel");
    if (geminiPanel) geminiPanel.style.display = "none";
  } finally {
    spinner.classList.remove("visible");
    btnText.textContent = "EJECUTAR_RUN";
    generateBtn.disabled = false;
  }
}
