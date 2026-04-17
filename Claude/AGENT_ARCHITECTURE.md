# Arquitectura de Agentes
> Plataforma médica de conexión paciente-doctor
> Tres agentes especializados en pipeline secuencial

---

## Visión general

El sistema opera con tres agentes en cadena. Cada agente recibe el output del anterior como input, enriquece el contexto y lo pasa al siguiente. Ningún agente toma decisiones que no le corresponden.

```
síntomas + seguro + presupuesto + ubicación
                    ↓
          [ Agente de Triaje ]
                    ↓
        urgency + specialty + clinical_summary
                    ↓
          [ Agente de Ruteo ]
                    ↓
        lista rankeada de opciones viables
                    ↓
       [ Agente de Recomendación ]
                    ↓
     top 3 con justificación + contacto + mapa
```

---

## Principios de diseño de los agentes

- **Responsabilidad única** — cada agente hace exactamente una cosa
- **Contexto acumulativo** — cada agente recibe todo lo que produjeron los anteriores
- **Output estructurado** — siempre JSON validado con Pydantic antes de pasar al siguiente agente
- **Fallo explícito** — si un agente falla, el pipeline se detiene y devuelve error claro, sin respuestas inventadas
- **Sin estado interno** — los agentes son funciones puras, el estado vive en MongoDB

---

## Agente 1 — Triaje

### Responsabilidad
Interpretar síntomas en lenguaje natural y producir un perfil clínico estructurado que los agentes siguientes puedan procesar.

### Método: LLM Wiki
No usa RAG. El conocimiento médico necesario para clasificar síntomas y urgencia es estático y curado — vive en un archivo markdown que se inyecta en el system prompt de Gemini en cada llamada.

**Por qué LLM Wiki y no RAG aquí:**
- El triaje no puede tolerar fallos de recuperación — si RAG no encuentra el chunk correcto, el modelo alucina urgencia
- El conocimiento es pequeño y estático — no necesita escala
- Todo en contexto garantiza que el modelo razona sobre el panorama completo

### Archivo wiki del triaje
`backend/wiki/triage_wiki.md` — contiene:
- Tabla de síntomas → especialidad probable
- Criterios de clasificación de urgencia (low / medium / critical)
- Señales de alarma que escalan automáticamente a critical
- Tipos de unidad médica y cuándo derivar a cada una
- Instrucciones de formato de output

### Input
```python
{
    "symptoms": str,          # descripción libre del paciente
    "session_id": str         # para trazabilidad
}
```

### Llamada a Gemini
```python
async def run(symptoms: str) -> TriageResult:
    wiki = load_wiki("triage_wiki.md")

    system_prompt = f"""
    {wiki}

    Eres un agente médico de triaje. Tu única tarea es clasificar
    los síntomas del paciente y producir un perfil clínico estructurado.
    No diagnosticas. No recomiendas tratamientos.
    Respondes ÚNICAMENTE con JSON válido, sin markdown, sin texto extra.
    """

    user_prompt = f"El paciente describe: {symptoms}"

    raw = await gemini_service.generate(
        system=system_prompt,
        user=user_prompt,
        model="gemini-2.0-pro"
    )
    return TriageResult(**json.loads(raw))
```

### Output
```json
{
    "urgency_level": "low | medium | critical",
    "unit_type": "urgencias | general | especialista",
    "specialty": "cardiología | neurología | medicina_general | ...",
    "clinical_summary": "Paciente refiere dolor torácico de 20 min con disnea. Posible origen cardíaco. Requiere evaluación urgente.",
    "reasoning": "Síntomas compatibles con síndrome coronario agudo. Tiempo de inicio menor a 30 min.",
    "red_flags": ["dolor_torácico", "disnea"],
    "session_id": "uuid"
}
```

### Reglas de escalación automática
Si el modelo detecta cualquiera de estas señales, `urgency_level` es siempre `critical` sin importar el resto:
- Dolor torácico con disnea
- Pérdida de conciencia
- Dificultad para hablar o mover extremidades
- Sangrado sin control
- Dificultad respiratoria severa
- Dolor abdominal severo súbito

