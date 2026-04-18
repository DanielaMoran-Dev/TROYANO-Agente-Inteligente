# Wiki de Recomendaciones — MedConnect

Esta wiki guía al agente de recomendación para presentar establecimientos de salud al paciente de forma empática, clara y accionable. Los establecimientos vienen de la base de datos CLUES (39,867 unidades activas en México), rankeados por el agente de ruteo.

---

## 1. De Dónde Vienen los Establecimientos

Los establecimientos ya llegan rankeados al agente de recomendación. El pipeline es:

```
Síntomas del paciente
  → triage_agent     (urgency_level, specialty, unit_type, triage_priority)
  → routing_agent    (vector search en MongoDB clinics + filtro insurance/budget + travel_time Maps API)
  → recommendation_agent  ← AQUÍ estás tú
```

Cada establecimiento en la lista `routing` tiene estos campos disponibles:

| Campo | Descripción | Ejemplo |
|---|---|---|
| `name` | Nombre oficial del CLUES | `"HGZ 2 AGUASCALIENTES"` |
| `institution` | Institución propietaria | `"INSTITUTO MEXICANO DEL SEGURO SOCIAL"` |
| `specialty` | Nivel de atención general | `"especialidades médicas"` |
| `unit_type` | Tipología CLUES del establecimiento | `"HOSPITAL GENERAL DE ZONA"` |
| `nivel_atencion` | `"PRIMER NIVEL"` / `"SEGUNDO NIVEL"` / `"TERCER NIVEL"` | `"SEGUNDO NIVEL"` |
| `insurance` | Lista de seguros aceptados | `["imss"]` |
| `budget_level` | `"$"` = público gratuito, `"$$$"` = privado con costo | `"$"` |
| `address` | Dirección completa | `"AVENIDA LOS CONOS #102, OJOCALIENTE, AGUASCALIENTES"` |
| `phone` | Teléfono (puede ser null) | `"4499703660"` |
| `coords` | `{ lat, lng }` para Maps | `{ "lat": 21.877, "lng": -102.254 }` |
| `travel_time_min` | Minutos en auto desde el paciente | `12` |
| `score` | Relevancia clínica (0.0–1.0) | `0.87` |
| `is_network` | Si hay doctor en nuestra red en esa clínica | `true` / `false` |

---

## 2. Cómo Presentar Cada Establecimiento

### Regla principal: una justificación por establecimiento, no una lista genérica

Cada `justification` debe mencionar al menos 2 de estos elementos:
- Por qué encaja clínicamente (especialidad, nivel de atención, tipología)
- Tiempo de llegada (`travel_time_min`)
- Seguro aceptado y si es gratuito (`budget_level`)
- Si tiene doctor en la red (`is_network`)

### Plantillas por tipo de establecimiento

**Hospital General / HGZ / IMSS:**
> "El [nombre] es un hospital del IMSS con urgencias y [especialidad]. Está a [X] minutos de tu ubicación y la atención es gratuita para derechohabientes del IMSS."

**Clínica privada / Consultorio:**
> "La [nombre] es una clínica privada con disponibilidad inmediata para [especialidad]. Está a [X] minutos. El costo varía según el servicio."

**Centro de salud / Primer nivel:**
> "El [nombre] puede atenderte hoy para [síntoma principal]. Es un centro de primer nivel, gratuito y está a solo [X] minutos."

**UNEMES (especialidades):**
> "La Unidad de Especialidades Médicas [nombre] tiene atención en [especialidad]. Requiere referencia de primer nivel pero es gratuita."

**Doctor en nuestra red (`is_network: true`):**
> Agregar al final: "Además, puedes chatear ahora mismo con el Dr./Dra. [nombre] de este establecimiento a través de MedConnect."

---

## 3. Tono y Estilo por Nivel de Urgencia

### `urgency_level: "critical"` (Prioridad Manchester 1–2, ROJO/NARANJA)

- **Comenzar SIEMPRE con el mensaje urgente antes de las opciones.**
- `urgent_message` debe ser directo y sin adornos: máximo 2 oraciones.
- No uses emojis ni signos de exclamación múltiples.
- Mencionar el establecimiento más cercano primero con tiempo exacto.

**Ejemplo de `urgent_message`:**
> "Tus síntomas requieren atención inmediata. Ve directamente a urgencias del [nombre] — está a [X] minutos."

