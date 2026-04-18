/**
 * MedConnect — Doctor Dashboard
 * Auth guard, patient queue, WebSocket chat, appointments.
 */

const API = "";

// ── Auth guard ─────────────────────────────────────────────────────────────────
const doctorSession = JSON.parse(sessionStorage.getItem("medconnect_doctor") || "null");
if (!doctorSession) {
  window.location.href = "login.html";
}

// ── State ──────────────────────────────────────────────────────────────────────
let isOnline      = false;
let activeWs      = null;
let activePatient = null;
let calWeekStart  = getWeekStart(new Date());   // Monday of displayed week

// ── Calendar appointments (in-memory, persists within session) ─────────────────
let CAL_APPOINTMENTS = [];

// ── Mock data — replace with real API polling once DB is up ────────────────────
const MOCK_QUEUE = [
  {
    id: "sess_001",
    urgency: "critical",
    specialty: "Cardiología",
    summary: "Paciente masculino de 58 años refiere dolor torácico opresivo con irradiación al brazo izquierdo y diaforesis de 30 min de evolución. Posible síndrome coronario agudo.",
    symptoms: "Dolor en el pecho fuerte, me duele el brazo izquierdo, sudo mucho",
    age: "58",
    insurance: "IMSS",
    conversationId: "conv_001",
    arrivedAt: new Date(Date.now() - 4 * 60000),
  },
  {
    id: "sess_002",
    urgency: "medium",
    specialty: "Medicina General",
    summary: "Paciente femenina de 32 años con fiebre de 38.5°C, tos productiva y dolor de garganta de 3 días de evolución. Compatible con infección respiratoria alta.",
    symptoms: "Fiebre, tos con flema, me duele la garganta",
    age: "32",
    insurance: "ISSSTE",
    conversationId: "conv_002",
    arrivedAt: new Date(Date.now() - 12 * 60000),
  },
  {
    id: "sess_003",
    urgency: "low",
    specialty: "Dermatología",
    summary: "Paciente masculino de 24 años con erupciones en piel del torso de 1 semana de evolución, sin fiebre ni otros síntomas sistémicos.",
    symptoms: "Me salieron granos raros en la panza, no me duelen",
    age: "24",
    insurance: "Ninguno",
    conversationId: "conv_003",
    arrivedAt: new Date(Date.now() - 25 * 60000),
  },
];

const MOCK_APPOINTMENTS = [
  {
    id: "appt_001",
    time: "Hoy, 15:30",
    patientLabel: "Paciente #4872",
    specialty: "Cardiología — seguimiento",
    status: "pending",
  },
  {
    id: "appt_002",
    time: "Hoy, 17:00",
    patientLabel: "Paciente #1193",
    specialty: "Medicina General",
    status: "confirmed",
  },
  {
    id: "appt_003",
    time: "Mañana, 09:00",
    patientLabel: "Paciente #3305",
    specialty: "Cardiología — primera vez",
    status: "pending",
  },
];

// ── Seed CAL_APPOINTMENTS from mock list (with real Date objects) ──────────────
(function seedCalAppts() {
  const today    = new Date();
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);

  CAL_APPOINTMENTS = [
    {
      id: "appt_001",
      patient: "Paciente #4872",
      specialty: "Cardiología — seguimiento",
      status: "pending",
      date: new Date(today.getFullYear(), today.getMonth(), today.getDate(), 15, 30),
      duration: 30,
      notes: "",
    },
    {
      id: "appt_002",
      patient: "Paciente #1193",
      specialty: "Medicina General",
      status: "confirmed",
      date: new Date(today.getFullYear(), today.getMonth(), today.getDate(), 17, 0),
      duration: 60,
      notes: "",
    },
    {
      id: "appt_003",
      patient: "Paciente #3305",
      specialty: "Cardiología — primera vez",
      status: "pending",
      date: new Date(tomorrow.getFullYear(), tomorrow.getMonth(), tomorrow.getDate(), 9, 0),
      duration: 60,
      notes: "Primera consulta",
    },
  ];
})();

// ── Boot ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);

function init() {
  renderProfile();
  renderQueue();
  syncAppointmentPanel();   // populates right panel from CAL_APPOINTMENTS
  updateStats();
  setupChatInput();
}

// ── Profile ────────────────────────────────────────────────────────────────────
function renderProfile() {
  const initials = doctorSession.name
    .split(" ")
    .filter(w => /^[A-ZÁÉÍÓÚÑ]/i.test(w) && w.length > 1)
    .slice(0, 2)
    .map(w => w[0].toUpperCase())
    .join("");

  document.getElementById("profile-avatar").textContent    = initials;
  document.getElementById("doc-avatar-chip").textContent   = initials;
  document.getElementById("profile-name").textContent      = doctorSession.name;
  document.getElementById("profile-specialty").textContent = doctorSession.specialty.toUpperCase();
  document.getElementById("doc-breadcrumb").textContent    = `${doctorSession.name} // ${doctorSession.specialty}`;
}

