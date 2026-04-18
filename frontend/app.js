/**
 * MedConnect — Frontend
 * Handles: symptom chat, consult pipeline, map with clinic markers, doctor chat (WebSocket).
 */

const API = "";  // same-origin; empty string = relative URLs

// If a doctor session exists, redirect to the doctor dashboard.
if (sessionStorage.getItem("medconnect_doctor")) {
  window.location.href = "doctor.html";
}

// ── State ──────────────────────────────────────────────────────────────────────
let sessionId = crypto.randomUUID();
let userCoords = null;   // { lat, lng }
let map = null;
let clinicMarkers = [];
let activeWs = null;     // WebSocket for doctor chat
let budgetLevel = "$$";

// Conversation state — the backend chat agent owns the dialogue;
// frontend just relays messages and triggers /consult when agent says ready.
let collectedData = {};   // last data snapshot from chat agent
let consulting = false;

// ── DOM refs ───────────────────────────────────────────────────────────────────
const chatMessages     = document.getElementById("chat-messages");
const chatInput        = document.getElementById("chat-input");
const chatSendBtn      = document.getElementById("chat-send-btn");
const mapSearchInput   = document.getElementById("map-search-input");
const mapSearchBtn     = document.getElementById("map-search-btn");
const spinner          = document.getElementById("spinner");
const apiStatus        = document.getElementById("api-status");
const recPanel         = document.getElementById("recommendations-panel");
const recCards         = document.getElementById("rec-cards");
const recCloseBtn      = document.getElementById("rec-close-btn");
const mapLoading       = document.getElementById("map-loading");
const chatModal        = document.getElementById("chat-modal");
const modalMessages    = document.getElementById("modal-messages");
const modalInput       = document.getElementById("modal-input");
const modalSendBtn     = document.getElementById("modal-send-btn");
const modalCloseBtn    = document.getElementById("modal-close-btn");
const modalDoctorName  = document.getElementById("modal-doctor-name");

// ── Init ───────────────────────────────────────────────────────────────────────

async function init() {
  setupBudgetButtons();
  setupChatInput();
  setupMapSearch();
  setupRecPanel();
  setupModal();
  await initMap();
  await checkApiStatus();
  autoDetectLocation();   // fire-and-forget; bot adapts based on coords presence
  await bootstrapChat();
}

async function bootstrapChat() {
  // Ask the backend chat agent for its opening line.
  await sendToChatAgent("");
}

// ── Budget selector ────────────────────────────────────────────────────────────

function setupBudgetButtons() {
  document.querySelectorAll(".budget-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".budget-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      budgetLevel = btn.dataset.val;
    });
  });
}

// ── Chat ───────────────────────────────────────────────────────────────────────

function setupChatInput() {
  chatSendBtn.addEventListener("click", handleUserMessage);
  chatInput.addEventListener("keydown", e => { if (e.key === "Enter") handleUserMessage(); });
}

async function handleUserMessage() {
  const text = chatInput.value.trim();
  if (!text || consulting) return;
  chatInput.value = "";
  addUserMessage(text);
  await sendToChatAgent(text);
}

