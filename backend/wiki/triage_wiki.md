# Wiki de Triaje Médico — MedConnect

Esta wiki guía al agente de triaje para clasificar síntomas y determinar qué tipo de establecimiento de salud buscar en la base de datos CLUES de México.

---

## 1. Niveles de Urgencia y Mapeo a Búsqueda de Establecimientos

Cada nivel de urgencia determina qué `nivel_atencion` y `tipologia` buscar en la colección MongoDB `clinics` (seeded desde CLUES).

### CRITICAL — Prioridad Manchester 1 o 2 (ROJO / NARANJA)

**Buscar en MongoDB:**
- `nivel_atencion`: `"SEGUNDO NIVEL"` o `"TERCER NIVEL"`
- `tipologia` preferida: `"HOSPITAL GENERAL DE ZONA"`, `"HOSPITAL GENERAL"`, `"HOSPITAL INTEGRAL (COMUNITARIO)"`, `"UNIDAD DE MEDICINA FAMILIAR CON HOSPITALIZACION"`
- `unit_type` a devolver: `"urgencias"`
- Ordenar por: menor `travel_time_min` primero (urgencia = tiempo)

**Indicadores clínicos:**
- Dolor torácico con irradiación, diaforesis, disnea
- Pérdida de conciencia, convulsiones activas, status epiléptico
- Signos FAST de EVC: asimetría facial, debilidad de brazo, alteración del habla
- Dificultad respiratoria con cianosis, tiraje o SatO2 < 90%
- Sangrado severo o incontrolable
- Trauma grave: TEC con pérdida de conciencia, fractura expuesta, politraumatismo
- Anafilaxia: inflamación de garganta, hipotensión, urticaria generalizada
- Crisis hipertensiva: PA > 180/120 + cefalea intensa o déficit neurológico
- Abdomen agudo con descompensación hemodinámica
- Embarazo ectópico roto, hemorragia obstétrica
- Glucosa < 60 mg/dL con pérdida de conciencia, o cetoacidosis diabética
- Bebé < 3 meses con fiebre ≥ 38°C

### MEDIUM — Prioridad Manchester 3 (AMARILLO)

**Buscar en MongoDB:**
- `nivel_atencion`: `"PRIMER NIVEL"` o `"SEGUNDO NIVEL"`
- `tipologia` preferida: `"UNIDAD MÉDICA RURAL"`, `"URBANO DE 01 NÚCLEOS BÁSICOS"`, `"UNIDAD DE MEDICINA FAMILIAR"`, `"HOSPITAL INTEGRAL (COMUNITARIO)"`
- `unit_type` a devolver: `"general"` o `"especialista"` según síntomas
- Ordenar por: combinación de `travel_time_min` y `score` de vector search

**Indicadores clínicos:**
- Fiebre > 39°C por más de 48 horas sin síntomas de alarma
- Dolor moderado que no cede con analgésicos comunes
- Infección con signos locales (herida con pus, celulitis)
- Síntomas urinarios intensos (ardor, frecuencia, hematuria)
- Vómito o diarrea con deshidratación moderada
- Lumbalgia o dolor articular que limita movilidad
- Crisis asmática leve-moderada sin cianosis
- Otitis media aguda, sinusitis aguda con fiebre
- Hipertensión arterial leve no controlada (sin síntomas de órgano blanco)
- Dolor abdominal leve en FID (evaluar escala Alvarado; si ≥ 5 → CRITICAL)

### LOW — Prioridad Manchester 4 o 5 (VERDE / AZUL)

**Buscar en MongoDB:**
- `nivel_atencion`: `"PRIMER NIVEL"`
- `tipologia` preferida: `"CONSULTORIO ADYACENTE A FARMACIA"`, `"CONSULTORIO PARTICULAR"`, `"RURAL DE 01 NÚCLEO BÁSICO"`, `"UNIDAD DE MEDICINA FAMILIAR"`, `"URBANO DE 01 NÚCLEOS BÁSICOS"`
- `unit_type` a devolver: `"general"`
- Ordenar por: `score` de vector search primero (relevancia clínica > distancia)

**Indicadores clínicos:**
- Síntomas leves controlados con medicamentos caseros
- Seguimiento de condición crónica estable (diabetes, HTA controlada)
- Resfriado común, dolor de garganta sin disfagia, fiebre sin síntomas asociados
- Chequeo preventivo o de rutina

---

## 2. Mapeo Síntoma → Especialidad → Tipo de Establecimiento CLUES

