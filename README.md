# MedConnect — Plataforma Médica Inteligente

Plataforma médica de conexión paciente-doctor impulsada por IA avanzada (**Gemini 2.5 flash**) para triaje automatizado, ruteo inteligente y comunicación en tiempo real.

## Características Principales

- **Triaje Inteligente Multi-Agente:** Pipeline secuencial de 3 agentes (Triaje, Ruteo y Recomendación) que procesan síntomas en lenguaje natural para clasificar la urgencia y especialidad.
- **RAG con MongoDB Vector Search:** Búsqueda semántica sobre miles de registros de establecimientos de salud (CLUES) para encontrar la mejor opción médica basada en especialidad, seguros y presupuesto.
- **Geolocalización y Ruteo Real:** Integración profunda con **Google Maps Platform** para calcular tiempos reales de traslado (Distance Matrix) y visualización interactiva.
- **Chat Médico en Tiempo Real:** Comunicación directa entre doctor y paciente vía **WebSockets** y **Redis Pub/Sub**, permitiendo una atención inmediata tras el triaje.
- **Sincronización de Calendarios:** Gestión de citas integrada con Google Calendar, Outlook y Apple (CalDAV) para doctores en red.

## Arquitectura de Agentes

El sistema utiliza un flujo de trabajo orquestado donde cada agente tiene una responsabilidad única:

1.  **Agente de Triaje (Gemini 2.0 Pro):** Clasifica la urgencia y genera un perfil clínico estructurado.
2.  **Agente de Ruteo (RAG + Distance Matrix):** Filtra y rankea opciones médicas viables por cercanía, costo y seguro.
3.  **Agente de Recomendación (Gemini 2.0 Pro):** Genera recomendaciones empáticas y personalizadas para el paciente.

## Stack Tecnológico

### Backend

- **Core:** FastAPI (Python 3.12), Pydantic v2.
- **IA:** Google Gemini 2.0 Pro/Flash, Gemini Embeddings.
- **Base de Datos:** MongoDB Atlas + Vector Search.
- **Mensajería/Caché:** Redis (Caché de sesiones, Pub/Sub para chat).
- **APIs Externas:** Google Maps Platform, Google/Microsoft/Apple Calendar APIs.

### Frontend

- **Framework:** Vanilla HTML5, CSS3 (Modern Glassmorphism), JavaScript (ES6+).
- **Mapas:** Google Maps JavaScript API.
- **Comunicación:** WebSockets nativos para chat doctor-paciente.

## Estructura del Proyecto

```text
├── backend/
│   ├── agents/          # Lógica de los agentes (Triaje, Ruteo, Recomendación)
│   ├── services/        # Clientes de Gemini, MongoDB, Maps, Redis
│   ├── routers/         # Endpoints de API (Patient, Doctor, Chat, Appointments)
│   ├── schemas/         # Modelos Pydantic para validación
│   ├── wiki/            # Conocimiento estático inyectado a los agentes
│   └── main.py          # Punto de entrada FastAPI
├── frontend/
│   ├── index.html       # Interfaz principal
│   ├── style.css        # Estilos modernos y glassmorphism
│   └── app.js           # Lógica del cliente y mapas
└── docker-compose.yml   # Orquestación de servicios (Backend + Redis)
```

## Instalación y Configuración

1.  **Clonar el repositorio:**

    ```bash
    git clone https://github.com/tu-usuario/TROYANO.git
    cd TROYANO
    ```

2.  **Configurar Backend:**

    ```bash
    cd backend
    python -m venv .venv
    source .venv/bin/activate  # En Linux/macOS
    pip install -r requirements.txt
    ```

3.  **Variables de Entorno:**
    Crea un archivo `.env` en la carpeta `backend/` basándote en la documentación de arquitectura.

4.  **Ejecutar con Docker (Recomendado):**
    ```bash
    docker-compose up --build
    ```

## Licencia

Este proyecto está bajo la licencia MIT.
