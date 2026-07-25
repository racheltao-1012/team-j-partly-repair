# Team J — Partly inspection MVP

Team J is an extensible photo-to-order workflow for the **Partly Hackathon 2026
Dataset API**. The product focus is:

1. Upload damage photos.
2. Enter or identify the vehicle information.
3. Use AI to extract damage from the current photos.
4. Recommend parts that should be inspected or replaced.
5. Match the accurate OEM number.
6. Compare supplier stock, price and arrival time.
7. Let the repairer confirm the result and generate the order.

The current prototype keeps the official API unchanged on port `8420`, runs on
port `8501`, and combines real photo analysis, an auditable impact-propagation
graph, Partly demo data, local vehicles, and imported OEM catalogues. The
prototype includes a manual supplier-quote workspace that compares stock,
unit price and estimated arrival for each technician-confirmed OEM number.
No supplier value is invented. Live quotes and direct order submission still
require a connected supplier inventory and ordering API.

## What this prototype does

- Reads the eight Partly demo vehicles.
- Adds any number of local vehicles through the website or API.
- Imports real OEM part catalogues from CSV.
- Returns Partly and local vehicles in one normalised format.
- Keeps local vehicles usable when the Partly API is offline.
- Loads the eight supplied Partly vehicle identities from
  `data/vehicles.json` when the live Partly API is unavailable.
- Shows only vehicle identity in the selector; a vehicle never carries a fixed
  damage result.
- Accepts 1–4 real collision photos and sanitises them before storage.
- Uses a configured vision provider to identify directly visible damaged parts,
  damage types, confidence, severity, impact zone, and normalised boxes.
- Joins each `part_id` to the catalogue in `/assemblies`.
- Shows the standard part name, OEM number, confidence and parts diagram.
- Highlights the catalogue hotspot on the diagram.
- Queries a SQLite `part_relations` graph and ranks clearly labelled
  impact-path **inspection suggestions** with traceable paths and probabilities.
- Lets a technician confirm, reject, request inspection, correct, or add a part.
- Stores each review in SQLite.
- Retrieves past cases only when the current photo pattern passes a similarity
  threshold based on impact zone, visible part, damage type and severity.
- Uses only technician-confirmed parts from matched cases as clearly labelled
  additional inspection suggestions.
- Exports a technician-reviewed CSV report.

Vehicle selection supplies identity and a compatible OEM catalogue only. Every
damage assessment requires current-case photos. Without a vision provider, the
UI offers an explicitly labelled technician-guided demo; it never presents the
manual seed as image inference. This MVP does not query VIN/registration
providers, run a finite-element crash simulation, or automatically retrain a
model.

## Extensible architecture

```text
Frontend
   ↓
Versioned routers (/api/v1)
   ↓
VehicleService / AssessmentService / PhotoAssessmentService
   ├── PartlyProvider → official API :8420
   ├── LocalCatalogueProvider → SQLite
   ├── VisionProvider → OpenAI Responses API or segmentation webhook
   └── ImpactPropagationService → part_relations
```

Every provider returns the same vehicle fields and a `capabilities` object.
Adding a future VIN, OEM, workshop-database, or computer-vision provider does
not require changing the frontend's vehicle format.

## Run on Windows with Docker

### 1. Start the official Partly API

Open the official `partly-hackathon-2026` folder in VS Code. In its terminal:

```powershell
docker compose up
```

Check that this page opens:

```text
http://localhost:8420/docs
```

Keep that terminal running.

### 2. Start Team J

Extract this project. Open the `partly_hackthon_team_j` folder in a **second**
VS Code window. In its terminal:

No API key is required to run this project.

```powershell
docker compose up --build
```

When the terminal says Uvicorn is running, open:

```text
http://localhost:8501
```

Do not click VS Code's green Python run button. Both applications run inside
Docker, so your local Python installation does not need FastAPI.

### 3. Use the workflow

1. Upload one to four collision photos.
2. Choose a Partly vehicle, or click **Add new vehicle** and import an OEM CSV.
   Add the VIN, registration or technician-confirmed variant where available.
3. Click **Analyse photos**. The vehicle-only fixed-prediction route is disabled.
4. Review the photo-based damage and the separately labelled impact-path or
   similar-case inspection recommendations.