| Síntoma principal | Especialidad | `tipologia` CLUES preferida | Nivel |
|---|---|---|---|
| Dolor torácico, palpitaciones, HTA | Cardiología | HOSPITAL GENERAL DE ZONA, UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES) | 2º/3er |
| Cefalea intensa súbita, déficit neurológico | Neurología | HOSPITAL GENERAL, TERCER NIVEL | 3er |
| Tos crónica, disnea, asma | Neumología | UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES), HOSPITAL GENERAL | 2º |
| Dolor abdominal, náuseas, sangrado digestivo | Cirugía General / Gastro | HOSPITAL GENERAL DE ZONA | 2º |
| Fiebre, infección, síntomas generales | Medicina General | UNIDAD DE MEDICINA FAMILIAR, CENTRO DE SALUD URBANO | 1er |
| Dolor al orinar, hematuria | Urología | HOSPITAL GENERAL, SEGUNDO NIVEL | 2º |
| Síntomas reproductivos, embarazo | Ginecología y Obstetricia | HOSPITAL GENERAL CON CAMAS | 2º |
| Diabetes descontrolada, tiroides | Endocrinología | UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES) | 2º |
| Trauma, fractura, lesión muscular | Ortopedia / Traumatología | HOSPITAL GENERAL DE ZONA | 2º |
| Ansiedad severa, crisis emocional | Psiquiatría / Psicología | UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES), CENTRO DE SALUD | 2º |
| Control preventivo, vacunación | Medicina Preventiva | RURAL DE 01 NÚCLEO BÁSICO, CENTRO DE SALUD | 1er |
| Adicciones | Salud Mental / Adicciones | CENTRO DE PREVENCION EN ADICCIONES (CIJ) | 1er |

---

## 3. Campos Disponibles en la Colección `clinics` (MongoDB)

Estos son los campos que el agente de ruteo devuelve y que Gemini puede usar para generar recomendaciones:

```
name           — Nombre oficial del establecimiento (de CLUES)
institution    — Institución: "IMSS", "ISSSTE", "SECRETARIA DE SALUD", etc.
specialty      — "medicina general" | "especialidades médicas" | "alta especialidad"
unit_type      — Tipología CLUES: "HOSPITAL GENERAL DE ZONA", "UNIDAD DE MEDICINA FAMILIAR", etc.
nivel_atencion — "PRIMER NIVEL" | "SEGUNDO NIVEL" | "TERCER NIVEL"
insurance      — Lista: ["imss"] | ["issste"] | ["seguro_popular"] | ["ninguno"]
budget_level   — "$" (público gratuito) | "$$$" (privado con costo)
coords         — { lat: float, lng: float }
address        — Dirección completa reconstruida del CLUES
phone          — Teléfono del establecimiento (puede ser null)
state          — Estado de la república
municipality   — Municipio
travel_time_min — Minutos de viaje desde la ubicación del paciente (vía Maps API)
score          — Relevancia de vector search (0.0–1.0, mayor es mejor)
```

---

## 4. Reglas de Clasificación por Seguro/Derechohabiencia

Cuando el paciente menciona su tipo de seguro, filtrar `insurance` en MongoDB:

| El paciente dice... | Filtrar `insurance` |
|---|---|
| "Tengo IMSS" / "soy derechohabiente del seguro" | `["imss"]` |
| "Soy empleado del gobierno" / "tengo ISSSTE" | `["issste"]` |
| "Tengo seguro popular" / "IMSS Bienestar" / "no tengo seguro pero soy de zona rural" | `["seguro_popular"]` |
| "No tengo seguro" / "pago de mi bolsillo" / "tengo seguro privado" | `["ninguno"]` (clínicas privadas) |
| No menciona seguro | No filtrar — devolver opciones de todos los seguros |

---

## 5. Reglas Generales de Triaje

1. En duda entre LOW y MEDIUM → clasificar MEDIUM.
2. En duda entre MEDIUM y CRITICAL → clasificar CRITICAL.
3. Cualquier síntoma en bebés < 3 meses → MEDIUM o CRITICAL.
4. Paciente con comorbilidades (diabetes, HTA, inmunosupresión) → subir un nivel de urgencia.
5. Si el paciente describe señales de emergencia en el chat → marcar `emergency: true` y `urgency_level: "critical"` inmediatamente, sin esperar más datos.
6. `triage_priority` numérico (1–5 Manchester) debe coincidir con `urgency_level`:
   - 1–2 → critical
   - 3 → medium
   - 4–5 → low