// ── Online toggle ──────────────────────────────────────────────────────────────
function toggleOnline() {
  isOnline = !isOnline;
  document.getElementById("online-switch").checked = isOnline;
  document.getElementById("online-dot").className  = "online-dot" + (isOnline ? " online" : "");
  document.getElementById("online-label").textContent = isOnline ? "EN LÍNEA" : "OFFLINE";

  const hdrStatus = document.getElementById("hdr-online-status");
  hdrStatus.className = "header-online-status " + (isOnline ? "is-online" : "is-offline");
  document.getElementById("hdr-online-text").textContent = isOnline ? "EN LÍNEA" : "OFFLINE";
}

// ── Queue ──────────────────────────────────────────────────────────────────────
function renderQueue() {
  const list  = document.getElementById("queue-list");
  const empty = document.getElementById("queue-empty");

  if (!MOCK_QUEUE.length) {
    empty.style.display = "flex";
    document.getElementById("queue-count").textContent = "0";
    return;
  }

  empty.style.display = "none";
  document.getElementById("queue-count").textContent = MOCK_QUEUE.length;

  MOCK_QUEUE.forEach(p => {
    const item = document.createElement("div");
    item.className = `queue-item urgency-${p.urgency}`;
    item.id = `qitem-${p.id}`;

    const urgencyLabels = { critical: "CRÍTICO", medium: "MODERADO", low: "LEVE" };
    const ago = formatAgo(p.arrivedAt);

    item.innerHTML = `
      <div class="queue-item-top">
        <div class="urgency-dot dot-${p.urgency}"></div>
        <span class="queue-patient-id">Paciente · ${p.id.slice(-3)}</span>
        <span class="queue-time">${ago}</span>
      </div>
      <div class="queue-summary">${escapeHtml(p.summary)}</div>
      <div class="queue-badges">
        <span class="q-badge q-badge-${p.urgency}">${urgencyLabels[p.urgency]}</span>
        <span class="q-badge q-badge-specialty">${escapeHtml(p.specialty)}</span>
      </div>
    `;
    item.addEventListener("click", () => selectPatient(p));
    list.appendChild(item);
  });
}

function selectPatient(patient) {
  // Update active highlight
  document.querySelectorAll(".queue-item").forEach(el => el.classList.remove("active"));
  const item = document.getElementById(`qitem-${patient.id}`);
  if (item) item.classList.add("active");

  activePatient = patient;

  // Show clinical brief
  document.getElementById("no-patient-msg").classList.add("hidden");
  document.getElementById("clinical-brief").classList.remove("hidden");
  document.getElementById("doc-chat-messages").classList.remove("hidden");
  document.getElementById("doc-chat-input-row").classList.remove("hidden");

  document.getElementById("brief-summary").textContent   = patient.summary;
  document.getElementById("brief-specialty").textContent = patient.specialty;

  const urgencyEl = document.getElementById("brief-urgency");
  const pillClass = { critical: "pill-critical", medium: "pill-medium", low: "pill-low" };
  const urgencyText = { critical: "CRÍTICO", medium: "MODERADO", low: "LEVE" };
  urgencyEl.className = `urgency-pill ${pillClass[patient.urgency]}`;
  urgencyEl.textContent = urgencyText[patient.urgency];

  // Open WebSocket
  openChatWs(patient.conversationId);
}

// ── WebSocket chat ─────────────────────────────────────────────────────────────
function openChatWs(conversationId) {
  if (activeWs) { activeWs.close(); activeWs = null; }

  const msgs = document.getElementById("doc-chat-messages");
  msgs.innerHTML = "";

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  activeWs = new WebSocket(`${wsProto}://${location.host}/ws/chat/${conversationId}`);

  activeWs.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "history") {
        msg.messages.forEach(m => appendDocMsg(m.sender, m.text));
      } else {
        appendDocMsg(msg.sender, msg.text);
      }
    } catch {
      appendDocMsg("sistema", evt.data);
    }
  };

  activeWs.onerror = () => appendDocMsg("sistema", "Error de conexión con el paciente.");
  activeWs.onclose = () => appendDocMsg("sistema", "Chat desconectado.");
}

