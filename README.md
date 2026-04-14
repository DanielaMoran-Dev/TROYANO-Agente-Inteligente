# Linealp — Smart City Planner

Plataforma de planificación urbana de alta fidelidad que combina **IA Generativa (IBM watsonx.ai)** con visualización **3D avanzada (Deck.gl)** para diseñar ciudades resilientes y sostenibles.

## Características Principales

- **Orquestación Multi-Agente:** Pipeline de 4 agentes especializados (Construcción, Viabilidad, Evaluación y Análisis) impulsado por **LangGraph**.
- **Validación RAG (PDFs):** El sistema consulta automáticamente normativas locales (NOM-001, PMDU, Manual de Calles) en formato PDF para validar la factibilidad legal de cada propuesta.
- **Visualización 3D Pro:** Renderizado de edificios neón, corredores de movilidad y zonas verdes utilizando el motor **Deck.gl**.
- **Análisis de Impacto Real:** Cálculo dinámico de reducción de CO2, presupuesto estimado, población afectada y resiliencia ante inundaciones.
- **Diseño Glassmorphism:** Interfaz moderna y técnica diseñada bajo los estándares de estética IBM Enterprise.

## Stack Tecnológico

- **Backend:** FastAPI (Python 3.11), LangGraph, PyPDF2.
- **IA:** IBM watsonx.ai (Llama-3.2-11b-vision-instruct).
- **Frontend:** Deck.gl, MapLibre GL, Turf.js.
- **Geospacial:** GeoPandas, Shapely.
- **Geodata API:** Consumo directo de SIIMP (ArcGIS) via [Geodata Documentation](backend/services/GEODATA_API.md).

## Instalación y Configuración

1. **Clonar el repositorio:**

   ```bash
   git clone https://github.com/tu-usuario/Lineal.git
   cd Lineal
   ```

2. **Configurar entorno virtual:**

   ```bash
   python -m venv .venv
   source .venv/Scripts/activate  # En Windows: .venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

3. **Variables de Entorno:**
   Configura el archivo .env con tus credenciales de IBM watsonx.

4. **Ejecutar la aplicación:**
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```
   Accede a la interfaz en: `http://127.0.0.1:8000/ui/`

## Licencia

Este proyecto es parte del Hackathon de IBM y está bajo la licencia MIT.
