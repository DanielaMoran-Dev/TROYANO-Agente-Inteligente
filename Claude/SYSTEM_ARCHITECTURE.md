# Arquitectura del Sistema
> Plataforma médica de conexión paciente-doctor
> Stack completo, infraestructura, datos y flujos

---

## Visión general del sistema

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│          React + Gemini Chat SDK + Google Maps JS           │
└─────────────────┬───────────────────────────────────────────┘
                  │ HTTP / WebSocket
┌─────────────────▼───────────────────────────────────────────┐
│                        BACKEND                              │
│                    FastAPI (Python)                         │
│                                                             │
│   /consult    /doctors    /ws/chat    /appointments         │
│   /maps       /calendar                                     │
└──────┬─────────────┬──────────────┬────────────────┬────────┘
       │             │              │                │
┌──────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐ ┌──────▼──────┐
│  Gemini API │ │ MongoDB  │ │   Redis    │ │ Google Maps │
│  Pro/Flash  │ │  Atlas   │ │            │ │  Platform   │
│  Embeddings │ │ VectorDB │ │  Pub/Sub   │ │             │
└─────────────┘ └──────────┘ └────────────┘ └─────────────┘
                                                      │
                              ┌───────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Calendar APIs     │
                    │  Google / Outlook  │
                    │  Apple CalDAV      │
                    └────────────────────┘
