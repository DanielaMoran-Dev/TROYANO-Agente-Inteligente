# Project Requirements Document (PRD): Lineal

## 1. Project Overview
**Project Name:** Lineal  
**Slogan:** "Planeación Urbana Inteligente"  
**Core Mission:** To empower private capital construction companies with a data-driven hub for urban prospecting and planning, identifying highly profitable and feasible development opportunities.

---

## 2. Problem Statement
The process of urban development prospecting is currently fragmented, manual, and high-risk. Developers often struggle to cross-reference traffic data, environmental restrictions, and regulatory compliance to find truly "redituables" (profitable) projects. Lineal streamlines this by automating the initial planning phase through an agentic AI system.

---

## 3. Target Audience & Use Case
**Primary User:** Real Estate Developers and Investment Funds.  
**Use Case Example:**  
A developer selects "Aguascalientes" in the system. The AI analyzes roadway data, legal restrictions, and population demand. It suggests constructing a "Light Rail Line" integrated into the main transport system.  
*   **Output:** Estimated Cost ($X), Execution Time (Y months), Expected ROI (Z%), and Estimated Monthly Ridership (A passengers).

---

## 4. Functional Requirements

### 4.1 Frontend (React Web App)
The interface is designed for high-density information visualization and conversational interaction using **MapLibre GL JS** for map rendering.
*   **Left Sidebar:**
    *   **City Selection:** Dropdown or search to define the working area.
    *   **Orchestrator Chatbot:** A conversational interface where the user describes needs (e.g., "I want to invest in mobility projects with high ROI") and interacts with the Multi-Agent system powered by **Watson Orchestrate**.
*   **Central Map View (MapLibre 2D Render):**
    *   Visualization of the original area with high-performance vector tiles.
    *   Dynamic overlays showing "Opportunity Zones."
    *   **Interactive Icons:** Markers representing specific project proposals.
    *   **Hover Interaction:** Displays a summary card (Cost, Time, ROI, and an "Expand Justification" button).
*   **Right Sidebar:**
    *   **Ranked Opportunities:** A list of project cards ranked by a balance of **Feasibility** and **Profitability**.
    *   **Detailed Analysis:** Clicking an opportunity expands a deep-dive analysis (data sources, agent reasoning, and justifications).

### 4.2 Backend (IBM Cloud Code Engine & Agentic)
El backend utiliza **IBM Cloud Code Engine** como la **plataforma de hosting contenerizada** del proyecto. Esta arquitectura **Serverless basada en contenedores** permite:
*   **Gestión de Dependencias Complejas:** Soporte nativo para librerías geoespaciales (GDAL, GEOS, PROJ) mediante contenedores Docker personalizados.
*   **Escalabilidad Dinámica:** Escalado automático de los agentes según la demanda, con capacidad de "scale-to-zero" para optimización de costos.
*   **Orquestación:** **Watson Orchestrate** actúa como el coordinador central, activando habilidades (skills) desplegadas en los contenedores de Code Engine.
*   **Lenguaje:** Python 3.11+.

---

## 5. Technical Architecture (Multi-Agent System)

The system operates through a collaborative network of specialized agents optimized for geospatial and regulatory analysis.

### 5.1 Specialized Agents
| Agent | Primary Function | Data Input |
| :--- | :--- | :--- |
| **Watson Orchestrate** | Primary interface; gathers requirements and coordinates results via Skill Catalog. | Natural Language (User Input) |
| **Construcción** | Estimates costs and execution timelines for physical structures. | GeoJSON, Geopandas Dataframe |
| **Áreas Verdes** | Ensures ecological balance and suggests reforestation/park projects. | GeoJSON, Geopandas Dataframe |
| **Vialidades y Movilidad** | Analyzes traffic patterns and suggests infrastructure (Transit, Roads). | GeoJSON, Geopandas Dataframe |
| **Resiliencia Climática** | Evaluates environmental risks (flooding, heat islands). | GeoJSON, Geopandas Dataframe |
| **Restricciones** | Performs RAG on local regulations via Watson Discovery. | Watson Discovery Collection |

