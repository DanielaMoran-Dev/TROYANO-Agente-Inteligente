# Geodata API Strategy & Usage Guide

Este documento describe cómo interactuar con el servicio de geolocalización y capas urbanas de **Lineal**. Este servicio es la fuente de verdad única para datos geográficos, reemplazando cualquier archivo local.

## 1. Catalog of Available Layers

Cada capa representa un conjunto de datos específico extraído del sistema **SIIMP (ArcGIS Online)**.

| Layer Name | Description | ArcGIS Item ID |
| :--- | :--- | :--- |
| `vialidades` | Red vial primaria y secundaria de Aguascalientes. | `326852c2fee84bd29309c5f233fc95e1` |
| `contencion_urbana` | Polígono de límite de crecimiento urbano permitido. | `b372b2da8ff5413ab91ec8fd660729e3` |
| `zufos` | Zonas de Focalización Urbana (prioridad de desarrollo). | `00c831a39c364076a370c66c7e54c48c` |
| `zonas_dinamica_especial` | Áreas con normativas de construcción especiales. | `f77c54918844465eaab349127455f256` |
| `materiales_petreos` | Zonas con aptitud para materiales de construcción. | `eb0567fce7ac4f048d8c3bc93db71691` |

---

## 2. API Endpoints (FastAPI)

El backend expone los siguientes endpoints para el consumo de datos:

### `GET /geo/layers`
Retorna la lista de nombres de capas disponibles.
**Response:**
```json
{ "layers": ["vialidades", "contencion_urbana", ...] }
```

### `GET /geo/layer/{layer_name}`
Descarga la capa solicitada en formato **GeoJSON FeatureCollection**.
**Ejemplo:** `GET /geo/layer/vialidades`

### `POST /geo/multi`
Solicita múltiples capas en una sola petición.
**Body:**
```json
{ "layers": ["vialidades", "zufos"] }
```

### `GET /geo/layer/{layer_name}/metadata`
Obtiene metadatos informativos (título del IMPLAN, descripción, extensión geográfica).

---

## 3. Guía para Agentes (Prompting & Logic)

Cuando un agente necesite validar una acción contra la realidad urbana, debe seguir este flujo:

1. **Identificar la necesidad:** (Ej: "Necesito saber si esta calle es primaria").
2. **Solicitar la capa:** Usar el `geodata_service.get_layer("vialidades")`.
3. **Cargar en GeoPandas:**
```python
import geopandas as gpd
from services import geodata_service

# Fetching
geojson = geodata_service.get_layer("vialidades")
gdf = gpd.GeoDataFrame.from_features(geojson["features"])
```

### Reglas de Uso:
* **No Cache Local:** El servicio ya implementa cache en memoria. No guardes archivos `.json` en disco dentro del contenedor.
* **Serverless First:** Todas las peticiones deben ser tratadas como efímeras.
* **Fallback:** Si la capa falla, el agente debe reportar "Información geográfica no disponible" en lugar de inventar coordenadas.

---

## 4. Configuration (Environment Variables)

Para cambiar el origen de los datos sin modificar código en Code Engine:
* `ARCGIS_BASE_URL`: URL base de ArcGIS Sharing API.
* `SIIMP_VIALIDADES_ID`: Override para el ID de vialidades.
* `SIIMP_CONTENCION_ID`: Override para el ID de contención.
* `GEODATA_TIMEOUT`: Tiempo límite de descarga (default: 30s).