```

---

## Stack tecnológico

### Frontend
| Tecnología | Uso |
|---|---|
| React | Framework principal |
| Gemini Chat SDK | Streaming de respuestas del triaje en tiempo real |
| Google Maps JavaScript API | Visualización de mapa, pins, rutas |
| WebSocket nativo | Chat doctor-paciente |

### Backend
| Tecnología | Uso |
|---|---|
| FastAPI (Python) | Framework API, async nativo |
| Uvicorn | ASGI server |
| Pydantic v2 | Validación de schemas input/output |
| Motor | Driver async de MongoDB |
| Redis (aioredis) | Caché, sesiones, broker de mensajes |
| python-jose | JWT para OAuth de calendarios |
| caldav | Integración Apple Calendar |

### IA
| Tecnología | Uso |
|---|---|
| Gemini 2.0 Pro | Triaje y recomendación — razonamiento complejo |
| Gemini 2.0 Flash | Chat en tiempo real — velocidad |
| Gemini Embeddings (exp-03-07) | Vectorización de clínicas para RAG |

### Datos
| Tecnología | Uso |
|---|---|
| MongoDB Atlas | Base de datos principal |
| MongoDB Vector Search | RAG de clínicas — búsqueda semántica |
| CLUES | Dataset abierto de establecimientos de salud México |

### Infraestructura
| Tecnología | Uso |
|---|---|
| Docker | Contenedores de backend y servicios |
| Docker Compose | Orquestación local y despliegue |
| Redis | Caché + broker WebSocket |

---

## Estructura de carpetas

```
proyecto/
├── backend/
│   ├── agents/
│   │   ├── triage_agent.py
│   │   ├── routing_agent.py
│   │   ├── recommendation_agent.py
│   │   └── __init__.py
│   ├── services/
│   │   ├── gemini_service.py       # cliente único Gemini
│   │   ├── mongo_service.py        # cliente Motor async
│   │   ├── maps_service.py         # Distance Matrix, Geocoding, Directions
│   │   ├── calendar_service.py     # Google, Outlook, Apple
│   │   └── redis_service.py        # caché y pub/sub
│   ├── routers/
│   │   ├── patient.py              # POST /consult y flujo principal
│   │   ├── doctor.py               # registro y perfil de doctor
│   │   ├── chat.py                 # WebSocket /ws/chat
│   │   └── appointments.py         # gestión de citas
│   ├── schemas/
│   │   ├── patient.py
│   │   ├── doctor.py
│   │   └── recommendation.py
│   ├── wiki/
│   │   ├── triage_wiki.md
│   │   └── recommendation_wiki.md
│   ├── scripts/
│   │   └── ingest_clues.py         # ingesta CLUES → MongoDB + embeddings
│   ├── main.py
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ConsultForm.jsx     # síntomas + seguro + presupuesto
│   │   │   ├── MapView.jsx         # mapa con pins de recomendaciones
│   │   │   ├── RecommendationCard.jsx
│   │   │   ├── ChatWindow.jsx      # messenger doctor-paciente
│   │   │   └── DoctorDashboard.jsx
│   │   ├── services/
│   │   │   ├── api.js
│   │   │   └── websocket.js
│   │   └── App.jsx
│   └── package.json
└── docker-compose.yml
```

---

## Base de datos — MongoDB Atlas

### Colección: `patients`
```json
{
    "_id": "ObjectId",
    "session_id": "uuid-string",
    "symptoms": "me duele el pecho desde hace 20 minutos",
    "insurance": "imss",
    "budget_level": "$",
    "coords": { "lat": 19.43, "lng": -99.13 },
    "triage": { },
    "recommendation_ids": ["clinic_123", "clinic_456"],
    "selected_clinic_id": "clinic_123",
    "created_at": "ISODate"
}
```

### Colección: `doctors`
```json
{
    "_id": "ObjectId",
    "name": "Dr. Alejandro Vega",
    "specialty": "cardiología",
    "license_number": "12345678",
    "insurances": ["imss", "issste", "ninguno"],
    "price_level": 2,
    "location": {
        "address": "Orizaba 92, Roma Norte, CDMX",
        "lat": 19.4187,
        "lng": -99.1624
    },
    "calendar": {
        "provider": "google | outlook | apple",
        "access_token": "encrypted",
        "refresh_token": "encrypted",
        "calendar_id": "string"
    },
    "is_active": true,
    "is_network": true,
    "created_at": "ISODate",
    "subscription_expires": "ISODate"
}
```

### Colección: `clinics` (CLUES vectorizado)
```json
{
    "_id": "ObjectId",
    "clues_id": "QROO000000",
    "name": "Centro de Salud Urbano",
    "type": "Centro de Salud",
    "unit_type": "general",
    "specialty": "medicina_general",
    "services": ["consulta_general", "urgencias_menores", "laboratorio"],
    "insurances": ["seguro_popular", "imss"],
    "price_level": 1,
    "state": "Querétaro",
    "municipality": "Querétaro",
    "address": "Av. Constituyentes 123",
    "lat": 20.5888,
    "lng": -100.3899,
    "phone": "442-123-4567",
    "doctor_id": null,
    "embedding": [0.123, -0.456, ...],
    "embedding_text": "medicina_general general consulta urgencias menores laboratorio",
    "indexed_at": "ISODate"
}
```

**Índice Vector Search en Atlas:**
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

**Índices adicionales en `clinics`:**
```python
await clinics.create_index([("insurances", 1)])
await clinics.create_index([("price_level", 1)])
await clinics.create_index([("state", 1), ("municipality", 1)])
await clinics.create_index([("lat", 1), ("lng", 1)])
```

### Colección: `conversations`
```json
{
    "_id": "ObjectId",
    "conversation_id": "uuid-string",
    "patient_session_id": "uuid-string",
    "doctor_id": "ObjectId",
    "clinic_id": "clues_123",
    "clinical_summary": "Paciente refiere dolor torácico...",
    "urgency_level": "critical",
    "messages": [
        {
            "sender": "system",
            "text": "PERFIL CLÍNICO: Paciente refiere dolor torácico...",
            "timestamp": "ISODate"
        },
        {
            "sender": "patient",
            "text": "Hola doctor, me sigue doliendo",
            "timestamp": "ISODate"
        },
        {
            "sender": "doctor",
            "text": "¿El dolor irradia al brazo izquierdo?",
            "timestamp": "ISODate"
        }
    ],
    "status": "active | closed",
    "created_at": "ISODate"
}
```

### Colección: `appointments`
```json
{
    "_id": "ObjectId",
    "conversation_id": "uuid-string",
    "patient_session_id": "uuid-string",
    "doctor_id": "ObjectId",
    "clinic_id": "string",
    "scheduled_at": "ISODate",
    "duration_min": 30,
    "status": "pending | confirmed | cancelled | completed",
    "calendar_event_id": "google_event_id_string",
    "notes": "Primera consulta por dolor torácico",
    "created_at": "ISODate",
    "updated_at": "ISODate"
}
```

---

## Endpoints API

### Paciente
```
POST   /consult
       Body: { session_id, symptoms, coords, insurance, budget_level }
       Response: RecommendationResult

