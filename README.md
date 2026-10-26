# D2S2C – HOCHBAHN UC44: AI-Supported GHG Emissions Analysis & Calculation for Product Categories

## Project Overview

- **Co-developed an AI-supported software prototype for Hamburger Hochbahn AG within the "Data-driven Solutions for the Smart City Hamburg" (D²S²C) initiative.**
- **Automated the calculation and analysis of greenhouse gas (GHG) emissions across corporate procurement and product categories.**
- **Implemented backend data pipelines and machine learning models in Java combined with interactive frontend components.** *(Note: Prototyped with a robust Python/FastAPI backend & Angular frontend, integrated with advanced LLM pipelines).*
- **Collaborated in an agile Scrum team utilizing GitLab for code reviews, issue tracking, and version control.**

---

## Key Features & Architecture

This repository contains the complete open-source release of the UC44 AI-supported reporting prototype for Hamburger Hochbahn AG (SoSe 2026). The system automates corporate carbon footprint calculations based on procurement invoice data and spend-based emission factors.

### Three-Stage User Workflow

1. **Upload**: Ingestion of procurement invoice data (Excel/CSV) with mandatory columns (`Warengruppe`, `Bestelltext`, spend amounts).
2. **AI Analysis & Review**: Dual LLM pipelines execute sequentially:
   - **Plausibility Check**: Validates whether existing product category (`Warengruppe`) assignments are plausible.
   - **Prediction / Regrouping**: Suggests correct category classifications for implausible or unassigned records.
3. **Dashboard & Export**: Aggregate KPIs, CO₂e footprint before and after reclassification, top product category rankings, and Excel reporting exports.

### Repository Structure

```tree
├── app/
│   ├── backend/          # FastAPI backend (API routers, services, LLM orchestrators)
│   └── frontend/         # Angular application (Views, components, OpenAPI generated client)
├── models/               # Standalone LLM processing scripts and shared catalog logic
├── tests/                # Automated test suite (catalog loaders, model cache, plausibility validation)
├── docker-compose.yml    # Full-stack container orchestration
└── README.md
```

---

## Getting Started

### Prerequisites

- Docker & Docker Compose (recommended for full-stack deployment)
- Python 3.10+ (for backend and standalone models)
- Node.js 18+ & npm (for frontend development)

### Running with Docker

```bash
cd app
# Copy environment template and configure your OpenAI API key and auth token
cp .env.example .env
# Edit .env and set OPENAI_API_KEY and UC44_AUTH_TOKEN

docker compose up --build
```
- Frontend: `http://localhost:8080` (or configured port)
- Backend Swagger API Docs: `http://localhost:8000/docs`

### Manual Development Setup

#### 1. Backend (FastAPI)
```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend (Angular)
```bash
cd app/frontend
npm install
npm start
```
Development server runs at `http://localhost:4200` (proxies `/api` calls to backend).

#### 3. Standalone LLM Models
```bash
cd models
pip install -r requirements.txt
# Set OPENAI_API_KEY in environment
cd prediction_model && python run.py
cd plausibility_model && python run.py
```

---

## Testing & Quality Assurance

Run backend and integration tests located in `tests/`:
```bash
pytest tests/
```

Run frontend unit tests:
```bash
cd app/frontend
npm test
```

---

## License

This project was developed as part of the D²S²C initiative for Hamburger Hochbahn AG. All proprietary internal datasets and credentials have been scrubbed for this public repository release.
