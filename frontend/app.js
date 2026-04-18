/**
 * MedConnect — Frontend
 * Handles: symptom chat, consult pipeline, map with clinic markers, doctor chat (WebSocket).
 */

const API = "";  // same-origin; empty string = relative URLs

// ── Auth guard ─────────────────────────────────────────────────────────────────
// Doctor → redirige a doctor.html. Paciente sin sesión → redirige a login.
if (sessionStorage.getItem("medconnect_doctor")) {
  window.location.replace("doctor.html");
}
const userSession = JSON.parse(sessionStorage.getItem("medconnect_user") || "null");
if (!userSession) {
  window.location.replace("login.html");
}

// ── State ──────────────────────────────────────────────────────────────────────
let sessionId = crypto.randomUUID();
let userCoords = userSession?.coords || null;   // { lat, lng }
let map = null;
let clinicMarkers = [];
let userMarker = null;        // marker de "tú estás aquí"
let radiusCircle = null;      // círculo del perímetro de búsqueda
let activeWs = null;     // WebSocket for doctor chat
let budgetLevel = "$$";
let searchRadiusM = 5000;     // perímetro de búsqueda (metros)
let facilityType = "any";     // "public" | "private" | "any"
let _locationResolve = null;  // resolves the autoDetectLocation promise on confirm

// Conversation state — the backend chat agent owns the dialogue.
// Frontend relays messages, applies preference updates, and re-runs /consult
// when the agent emits action="consult" (first run) or "refine_consult" (after).
let collectedData = {};   // last data snapshot from chat agent
let consulting = false;
let hasRecommendations = false;   // flips to true after the first /consult

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
  setupUserChip();
  applyUserPreferences();
  setupBudgetButtons();
  setupChatInput();
  setupMapSearch();
  setupRecPanel();
  setupModal();
  setupTriageToggle();
  await initMap();
  if (userCoords) {
    map?.setCenter(userCoords);
    map?.setZoom(14);
    drawUserLocation();
  }
  await checkApiStatus();
  if (userCoords) {
    // Coords already known from session — skip detection, go straight to chat
    drawUserLocation();
    await bootstrapChat();
  } else {
    // Wait for geolocation + user confirmation before starting chat
    await autoDetectLocation();
    await bootstrapChat();
  }
}

function setupUserChip() {
  const chip = document.getElementById("user-chip");
  if (!chip || !userSession) return;
  const first = (userSession.name || userSession.full_name || "P").trim();
  const last  = (userSession.last_name || "").trim();
  const initials = ((first[0] || "P") + (last[0] || "")).toUpperCase();
  chip.textContent = initials;
  chip.title = `${userSession.full_name || first} — clic para cerrar sesión`;
  chip.style.cursor = "pointer";
  chip.addEventListener("click", () => {
    if (!confirm("¿Cerrar sesión?")) return;
    if (activeWs) activeWs.close();
    sessionStorage.removeItem("medconnect_user");
    window.location.replace("login.html");
  });
}