async function sendToChatAgent(message) {
  showSpinner();
  try {
    const resp = await fetch(`${API}/chat/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        has_coords: !!userCoords,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const turn = await resp.json();

    if (turn.reply) addBotMessage(turn.reply);
    collectedData = { ...collectedData, ...(turn.data || {}) };

    if (turn.ready) {
      await triggerConsult(turn.emergency);
    }
  } catch (e) {
    addBotMessage(`No pude procesar tu mensaje: ${e.message}`);
    console.error(e);
  } finally {
    hideSpinner();
  }
}

async function triggerConsult(emergency) {
  if (consulting) return;
  consulting = true;
  try {
    // If coords are missing, geocode the location_text the agent collected.
    if (!userCoords && collectedData.location_text) {
      try {
        const geo = await fetch(`${API}/maps/search?q=${encodeURIComponent(collectedData.location_text)}`);
        if (geo.ok) {
          const data = await geo.json();
          userCoords = { lat: data.lat, lng: data.lng };
          if (map) map.setCenter(userCoords);
        }
      } catch (e) {
        console.warn("Geocoding failed:", e);
      }
    }

    if (!userCoords) {
      addBotMessage("No pude determinar tu ubicación. Usa la barra de búsqueda del mapa para fijarla y reintentaré.");
      consulting = false;
      return;
    }

    const symptomsBlob = [
      collectedData.symptoms,
      collectedData.duration ? `Duración: ${collectedData.duration}` : "",
      collectedData.severity ? `Severidad: ${collectedData.severity}` : "",
      collectedData.age ? `Edad: ${collectedData.age}` : "",
      emergency ? "EMERGENCIA reportada por el paciente." : "",
    ].filter(Boolean).join(". ");

    await runConsult(symptomsBlob);
  } finally {
    consulting = false;
  }
}

function addBotMessage(text) {
  const div = document.createElement("div");
  div.className = "chat-msg bot";
  div.innerHTML = `<span class="material-symbols-outlined msg-icon">smart_toy</span><div class="msg-bubble">${escapeHtml(text)}</div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "chat-msg user";
  div.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Consult pipeline ───────────────────────────────────────────────────────────

async function runConsult(symptoms) {
  if (!symptoms || symptoms.length < 5) {
    addBotMessage("No tengo suficiente información para hacer una consulta.");
    return;
  }
  if (!userCoords) {
    addBotMessage("Necesito tu ubicación antes de buscar clínicas.");
    return;
  }

  const insurance = document.getElementById("insurance-select").value;

  showSpinner();
  addBotMessage("Analizando tus síntomas con IA...");

  try {
    const resp = await fetch(`${API}/consult`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        symptoms,
        coords: userCoords,
        insurance,
        budget_level: budgetLevel,
      }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    handleConsultResponse(data);
  } catch (e) {
    addBotMessage(`Error al procesar tu consulta: ${e.message}. Intenta de nuevo.`);
    console.error(e);
  } finally {
    hideSpinner();
  }
}

function handleConsultResponse(data) {
  const { triage, recommendations } = data;

  const urgencyEmoji = { critical: "🚨", medium: "⚠️", low: "✅" }[triage.urgency_level] || "ℹ️";
  addBotMessage(
    `${urgencyEmoji} ${triage.clinical_summary}\n\nEspecialidad requerida: ${triage.specialty}`
  );

  if (recommendations.urgent_message) {
    addBotMessage(`🚨 ${recommendations.urgent_message}`);
  }

  if (!recommendations.recommendations?.length) {
    addBotMessage("No encontramos clínicas disponibles con tus criterios. Prueba cambiando el presupuesto o seguro.");
    return;
  }

  addBotMessage("Encontré estas opciones para ti. Puedes ver las clínicas en el mapa.");
  showRecommendations(recommendations.recommendations);
  plotClinicsOnMap(recommendations.recommendations);
}

// ── Recommendations panel ──────────────────────────────────────────────────────

function setupRecPanel() {
  recCloseBtn.addEventListener("click", () => recPanel.classList.add("hidden"));
}

function showRecommendations(recs) {
  recCards.innerHTML = "";
  recs.forEach((rec, i) => {
    const card = document.createElement("div");
    card.className = "rec-card";

    const networkBadge = rec.is_network
      ? `<span class="badge badge-network">En red</span>`
      : `<span class="badge badge-external">Externo</span>`;

    const travelTime = rec.travel_time_min
      ? `<span class="rec-travel"><span class="material-symbols-outlined">directions_car</span>${rec.travel_time_min} min</span>`
      : "";

    const actionBtn = rec.is_network
      ? `<button class="rec-action-btn btn-chat" data-conv="${sessionId}-${rec.clinic_id}" data-doctor="${rec.contact?.doctor_id || ""}">
           <span class="material-symbols-outlined">chat</span> Chatear
         </button>`
      : `<button class="rec-action-btn btn-info" data-phone="${rec.contact?.phone || ""}" data-address="${rec.contact?.address || ""}">
           <span class="material-symbols-outlined">info</span> Contacto
         </button>`;

    card.innerHTML = `
      <div class="rec-card-header">
        <span class="rec-priority">${i + 1}</span>
        ${networkBadge}
        ${travelTime}
      </div>
      <div class="rec-justification">${escapeHtml(rec.justification)}</div>
      <div class="rec-card-footer">
        ${actionBtn}
        ${rec.coords ? `<button class="rec-action-btn btn-map" data-lat="${rec.coords.lat}" data-lng="${rec.coords.lng}">
          <span class="material-symbols-outlined">map</span> Ver en mapa
        </button>` : ""}
      </div>
    `;

    recCards.appendChild(card);
  });

  recCards.querySelectorAll(".btn-chat").forEach(btn => {
    btn.addEventListener("click", () => openDoctorChat(btn.dataset.conv, btn.dataset.doctor));
  });
  recCards.querySelectorAll(".btn-map").forEach(btn => {
    btn.addEventListener("click", () => {
      if (map) map.setCenter({ lat: +btn.dataset.lat, lng: +btn.dataset.lng });
    });
  });
  recCards.querySelectorAll(".btn-info").forEach(btn => {
    btn.addEventListener("click", () => {
      alert(`Teléfono: ${btn.dataset.phone || "N/D"}\nDirección: ${btn.dataset.address || "N/D"}`);
    });
  });

  recPanel.classList.remove("hidden");
}

// ── Google Maps ────────────────────────────────────────────────────────────────

async function initMap() {
  try {
    const keyResp = await fetch(`${API}/maps/key`);
    if (!keyResp.ok) throw new Error("No API key");
    const { key } = await keyResp.json();
    await loadGoogleMaps(key);
    mapLoading.style.display = "none";
  } catch (e) {
    console.warn("Google Maps not available:", e.message);
    mapLoading.innerHTML = `<span class="material-symbols-outlined">map</span><span>Mapa no disponible</span>`;
  }
}

function loadGoogleMaps(apiKey) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`;
    script.onload = () => {
      map = new google.maps.Map(document.getElementById("map-container"), {
        center: { lat: 19.43, lng: -99.13 },
        zoom: 12,
        mapTypeId: "roadmap",
      });
      resolve();
    };
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function plotClinicsOnMap(recs) {
  clinicMarkers.forEach(m => m.setMap(null));
  clinicMarkers = [];

  recs.forEach((rec, i) => {
    if (!rec.coords || !map) return;
    const marker = new google.maps.Marker({
      position: { lat: rec.coords.lat, lng: rec.coords.lng },
      map,
      label: String(i + 1),
      title: rec.justification,
    });
    clinicMarkers.push(marker);
  });

  if (clinicMarkers.length) {
    const bounds = new google.maps.LatLngBounds();
    clinicMarkers.forEach(m => bounds.extend(m.getPosition()));
    if (userCoords) bounds.extend(userCoords);
    map.fitBounds(bounds);
  }
}

// ── Map search / geolocation ───────────────────────────────────────────────────

function setupMapSearch() {
  mapSearchBtn.addEventListener("click", searchLocation);
  mapSearchInput.addEventListener("keydown", e => { if (e.key === "Enter") searchLocation(); });
}

async function searchLocation() {
  const q = mapSearchInput.value.trim();
  if (!q) return;
  try {
    const resp = await fetch(`${API}/maps/search?q=${encodeURIComponent(q)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    userCoords = { lat: data.lat, lng: data.lng };
    if (map) map.setCenter(userCoords);
    addBotMessage(`Ubicación establecida: ${data.formatted_address}`);
  } catch (e) {
    addBotMessage(`No pude encontrar esa ubicación: ${e.message}`);
  }
}

async function autoDetectLocation() {
  return new Promise(resolve => {
    if (!navigator.geolocation) return resolve();
    navigator.geolocation.getCurrentPosition(
      pos => {
        userCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        if (map) map.setCenter(userCoords);
        addBotMessage("Ubicación detectada automáticamente.");
        resolve();
      },
      () => resolve(),
      { timeout: 5000 },
    );
  });
}

// ── Doctor WebSocket Chat ──────────────────────────────────────────────────────

function setupModal() {
  modalCloseBtn.addEventListener("click", closeDoctorChat);
  modalSendBtn.addEventListener("click", sendModalMessage);
  modalInput.addEventListener("keydown", e => { if (e.key === "Enter") sendModalMessage(); });
}

function openDoctorChat(conversationId, doctorId) {
  if (activeWs) activeWs.close();
  modalMessages.innerHTML = "";
  modalDoctorName.textContent = `Chat (${conversationId.slice(-8)})`;
  chatModal.classList.remove("hidden");

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  activeWs = new WebSocket(`${wsProto}://${location.host}/ws/chat/${conversationId}`);

  activeWs.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "history") {
        msg.messages.forEach(m => appendModalMsg(m.sender, m.text));
      } else {
        appendModalMsg(msg.sender, msg.text);
      }
    } catch {
      appendModalMsg("sistema", evt.data);
    }
  };

  activeWs.onerror = () => appendModalMsg("sistema", "Error de conexión.");
}