GET    /maps/search?q={query}
       Response: { name, lat, lng, formatted_address }

POST   /maps/routes
       Body: { origin, destinations }
       Response: { travel_times }

GET    /maps/key
       Response: { key }
```

### Doctor
```
POST   /doctors/register
       Body: { name, specialty, license_number, insurances, price_level, location }
       Response: { doctor_id }

GET    /doctors/profile
       Headers: Authorization: Bearer {token}
       Response: DoctorProfile

PUT    /doctors/calendar
       Body: { provider, auth_code }
       Response: { connected: true }

GET    /doctors/appointments
       Response: lista de citas del doctor

PUT    /doctors/status
       Body: { is_active: bool }
       Response: { updated: true }
```

### Chat
```
WS     /ws/chat/{conversation_id}
       Protocolo: JSON messages
       { "sender": "patient|doctor", "text": "...", "timestamp": "..." }

POST   /conversations
       Body: { patient_session_id, doctor_id, clinic_id, clinical_summary }
       Response: { conversation_id }

GET    /conversations/{conversation_id}
       Response: historial completo
```

### Citas
```
POST   /appointments
       Body: { conversation_id, doctor_id, scheduled_at, duration_min }
       Response: { appointment_id, calendar_event_id }

PUT    /appointments/{id}
       Body: { status: "confirmed | cancelled" }
       Response: { updated: true }

GET    /appointments/{id}
       Response: AppointmentDetail
```

---

## Flujo completo del sistema

### Flujo del paciente

```
1. Paciente abre la app
   → Geolocalización automática (browser API)
   → Se genera session_id (UUID)

2. Paciente describe síntomas
   → Campo de texto libre
   → Selecciona seguro (IMSS / ISSSTE / Seguro Popular / Ninguno)
   → Selecciona presupuesto ($ / $$ / $$$)

3. POST /consult
   → Agente de Triaje → Agente de Ruteo → Agente de Recomendación
   → Streaming de respuesta via Gemini Chat SDK (el usuario ve progreso)

4. Mapa se renderiza con top 3 pins
   → Pin verde: dentro de la red (chat disponible)
   → Pin azul: fuera de la red (solo info)
   → Cards con justificación, tiempo de traslado, contacto

5a. Si elige opción dentro de la red:
    → Botón "Contactar doctor"
    → Se crea conversation en MongoDB con clinical_summary
    → WebSocket abre chat
    → Doctor recibe notificación con perfil clínico
    → Paciente puede agendar cita desde el chat

5b. Si elige opción fuera de la red:
    → Botón "Ver ruta" → Google Maps Directions
    → Teléfono de contacto visible
    → Sin chat ni agenda
```

### Flujo del doctor

```
1. Doctor se registra en la plataforma
   → Perfil: nombre, especialidad, cédula, seguros, precio, ubicación

2. Doctor conecta su calendario
   → OAuth Google / Microsoft
   → CalDAV Apple
   → Se almacenan tokens encriptados en MongoDB

3. Doctor activa su perfil (is_active: true)
   → Aparece como opción de red en el sistema de recomendación

4. Llega un paciente
   → Notificación push (Firebase Cloud Messaging)
   → Dashboard muestra: clinical_summary + urgency_level + síntomas originales
   → Doctor responde antes de que el paciente escriba su primer mensaje

5. Doctor gestiona cita
   → Propone horario desde la plataforma
   → Se crea evento en su calendario externo via API
   → Paciente recibe confirmación
```

### Flujo del chat en tiempo real

```
Paciente                    Backend                     Doctor
   │                           │                           │
   │── WS connect ────────────►│                           │
   │                           │── Redis subscribe ───────►│
   │                           │   doctor:{id} channel     │
   │                           │                           │
   │── "mensaje" ─────────────►│                           │
   │                           │── save MongoDB ───────────│
   │                           │── Redis publish ──────────│
   │                           │   doctor:{id}             │
   │                           │                           │──► notificación
   │                           │                           │
   │                           │◄── "respuesta" ───────────│
   │                           │── save MongoDB            │
   │                           │── WS send ───────────────►│
   │◄── "respuesta" ───────────│                           │