### Archivo `backend/agents/triage_agent.py`
```python
import json
from services import gemini_service
from schemas.patient import TriageResult

WIKI_PATH = "wiki/triage_wiki.md"

def _load_wiki() -> str:
    with open(WIKI_PATH, "r", encoding="utf-8") as f:
        return f.read()

async def run(symptoms: str, session_id: str = None) -> dict:
    wiki = _load_wiki()

    system_prompt = f"""
{wiki}

Eres un agente médico de triaje. Clasifica síntomas y produce
perfil clínico estructurado. No diagnosticas ni recomiendas tratamientos.
Responde ÚNICAMENTE con JSON válido.
"""
    user_prompt = f"El paciente describe: \"{symptoms}\""

    try:
        raw = await gemini_service.generate(
            system=system_prompt,
            user=user_prompt,
            model="gemini-2.0-pro"
        )
        result = json.loads(raw)
        result["session_id"] = session_id
        return result
    except Exception as e:
        raise ValueError(f"Triage agent failed: {e}")
```

---

## Agente 2 — Ruteo

### Responsabilidad
Encontrar, filtrar y rankear establecimientos médicos compatibles con el perfil del paciente, calculando tiempos reales de traslado.

### Método: RAG con MongoDB Atlas Vector Search
A diferencia del triaje, el ruteo opera sobre miles de registros de CLUES que cambian y necesitan búsqueda semántica. RAG es el enfoque correcto aquí.

**Por qué RAG y no LLM Wiki aquí:**
- CLUES tiene miles de establecimientos — no caben en contexto
- La búsqueda semántica es necesaria — el paciente dice "me duele el corazón" y el agente debe encontrar cardiología
- Los datos se actualizan — el índice vectorial se puede re-indexar sin tocar el código

### Pipeline interno del agente

```
specialty + unit_type del triaje
            ↓
    Gemini Embeddings
            ↓
    Vector Search MongoDB (colección clinics)
    top 50 candidatos semánticamente relevantes
            ↓
    Filtro hard por seguro médico
            ↓
    Filtro hard por budget_level ($, $$, $$$)
            ↓
    Google Maps Distance Matrix API
    tiempo real de traslado por tráfico actual
            ↓
    Ranking: urgency_weight * time + price_level
            ↓
    top 10 opciones estructuradas
```

### Input
```python
{
    "triage": TriageResult,       # output completo del Agente de Triaje
    "insurance": str,             # imss | issste | seguro_popular | ninguno
    "budget_level": str,          # $ | $$ | $$$
    "coords": {
        "lat": float,
        "lng": float
    }
}
```

### Mapeo de budget_level
```python
BUDGET_MAP = {
    "$":   {"price_level": [1],    "sectors": ["público", "general"]},
    "$$":  {"price_level": [1, 2], "sectors": ["público", "privado_bajo"]},
    "$$$": {"price_level": [1, 2, 3], "sectors": ["público", "privado", "premium"]}
}
```

### Vector Search en MongoDB
```python
async def _vector_search(query_embedding: list, limit: int = 50) -> list:
    pipeline = [
        {
            "$vectorSearch": {
                "index": "clinics_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 150,
                "limit": limit
            }
        },
        {
            "$project": {
                "_id": 1, "name": 1, "specialty": 1,
                "insurances": 1, "price_level": 1,
                "lat": 1, "lng": 1, "phone": 1,
                "address": 1, "doctor_id": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    return await mongo_service.clinics.aggregate(pipeline).to_list(limit)
```

### Lógica de ranking
```python
def _rank(clinics: list, travel_times: list, urgency_level: str) -> list:
    urgency_weight = {"low": 0.3, "medium": 0.6, "critical": 1.0}
    w = urgency_weight[urgency_level]

    scored = []
    for clinic, time in zip(clinics, travel_times):
        score = (w * time) + ((1 - w) * clinic.get("price_level", 1) * 10)
        scored.append({**clinic, "travel_time_min": time, "rank_score": score})

    return sorted(scored, key=lambda x: x["rank_score"])
```

### Output
```json
{
    "options": [
        {
            "clinic_id": "clues_123456",
            "name": "Centro de Salud Especializado Roma Norte",
            "specialty": "cardiología",
            "insurances": ["imss", "seguro_popular"],
            "price_level": 1,
            "lat": 19.4187,
            "lng": -99.1624,
            "address": "Orizaba 92, Roma Norte, CDMX",
            "phone": "55-1234-5678",
            "doctor_id": "doc_789",
            "travel_time_min": 8,
            "rank_score": 4.8
        }
    ],
    "triage_ref": { },
    "total_candidates": 47,
    "filtered_count": 12
}
```