function closeDoctorChat() {
  chatModal.classList.add("hidden");
  if (activeWs) { activeWs.close(); activeWs = null; }
}

function sendModalMessage() {
  const text = modalInput.value.trim();
  if (!text || !activeWs) return;
  activeWs.send(JSON.stringify({ sender: "patient", text }));
  appendModalMsg("patient", text);
  modalInput.value = "";
}

function appendModalMsg(sender, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${sender === "patient" ? "user" : "bot"}`;
  div.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  modalMessages.appendChild(div);
  modalMessages.scrollTop = modalMessages.scrollHeight;
}

// ── API Status ─────────────────────────────────────────────────────────────────

async function checkApiStatus() {
  try {
    const resp = await fetch(`${API}/`);
    if (resp.ok) {
      apiStatus.innerHTML = `<span class="material-symbols-outlined" style="color:#34a853">fiber_manual_record</span><span>CONECTADO</span>`;
    }
  } catch {
    apiStatus.innerHTML = `<span class="material-symbols-outlined" style="color:#ea4335">fiber_manual_record</span><span>SIN CONEXIÓN</span>`;
  }
}

// ── Spinner ────────────────────────────────────────────────────────────────────

function showSpinner() { spinner.classList.remove("hidden"); }
function hideSpinner() { spinner.classList.add("hidden"); }

// ── Helpers ────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

// ── Boot ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
