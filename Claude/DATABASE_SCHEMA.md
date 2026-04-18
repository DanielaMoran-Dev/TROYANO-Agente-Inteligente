# Esquema de Base de Datos — MongoDB Atlas
> Plataforma médica de conexión paciente-doctor
> Documento de referencia para desarrollo e integración

---

## Resumen de colecciones

| Colección | Propósito | Notas |
|---|---|---|
| `users` | Pacientes registrados | Registro obligatorio |
| `doctors` | Médicos de la plataforma | Con y sin red (`is_network`) |
| `clinics` | Establecimientos CLUES vectorizados | Dataset abierto IMSS/SSA |
| `gemini_sessions` | Historial de triaje con IA | Por sesión de consulta |
| `conversations` | Chat en tiempo real paciente ↔ doctor | Solo doctores `is_network: true` |
| `appointments` | Citas agendadas | Vinculadas al calendario del doctor |

---

## Relaciones entre colecciones

```
users ──────────────────────────────────────┐
  │                                         │
  ├──(1:N)──► gemini_sessions               │
  ├──(1:N)──► conversations                 │
  └──(1:N)──► appointments                  │
                                            │
doctors ────────────────────────────────────┤
  │                                         │
  ├──(1:N)──► conversations                 │
  ├──(1:N)──► appointments                  │
  └──(1:1)──► clinics (si is_network=true)  │
                                            │
conversations ──(1:N)──► appointments ──────┘
```

**Reglas de negocio importantes:**
- Un paciente (`user`) no necesita doctor asignado para iniciar una consulta con IA.
- Solo los doctores con `is_network: true` pueden iniciar `conversations` y `appointments`.
- Una `clinic` puede existir sin `doctor_id` (establecimientos CLUES sin doctor en red).
- `gemini_sessions` son independientes — no requieren doctor.

---

## Colección: `users`

Pacientes registrados en la plataforma. El registro es obligatorio.