function applyUserPreferences() {
  if (!userSession) return;
  const insSelect = document.getElementById("insurance-select");
  if (insSelect && userSession.insurance) {
    const opt = Array.from(insSelect.options).find(o => o.value === userSession.insurance);
    if (opt) insSelect.value = userSession.insurance;
  }
  if (userSession.coords && map) {
    map.setCenter(userSession.coords);
  }
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
  const typingEl = showTypingIndicator();
  try {
    const resp = await fetch(`${API}/chat/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        has_coords: !!userCoords,
        has_recommendations: hasRecommendations,
        user_id: userSession?.user_id || null,
        current_prefs: {
          facility_type: facilityType,
          insurance: document.getElementById("insurance-select")?.value || null,
          budget_level: budgetLevel,
          radius_m: searchRadiusM,
        },
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const turn = await resp.json();

    hideTypingIndicator(typingEl);
    if (turn.reply) addBotMessage(turn.reply);
    collectedData = { ...collectedData, ...(turn.data || {}) };
    if (turn.preferences) applyPreferenceUpdates(turn.preferences);

    const action = turn.action || (turn.ready ? "consult" : "none");
    if (action === "consult" || action === "refine_consult") {
      await triggerConsult(turn.emergency, action === "refine_consult");
    }
  } catch (e) {
    hideTypingIndicator(typingEl);
    addBotMessage(`No pude procesar tu mensaje: ${e.message}`);
    console.error(e);
  } finally {
    hideSpinner();
  }
}

// Merge preferences the chat agent has inferred/updated into the UI state.
function applyPreferenceUpdates(prefs) {
  if (prefs.facility_type) facilityType = prefs.facility_type;

  if (prefs.insurance) {
    const sel = document.getElementById("insurance-select");
    if (sel) {
      const opt = Array.from(sel.options).find(o => o.value === prefs.insurance);
      if (opt) sel.value = prefs.insurance;
    }
  }

  if (prefs.budget_level) {
    budgetLevel = prefs.budget_level;
    document.querySelectorAll(".budget-btn").forEach(b => {
      b.classList.toggle("active", b.dataset.val === prefs.budget_level);
    });
  }

  if (prefs.radius_m && prefs.radius_m !== searchRadiusM) {
    searchRadiusM = Math.max(500, Math.min(50000, prefs.radius_m));
    if (userCoords && typeof drawUserLocation === "function") {
      drawUserLocation();   // redraws radiusCircle at the new radius
    }
  }
}

async function triggerConsult(emergency, isRefine = false) {
  if (consulting) return;
  consulting = true;
  if (isRefine) {
    addBotMessage("Ajustando las recomendaciones con tus nuevas preferencias...");
  }
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

    const ageForBlob = collectedData.age || userSession?.age || "";
    const symptomsBlob = [
      collectedData.symptoms,
      collectedData.duration ? `Duración: ${collectedData.duration}` : "",
      collectedData.severity ? `Severidad: ${collectedData.severity}` : "",
      ageForBlob ? `Edad: ${ageForBlob}` : "",
      emergency ? "EMERGENCIA reportada por el paciente." : "",
    ].filter(Boolean).join(". ");

    await runConsult(symptomsBlob);
  } finally {
    consulting = false;
  }
}

function showTypingIndicator() {
  const div = document.createElement("div");
  div.className = "chat-msg bot typing-indicator";
  div.innerHTML = `
    <div class="bot-avatar"><span class="material-symbols-outlined">smart_toy</span></div>
    <div class="bot-content"><div class="msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function hideTypingIndicator(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}

function showAnalyzingMessage(text) {
  const div = document.createElement("div");
  div.className = "chat-msg bot typing-indicator";
  div.innerHTML = `
    <div class="bot-avatar"><span class="material-symbols-outlined">smart_toy</span></div>
    <div class="bot-content"><div class="msg-bubble"><span class="analyzing-text">${escapeHtml(text)}</span><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function dismissWelcome() {
  const w = document.getElementById("chat-welcome");
  if (w) w.remove();
}

function addBotMessage(text) {
  dismissWelcome();
  const div = document.createElement("div");
  div.className = "chat-msg bot";
  div.innerHTML = `
    <div class="bot-avatar"><span class="material-symbols-outlined">smart_toy</span></div>
    <div class="bot-content">
      <div class="msg-text">${escapeHtml(text)}</div>
      <div class="msg-actions">
        <button class="msg-action-btn" title="Copiar" onclick="navigator.clipboard?.writeText(this.closest('.bot-content').querySelector('.msg-text').innerText)">
          <span class="material-symbols-outlined">content_copy</span>
        </button>
      </div>
    </div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addUserMessage(text) {
  dismissWelcome();
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

  if (!userSession?.user_id) {
    addBotMessage("Tu sesión expiró. Vuelve a iniciar sesión para continuar.");
    window.location.replace("login.html");
    return;
  }

  const insurance = document.getElementById("insurance-select").value;

  showSpinner();
  const analyzingEl = showAnalyzingMessage("Analizando tus síntomas con IA...");

  try {
    const resp = await fetch(`${API}/consult`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        user_id: userSession.user_id,
        symptoms,
        coords: userCoords,
        insurance,
        budget_level: budgetLevel,
        radius_m: searchRadiusM,
        facility_type: facilityType,
      }),
    });

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        if (err?.detail) detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      } catch { /* ignore */ }
      throw new Error(detail);
    }
    const data = await resp.json();

    hideTypingIndicator(analyzingEl);
    handleConsultResponse(data);
  } catch (e) {
    hideTypingIndicator(analyzingEl);
    addBotMessage(`Error al procesar tu consulta: ${e.message}. Intenta de nuevo.`);
    console.error(e);
  } finally {
    hideSpinner();
  }
}