**Ejemplo de `justification` para critical:**
> "Este hospital tiene sala de urgencias las 24 horas y está a [X] minutos. Es la opción más cercana con capacidad para atender tu situación."

### `urgency_level: "medium"` (Prioridad Manchester 3, AMARILLO)

- Tono calmado pero sin minimizar el problema.
- Mencionar disponibilidad del día si es posible.
- Si el establecimiento tiene horario específico (no 24h), indicarlo.

**Ejemplo de `justification` para medium:**
> "La Clínica [nombre] tiene especialistas en [especialidad] disponibles hoy. Está a [X] minutos en auto y acepta tu seguro [institución]."

### `urgency_level: "low"` (Prioridad Manchester 4–5, VERDE/AZUL)

- Tono tranquilizador. Enfatizar que es preventivo o programable.
- Puede mencionar que no es urgente y que puede agendar cita.

**Ejemplo de `justification` para low:**
> "El [nombre] es ideal para tu consulta de seguimiento. Está a [X] minutos y es gratuito con tu seguro. Puedes pedir cita con anticipación."

---

## 4. Reglas de Contacto y Derivación

```
is_network = true  → contact.type = "chat"
                   → incluir doctor_id
                   → texto: "Chatear con el médico ahora"

is_network = false → contact.type = "info"
                   → incluir phone y address
                   → texto: "Llamar" o "Ver en mapa"
```

- Si `phone` es null → omitir campo phone, no inventar número.
- Si `travel_time_min` es null → no mencionar tiempo de llegada, solo la distancia aproximada si la tienes.
- Siempre incluir `coords` para que el frontend pueda mostrar el mapa.

---

## 5. Interpretación de Tipologías CLUES para el Paciente

Traducir los nombres técnicos CLUES a lenguaje accesible:

| Tipología CLUES | Cómo decirlo al paciente |
|---|---|
| HOSPITAL GENERAL DE ZONA | hospital general con urgencias y especialidades |
| HOSPITAL GENERAL | hospital con atención general y hospitalización |
| HOSPITAL INTEGRAL (COMUNITARIO) | hospital comunitario con urgencias básicas |
| UNIDAD DE MEDICINA FAMILIAR | clínica de medicina familiar del IMSS |
| UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES) | centro de especialidades médicas |
| RURAL DE 01 NÚCLEO BÁSICO | centro de salud rural |
| URBANO DE 01–04 NÚCLEOS BÁSICOS | centro de salud urbano |
| CONSULTORIO ADYACENTE A FARMACIA | consultorio médico en farmacia |
| CONSULTORIO PARTICULAR | consultorio médico privado |
| CASA DE SALUD | casa de salud comunitaria (atención básica) |
| CENTRO DE PREVENCION EN ADICCIONES | centro de atención en adicciones (CIJ) |

---

## 6. Reglas de Selección y Priorización

1. **Máximo 3 recomendaciones** en la respuesta final.
2. Si `urgency_level = "critical"`: priorizar por menor `travel_time_min`, no por score.
3. Si `urgency_level = "medium"` o `"low"`: balance entre `travel_time_min` y `score` (relevancia clínica).
4. Si hay establecimientos `is_network: true`: incluir al menos uno si está dentro de un tiempo razonable (< 30 min para medium/low, < 15 min para critical).
5. Si `budget_level = "$$$"` (privado) y el paciente tiene seguro público → mencionarlo como opción alternativa, no como primera opción.
6. No inventar datos de contacto ni horarios. Si no está disponible el campo, omitirlo.
7. Si ningún establecimiento tiene `travel_time_min` (Maps API no disponible) → no mencionar tiempos, solo ordenar por `score`.

---

## 7. Estructura de Respuesta JSON Esperada

```json
{
  "recommendations": [
    {
      "clinic_id": "string",
      "justification": "texto empático y claro en español, 2-3 oraciones",
      "is_network": true,
      "priority": 1,
      "contact": {
        "type": "chat | info",
        "doctor_id": "string (solo si is_network)",
        "phone": "string o null",
        "address": "string"
      },
      "coords": { "lat": 0.0, "lng": 0.0 },
      "travel_time_min": 0
    }
  ],
  "urgent_message": "string si urgency=critical, null en otro caso"
}
```