```json
{
  "_id": "ObjectId",
  "name": "Carlos",
  "last_name": "Ramírez Torres",
  "email": "carlos@email.com",
  "password_hash": "bcrypt_hash",
  "age": 34,
  "phone": "5512345678",
  "coords": {
    "lat": 19.4326,
    "lng": -99.1332
  },
  "insurance": "imss",
  "medical_history": {
    "free_text": "Operado del apéndice en 2018, fumador ocasional.",
    "conditions": ["hipertensión", "diabetes_tipo_2"],
    "allergies": ["penicilina", "ibuprofeno"],
    "medications": ["metformina 500mg", "losartán 50mg"],
    "blood_type": "O+"
  },
  "is_active": true,
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `_id` | ObjectId | Sí | Auto-generado por MongoDB |
| `email` | string | Sí | Único — índice único |
| `password_hash` | string | Sí | Bcrypt, nunca texto plano |
| `coords` | object | No | Última ubicación conocida |
| `insurance` | string | Sí | `imss`, `issste`, `seguro_popular`, `ninguno` |
| `medical_history.free_text` | string | No | Texto libre del paciente |
| `medical_history.conditions` | array | No | Enfermedades crónicas estructuradas |
| `medical_history.allergies` | array | No | Alergias a medicamentos/sustancias |
| `medical_history.medications` | array | No | Medicamentos actuales |
| `medical_history.blood_type` | string | No | `A+`, `A-`, `B+`, `B-`, `O+`, `O-`, `AB+`, `AB-` |

**Índices:**
```python
await db.users.create_index([("email", 1)], unique=True)
await db.users.create_index([("is_active", 1)])
```

---

## Colección: `doctors`

Médicos registrados. Solo los `is_network: true` tienen acceso a chat y citas.

```json
{
  "_id": "ObjectId",
  "name": "Alejandro",
  "last_name": "Vega Morales",
  "email": "dr.vega@email.com",
  "password_hash": "bcrypt_hash",
  "phone": "5598765432",
  "license_number": "12345678",
  "specialty": "cardiología",
  "price_level": 2,
  "insurances": ["imss", "issste", "ninguno"],
  "location": {
    "address": "Orizaba 92, Roma Norte, CDMX",
    "lat": 19.4187,
    "lng": -99.1624,
    "maps_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"
  },
  "schedule": {
    "monday":    { "open": "09:00", "close": "18:00" },
    "tuesday":   { "open": "09:00", "close": "18:00" },
    "wednesday": { "open": "09:00", "close": "14:00" },
    "thursday":  { "open": "09:00", "close": "18:00" },
    "friday":    { "open": "09:00", "close": "15:00" },
    "saturday":  null,
    "sunday":    null
  },
  "calendar": {
    "provider": "google",
    "access_token": "encrypted_fernet",
    "refresh_token": "encrypted_fernet",
    "calendar_id": "string"
  },
  "is_active": true,
  "is_network": true,
  "subscription_expires": "ISODate",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `license_number` | string | Sí | Único — cédula profesional |
| `specialty` | string | Sí | Especialidad médica |
| `price_level` | int | Sí | `1`=público, `2`=privado_bajo, `3`=premium |
| `insurances` | array | Sí | Seguros que acepta |
| `location.maps_place_id` | string | No | Google Maps Place ID para vincular al mapa |
| `calendar.provider` | string | No | `google`, `outlook`, `apple` |
| `calendar.access_token` | string | No | Encriptado con Fernet — nunca texto plano |
| `is_network` | bool | Sí | `true` = suscripción activa, puede chatear y agendar |
| `subscription_expires` | ISODate | No | Nulo si no está en red |

**Valores válidos para `specialty`:**
`cardiología`, `neurología`, `medicina_general`, `pediatría`, `ginecología`, `traumatología`, `dermatología`, `oftalmología`, `otorrinolaringología`, `gastroenterología`, `neumología`, `urología`, `nefrología`, `psiquiatría`, `endocrinología`

**Índices:**
```python
await db.doctors.create_index([("email", 1)], unique=True)
await db.doctors.create_index([("license_number", 1)], unique=True)
await db.doctors.create_index([("specialty", 1)])
await db.doctors.create_index([("is_network", 1)])
await db.doctors.create_index([("insurances", 1)])
await db.doctors.create_index([("location.lat", 1), ("location.lng", 1)])
```

---

## Colección: `clinics`

Establecimientos del dataset CLUES (abierto, SSA México), vectorizados con Gemini Embeddings para búsqueda semántica. Un doctor en red puede estar vinculado a una clínica.

```json
{
  "_id": "ObjectId",
  "clues_id": "DFDF000001",
  "name": "Centro de Salud Urbano Dr. José Castro Villagrana",
  "type": "Centro de Salud",
  "unit_type": "general",
  "specialty": "medicina_general",
  "services": ["consulta_general", "urgencias_menores", "laboratorio"],
  "insurances": ["seguro_popular", "imss"],
  "price_level": 1,
  "state": "Ciudad de México",
  "municipality": "Benito Juárez",
  "address": "Av. Insurgentes Sur 300, CDMX",
  "lat": 19.4100,
  "lng": -99.1650,
  "phone": "55-1234-5678",
  "doctor_id": null,
  "embedding": [0.123, -0.456, "...768 valores..."],
  "embedding_text": "medicina_general general consulta urgencias menores laboratorio benito juárez",
  "indexed_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `clues_id` | string | Sí | ID único del catálogo CLUES |
| `unit_type` | string | Sí | `general`, `especialidad`, `urgencias`, `hospital` |
| `price_level` | int | Sí | `1`=público/gratuito, `2`=bajo costo, `3`=privado |
| `doctor_id` | ObjectId | No | Nulo si no hay doctor en red vinculado |
| `embedding` | array[float] | Sí | 768 dimensiones — Gemini `embedding-exp-03-07` |
| `embedding_text` | string | Sí | Texto fuente del embedding (para re-indexar) |

**Índice Vector Search (configurar en Atlas UI):**
```json
{
  "name": "clinics_vector_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "embedding",
        "numDimensions": 768,
        "similarity": "cosine"
      }
    ]
  }
}
```

**Índices adicionales:**
```python
await db.clinics.create_index([("clues_id", 1)], unique=True)
await db.clinics.create_index([("insurances", 1)])
await db.clinics.create_index([("price_level", 1)])
await db.clinics.create_index([("specialty", 1)])
await db.clinics.create_index([("state", 1), ("municipality", 1)])
await db.clinics.create_index([("lat", 1), ("lng", 1)])
```

---

## Colección: `gemini_sessions`

Historial de cada consulta de triaje con la IA. Una por cada vez que un usuario describe síntomas.

```json
{
  "_id": "ObjectId",
  "session_id": "uuid-v4",
  "user_id": "ObjectId",
  "symptoms": "me duele el pecho desde hace 20 minutos y me falta el aire",
  "triage": {
    "urgency_level": "critical",
    "unit_type": "urgencias",
    "specialty": "cardiología",
    "clinical_summary": "Paciente refiere dolor torácico de 20 min con disnea. Posible origen cardíaco.",
    "reasoning": "Síntomas compatibles con síndrome coronario agudo.",
    "red_flags": ["dolor_torácico", "disnea"]
  },
  "messages": [
    {
      "role": "user",
      "text": "me duele el pecho desde hace 20 minutos",
      "timestamp": "ISODate"
    },
    {
      "role": "gemini",
      "text": "Entiendo. ¿El dolor irradia hacia el brazo o la mandíbula?",
      "timestamp": "ISODate"
    }
  ],
  "created_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `session_id` | string | Sí | UUID v4 — referencia cruzada con otras colecciones |
| `user_id` | ObjectId | Sí | Ref → `users._id` |
| `triage` | object | No | Nulo si el triaje no completó |
| `triage.urgency_level` | string | Sí | `low`, `medium`, `critical` |
| `triage.unit_type` | string | Sí | `urgencias`, `general`, `especialista` |
| `messages` | array | Sí | Historial del chat con Gemini |

**Índices:**
```python
await db.gemini_sessions.create_index([("user_id", 1)])
await db.gemini_sessions.create_index([("session_id", 1)], unique=True)
await db.gemini_sessions.create_index([("created_at", -1)])
```

---

## Colección: `conversations`

Chat en tiempo real entre paciente y doctor vía WebSocket. Solo se crea si el doctor es `is_network: true`.

```json
{
  "_id": "ObjectId",
  "conversation_id": "uuid-v4",
  "user_id": "ObjectId",
  "doctor_id": "ObjectId",
  "clinic_id": "DFDF000001",
  "session_id": "uuid-v4",
  "urgency_level": "critical",
  "clinical_summary": "Paciente refiere dolor torácico de 20 min con disnea.",
  "messages": [
    {
      "sender": "system",
      "text": "PERFIL CLÍNICO: Paciente masculino, 34 años. Dolor torácico con disnea. Urgency: critical.",
      "timestamp": "ISODate"
    },
    {
      "sender": "user",
      "text": "Hola doctor, me sigue doliendo",
      "timestamp": "ISODate"
    },
    {
      "sender": "doctor",
      "text": "¿El dolor irradia al brazo izquierdo?",
      "timestamp": "ISODate"
    }
  ],
  "status": "active",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `conversation_id` | string | Sí | UUID v4 |
| `user_id` | ObjectId | Sí | Ref → `users._id` |
| `doctor_id` | ObjectId | Sí | Ref → `doctors._id` |
| `clinic_id` | string | No | Ref → `clinics.clues_id` |
| `session_id` | string | Sí | Ref → `gemini_sessions.session_id` |
| `status` | string | Sí | `active`, `closed` |
| `messages[].sender` | string | Sí | `system`, `user`, `doctor` |

**Notas de implementación:**
- El primer mensaje siempre es del `sender: "system"` con el perfil clínico del triaje.
- Los mensajes nuevos se agregan con `$push` en MongoDB (no reemplaza el array completo).
- Redis Pub/Sub maneja la entrega en tiempo real; MongoDB es la fuente de verdad.

**Índices:**
```python
await db.conversations.create_index([("user_id", 1)])
await db.conversations.create_index([("doctor_id", 1)])
await db.conversations.create_index([("conversation_id", 1)], unique=True)
await db.conversations.create_index([("status", 1)])
await db.conversations.create_index([("created_at", -1)])
```

---

## Colección: `appointments`

Citas agendadas, vinculadas al calendario externo del doctor (Google, Outlook o Apple).

```json
{
  "_id": "ObjectId",
  "conversation_id": "uuid-v4",
  "user_id": "ObjectId",
  "doctor_id": "ObjectId",
  "clinic_id": "DFDF000001",
  "scheduled_at": "ISODate",
  "duration_min": 30,
  "status": "confirmed",
  "calendar_event_id": "google_event_abc123",
  "notes": "Primera consulta por dolor torácico. Paciente con antecedente de hipertensión.",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

**Campos clave:**

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `conversation_id` | string | Sí | Ref → `conversations.conversation_id` |
| `user_id` | ObjectId | Sí | Ref → `users._id` |
| `doctor_id` | ObjectId | Sí | Ref → `doctors._id` |
| `scheduled_at` | ISODate | Sí | Fecha y hora de la cita (UTC) |
| `duration_min` | int | Sí | Duración en minutos (default: 30) |
| `status` | string | Sí | `pending`, `confirmed`, `cancelled`, `completed` |
| `calendar_event_id` | string | No | ID del evento en el calendario externo del doctor |

**Flujo de estados:**
```
pending → confirmed → completed
        ↘ cancelled
```

**Índices:**
```python
await db.appointments.create_index([("user_id", 1)])
await db.appointments.create_index([("doctor_id", 1)])
await db.appointments.create_index([("status", 1)])
await db.appointments.create_index([("scheduled_at", 1)])
await db.appointments.create_index([("doctor_id", 1), ("scheduled_at", 1)])
```

---

## Seguridad y consideraciones

### Datos sensibles
- `password_hash` — nunca texto plano. Usar `bcrypt` con salt factor ≥ 12.
- `calendar.access_token` y `calendar.refresh_token` — encriptados con `cryptography.fernet` antes de guardar en MongoDB.
- `medical_history` — acceso restringido. Solo el paciente y su doctor en conversación activa pueden leerlo.

### Privacidad del paciente
- Los síntomas se ligan a `user_id` (registro obligatorio en esta versión).
- Las sesiones de Gemini expiran en Redis a los 60 minutos; la persistencia permanente está en MongoDB.

### Campos que NUNCA deben exponerse en la API
- `password_hash`
- `calendar.access_token`
- `calendar.refresh_token`
- `medical_history` (excepto al propio usuario y su doctor activo)

---

## Variables de entorno requeridas

```env
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/
MONGO_DB_NAME=healthapp
```

---

## Inicialización completa — script Python

```python
# scripts/init_db.py
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def init():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME", "healthapp")]

    # users
    await db.users.create_index([("email", 1)], unique=True)
    await db.users.create_index([("is_active", 1)])

    # doctors
    await db.doctors.create_index([("email", 1)], unique=True)
    await db.doctors.create_index([("license_number", 1)], unique=True)
    await db.doctors.create_index([("specialty", 1)])
    await db.doctors.create_index([("is_network", 1)])
    await db.doctors.create_index([("insurances", 1)])
    await db.doctors.create_index([("location.lat", 1), ("location.lng", 1)])

    # clinics
    await db.clinics.create_index([("clues_id", 1)], unique=True)
    await db.clinics.create_index([("insurances", 1)])
    await db.clinics.create_index([("price_level", 1)])
    await db.clinics.create_index([("specialty", 1)])
    await db.clinics.create_index([("state", 1), ("municipality", 1)])
    await db.clinics.create_index([("lat", 1), ("lng", 1)])

    # gemini_sessions
    await db.gemini_sessions.create_index([("user_id", 1)])
    await db.gemini_sessions.create_index([("session_id", 1)], unique=True)
    await db.gemini_sessions.create_index([("created_at", -1)])

    # conversations
    await db.conversations.create_index([("user_id", 1)])
    await db.conversations.create_index([("doctor_id", 1)])
    await db.conversations.create_index([("conversation_id", 1)], unique=True)
    await db.conversations.create_index([("status", 1)])
    await db.conversations.create_index([("created_at", -1)])

    # appointments
    await db.appointments.create_index([("user_id", 1)])
    await db.appointments.create_index([("doctor_id", 1)])
    await db.appointments.create_index([("status", 1)])
    await db.appointments.create_index([("scheduled_at", 1)])
    await db.appointments.create_index([("doctor_id", 1), ("scheduled_at", 1)])

    print("Todos los índices creados correctamente.")
    client.close()

if __name__ == "__main__":
    asyncio.run(init())
```

> **Nota:** El índice Vector Search de `clinics` debe crearse manualmente desde la UI de MongoDB Atlas o via Atlas API — no es posible crearlo con Motor/PyMongo.