function handleConsultResponse(data) {
  const { triage, recommendations } = data;

  // Save to chat history (hidden in split mode until toggled)
  const urgencyEmoji = { critical: "🚨", medium: "⚠️", low: "✅" }[triage.urgency_level] || "ℹ️";
  addBotMessage(`${urgencyEmoji} ${triage.clinical_summary}\n\nEspecialidad requerida: ${triage.specialty}`);
  if (recommendations.urgent_message) addBotMessage(`🚨 ${recommendations.urgent_message}`);

  if (!recommendations.recommendations?.length) {
    addBotMessage("No encontramos clínicas disponibles con tus criterios. Prueba cambiando el presupuesto o seguro.");
    return;
  }

  addBotMessage(`Encontré ${recommendations.recommendations.length} opciones para ti. Puedes ver las clínicas en el mapa.`);

  // Build triage summary card
  const urgencyLabel = { critical: "Crítica 🚨", medium: "Moderada ⚠️", low: "Baja ✅" }[triage.urgency_level] || triage.urgency_level;
  const urgencyColor = { critical: "#f28b82", medium: "#FFD700", low: "#34a853" }[triage.urgency_level] || "#8ab4f8";
  document.getElementById("triage-pills").innerHTML = `
    <span class="triage-pill" style="color:${urgencyColor};border-color:${urgencyColor}55;background:${urgencyColor}18">Urgencia ${urgencyLabel}</span>
    <span class="triage-pill">${escapeHtml(triage.specialty)}</span>`;
  document.getElementById("triage-text").textContent = triage.clinical_summary;
  document.getElementById("toggle-chat-label").textContent =
    `${recommendations.recommendations.length} opciones encontradas · Ver historial`;
  document.getElementById("triage-summary").classList.remove("hidden");

  triggerSplitView();
  const sortedRecs = [...recommendations.recommendations].sort((a, b) => (b.is_network ? 1 : 0) - (a.is_network ? 1 : 0));
  showRecommendations(sortedRecs);
  plotClinicsOnMap(sortedRecs);
  hasRecommendations = true;
}

function triggerSplitView() {
  document.getElementById("workspace").classList.add("split-mode");
  setTimeout(() => {
    if (map && typeof google !== "undefined") {
      google.maps.event.trigger(map, "resize");
      if (userCoords) {
        map.setCenter(userCoords);
        map.setZoom(15);
      }
    }
  }, 450);
}

function setupTriageToggle() {
  const btn = document.getElementById("toggle-chat-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const chatLeft = document.querySelector(".chat-left");
    chatLeft.classList.toggle("chat-expanded");
    const icon = btn.querySelector(".toggle-icon");
    icon.textContent = chatLeft.classList.contains("chat-expanded") ? "expand_less" : "expand_more";
  });
}

// ── Recommendations panel ──────────────────────────────────────────────────────

function setupRecPanel() {
  recCloseBtn.addEventListener("click", () => recPanel.classList.add("hidden"));
}