### Archivo `backend/agents/routing_agent.py`
```python
import asyncio
from services import gemini_service, mongo_service, maps_service

BUDGET_MAP = {
    "$":   [1],
    "$$":  [1, 2],
    "$$$": [1, 2, 3]
}

async def run(triage: dict, insurance: str, budget_level: str, coords: dict) -> dict:
    # 1. Embeddings de la consulta
    query_text = f"{triage['specialty']} {triage['unit_type']} {' '.join(triage.get('red_flags', []))}"
    embedding = await gemini_service.embed(query_text)

    # 2. Vector Search
    candidates = await _vector_search(embedding, limit=50)

    # 3. Filtros hard
    price_levels = BUDGET_MAP.get(budget_level, [1, 2, 3])
    filtered = [
        c for c in candidates
        if (insurance in c.get("insurances", []) or insurance == "ninguno")
        and c.get("price_level", 1) in price_levels
    ]

    if not filtered:
        filtered = candidates[:10]  # fallback sin filtro de seguro

    # 4. Travel times en paralelo
    destinations = [{"lat": c["lat"], "lng": c["lng"]} for c in filtered[:15]]
    travel_times = await maps_service.get_travel_times(coords, destinations)

    # 5. Ranking
    ranked = _rank(filtered[:15], travel_times, triage["urgency_level"])

    return {
        "options": ranked[:10],
        "triage_ref": triage,
        "total_candidates": len(candidates),
        "filtered_count": len(filtered)
    }
```

---

## Agente 3 — Recomendación

### Responsabilidad
Convertir la lista técnica del Agente de Ruteo en recomendaciones comprensibles, empáticas y accionables para el paciente. Diferencia opciones dentro y fuera de la red de doctores.

### Método: LLM Wiki
Similar al triaje, las reglas de tono, formato y diferenciación de red son estáticas y pequeñas — van en system prompt como wiki.

**Por qué LLM Wiki aquí:**
- Las reglas de presentación no cambian con frecuencia
- El modelo necesita razonar sobre el contexto completo — todas las opciones a la vez
- No hay recuperación de información — solo síntesis y redacción

### Archivo wiki de recomendación
`backend/wiki/recommendation_wiki.md` — contiene:
- Tono por nivel de urgencia (critical: directo y urgente / low: tranquilo y orientador)
- Formato exacto de justificación por opción
- Cómo presentar opciones de red vs fuera de red
- Qué información destacar según el tipo de unidad
- Instrucciones de output JSON

### Lógica de red de doctores
```python
async def _identify_network(options: list) -> set:
    doctor_ids = [o.get("doctor_id") for o in options if o.get("doctor_id")]
    if not doctor_ids:
        return set()

    network = await mongo_service.doctors.find(
        {"_id": {"$in": doctor_ids}, "is_active": True},
        {"_id": 1}
    ).to_list(len(doctor_ids))

    return {str(d["_id"]) for d in network}
```

### Diferenciación de contacto
```python
def _build_contact(option: dict, is_network: bool) -> dict:
    if is_network:
        return {
            "type": "chat",
            "doctor_id": option["doctor_id"],
            "can_schedule": True
        }
    else:
        return {
            "type": "info",
            "phone": option.get("phone"),
            "address": option.get("address"),
            "can_schedule": False
        }
```

### Input
```python
{
    "routing": RoutingResult,     # output completo del Agente de Ruteo
    "triage": TriageResult        # output completo del Agente de Triaje
}
```

### Llamada a Gemini
```python
async def run(routing: dict, triage: dict) -> dict:
    wiki = _load_wiki("recommendation_wiki.md")
    options = routing["options"][:5]
    network_ids = await _identify_network(options)

    options_with_network = [
        {**o, "is_network": str(o.get("doctor_id")) in network_ids}
        for o in options
    ]

    system_prompt = f"""
{wiki}

Urgencia del paciente: {triage['urgency_level']}
Especialidad requerida: {triage['specialty']}
Resumen clínico: {triage['clinical_summary']}

Genera justificaciones empáticas y claras en español para cada opción.
Responde ÚNICAMENTE con JSON válido.
"""
    user_prompt = f"Opciones disponibles: {json.dumps(options_with_network, ensure_ascii=False)}"

    raw = await gemini_service.generate(system=system_prompt, user=user_prompt)
    result = json.loads(raw)

    # Enriquecer con datos de contacto y coords
    for rec in result["recommendations"]:
        option = next((o for o in options if o["clinic_id"] == rec["clinic_id"]), {})
        rec["contact"] = _build_contact(option, rec["is_network"])
        rec["coords"] = {"lat": option.get("lat"), "lng": option.get("lng")}
        rec["travel_time_min"] = option.get("travel_time_min")
        rec["clinic_name"] = option.get("name")

    return result
```

