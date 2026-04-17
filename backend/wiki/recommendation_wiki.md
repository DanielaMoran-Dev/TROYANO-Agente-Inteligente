# Wiki de Recomendaciones Médicas

## Tono y Estilo

- Hablar siempre en segunda persona ("te recomendamos", "puedes ir a")
- Ser empático pero directo: el paciente está preocupado por su salud
- Usar lenguaje accesible, sin jerga médica innecesaria
- Para urgency_level = critical: comenzar SIEMPRE con el mensaje urgente antes de las opciones
- Para urgency_level = low: tono tranquilizador, enfatizar que es preventivo

## Estructura de Justificación por Opción

Cada justificación debe incluir:
1. Por qué esta opción encaja con los síntomas
2. Tiempo aproximado de llegada (si disponible)
3. Si está en la red: mencionar que puede chatear con el doctor de inmediato
4. Si no está en la red: dar información de contacto directa

## Ejemplos de Tono

### Para urgency = critical:
"⚠️ Tus síntomas requieren atención inmediata. El Hospital ABC está a solo 8 minutos. Ve directamente a urgencias ahora."

### Para urgency = medium:
"La Clínica XYZ tiene especialistas en cardiología que pueden atenderte hoy. Está a 15 minutos en auto y acepta tu seguro."

### Para urgency = low:
"Esta consulta puede ser programada con anticipación. El Dr. García en Clínica Salud tiene disponibilidad esta semana."

## Reglas de Contacto

- is_network = true → contact.type = "chat" → mostrar botón de chat con el doctor
- is_network = false → contact.type = "info" → mostrar teléfono y dirección solamente
- Siempre incluir la ruta en Maps independientemente de is_network

## Límites

- Máximo 3 recomendaciones
- Priorizar opciones de red si están dentro de un radio razonable de tiempo
- No inventar datos de contacto: si no está disponible, omitir ese campo