```

---

## Redis — usos específicos

```python
# services/redis_service.py

# 1. Caché de sesiones activas
await redis.setex(f"session:{session_id}", 3600, json.dumps(triage_result))

# 2. Broker de mensajes del chat
await redis.publish(f"doctor:{doctor_id}", json.dumps(message))
await redis.subscribe(f"patient:{session_id}")

# 3. Rate limiting por session_id (evitar spam al pipeline)
await redis.incr(f"rate:{session_id}")
await redis.expire(f"rate:{session_id}", 60)

# 4. Caché de travel times (Maps es costoso)
cache_key = f"travel:{origin_lat}:{origin_lng}:{dest_lat}:{dest_lng}"
await redis.setex(cache_key, 300, json.dumps(travel_time))
```

---

## Google Maps — APIs utilizadas

### Geocoding API
```python
# Convertir ubicación del usuario a coordenadas
GET https://maps.googleapis.com/maps/api/geocode/json
    ?address={query}&key={API_KEY}
```

### Distance Matrix API
```python
# Tiempos reales de traslado a múltiples destinos en paralelo
GET https://maps.googleapis.com/maps/api/distancematrix/json
    ?origins={lat,lng}
    &destinations={lat1,lng1}|{lat2,lng2}|...
    &mode=driving
    &departure_time=now
    &key={API_KEY}
```

### Directions API
```python
# Ruta detallada una vez que el paciente elige destino
GET https://maps.googleapis.com/maps/api/directions/json
    ?origin={lat,lng}
    &destination={lat,lng}
    &mode=driving
    &key={API_KEY}
```

### Maps JavaScript API (frontend)
```javascript
// Inicializar mapa
const map = new google.maps.Map(document.getElementById("map"), {
    center: userCoords,
    zoom: 14
})

// Pins diferenciados
const networkMarker = new google.maps.Marker({
    position: coords,
    map,
    icon: { url: "/icons/pin-green.svg" }  // en red
})

const externalMarker = new google.maps.Marker({
    position: coords,
    map,
    icon: { url: "/icons/pin-blue.svg" }   // fuera de red
})
```

---

## Calendario — sincronización

### Google Calendar
```python
# services/calendar_service.py
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

async def create_event(doctor_id: str, appointment: dict) -> str:
    doctor = await mongo_service.doctors.find_one({"_id": doctor_id})
    creds = Credentials(token=decrypt(doctor["calendar"]["access_token"]))
    service = build("calendar", "v3", credentials=creds)

    event = {
        "summary": f"Consulta — {appointment['specialty']}",
        "description": appointment["clinical_summary"],
        "start": {"dateTime": appointment["scheduled_at"].isoformat()},
        "end":   {"dateTime": (appointment["scheduled_at"] + timedelta(minutes=30)).isoformat()},
    }

    result = service.events().insert(
        calendarId=doctor["calendar"]["calendar_id"],
        body=event
    ).execute()

    return result["id"]
```

### Microsoft Graph (Outlook)
```python
async def create_outlook_event(doctor_id: str, appointment: dict) -> str:
    token = await get_outlook_token(doctor_id)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject": f"Consulta — {appointment['specialty']}",
                "body": {"content": appointment["clinical_summary"]},
                "start": {"dateTime": appointment["scheduled_at"].isoformat(), "timeZone": "America/Mexico_City"},
                "end":   {"dateTime": end_time.isoformat(), "timeZone": "America/Mexico_City"}
            }
        )
    return r.json()["id"]
```

---

## Ingesta de CLUES — script de vectorización

```python
# scripts/ingest_clues.py
import pandas as pd
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from google import genai

CLUES_CSV = "data/clues.csv"
BATCH_SIZE = 50