### Output
```json
{
    "recommendations": [
        {
            "clinic_id": "clues_123456",
            "clinic_name": "Centro de Salud Especializado Roma Norte",
            "priority": 1,
            "justification": "Este centro tiene cardiología disponible y acepta tu seguro IMSS. Está a solo 8 minutos de donde estás y es la opción más rápida dado el nivel de urgencia de tus síntomas.",
            "is_network": true,
            "contact": {
                "type": "chat",
                "doctor_id": "doc_789",
                "can_schedule": true
            },
            "coords": { "lat": 19.4187, "lng": -99.1624 },
            "travel_time_min": 8
        },
        {
            "clinic_id": "clues_654321",
            "clinic_name": "Hospital Ángeles Metropolitano",
            "priority": 2,
            "justification": "Hospital privado con unidad de cardiología de alta complejidad. Tiempo de traslado de 14 minutos.",
            "is_network": false,
            "contact": {
                "type": "info",
                "phone": "55-8765-4321",
                "address": "Tlacotalpan 59, Roma Sur, CDMX",
                "can_schedule": false
            },
            "coords": { "lat": 19.4050, "lng": -99.1580 },
            "travel_time_min": 14
        }
    ],
    "urgent_message": "Tus síntomas sugieren una posible emergencia cardíaca. Ve al centro más cercano ahora o llama al 911.",
    "total_options_evaluated": 10
}
```

---

## Comunicación entre agentes

### Contexto acumulativo
Cada agente recibe el output de todos los anteriores. El Agente de Recomendación tiene acceso al triaje original para mantener coherencia de tono y urgencia.

```python
# patient.py router
@router.post("/consult")
async def consult(request: ConsultRequest):

    # Agente 1
    triage = await triage_agent.run(
        symptoms=request.symptoms,
        session_id=request.session_id
    )

    # Agente 2 — recibe output del 1
    routing = await routing_agent.run(
        triage=triage,
        insurance=request.insurance,
        budget_level=request.budget_level,
        coords=request.coords
    )

    # Agente 3 — recibe outputs del 1 y del 2
    recommendation = await recommendation_agent.run(
        routing=routing,
        triage=triage
    )

    # Persistir sesión completa
    await mongo_service.patients.insert_one({
        "session_id": request.session_id,
        "symptoms": request.symptoms,
        "triage": triage,
        "routing": {"total_candidates": routing["total_candidates"]},
        "recommendation": recommendation,
        "created_at": datetime.utcnow()
    })

    return recommendation
```

### Manejo de errores por agente
```python
# Cada agente tiene su propio try/except
# El pipeline falla rápido y devuelve error descriptivo

try:
    triage = await triage_agent.run(symptoms)
except ValueError as e:
    raise HTTPException(status_code=422, detail=f"Triage failed: {e}")

try:
    routing = await routing_agent.run(triage, insurance, budget_level, coords)
except Exception as e:
    raise HTTPException(status_code=502, detail=f"Routing failed: {e}")

try:
    recommendation = await recommendation_agent.run(routing, triage)
except Exception as e:
    raise HTTPException(status_code=502, detail=f"Recommendation failed: {e}")
```

---

## Gemini Service — cliente único compartido

Todos los agentes llaman a Gemini a través de un solo servicio. Nunca directamente.

```python
# services/gemini_service.py
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def generate(system: str, user: str, model: str = "gemini-2.0-flash") -> str:
    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            {"role": "system", "parts": [{"text": system}]},
            {"role": "user",   "parts": [{"text": user}]}
        ]
    )
    return response.text

async def embed(text: str) -> list[float]:
    response = await client.aio.models.embed_content(
        model="gemini-embedding-exp-03-07",
        contents=text
    )
    return response.embeddings[0].values

async def stream(system: str, user: str):
    async for chunk in client.aio.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=[
            {"role": "system", "parts": [{"text": system}]},
            {"role": "user",   "parts": [{"text": user}]}
        ]
    ):
        yield chunk.text
```