function showRecommendations(recs) {
  recCards.innerHTML = "";
  recs.forEach((rec, i) => {
    const card = document.createElement("div");
    card.className = "rec-card" + (rec.is_network ? " is-network" : "");

    const networkBadge = rec.is_network
      ? `<span class="badge badge-network">En red</span>`
      : `<span class="badge badge-external">Externo</span>`;

    const travelTime = rec.travel_time_min
      ? `<span class="rec-travel"><span class="material-symbols-outlined">directions_car</span>${Math.round(rec.travel_time_min)} min</span>`
      : "";

    const scoreHtml = rec.match_score != null ? `<div class="rec-score">
      <div class="rec-score-bar"><div class="rec-score-fill" style="width:${rec.match_score}%"></div></div>
      <span class="rec-score-label">${rec.match_score}%</span>
    </div>` : "";

    const clinicName = rec.name
      ? `<div class="rec-name">${escapeHtml(rec.name)}</div>`
      : "";

    const doctors = rec.contact?.doctors || [];
    const doctorRows = doctors.map(d =>
      `<div class="doctor-catalogue-row">
         <span class="doctor-catalogue-name">${escapeHtml(d.name)}${d.specialty ? " · " + escapeHtml(d.specialty) : ""}</span>
         <button class="rec-action-btn btn-chat doctor-chat-btn"
             data-doctor="${d.doctor_id}"
             data-clinic="${rec.clinic_id || ""}">
           <span class="material-symbols-outlined" style="font-size:15px">chat</span>
         </button>
       </div>`
    ).join("");
    const networkActions = rec.is_network
      ? `<div class="doctor-catalogue-label">Doctores disponibles</div>
         <div class="doctor-catalogue">${doctorRows || '<span class="doctor-catalogue-empty">Sin doctores en red</span>'}</div>
         <button class="rec-action-btn btn-appt"
             data-doctor="${rec.contact?.doctor_id || ""}"
             data-clinic="${rec.clinic_id || ""}"
             data-name="${escapeAttr(rec.name || "")}">
           <span class="material-symbols-outlined">event</span> Agendar cita
         </button>`
      : `<button class="rec-action-btn btn-info" data-phone="${rec.contact?.phone || ""}" data-address="${escapeAttr(rec.contact?.address || "")}">
           <span class="material-symbols-outlined">info</span> Contacto
         </button>`;

    card.innerHTML = `
      <div class="rec-card-header">
        <span class="rec-priority">${i + 1}</span>
        ${networkBadge}
        ${travelTime}
      </div>
      ${clinicName}
      ${scoreHtml}
      <div class="rec-justification">${escapeHtml(rec.justification)}</div>
      <div class="rec-card-footer">
        ${networkActions}
        ${rec.coords ? `<button class="rec-action-btn btn-map" data-lat="${rec.coords.lat}" data-lng="${rec.coords.lng}">
          <span class="material-symbols-outlined">map</span> Ver en mapa
        </button>` : ""}
      </div>
    `;

    recCards.appendChild(card);
  });

  recCards.querySelectorAll(".btn-chat").forEach(btn => {
    btn.addEventListener("click", () => openDoctorChat(btn.dataset.doctor, btn.dataset.clinic));
  });
  recCards.querySelectorAll(".btn-appt").forEach(btn => {
    btn.addEventListener("click", () => openAppointmentModal(btn.dataset.doctor, btn.dataset.clinic, btn.dataset.name));
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

  const infoWindow = new google.maps.InfoWindow();

  recs.forEach((rec, i) => {
    if (!rec.coords || !map) return;
    const pinColor = rec.is_network ? "#34a853" : "#38BDF8";
    const pinSvg = encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="42">` +
      `<path d="M16 2C9.9 2 5 6.9 5 13c0 8.5 11 25 11 25s11-16.5 11-25c0-6.1-4.9-11-11-11z" fill="${pinColor}" stroke="rgba(0,0,0,0.25)" stroke-width="1.5"/>` +
      `<text x="16" y="17" text-anchor="middle" dy=".3em" fill="white" font-size="11" font-family="sans-serif" font-weight="700">${i + 1}</text>` +
      `</svg>`
    );
    const marker = new google.maps.Marker({
      position: { lat: rec.coords.lat, lng: rec.coords.lng },
      map,
      title: rec.name || rec.justification,
      icon: {
        url: `data:image/svg+xml,${pinSvg}`,
        scaledSize: new google.maps.Size(32, 42),
        anchor: new google.maps.Point(16, 42),
      },
    });

    const scoreColor = rec.match_score >= 80 ? "#34a853" : rec.match_score >= 60 ? "#fbbc04" : "#ea4335";
    const scoreHtml = rec.match_score != null
      ? `<span style="color:${scoreColor};font-weight:700">${rec.match_score}% compatibilidad</span>`
      : "";
    const travelLine = rec.travel_time_min
      ? `<span style="color:#8ab4f8">&#128664; ${Math.round(rec.travel_time_min)} min</span>`
      : "";

    if (rec.is_network) {
      const iwDoctors = rec.contact?.doctors || [];
      const doctorHtml = iwDoctors.map(d =>
        `<div style="display:flex;align-items:center;gap:6px;margin:3px 0">
           <span style="flex:1;font-size:12px;color:#e8eaed">${escapeHtml(d.name)}${d.specialty ? " · " + escapeHtml(d.specialty) : ""}</span>
           <button class="iw-chat-btn"
             data-doctor-id="${d.doctor_id}"
             data-clinic-id="${rec.clinic_id || ""}"
             style="background:#34a853;color:#fff;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;white-space:nowrap">Chat</button>
         </div>`
      ).join("") || `<span style="font-size:12px;color:#aaa">Sin doctores en red</span>`;

      const content = `
        <div style="font-family:sans-serif;font-size:13px;max-width:250px;line-height:1.5;background:#202124;color:#e8eaed;padding:2px">
          <div style="font-weight:700;margin-bottom:4px">${escapeHtml(rec.name || `Opción ${i + 1}`)}</div>
          ${scoreHtml ? `<div>${scoreHtml}</div>` : ""}
          ${travelLine ? `<div>${travelLine}</div>` : ""}
          <div style="margin-top:6px;color:#34a853;font-weight:600;font-size:11px;letter-spacing:.04em">DOCTORES EN RED</div>
          ${doctorHtml}
        </div>`;

      marker.addListener("click", () => {
        infoWindow.setContent(content);
        infoWindow.open(map, marker);
        google.maps.event.addListenerOnce(infoWindow, "domready", () => {
          document.querySelectorAll(".iw-chat-btn").forEach(btn => {
            btn.addEventListener("click", () => {
              openDoctorChat(btn.dataset.doctorId, btn.dataset.clinicId);
              infoWindow.close();
            });
          });
        });
      });
    } else {
      const contactLine = [
        rec.contact?.phone ? `Tel: ${rec.contact.phone}` : "",
        rec.contact?.address ? rec.contact.address : "",
      ].filter(Boolean).join("<br>");
      const content = `
        <div style="font-family:sans-serif;font-size:13px;max-width:220px;line-height:1.5">
          <div style="font-weight:700;margin-bottom:4px">${escapeHtml(rec.name || `Opción ${i + 1}`)}</div>
          ${scoreHtml ? `<div>${scoreHtml}</div>` : ""}
          ${travelLine ? `<div>${travelLine}</div>` : ""}
          <div style="margin-top:4px;color:#666;font-size:12px">${contactLine}</div>
        </div>`;
      marker.addListener("mouseover", () => {
        infoWindow.setContent(content);
        infoWindow.open(map, marker);
      });
      marker.addListener("mouseout", () => infoWindow.close());
    }

    clinicMarkers.push(marker);
  });

  if (clinicMarkers.length) {
    const bounds = new google.maps.LatLngBounds();
    clinicMarkers.forEach(m => bounds.extend(m.getPosition()));
    if (userCoords) bounds.extend(userCoords);
    map.fitBounds(bounds);
    drawUserLocation();   // re-asegura que el marker del usuario siga visible
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
    if (map) {
      map.setCenter(userCoords);
      map.setZoom(14);
    }
    drawUserLocation();
    addBotMessage(`Ubicación establecida: ${data.formatted_address}`);
  } catch (e) {
    addBotMessage(`No pude encontrar esa ubicación: ${e.message}`);
  }
}

async function autoDetectLocation() {
  return new Promise(resolve => {
    if (!navigator.geolocation) { resolve(); return; }
    navigator.geolocation.getCurrentPosition(
      async pos => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        userCoords = { lat, lng };
        if (map) { map.setCenter(userCoords); map.setZoom(14); }
        drawUserLocation();

        // Reverse-geocode to get a human-readable address, then show the card
        let address = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
        try {
          const r = await fetch(`${API}/maps/reverse?lat=${lat}&lng=${lng}`);
          if (r.ok) address = (await r.json()).short_address || address;
        } catch { /* keep coordinate fallback */ }

        // Store resolve — confirmLocationCard() will call it
        _locationResolve = resolve;
        showLocationCard(address, lat, lng);
        // Do NOT call resolve() here — wait for user to confirm
      },
      err => {
        console.warn("Geolocation error:", err);
        addBotMessage("No pude detectar tu ubicación automáticamente. Puedes escribir tu dirección cuando el asistente te lo pida.");
        resolve();
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  });
}

function showLocationCard(address, lat, lng) {
  const msgs = document.getElementById("chat-messages");
  const card = document.createElement("div");
  card.className = "location-card";
  card.id = "location-card";
  card.innerHTML = `
    <div class="lc-header">
      <span class="material-symbols-outlined">my_location</span>
      <span>Ubicación detectada</span>
    </div>
    <div class="lc-address" id="lc-address-text">${escapeHtml(address)}</div>
    <div class="lc-search-row">
      <input id="lc-input" class="lc-input" type="text" placeholder="Corregir dirección..." autocomplete="off" />
      <button class="lc-search-btn" onclick="searchLocationFromCard()">
        <span class="material-symbols-outlined">search</span>
      </button>
    </div>
    <div class="lc-radius-row">
      <span class="lc-radius-label">Radio de búsqueda</span>
      <div class="lc-radius-btns" id="lc-radius-btns">
        <button class="lc-radius-btn" data-val="3000">3 km</button>
        <button class="lc-radius-btn active" data-val="5000">5 km</button>
        <button class="lc-radius-btn" data-val="10000">10 km</button>
        <button class="lc-radius-btn" data-val="20000">20 km</button>
      </div>
    </div>
    <button class="lc-confirm-btn" id="lc-confirm-btn" onclick="confirmLocationCard()">
      <span class="material-symbols-outlined">check_circle</span>
      Confirmar y continuar
    </button>
  `;
  msgs.appendChild(card);
  msgs.scrollTop = msgs.scrollHeight;

  // Store pending coords on card element
  card._pendingLat = lat;
  card._pendingLng = lng;

  // Radius buttons
  card.querySelectorAll(".lc-radius-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      card.querySelectorAll(".lc-radius-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  // Enter key on address input
  card.querySelector("#lc-input").addEventListener("keydown", e => {
    if (e.key === "Enter") searchLocationFromCard();
  });
}

async function searchLocationFromCard() {
  const card = document.getElementById("location-card");
  if (!card) return;
  const q = card.querySelector("#lc-input").value.trim();
  if (!q) return;
  try {
    const r = await fetch(`${API}/maps/search?q=${encodeURIComponent(q)}`);
    if (!r.ok) return;
    const data = await r.json();
    card._pendingLat = data.lat;
    card._pendingLng = data.lng;
    card.querySelector("#lc-address-text").textContent = data.formatted_address || data.name || q;
    card.querySelector("#lc-input").value = "";
    if (map) { map.setCenter({ lat: data.lat, lng: data.lng }); map.setZoom(14); }
  } catch { /* ignore */ }
}

function confirmLocationCard() {
  const card = document.getElementById("location-card");
  if (!card) return;

  const lat       = card._pendingLat;
  const lng       = card._pendingLng;
  const activeBtn = card.querySelector(".lc-radius-btn.active");
  const radius    = activeBtn ? parseInt(activeBtn.dataset.val, 10) : searchRadiusM;
  const addr      = card.querySelector("#lc-address-text")?.textContent || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

  userCoords    = { lat, lng };
  searchRadiusM = radius;

  if (map) { map.setCenter(userCoords); map.setZoom(14); }
  drawUserLocation();

  card.innerHTML = `
    <div class="lc-confirmed">
      <span class="material-symbols-outlined">check_circle</span>
      <span>${escapeHtml(addr)} · Radio ${(radius / 1000).toFixed(0)} km</span>
    </div>
  `;

  // Unblock the init() flow so bootstrapChat() runs next
  if (_locationResolve) { _locationResolve(); _locationResolve = null; }
}

// Dibuja (o actualiza) marker del usuario + círculo del radio de búsqueda
function drawUserLocation() {
  if (!map || !userCoords || typeof google === "undefined") return;

  if (userMarker) {
    userMarker.setPosition(userCoords);
  } else {
    userMarker = new google.maps.Marker({
      position: userCoords,
      map,
      title: "Tu ubicación",
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 10,
        fillColor: "#1a73e8",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 3,
      },
      zIndex: 999,
    });
  }

  if (radiusCircle) {
    radiusCircle.setCenter(userCoords);
    radiusCircle.setRadius(searchRadiusM);
  } else {
    radiusCircle = new google.maps.Circle({
      center: userCoords,
      radius: searchRadiusM,
      map,
      fillColor: "#1a73e8",
      fillOpacity: 0.06,
      strokeColor: "#1a73e8",
      strokeOpacity: 0.35,
      strokeWeight: 1,
      clickable: false,
    });
  }
}

// ── Doctor WebSocket Chat ──────────────────────────────────────────────────────

// Cache conversación por doctor_id para no crearla dos veces (chat + cita).
const conversationCache = new Map();   // doctor_id → conversation_id

async function ensureConversation(doctorId, clinicId) {
  if (!doctorId) throw new Error("doctor_id requerido");
  if (conversationCache.has(doctorId)) return conversationCache.get(doctorId);

  const resp = await fetch(`${API}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userSession.user_id,
      doctor_id: doctorId,
      session_id: sessionId,
      clinic_id: clinicId || null,
    }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  const { conversation_id } = await resp.json();
  conversationCache.set(doctorId, conversation_id);
  return conversation_id;
}

function setupModal() {
  modalCloseBtn.addEventListener("click", closeDoctorChat);
  modalSendBtn.addEventListener("click", sendModalMessage);
  modalInput.addEventListener("keydown", e => { if (e.key === "Enter") sendModalMessage(); });
}

async function openDoctorChat(doctorId, clinicId) {
  if (activeWs) {
    const old = activeWs;
    old._intentionalClose = true;
    activeWs = null;
    old.close();
  }
  modalMessages.innerHTML = "";
  modalInput.setAttribute("disabled", "");
  modalDoctorName.textContent = "Conectando con el doctor...";
  chatModal.classList.remove("hidden");

  let conversationId;
  try {
    conversationId = await ensureConversation(doctorId, clinicId);
  } catch (e) {
    appendModalMsg("bot-info", `No se pudo iniciar el chat: ${e.message}`);
    return;
  }

  modalDoctorName.textContent = `Chat (${conversationId.slice(-8)})`;

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/chat/${conversationId}`);
  activeWs = ws;

  ws.onopen = () => modalInput.removeAttribute("disabled");
  ws.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "history") {
        msg.messages.forEach(m => appendModalMsg(m.sender, m.text));
      } else if (msg.type === "error") {
        appendModalMsg("bot-info", msg.detail || "Error en el chat.");
      } else {
        appendModalMsg(msg.sender, msg.text);
      }
    } catch {
      appendModalMsg("bot-info", evt.data);
    }
  };

  ws.onerror = () => appendModalMsg("bot-info", "Error de conexión.");
  ws.onclose = () => {
    if (activeWs === ws) activeWs = null;
    if (!ws._intentionalClose) appendModalMsg("bot-info", "Chat desconectado.");
  };
}

