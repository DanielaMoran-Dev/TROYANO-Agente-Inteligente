// ============================================================
// Lineal — Smart City Planner  |  app.js v3.0
// IBM watsonx.ai + LangGraph Multi-Agent Urban Planning
// ============================================================

const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : "";

// ── State ────────────────────────────────────────────────────
let map, deckOverlay, drawingManager, drawnPolygon;
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
  exportReportBtn  = document.getElementById("export-report-btn");
  pdfCountDisplay  = document.getElementById("pdf-count-display");
  pdfBadge         = document.getElementById("pdf-badge");
  sessionCity      = document.getElementById("session-city");
  systemEstado     = document.getElementById("system-estado");
  sidebarEl        = document.getElementById("sidebar");
  sidebarToggleBtn = document.getElementById("sidebar-toggle-btn");

  // Sliders
  sliderBlend.addEventListener("input", e => { updateBlend(e.target.value / 100); });

  // Scenario chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach(c => c.classList.remove("selected"));
      chip.classList.add("selected");
      promptEl.value = chip.dataset.prompt;
      promptEl.focus();
    });
  });

  // Vista toggle
  viewToggleMode.addEventListener("click", () => {
    currentViewMode = currentViewMode === "optimized" ? "current" : "optimized";
    const label = currentViewMode === "optimized" ? "Propuesta" : "Actual";
    const lbl = viewToggleMode.querySelector(".tool-label");
    if (lbl) lbl.textContent = label;
    viewToggleMode.classList.toggle("active", currentViewMode === "current");
    updateSimBadge();
    if (currentSimulationData) renderLayers(currentSimulationData);
  });

  // Main actions
  generateBtn.addEventListener("click", generatePlan);
  drawBtn.addEventListener("click", toggleDrawMode);
  viewToggle.addEventListener("click", toggle3D);
  searchBtn.addEventListener("click", searchLocation);
  searchInput.addEventListener("keyup", e => { if (e.key === "Enter") searchLocation(); });
  exportBtn.addEventListener("click", exportResults);

  // PDF Import
  importPdfBtn.addEventListener("click", () => pdfFileInput.click());
  pdfFileInput.addEventListener("change", () => handlePdfUpload(pdfFileInput.files));

  // Sidebar toggle
  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener("click", () => {
      const collapsed = sidebarEl.classList.toggle("collapsed");
      sidebarToggleBtn.classList.toggle("active", !collapsed);
    });
  }

  initMap();
  checkApiHealth();
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
    setApiStatus(data.mode === "watsonx" ? "WATSONX ACTIVO" : "MODO DEMO",
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
  // Fetch API key from backend
  let key = "";
  try {
    const r = await fetch(`${API_BASE}/maps/key`);
    key = (await r.json()).key || "";
  } catch (e) { console.warn("maps/key failed:", e); }

  if (!key) { console.error("No Google Maps API key available."); return; }

  await loadGoogleMapsScript(key);

  map = new google.maps.Map(document.getElementById("map-container"), {
    center: { lat: 21.88, lng: -102.29 },
    zoom: 15,
    tilt: 45,
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

  // ── Mover controles flotantes al sistema de controles de Google Maps ──
  // Esto garantiza que siempre queden por encima del canvas del mapa.
  const searchHud  = document.querySelector(".search-hud");
  const mapTools   = document.querySelector(".map-tools");
  const simBadgeEl = document.getElementById("sim-badge");

  if (searchHud)  map.controls[google.maps.ControlPosition.TOP_LEFT].push(searchHud);
  if (mapTools)   map.controls[google.maps.ControlPosition.TOP_RIGHT].push(mapTools);
  if (simBadgeEl) map.controls[google.maps.ControlPosition.TOP_CENTER].push(simBadgeEl);

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
      fillColor: "#ffffff", fillOpacity: 0.15,
      strokeColor: "#ffffff", strokeWeight: 2, editable: false,
    },
  });
  drawingManager.setMap(map);

  google.maps.event.addListener(drawingManager, "polygoncomplete", (polygon) => {
    if (drawnPolygon) drawnPolygon.setMap(null);
    drawnPolygon = polygon;
    drawingManager.setDrawingMode(null);
    drawBtn.classList.remove("active");
    const lbl = drawBtn.querySelector(".tool-label");
    if (lbl) lbl.textContent = "Dibujar";
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
      dataLayer.setMap(map);
      siimpDataLayers[name] = dataLayer;

      // Actualizar checkbox en sidebar
      const cb = document.getElementById(`toggle-siimp-${name}`);
      if (cb) { cb.disabled = false; cb.checked = true; }

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

function toggleDrawMode() {
  if (drawingManager.getDrawingMode() !== null) {
    drawingManager.setDrawingMode(null);
    const lbl = drawBtn.querySelector(".tool-label");
    if (lbl) lbl.textContent = "Dibujar";
    drawBtn.classList.remove("active");
  } else {
    if (drawnPolygon) { drawnPolygon.setMap(null); drawnPolygon = null; }
    drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
    const lbl = drawBtn.querySelector(".tool-label");
    if (lbl) lbl.textContent = "Cancelar";
    drawBtn.classList.add("active");
  }
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

// ── Building Cluster Generator ────────────────────────────────   

function generateBuildingCluster(lng, lat, vp, isFeasible, meta) {
  const { building_count = 4, height_floors = 10 } = vp || {};
  const count  = Math.min(Math.max(building_count, 1), 12);
  const fH     = 3.4;
  const base   = height_floors * fH;
  const seed   = lng * 1000 + lat * 1000;
  const col    = isFeasible ? P.housing : P.blocked;
  const pieces = [];

  const addPiece = (polygon, height, color, border) =>
    pieces.push({ polygon, height, color, border, _meta: meta });

  // Central tower
  addPiece(rect(lng, lat, 0.00020, 0.00025), base * (1.5 + srand(seed)*0.35),
    isFeasible ? [...P.housing.tower] : [...P.blocked.fill],
    isFeasible ? [...P.housing.border] : [...P.blocked.border]);

  // Podium
  addPiece(rect(lng, lat, 0.00046, 0.00040), base * 0.20,
    isFeasible ? [...P.housing.podium] : [...P.blocked.fill, 120],
    isFeasible ? [...P.housing.border.slice(0,3), 100] : [...P.blocked.border.slice(0,3), 80]);

  if (count <= 2) return pieces;

  const positions = [
    [lng+0.00068, lat+0.00008], [lng-0.00070, lat-0.00012],
    [lng+0.00018, lat+0.00066], [lng-0.00022, lat-0.00068],
    [lng+0.00066, lat-0.00052], [lng-0.00064, lat+0.00050],
    [lng+0.00000, lat-0.00078], [lng-0.00072, lat+0.00018],
  ];
  const extra = Math.min(count - 2, positions.length);
  for (let i = 0; i < extra; i++) {
    const [bx, by] = positions[i];
    const r1 = srand(seed + i*7.31), r2 = srand(seed + i*3.14), r3 = srand(seed + i*1.77);
    const poly = rotatePoly(rect(bx, by, 0.00014+r1*0.00017, 0.00012+r2*0.00015), bx, by, r1*28-14);
    addPiece(poly, base*(0.35+r3*0.55),
      isFeasible ? [P.housing.mid[0]-15+r1*30, P.housing.mid[1]-10+r2*20, P.housing.mid[2], 215] : [...P.blocked.fill],
      isFeasible ? [...P.housing.border] : [...P.blocked.border]);
  }
  return pieces;
}

// ── Green Space Generator ─────────────────────────────────────

function generateGreenData(lng, lat, vp, isFeasible, meta) {
  const area   = (vp && vp.area_m2) ? vp.area_m2 : 6500;
  const radius = Math.sqrt(area) * 0.0000098;
  const seed   = lng*1000 + lat*500;
  const fillC  = isFeasible ? [...P.green_space.fill] : [...P.blocked.fill];
  const borderC = isFeasible ? [...P.green_space.border] : [...P.blocked.border];

  const polygon = organicPoly(lng, lat, radius, 22, seed);

  const treeCount = Math.min(Math.floor(area/160), 65);
  const trees = [];
  for (let i = 0; i < treeCount; i++) {
    const a  = srand(i*7.31+seed)*Math.PI*2;
    const r  = srand(i*3.17+seed)*radius*0.80;
    const s1 = srand(i*1.43+seed), s2 = srand(i*2.89+seed);
    trees.push({
      position: [lng + Math.cos(a)*r, lat + Math.sin(a)*r*0.88],
      radius:   isFeasible ? 4+s1*5.5 : 3,
      color:    isFeasible
        ? [25+s2*30, 135+s1*80, 38+s2*18, 215]
        : [200, 60, 60, 150],
      _meta: meta,
    });
  }
  return {
    base: [{ polygon, color: fillC, border: borderC, _meta: meta }],
    trees,
  };
}

// ── Road / Transport Generator ────────────────────────────────   

function generateRoadPaths(lng, lat, isFeasible, meta) {
  const roadC     = isFeasible ? [...P.transport.road]     : [...P.blocked.fill.slice(0,3), 220];
  const laneC     = isFeasible ? [...P.transport.lane]     : [180,60,60,120];
  const sidewalkC = isFeasible ? [...P.transport.sidewalk] : [160,60,60,100];
  const len = 0.0024;

  const path = (p, width, color, type) => ({ path: p, width, color, type, _meta: meta });
  return [
    path([[lng-len, lat],     [lng+len, lat]],          18, roadC,     "road"),
    path([[lng, lat-len*0.7], [lng, lat+len*0.7]],       14, roadC,     "road"),
    path([[lng-len*0.9, lat+0.000058],[lng+len*0.9, lat+0.000058]], 2.5, laneC, "lane"),
    path([[lng-len*0.9, lat-0.000058],[lng+len*0.9, lat-0.000058]], 2.5, laneC, "lane"),
    path([[lng-len, lat+0.000148],[lng+len, lat+0.000148]], 4.5, sidewalkC, "sidewalk"),
    path([[lng-len, lat-0.000148],[lng+len, lat-0.000148]], 4.5, sidewalkC, "sidewalk"),
  ];
}

// ── Flood / Retention Generator ───────────────────────────────     

function generateFloodData(lng, lat, vp, isFeasible, meta) {
  const area   = (vp && vp.area_m2) ? vp.area_m2 : 8500;
  const radius = Math.sqrt(area)*0.0000115;
  const seed   = lng*500 + lat*800;

  if (!isFeasible) {
    const poly = organicPoly(lng, lat, radius, 16, seed);
    return [{ polygon: poly, height: 1, color: [...P.blocked.fill], border: [...P.blocked.border], _meta: meta }];
  }

  const outer = organicPoly(lng, lat, radius,      18, seed);
  const inner = organicPoly(lng, lat, radius*0.48, 14, seed+3.5);
  return [
    { polygon: outer, height: 1.2, color: [...P.flood.outer], border: [...P.flood.border.slice(0,3), 70],  _meta: meta },
    { polygon: inner, height: 3.0, color: [...P.flood.inner], border: [...P.flood.border], _meta: meta },
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
      fontFamily: "'IBM Plex Sans', sans-serif",
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

function startPipelineProgress() {
  currentStep = 0;
  for (let i=1;i<=4;i++){const s=document.getElementById(`step-${i}`);if(s)s.classList.remove("active","done");}
  advanceStep();
}
function advanceStep() {
  if (currentStep >= 4) return;
  currentStep++;
  if (currentStep > 1) { const p=document.getElementById(`step-${currentStep-1}`); if(p){p.classList.remove("active");p.classList.add("done");} }
  const cur=document.getElementById(`step-${currentStep}`); if(cur) cur.classList.add("active");
  if (currentStep < 4) stepInterval = setTimeout(advanceStep, STEP_DURATIONS[currentStep-1]);
}
function finishPipelineProgress() {
  if (stepInterval) clearTimeout(stepInterval);
  for (let i=1;i<=4;i++){const s=document.getElementById(`step-${i}`);if(s){s.classList.remove("active");s.classList.add("done");}}     
}

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

  buildDynamicLegend(actions, validated);
  updateSimBadge();
  renderLayers(data);
}

function renderLayers(data) {
  const actions   = data.proposed_actions  || [];
  const validated = data.validated_actions || [];
  const geoCurrent = data.geojson_current;
  const layers    = [];
  const bounds    = new google.maps.LatLngBounds();
  const opacity   = sliderBlend ? sliderBlend.value/100 : 1;

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
        opacity,
      }));
      // Also overlay the user's drawn zone if present
      if (geoCurrent && geoCurrent.features && geoCurrent.features.length > 0) {
        layers.push(new deck.GeoJsonLayer({ id: "geojson-zone", data: geoCurrent, getFillColor: [255, 255, 255, 20], getLineColor: [255, 255, 255, 120], getLineWidth: 1, lineWidthMinPixels: 1, opacity }));
      }
    }
  } else {
    actions.forEach(a => {
      const v         = validated.find(x => x.id === a.id);
      const feasible  = v ? v.feasible : true;
      const vp        = a.visual_params || {};
      const type      = String(a.type||"").toLowerCase();
      const name      = String(a.action||"").toLowerCase();
      const meta = { id: a.id, action: a.action, type: a.type, cost_usd: a.cost_usd, feasible, notes: v ? v.notes : "", pdf_sources: v ? (v.pdf_sources||[]) : [] };

      const isGreen   = type.includes("green")||type.includes("park")||name.includes("parque")||name.includes("verde");
      const isHousing = type.includes("housing")||type.includes("residen")||name.includes("vivienda");
      const isTraffic = type.includes("transport")||type.includes("road")||name.includes("vial")||name.includes("mobility");
      const isFlood   = type.includes("flood")||type.includes("water")||name.includes("retention")||name.includes("inundac");

      if (isGreen) {
        const { base, trees } = generateGreenData(a.longitude, a.latitude, vp, feasible, meta);
        layers.push(new deck.PolygonLayer({ id: `green-${a.id}`, data: base, getPolygon: d=>d.polygon, getFillColor: d=>d.color, getLineColor: d=>d.border, lineWidthMinPixels: 1.5, extruded: false, pickable: true, opacity }));
        if (feasible && trees.length > 0) {
          layers.push(new deck.ScatterplotLayer({ id: `trees-${a.id}`, data: trees, getPosition: d=>[...d.position, 0], getRadius: d=>d.radius, getFillColor: d=>d.color, radiusUnits: "meters", pickable: true, opacity: opacity*0.95 }));
        }
      } else if (isHousing) {
        const pieces = generateBuildingCluster(a.longitude, a.latitude, vp, feasible, meta);
        layers.push(new deck.PolygonLayer({ id: `housing-${a.id}`, data: pieces, getPolygon: d=>d.polygon, getFillColor: d=>d.color, getLineColor: d=>d.border, lineWidthMinPixels: 1, getElevation: d=>d.height, extruded: true, material: { ambient: 0.30, diffuse: 0.80, shininess: 64 }, pickable: true, opacity }));
      } else if (isTraffic) {
        const paths = generateRoadPaths(a.longitude, a.latitude, feasible, meta);
        layers.push(new deck.PathLayer({ id: `road-${a.id}`, data: paths, getPath: d=>d.path, getColor: d=>d.color, getWidth: d=>d.width, widthUnits: "meters", capRounded: true, jointRounded: true, pickable: true, opacity }));
      } else if (isFlood) {
        const basins = generateFloodData(a.longitude, a.latitude, vp, feasible, meta);
        layers.push(new deck.PolygonLayer({ id: `flood-${a.id}`, data: basins, getPolygon: d=>d.polygon, getFillColor: d=>d.color, getLineColor: d=>d.border, lineWidthMinPixels: 1.5, getElevation: d=>d.height, extruded: true, material: { ambient: 0.45, diffuse: 0.85 }, pickable: true, opacity }));
      } else {
        const col = feasible ? P.infrastructure : P.blocked;
        const ht  = (vp.height_floors||5)*3.4;
        const hw  = 0.00030, hh = 0.00024;
        const infData = [{ polygon: rect(a.longitude, a.latitude, hw, hh), height: ht, color:[...col.main||col.fill], border:[...col.border], _meta: meta }];
        layers.push(new deck.PolygonLayer({ id: `infra-${a.id}`, data: infData, getPolygon: d=>d.polygon, getFillColor: d=>d.color, getLineColor: d=>d.border, getElevation: d=>d.height, extruded: true, pickable: true, opacity }));
      }
      if (!isNaN(a.longitude) && !isNaN(a.latitude)) bounds.extend({ lat: a.latitude, lng: a.longitude });
    });
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

function exportResults() {
  if (!currentSimulationData) { alert("Ejecuta primero una simulación."); return; }
  window.print();
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
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    finishPipelineProgress();
    renderResults(data);
  } catch (err) {
    finishPipelineProgress();
    console.error("Pipeline error:", err);
  } finally {
    spinner.classList.remove("visible");
    btnText.textContent = "EJECUTAR_RUN";
    generateBtn.disabled = false;
  }
}