### Modelos por agente
| Agente | Modelo | Razón |
|---|---|---|
| Triaje | gemini-2.0-pro | Razonamiento complejo, clasificación médica |
| Ruteo | gemini-embedding-exp-03-07 | Solo embeddings, no generación |
| Recomendación | gemini-2.0-pro | Redacción empática y estructurada |
| Chat en tiempo real | gemini-2.0-flash | Velocidad, respuestas cortas al doctor |

---

## Schemas Pydantic de los agentes

```python
# schemas/patient.py

from pydantic import BaseModel
from typing import Optional, Literal
from enum import Enum

class UrgencyLevel(str, Enum):
    low = "low"
    medium = "medium"
    critical = "critical"

class UnitType(str, Enum):
    urgencias = "urgencias"
    general = "general"
    especialista = "especialista"

class ConsultRequest(BaseModel):
    session_id: str
    symptoms: str
    coords: dict                              # {"lat": float, "lng": float}
    insurance: Literal["imss", "issste", "seguro_popular", "ninguno"]
    budget_level: Literal["$", "$$", "$$$"]

class TriageResult(BaseModel):
    urgency_level: UrgencyLevel
    unit_type: UnitType
    specialty: str
    clinical_summary: str
    reasoning: str
    red_flags: list[str] = []
    session_id: Optional[str] = None

class ContactInfo(BaseModel):
    type: Literal["chat", "info"]
    doctor_id: Optional[str] = None
    can_schedule: bool
    phone: Optional[str] = None
    address: Optional[str] = None

class RecommendationItem(BaseModel):
    clinic_id: str
    clinic_name: str
    priority: int
    justification: str
    is_network: bool
    contact: ContactInfo
    coords: dict
    travel_time_min: int

class RecommendationResult(BaseModel):
    recommendations: list[RecommendationItem]
    urgent_message: Optional[str] = None
    total_options_evaluated: int
```

---

## LLM Wiki — estructura de archivos

### `backend/wiki/triage_wiki.md` — esqueleto
```markdown
# Guía de Triaje Médico

## Niveles de urgencia
- **critical**: requiere atención inmediata, riesgo de vida
- **medium**: requiere atención en las próximas horas
- **low**: puede esperar consulta programada

## Señales de alarma — siempre critical
- Dolor torácico con disnea o sudoración
- Pérdida de conciencia o confusión súbita
- Dificultad para hablar o mover extremidades (posible EVC)
- Sangrado activo sin control
- Dificultad respiratoria severa
- Dolor abdominal súbito e intenso

## Síntomas → Especialidad
| Síntomas | Especialidad | Tipo de unidad |
|---|---|---|
| dolor torácico, palpitaciones | cardiología | urgencias o especialista |
| dolor de cabeza intenso, mareos | neurología | urgencias o especialista |
| fiebre alta, tos, dificultad respiratoria | neumología | urgencias o general |
| dolor abdominal, náuseas, vómito | gastroenterología | general o urgencias |
| dolor de garganta, gripe | medicina_general | general |
| dolor de oído | otorrinolaringología | general |
| dolor articular, muscular | traumatología | general o especialista |
| problemas de piel | dermatología | especialista |
| problemas visuales súbitos | oftalmología | urgencias |
| síntomas urinarios | urología o nefrología | general o especialista |

## Formato de output requerido
JSON estricto sin markdown ni texto adicional.
```

### `backend/wiki/recommendation_wiki.md` — esqueleto
```markdown
# Guía de Recomendación Médica

## Tono por nivel de urgencia
- **critical**: directo, urgente, sin rodeos. Mensaje de urgencia primero.
- **medium**: claro y orientador, transmite que hay tiempo pero hay que actuar.
- **low**: tranquilo, informativo, sin alarmar.

## Diferenciación de red
- **is_network: true**: menciona que hay contacto directo disponible.
- **is_network: false**: solo información de contacto, no menciones la red.

## Formato de justificación
- Máximo 2 oraciones por opción
- Mencionar especialidad, seguro si aplica, y tiempo de traslado
- Nunca usar jerga médica compleja
- Nunca diagnosticar

## Formato de output requerido
JSON estricto con el array recommendations y urgent_message.
```