// ── Appointment booking ────────────────────────────────────────────────────────

function openAppointmentModal(doctorId, clinicId, clinicName) {
  const overlay = document.getElementById("appt-overlay");
  const errEl   = document.getElementById("appt-error");
  errEl.textContent = "";

  overlay.dataset.doctorId = doctorId || "";
  overlay.dataset.clinicId = clinicId || "";

  document.getElementById("appt-clinic-name").textContent = clinicName || "Doctor en red";

  // Pre-rellenar con mañana 10:00
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = n => String(n).padStart(2, "0");
  document.getElementById("appt-date").value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  document.getElementById("appt-time").value = "10:00";
  document.getElementById("appt-duration").value = "30";
  document.getElementById("appt-notes").value = "";

  overlay.classList.remove("hidden");
}

function closeAppointmentModal() {
  document.getElementById("appt-overlay").classList.add("hidden");
}

async function submitAppointment() {
  const overlay  = document.getElementById("appt-overlay");
  const btn      = document.getElementById("appt-submit-btn");
  const errEl    = document.getElementById("appt-error");
  const doctorId = overlay.dataset.doctorId;
  const clinicId = overlay.dataset.clinicId;

  const date     = document.getElementById("appt-date").value;
  const time     = document.getElementById("appt-time").value;
  const duration = parseInt(document.getElementById("appt-duration").value, 10) || 30;
  const notes    = document.getElementById("appt-notes").value.trim();

  if (!date || !time) {
    errEl.textContent = "Fecha y hora son obligatorias.";
    return;
  }

  const scheduledAt = new Date(`${date}T${time}:00`);
  if (isNaN(scheduledAt.getTime())) {
    errEl.textContent = "Fecha/hora inválida.";
    return;
  }
  if (scheduledAt.getTime() < Date.now()) {
    errEl.textContent = "La fecha debe ser futura.";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Enviando...";
  errEl.textContent = "";

  try {
    const conversationId = await ensureConversation(doctorId, clinicId);
    const payload = {
      conversation_id: conversationId,
      user_id: userSession.user_id,
      doctor_id: doctorId,
      clinic_id: clinicId || null,
      scheduled_at: scheduledAt.toISOString(),
      duration_min: duration,
      notes: notes || null,
    };
    const resp = await fetch(`${API}/appointments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      errEl.textContent = data.detail || `Error ${resp.status}`;
      return;
    }
    closeAppointmentModal();
    addBotMessage(`✅ Cita solicitada para ${scheduledAt.toLocaleString("es-MX")}. Estado: pendiente de confirmación.`);
  } catch (e) {
    errEl.textContent = e.message || "Error de conexión";
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined">check</span> Confirmar solicitud';
  }
}

function closeDoctorChat() {
  chatModal.classList.add("hidden");
  if (activeWs) {
    const old = activeWs;
    old._intentionalClose = true;
    activeWs = null;
    old.close();
  }
}

function sendModalMessage() {
  const text = modalInput.value.trim();
  if (!text) return;
  if (!activeWs || activeWs.readyState !== WebSocket.OPEN) {
    appendModalMsg("bot-info", "Reconectando…");
    return;
  }
  activeWs.send(JSON.stringify({ sender: "patient", text }));
  modalInput.value = "";
}

function appendModalMsg(sender, text) {
  if (sender === "system") return;   // clinical profile is doctor-facing only
  const div = document.createElement("div");
  if (sender === "bot-info") {
    div.className = "chat-modal-info";
    div.textContent = text;
  } else {
    const isMe = sender === "patient" || sender === "user";
    div.className = `chat-msg ${isMe ? "user" : "bot"}`;
    div.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  }
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

function showSpinner() { /* replaced by inline typing indicator */ }
function hideSpinner() { /* replaced by inline typing indicator */ }

// ── Helpers ────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

function escapeAttr(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Side panels (Chats + Appointments) ────────────────────────────────────────

function openPanel(which) {
  const panelId = which === "history" ? "history-panel" : "appt-panel";
  const btnId   = which === "history" ? "sb-history" : "sb-appts";
  const panel   = document.getElementById(panelId);
  const isOpen  = !panel.classList.contains("hidden");

  closeSidePanel();
  if (isOpen) return; // toggle off if already open

  panel.classList.remove("hidden");
  document.getElementById(btnId)?.classList.add("active");
  if (which === "history") loadConversations();
  else loadPatientAppointments();
}

function closeSidePanel() {
  ["history-panel", "appt-panel"].forEach(id =>
    document.getElementById(id)?.classList.add("hidden")
  );
  ["sb-history", "sb-appts"].forEach(id =>
    document.getElementById(id)?.classList.remove("active")
  );
}

function formatConvDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 60) return diffMin <= 1 ? "ahora" : `${diffMin}m`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h`;
  return d.toLocaleDateString("es-MX", { month: "short", day: "numeric" });
}

async function loadConversations() {
  const body = document.getElementById("conv-list");
  if (!body) return;
  body.innerHTML = '<div class="panel-loading">Cargando chats...</div>';
  const uid = userSession?.user_id;
  if (!uid) { body.innerHTML = '<div class="panel-empty">Inicia sesión para ver tus chats.</div>'; return; }
  try {
    const res = await fetch(`${API}/conversations?user_id=${uid}`);
    if (!res.ok) throw new Error();
    const { conversations } = await res.json();
    if (!conversations.length) {
      body.innerHTML = '<div class="panel-empty">Aún no tienes chats. Consulta con un médico para empezar.</div>';
      return;
    }
    body.innerHTML = conversations.map(c => `
      <div class="conv-item${c.status === "closed" ? " conv-closed" : ""}"
           onclick="reopenConversation('${c.conversation_id}', '${escapeAttr(c.doctor_name || "Doctor")}', '${c.status}')">
        <div class="conv-item-header">
          <span class="conv-doctor">${escapeHtml(c.doctor_name || "Doctor")}</span>
          <span class="conv-specialty">${escapeHtml(c.doctor_specialty || "")}</span>
        </div>
        <div class="conv-summary">${escapeHtml(c.clinical_summary || c.last_message_text || "—")}</div>
        <div class="conv-meta">
          <span class="conv-urgency-dot urgency-dot-${c.urgency_level || "low"}"></span>
          <span class="conv-date">${formatConvDate(c.updated_at)}</span>
          <span class="conv-status-badge conv-status-${c.status}">${c.status === "active" ? "Activo" : "Cerrado"}</span>
        </div>
      </div>`).join("");
  } catch {
    body.innerHTML = '<div class="panel-empty" style="color:#f28b82">No se pudieron cargar los chats.</div>';
  }
}

async function reopenConversation(conversationId, doctorName, status) {
  closeSidePanel();
  document.getElementById("modal-doctor-name").textContent = `Chat con ${doctorName}`;
  document.getElementById("modal-messages").innerHTML = "";
  modalInput.setAttribute("disabled", "");
  document.getElementById("chat-modal").classList.remove("hidden");

  if (status === "closed") {
    // Read-only history via REST — WS rejects closed conversations
    try {
      const res = await fetch(`${API}/conversations/${conversationId}/messages`);
      if (!res.ok) throw new Error();
      const { messages } = await res.json();
      messages.forEach(m => appendModalMsg(m.sender, m.text));
      appendModalMsg("bot-info", "Esta conversación está cerrada.");
    } catch {
      appendModalMsg("bot-info", "No se pudo cargar el historial.");
    }
    return;
  }

  // Active conversation — live WebSocket
  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  if (activeWs) {
    const old = activeWs;
    old._intentionalClose = true;
    activeWs = null;
    old.close();
  }
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/chat/${conversationId}`);
  activeWs = ws;
  ws.onopen = () => modalInput.removeAttribute("disabled");
  ws.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "history") {
        msg.messages.forEach(m => appendModalMsg(m.sender, m.text));
      } else if (msg.type === "error") {
        appendModalMsg("bot-info", msg.detail || "Error en el chat.");
      } else {
        appendModalMsg(msg.sender, msg.text);
      }
    } catch { /* ignore */ }
  };
  ws.onerror = () => appendModalMsg("bot-info", "Error de conexión.");
  ws.onclose = () => {
    if (activeWs === ws) activeWs = null;
    if (!ws._intentionalClose) appendModalMsg("bot-info", "Chat desconectado.");
  };
}

async function loadPatientAppointments() {
  const body = document.getElementById("appt-list");
  if (!body) return;
  body.innerHTML = '<div class="panel-loading">Cargando citas...</div>';
  const uid = userSession?.user_id;
  if (!uid) { body.innerHTML = '<div class="panel-empty">Inicia sesión para ver tus citas.</div>'; return; }
  try {
    const res = await fetch(`${API}/appointments?user_id=${uid}`);
    if (!res.ok) throw new Error();
    const { appointments } = await res.json();
    if (!appointments.length) {
      body.innerHTML = '<div class="panel-empty">Sin citas agendadas aún.</div>';
      return;
    }
    const statusLabel = { pending: "Pendiente", confirmed: "Confirmada", cancelled: "Cancelada", completed: "Completada" };
    body.innerHTML = appointments.map(a => {
      const dt = new Date(a.scheduled_at);
      const dateStr = dt.toLocaleDateString("es-MX", { weekday: "short", month: "short", day: "numeric" });
      const timeStr = dt.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
      return `<div class="appt-item appt-item-${a.status}">
        <div class="appt-item-datetime">${dateStr} · ${timeStr}</div>
        <div class="appt-item-doctor">${escapeHtml(a.doctor_name)}${a.doctor_specialty ? " · " + escapeHtml(a.doctor_specialty) : ""}</div>
        <div class="appt-item-clinic">${escapeHtml(a.clinic_name || "—")}</div>
        <div class="appt-item-footer">
          <span class="appt-status-badge appt-status-${a.status}">${statusLabel[a.status] || a.status}</span>
          <span class="appt-duration">${a.duration_min} min</span>
        </div>
      </div>`;
    }).join("");
  } catch {
    body.innerHTML = '<div class="panel-empty" style="color:#f28b82">No se pudieron cargar las citas.</div>';
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