### 5.2 Agent Workflow
1.  **Orchestrator** receives the user query.
2.  **Restricciones Agent** performs a RAG search on the vector database to find relevant building codes and zoning laws. These restrictions are shared with all other agents.
3.  **Domain Agents** (Mobility, Construction, etc.) process the shared GeoJSON/Dataframe data under the provided constraints.
4.  **Orchestrator** synthesizes the outputs into a coherent proposal.

---

## 6. Technology Stack
*   **Frontend:** React.js, **MapLibre GL JS** (Map Engine).
*   **Backend:** Python, **IBM Cloud Code Engine** (Plataforma de hosting contenerizada).
*   **AI Infrastructure:**
    *   **watsonx.ai:** LLM hosting for agent reasoning.
    *   **Watson Orchestrate:** Agentic orchestration and user interaction.
    *   **Watson Discovery:** Sole RAG engine for knowledge retrieval (PDFs, Regulations).
*   **Geospatial Tools:** Geopandas, Shapely, Turf.js.
*   **Data Services:** ArcGIS Online REST API (SIIMP Visor Integration).

---

## 7. Data Strategy (API-First) — [STATUS: LIVE]
Lineal has successfully transitioned to a fully API-driven architecture, eliminating local file dependencies.

*   **Primary Data Source:** SIIMP (Sistema Integral de Información Municipal y Planeación) de Aguascalientes, servido vía **ArcGIS Online REST API**.
*   **Active Services:**
    *   `geodata_service`: Fetches live GeoJSON from ArcGIS (Vialidades, ZUFOS, etc.).
    *   `discovery_service`: RAG skeleton querying a catalog of 5 regulatory PDFs (PMDU, NOM-001, etc.).
*   **Data Retrieval Process:** Los agentes consumen archivos GeoJSON mediante Item IDs específicos a través de la API del backend (`/geo/layer/{name}`).
*   **Knowledge Base:** Watson Discovery (Skeleton) para normativas y criterios de planeación que complementan la data geométrica.

---

## 8. Success Metrics (KPIs)
*   **Project Feasibility Score:** Confidence level of the proposal based on legal restrictions.
*   **ROI Estimation Accuracy:** Alignment with current market prices and demand forecasts.
*   **User Engagement:** Number of iterations needed until a project is "approved" for deeper study.

---

## 9. Implementation Roadmap

### Phase 1: Foundation & IBM Platform Scaffold — [COMPLETED ✅]
The objective of this phase was to establish a clean, serverless baseline and verify connectivity across the IBM Cloud ecosystem.

1.  **Legacy Cleanup (DONE):** Removed OSM extraction notebooks and local map files.
2.  **API Data Rendering (DONE):** MapLibre frontend connected to `/geo/` endpoints; verified rendering of 3,000+ vialidades features.
3.  **IBM Platform Skeleton (DONE):**
    *   **Cloud Code Engine:** Dockerized and verified on-the-fly hot reload.
    *   **watsonx.ai:** Integration verified with fallback "Demo Mode" for reliability.
    *   **watsonx Orchestrate:** OpenAPI manifest (`orchestrate_manifest.json`) exposed at `/orchestrate/manifest`.
    *   **Watson Discovery:** Skeleton query service functional with local PDF catalog.

### Phase 2: Domain Agent Implementation — [IN PROGRESS 🟢]
Specialized agents are being implemented to consume live SIIMP data and perform RAG-based validation.

1.  **Vialidades y Movilidad Agent (Next):** Implement GeoPandas analysis to suggest transportation infrastructure (BRT, Light Rail) based on live roadway density.
2.  **Restricciones Agent (RAG):** Transition from the `discovery_service` skeleton to live Watson Discovery API calls for building code validation.
3.  **Resiliencia Climática Agent:** Environmental risk assessment (flood zones) using SIIMP drainage layers.
4.  **Construcción & Áreas Verdes Agents:** ROI calculation and reforestation suggestions.
5.  **Conversational Integration:** Connecting the backend pipeline to Watson Orchestrate's chat interface for user-driven prospecting.
