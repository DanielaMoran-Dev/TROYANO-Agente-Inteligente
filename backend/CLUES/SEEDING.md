# Clinics DB Seeding Guide

Source: CLUES (Catálogo de la Red de Servicios de Salud), published monthly by the Mexican government.
Current file: `ESTABLECIMIENTO_SALUD_202602.xlsx` (February 2026).

## Prerequisites

- MongoDB running and `MONGO_URI` set in `backend/services/.env`
- Gemini API working (needed to generate embeddings — fix the Vertex AI IAM permission first, see root README)
- Atlas Vector Search index created (see step 3 below)

---

## Step 1 — Generate the wiki JSON

Only needed when you have a new CLUES `.xlsx` file. Skip if `clinics_wiki.json` is already up to date.

```bash
cd /home/angel/Escritorio/TROYANO-Agente-Inteligente
backend/.venv/bin/python << 'EOF'
# Re-run the extraction script embedded in this file or just run:
# backend/.venv/bin/python backend/CLUES/extract_clues.py
EOF
```

For now the wiki JSON is pre-built at `backend/CLUES/clinics_wiki.json` (39,867 active facilities).

---

## Step 2 — Seed MongoDB

### First time (full load, one state to test)

```bash
cd backend
python CLUES/seed_clinics.py --state AGUASCALIENTES --drop
```

### First time (full national dataset)

```bash
cd backend
python CLUES/seed_clinics.py --drop
```

> This calls Gemini embed for every document. At ~50 docs/batch expect ~800 batches.
> Cost: ~39k embedding calls. Keep an eye on Vertex AI quota.

### Monthly refresh (upsert — no downtime, no duplicate embeddings)

```bash
cd backend
python CLUES/seed_clinics.py  # no --drop flag = upsert mode
```

The script uses `clues` as the unique key. Records that already exist and haven't changed will be skipped (no re-embedding). New or modified facilities get inserted/updated.

---

## Step 3 — Create the Atlas Vector Search index

This only needs to be done **once** after the first seed.

1. Open MongoDB Atlas → your cluster → **Search** tab → **Create Search Index**
2. Choose **Vector Search**
3. Select database `healthapp`, collection `clinics`
4. Use this index definition:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    }
  ]
}
```

5. Name it exactly: `clinics_embedding_index`

> The routing agent's `vector_search_clinics()` in `mongo_service.py:55` hardcodes this index name.

---

## Monthly update checklist

1. Download the new CLUES file from [DGIS](https://www.gob.mx/salud/documentos/datos-abiertos-bases-de-datos-2025) and replace `ESTABLECIMIENTO_SALUD_202602.xlsx`
2. Re-run Step 1 to regenerate `clinics_wiki.json`
3. Run Step 2 in upsert mode (no `--drop`)
4. No index changes needed unless the embedding model changes

---

## Troubleshooting

| Error | Fix |
|---|---|
| `403 PERMISSION_DENIED aiplatform.endpoints.predict` | Grant `roles/aiplatform.user` to the service account in GCP Console |
| `GOOGLE_CLOUD_PROJECT` wrong project in error | Check shell env: `echo $GOOGLE_CLOUD_PROJECT` — should be `nuvia-489723` |
| `pymongo.errors.ServerSelectionTimeoutError` | MongoDB not running or `MONGO_URI` not set |
| `embedding: []` on many docs | Gemini quota exceeded — reduce `--batch` or wait and retry |
| Vector search returns nothing | Verify index name is exactly `clinics_embedding_index` and status is **Active** |