5. Check each OEM candidate and exact OEM number.
6. Confirm, reject, correct, or add parts before any procurement action.
7. For each confirmed OEM number, enter two or more supplier quotes and compare
   stock, unit price and estimated arrival. Select the preferred quote.
8. Click **Save technician review**, then **Export CSV** as the current order
   handoff. A supplier API can later replace manual quote entry with live data
   and direct order submission.

### Catalogue CSV format

Required columns:

```csv
part_name,oem_number,category,diagram_url
Front bumper cover,52119-12A30,body,
Left headlamp,81150-02M90,lighting,https://example.com/headlamp.png
```

`category` and `diagram_url` are optional. The website includes a downloadable
template. The prototype accepts UTF-8 CSV files up to 5 MB and 5,000 rows.

Saved cases remain in:

```text
storage/inspection.db
```

because the folder is mounted as a Docker volume.

## Project structure

```text
team-j-partly-repair/
├── app/
│   ├── main.py              # FastAPI routes and Partly proxy
│   ├── dependencies.py      # provider/service wiring
│   ├── partly_client.py     # calls the official API
│   ├── assessment.py        # joins predictions to OEM catalogue parts
│   ├── database.py          # vehicles, parts, feedback and CSV export
│   ├── schemas.py           # unified validated data models
│   ├── vision.py            # real vision and segmentation-webhook adapters
│   ├── impact_graph.py      # probability propagation over part relations
│   ├── case_similarity.py   # similarity gate for saved repair cases
│   ├── part_matching.py     # generic part to vehicle catalogue matching
│   ├── providers/           # Partly and local data adapters
│   ├── services/            # merging and assessment logic
│   ├── routers/             # versioned vehicle/catalogue endpoints
│   └── static/
│       ├── index.html       # website
│       ├── styles.css
│       └── app.js
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Website API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Check connection to the official API |
| `GET /api/v1/vehicles` | Merge all vehicle providers |
| `POST /api/v1/vehicles` | Create a local vehicle |
| `GET /api/v1/vehicles/{id}/parts` | Read normalised OEM parts |
| `POST /api/v1/vehicles/{id}/parts` | Add one local OEM part |
| `GET /api/v1/vehicles/{id}/assessment` | Disabled vehicle-only prediction route |
| `POST /api/v1/catalogues/import?vehicle_id=...` | Import local parts CSV |
| `GET /api/v1/photo-assessments/status` | Show whether real photo inference is configured |
| `POST /api/v1/photo-assessments/analyse` | Upload photos and run visible + hidden assessment |
| `GET /api/v1/photo-assessments/{run_id}` | Retrieve a saved photo run |
| `GET /api/v1/part-relations` | Inspect the graph and propagation weights |
| `POST /api/cases` | Save technician feedback |
| `GET /api/cases/{case_id}` | Read a saved case |
| `GET /api/cases/{case_id}/export.csv` | Download the reviewed report |
| `GET /api/history/{vehicle_slug}` | Retrieve simple past-case statistics |

Interactive documentation for this companion API is available at:

```text
http://localhost:8501/docs
```

The original `GET /api/vehicles` list alias remains for compatibility. The old
vehicle-only assessment routes now reject requests so fixed demo predictions
cannot be mistaken for a new photo analysis.

## Photo model choices

The default `openai` provider sends base64 image inputs to the Responses API and
uses strict structured output. It returns conservative bounding boxes rather
than pixel masks. See the official
[image-input guide](https://developers.openai.com/api/docs/guides/images-vision)
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

For a dedicated YOLO, Mask R-CNN, SAM, or other part/damage segmentation model,
configure:

```text
VISION_PROVIDER=webhook
VISION_WEBHOOK_URL=https://your-model-service/analyse
VISION_WEBHOOK_TOKEN=optional-secret
```

The adapter contract and probability formula are documented in
`PHOTO_DAMAGE_ANALYSIS_GUIDE.md`.

## Stop the applications

In each Docker terminal, press `Ctrl+C`. You can then run:

```powershell
docker compose down
```

## If the red hotspot is slightly offset

The frontend applies the diagram's `scale_x` and `scale_y` metadata. If a
specific dataset diagram uses a different coordinate convention, the
catalogue hotspot may appear offset. Adjust `hotspotToNormalised()` in
`app/static/app.js` after inspecting that diagram's meta and hotspot values.