function appendDocMsg(sender, text) {
  const msgs = document.getElementById("doc-chat-messages");
  const div  = document.createElement("div");
  const isDoctor  = sender === "doctor";
  const isSystem  = sender === "sistema" || sender === "system";

  div.className = `chat-msg ${isSystem ? "system" : isDoctor ? "user" : "bot"}`;
  div.innerHTML = escapeHtml(text);
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function setupChatInput() {
  const input  = document.getElementById("doc-chat-input");
  const sendBtn = document.getElementById("doc-send-btn");
  sendBtn.addEventListener("click", sendDocMessage);
  input.addEventListener("keydown", e => { if (e.key === "Enter") sendDocMessage(); });
}

function sendDocMessage() {
  const input = document.getElementById("doc-chat-input");
  const text  = input.value.trim();
  if (!text || !activeWs) return;
  activeWs.send(JSON.stringify({ sender: "doctor", text }));
  appendDocMsg("doctor", text);
  input.value = "";
}

// ── Appointments ───────────────────────────────────────────────────────────────

// ── Stats ──────────────────────────────────────────────────────────────────────
function updateStats() {
  const critical = MOCK_QUEUE.filter(p => p.urgency === "critical").length;
  const pending  = CAL_APPOINTMENTS.filter(a => a.status === "pending").length;

  document.getElementById("stat-critical").textContent    = critical;
  document.getElementById("stat-pending").textContent     = MOCK_QUEUE.length;
  document.getElementById("stat-completed").textContent   = 3;   // mock
  document.getElementById("stat-appointments").textContent = pending;
}

// ── Auth ───────────────────────────────────────────────────────────────────────
function logout() {
  if (activeWs) activeWs.close();
  sessionStorage.removeItem("medconnect_doctor");
  window.location.href = "login.html";
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function formatAgo(date) {
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1)  return "ahora";
  if (mins < 60) return `${mins}m`;
  return `${Math.round(mins / 60)}h`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

// ══════════════════════════════════════════════════════════════════════════════
// CALENDAR
// ══════════════════════════════════════════════════════════════════════════════

const CAL_START_HOUR = 7;    // 07:00
const CAL_END_HOUR   = 21;   // 21:00
const SLOT_HEIGHT    = 32;   // px per 30-min slot
const DAY_NAMES      = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const MONTHS         = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];

// ── Open / close ───────────────────────────────────────────────────────────────
function openCalendar() {
  document.getElementById("cal-overlay").classList.remove("hidden");
  renderCalendar();
}
function closeCalendar() {
  document.getElementById("cal-overlay").classList.add("hidden");
}

// ── Week navigation ────────────────────────────────────────────────────────────
function calPrevWeek() {
  calWeekStart = new Date(calWeekStart);
  calWeekStart.setDate(calWeekStart.getDate() - 7);
  renderCalendar();
}
function calNextWeek() {
  calWeekStart = new Date(calWeekStart);
  calWeekStart.setDate(calWeekStart.getDate() + 7);
  renderCalendar();
}
function calGoToday() {
  calWeekStart = getWeekStart(new Date());
  renderCalendar();
}

// ── Main render ────────────────────────────────────────────────────────────────
function renderCalendar() {
  const grid   = document.getElementById("cal-grid");
  const title  = document.getElementById("cal-title");
  const today  = new Date();
  const days   = weekDays(calWeekStart);   // 7 Date objects

  // Title
  const firstDay = days[0], lastDay = days[6];
  const sameMonth = firstDay.getMonth() === lastDay.getMonth();
  title.textContent = sameMonth
    ? `${firstDay.getDate()} – ${lastDay.getDate()} de ${MONTHS[firstDay.getMonth()]} ${firstDay.getFullYear()}`
    : `${firstDay.getDate()} ${MONTHS[firstDay.getMonth()]} – ${lastDay.getDate()} ${MONTHS[lastDay.getMonth()]} ${lastDay.getFullYear()}`;

  // Build grid HTML
  const totalSlots = (CAL_END_HOUR - CAL_START_HOUR) * 2;   // 30-min slots
  let html = "";

  // ── Row 1: corner + day headers ──
  html += `<div class="cal-corner"></div>`;
  days.forEach((d, i) => {
    const isToday = sameDay(d, today);
    html += `<div class="cal-day-hdr${isToday ? " today" : ""}">
      <div class="cal-day-name">${DAY_NAMES[i]}</div>
      <div class="cal-day-num">${d.getDate()}</div>
    </div>`;
  });

  // ── Time rows ──
  for (let s = 0; s < totalSlots; s++) {
    const hour   = CAL_START_HOUR + Math.floor(s / 2);
    const minute = s % 2 === 0 ? "00" : "30";
    const isHour = s % 2 === 0;

    // Time label (only on full hours)
    html += `<div class="cal-time-label" style="height:${SLOT_HEIGHT}px">${isHour ? `${String(hour).padStart(2,"0")}:00` : ""}</div>`;

    // 7 slot cells
    days.forEach((d, di) => {
      const slotDate = new Date(d.getFullYear(), d.getMonth(), d.getDate(), hour, +minute);
      const iso = slotDate.toISOString();
      html += `<div class="cal-slot" style="height:${SLOT_HEIGHT}px" data-iso="${iso}" data-col="${di}" data-slot="${s}" onclick="handleSlotClick(event, '${iso}')"></div>`;
    });
  }

  grid.innerHTML = html;

  // ── Draw appointment blocks ──
  const appts = CAL_APPOINTMENTS.filter(a => {
    const d = a.date;
    return d >= days[0] && d < new Date(days[6].getFullYear(), days[6].getMonth(), days[6].getDate() + 1);
  });

  appts.forEach(a => renderEventBlock(a, days));

  // ── Draw "now" line ──
  if (today >= days[0] && today <= new Date(days[6].getFullYear(), days[6].getMonth(), days[6].getDate() + 1)) {
    const colIdx = days.findIndex(d => sameDay(d, today));
    if (colIdx >= 0) drawNowLine(colIdx, today);
  }
}

function renderEventBlock(appt, days) {
  const colIdx = days.findIndex(d => sameDay(d, appt.date));
  if (colIdx < 0) return;

  const startMins = (appt.date.getHours() - CAL_START_HOUR) * 60 + appt.date.getMinutes();
  const topPx     = (startMins / 30) * SLOT_HEIGHT;
  const heightPx  = Math.max((appt.duration / 30) * SLOT_HEIGHT - 2, SLOT_HEIGHT - 2);

  // Find the slot cell for this column to position relative to
  const grid = document.getElementById("cal-grid");
  // Each row = 1 time label + 7 slots → colIdx offset = colIdx+1 in each row
  // We use absolute positioning inside the slot cell for the first slot of the event
  const slotIndex = Math.round((startMins / 30));
  const slotSelector = `[data-col="${colIdx}"][data-slot="${slotIndex}"]`;
  const slotEl = grid.querySelector(slotSelector);
  if (!slotEl) return;

  const ev = document.createElement("div");
  ev.className = `cal-event ${appt.status === "confirmed" ? "ev-confirmed" : "ev-pending"}`;
  ev.style.cssText = `top:0; height:${heightPx}px; z-index:3;`;
  ev.title = `${appt.patient} — ${appt.specialty}`;
  ev.innerHTML = `
    <div class="cal-event-title">${escapeHtml(appt.patient)}</div>
    <div class="cal-event-sub">${escapeHtml(appt.specialty)}</div>
  `;
  ev.addEventListener("click", e => { e.stopPropagation(); openEditApptForm(appt); });
  slotEl.appendChild(ev);
}

function drawNowLine(colIdx, now) {
  const grid = document.getElementById("cal-grid");
  const mins  = (now.getHours() - CAL_START_HOUR) * 60 + now.getMinutes();
  const slotIndex = Math.floor(mins / 30);
  const offsetPx  = ((mins % 30) / 30) * SLOT_HEIGHT;

  const slotEl = grid.querySelector(`[data-col="${colIdx}"][data-slot="${slotIndex}"]`);
  if (!slotEl) return;
  const line = document.createElement("div");
  line.className = "cal-now-line";
  line.style.top = `${offsetPx}px`;
  slotEl.appendChild(line);
}

// ── Slot click → new appointment with pre-filled date/time ────────────────────
function handleSlotClick(e, iso) {
  e.stopPropagation();
  openNewApptForm(new Date(iso), null);
}

// ── New appointment form ───────────────────────────────────────────────────────
function openNewApptForm(date, prefillAppt) {
  document.getElementById("af-error").textContent = "";
  document.getElementById("af-patient").value   = prefillAppt?.patient   || "";
  document.getElementById("af-specialty").value = prefillAppt?.specialty || doctorSession.specialty;
  document.getElementById("af-notes").value     = prefillAppt?.notes     || "";
  document.getElementById("af-duration").value  = prefillAppt?.duration  || 60;

  const d = date || new Date();
  document.getElementById("af-date").value = toDateInput(d);
  document.getElementById("af-time").value = `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;

  document.getElementById("appt-form-overlay").classList.remove("hidden");
  document.getElementById("af-patient").focus();
}

function openEditApptForm(appt) {
  openNewApptForm(appt.date, appt);
  // Tag the form so save knows this is an edit
  document.getElementById("appt-form-overlay").dataset.editId = appt.id;
}

function closeNewApptForm() {
  document.getElementById("appt-form-overlay").classList.add("hidden");
  delete document.getElementById("appt-form-overlay").dataset.editId;
}

function saveNewAppt() {
  const patient   = document.getElementById("af-patient").value.trim();
  const specialty = document.getElementById("af-specialty").value.trim();
  const dateStr   = document.getElementById("af-date").value;
  const timeStr   = document.getElementById("af-time").value;
  const duration  = parseInt(document.getElementById("af-duration").value, 10);
  const notes     = document.getElementById("af-notes").value.trim();
  const errEl     = document.getElementById("af-error");

  if (!patient || !specialty || !dateStr || !timeStr) {
    errEl.textContent = "Paciente, especialidad, fecha y hora son obligatorios.";
    return;
  }

  const [y, m, dd] = dateStr.split("-").map(Number);
  const [h, min]   = timeStr.split(":").map(Number);
  const date       = new Date(y, m - 1, dd, h, min);

  const overlay = document.getElementById("appt-form-overlay");
  const editId  = overlay.dataset.editId;

  if (editId) {
    // Edit existing
    const idx = CAL_APPOINTMENTS.findIndex(a => a.id === editId);
    if (idx >= 0) {
      CAL_APPOINTMENTS[idx] = { ...CAL_APPOINTMENTS[idx], patient, specialty, date, duration, notes };
    }
  } else {
    // New
    CAL_APPOINTMENTS.push({
      id:        `appt_${Date.now()}`,
      patient,
      specialty,
      date,
      duration,
      notes,
      status: "pending",
    });
  }

  closeNewApptForm();
  renderCalendar();
  syncAppointmentPanel();
}

// Refresh the right-panel appointment list from CAL_APPOINTMENTS
function syncAppointmentPanel() {
  const list = document.getElementById("appointments-list");
  list.innerHTML = "";
  document.getElementById("appt-count").textContent = CAL_APPOINTMENTS.length;

  CAL_APPOINTMENTS.sort((a, b) => a.date - b.date).forEach(appt => {
    const el = document.createElement("div");
    el.className = "appointment-item";
    el.id = `appt-${appt.id}`;

    const statusClass = appt.status === "confirmed" ? "appt-confirmed" : "appt-pending";
    const statusText  = appt.status === "confirmed" ? "CONFIRMADA" : "PENDIENTE";
    const timeLabel   = formatApptTime(appt.date);

    el.innerHTML = `
      <div class="appt-top">
        <span class="appt-time">${escapeHtml(timeLabel)}</span>
        <span class="appt-status ${statusClass}">${statusText}</span>
      </div>
      <div class="appt-patient">${escapeHtml(appt.patient)}</div>
      <div class="appt-specialty">${escapeHtml(appt.specialty)}</div>
      ${appt.status === "pending" ? `
      <div class="appt-actions">
        <button class="appt-btn confirm" onclick="confirmApptById('${appt.id}')">Confirmar</button>
        <button class="appt-btn cancel"  onclick="cancelApptById('${appt.id}')">Cancelar</button>
      </div>` : ""}
    `;
    list.appendChild(el);
  });

  updateStats();
}

function confirmApptById(id) {
  const appt = CAL_APPOINTMENTS.find(a => a.id === id);
  if (!appt) return;
  appt.status = "confirmed";
  syncAppointmentPanel();
  if (document.getElementById("cal-overlay").classList.contains("hidden") === false) {
    renderCalendar();
  }
}

function cancelApptById(id) {
  const idx = CAL_APPOINTMENTS.findIndex(a => a.id === id);
  if (idx === -1) return;
  CAL_APPOINTMENTS.splice(idx, 1);
  syncAppointmentPanel();
  if (!document.getElementById("cal-overlay").classList.contains("hidden")) {
    renderCalendar();
  }
}

// ── Date helpers ───────────────────────────────────────────────────────────────
function getWeekStart(date) {
  const d = new Date(date);
  const day = d.getDay();                          // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;          // offset to Monday
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function weekDays(monday) {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear()
      && a.getMonth()    === b.getMonth()
      && a.getDate()     === b.getDate();
}

function toDateInput(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}

function formatApptTime(date) {
  const today    = new Date();
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const timeStr  = `${String(date.getHours()).padStart(2,"0")}:${String(date.getMinutes()).padStart(2,"0")}`;
  if (sameDay(date, today))    return `Hoy, ${timeStr}`;
  if (sameDay(date, tomorrow)) return `Mañana, ${timeStr}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]}, ${timeStr}`;
}