async def ingest():
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME", "healthapp")]
    gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    df = pd.read_csv(CLUES_CSV)
    total = len(df)
    print(f"Ingesting {total} CLUES records...")

    for i in range(0, total, BATCH_SIZE):
        batch = df.iloc[i:i+BATCH_SIZE]
        docs = []

        for _, row in batch.iterrows():
            embed_text = f"{row['specialty']} {row['unit_type']} {row['services']} {row['municipality']}"

            # Gemini embedding
            response = await gemini.aio.models.embed_content(
                model="gemini-embedding-exp-03-07",
                contents=embed_text
            )
            embedding = response.embeddings[0].values

            docs.append({
                "clues_id":     row["clues_id"],
                "name":         row["name"],
                "unit_type":    row["unit_type"],
                "specialty":    row["specialty"],
                "services":     row["services"].split("|"),
                "insurances":   row["insurances"].split("|"),
                "price_level":  int(row["price_level"]),
                "state":        row["state"],
                "municipality": row["municipality"],
                "address":      row["address"],
                "lat":          float(row["lat"]),
                "lng":          float(row["lng"]),
                "phone":        row.get("phone", ""),
                "doctor_id":    None,
                "embedding":    embedding,
                "embedding_text": embed_text,
                "indexed_at":   datetime.utcnow()
            })

        await db.clinics.insert_many(docs)
        print(f"  Batch {i//BATCH_SIZE + 1} done — {min(i+BATCH_SIZE, total)}/{total}")

    print("Ingestion complete.")
    await db.clinics.create_index([("insurances", 1)])
    await db.clinics.create_index([("price_level", 1)])
    print("Indexes created.")

if __name__ == "__main__":
    asyncio.run(ingest())
```

---

## Variables de entorno

```env
# Gemini
GEMINI_API_KEY=

# MongoDB Atlas
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=healthapp

# Redis
REDIS_URL=redis://localhost:6379

# Google Maps
GOOGLE_MAPS_API_KEY=

# Google Calendar OAuth2
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

# Microsoft Graph (Outlook)
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_REDIRECT_URI=

# App
SECRET_KEY=                    # para JWT internos
ENVIRONMENT=development
```

---

## Docker Compose

```yaml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: ./backend/.env
    depends_on:
      - redis
    volumes:
      - ./backend:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

> MongoDB Atlas corre en la nube — no se incluye en Compose.
> Gemini y Google Maps son APIs externas — no se incluyen en Compose.

---

## requirements.txt

```
# Framework
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.0.0
python-dotenv

# MongoDB async
motor>=3.3.0
pymongo>=4.6.0

# Redis
redis>=5.0.0

# Gemini
google-generativeai>=0.7.0

# Google Maps
googlemaps>=4.10.0

# HTTP client
httpx>=0.27.0

# Autenticación y calendarios
python-jose[cryptography]>=3.3.0
google-auth>=2.29.0
google-auth-oauthlib>=1.2.0
google-api-python-client>=2.127.0
caldav>=1.3.9
msal>=1.28.0

# Utilidades
pandas>=2.2.0          # para ingesta de CLUES
python-multipart
websockets
```

---

## Seguridad

### Datos del paciente
- Los síntomas se guardan en MongoDB ligados a `session_id`, no a identidad real
- No se requiere registro del paciente para usar la plataforma
- Las sesiones expiran en Redis a los 60 minutos

### Tokens de calendario de doctores
- Los `access_token` y `refresh_token` se guardan encriptados en MongoDB
- Usar `cryptography.fernet` para encriptación simétrica en reposo

### JWT internos
- Los doctores autenticados reciben JWT firmado con `SECRET_KEY`
- Expiración de 24 horas
- Refresh token en Redis

### Rate limiting
- Máximo 5 llamadas a `/consult` por `session_id` por minuto
- Implementado con Redis INCR + EXPIRE

---

## Modelo de negocio técnico

| Usuario | Acceso | Costo |
|---|---|---|
| Paciente | Pipeline completo + mapa + rutas | Gratis |
| Doctor básico | Solo aparece en resultados fuera de red | Gratis |
| Doctor en red | Chat directo + agenda + perfil prioritario | Suscripción mensual |

El sistema identifica si un doctor es `is_network: true` en MongoDB. Solo esos aparecen con botón de chat y posibilidad de agendar cita.
