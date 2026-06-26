# DeltaMind Clarify

DeltaMind Clarify is an evidence-based claim investigation system designed to assess, explain, and eventually correct claims using provenance-aware evidence. The current system is built around **PIVOT — Provenance-Indexed Verification over Time**, a pipeline that decomposes user-provided claims, retrieves relevant evidence, classifies evidence stance, computes a final verdict, and generates reproducible evaluation reports.

The project is currently in MVP development. The short-term goal is to stabilize the core backend architecture and evaluation loop, then involve peers with specialized expertise in AI, frontend design, backend deployment, search API selection, and production infrastructure.

---

## 1. Purpose

The purpose of DeltaMind Clarify is to move beyond simple fact-checking and toward a transparent investigation engine.

Instead of only answering whether a claim is true or false, the system aims to answer:

- What parts of the claim are supported by evidence?
- What parts are contradicted or unverifiable?
- Which sources support or contradict the claim?
- How reliable and specific is the evidence?
- What corrected claim should be proposed if the original claim is wrong?
- How much did the investigation cost in terms of tokens, search calls, and compute?

The long-term vision is a system that can **verify, explain, correct, and learn** from previous investigations.

---

## 2. Features

### Current MVP Features

- **Claim decomposition**
  - Breaks an input claim into atomic claims.
  - Extracts subject, predicate, object, claim type, and confidence.

- **LLM-based search planning**
  - Generates search queries and candidate sources.
  - Supports direct source URL candidates when available.

- **Evidence retrieval**
  - Fetches direct source URLs.
  - Expands known domains such as NBA, ESPN, CBS Sports, and The Athletic.
  - Supports fallback behavior for deterministic local evaluation.

- **Evidence quality filtering**
  - Removes low-quality or irrelevant evidence.
  - Helps avoid treating search-result pages as factual evidence.

- **Stance classification**
  - Classifies each evidence item as supporting, contradicting, partially supporting, or insufficient.
  - Uses deterministic local fallback when external LLM APIs fail during local development.

- **PIVOT scoring**
  - Aggregates evidence stance, source reliability, specificity, independence, and freshness.
  - Produces verdicts such as `supported`, `contradicted`, `unverifiable`, `partial`, and `contested`.

- **Verified-claim cache**
  - Stores verified claim results to avoid repeated full investigations.

- **LLM cache**
  - Caches LLM outputs to reduce cost and improve reproducibility.

- **Audit trail**
  - Stores agent runs and intermediate outputs for debugging and transparency.

- **Local evaluation workflow**
  - Runs an end-to-end evaluation through the API.
  - Generates JSONL predictions, summary metrics, and a Markdown report.
  - Current smoke-test evaluation reaches 6/6 on the local deterministic set.

- **One-command local evaluation**
  - `make eval-local` starts the backend, enables local deterministic fallback, runs the evaluation, generates a report, restores `.env`, and shuts down the temporary server.

---

## 3. Novelty and Valuable Parts

### 3.1 Provenance-Indexed Verification

DeltaMind Clarify focuses on provenance: every verdict should be connected to traceable evidence, source metadata, and agent decisions. This makes the system more transparent than a single-step LLM answer.

### 3.2 Evidence-Aware Verdicts

The system separates claim decomposition, source planning, retrieval, evidence filtering, stance classification, and final scoring. This modular pipeline makes the final verdict easier to inspect and debug.

### 3.3 Claim Correction, Not Only Verification

A planned core feature is **claim repair**. When a claim is contradicted or partially wrong, the system should propose an evidence-supported corrected version.

Example:

> Original claim: The Miami Heat won the 2023 NBA Finals.  
> Verdict: Contradicted.  
> Corrected claim: The Denver Nuggets won the 2023 NBA Finals.

This makes the system more useful than a binary fact-checker.

### 3.4 Self-Learning Source Reliability

A planned learning module will update source reliability based on evaluated cases. Sources that repeatedly provide evidence aligned with trusted labels can be rewarded, while misleading or low-quality sources can be penalized.

The goal is auditable self-learning, not an opaque model that silently changes behavior.

### 3.5 Cost-Aware Investigation

The system is designed to track search calls, LLM tokens, provider usage, and estimated cost per case. This is important for real deployment because search APIs and LLM calls can become the main cost drivers.

### 3.6 Reproducible Local Evaluation

The local evaluation workflow is designed to be reproducible:

```bash
make eval-local
```

This creates a consistent evaluation result and Markdown report, making it easier to track regressions and demo progress.

---

## 4. Project Structure

```text
deltamind-verify/
├── Makefile
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── algorithm/
│   │   │   └── pivot/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── core/
│   │   ├── db/
│   │   ├── domain/
│   │   ├── providers/
│   │   │   ├── llm/
│   │   │   └── search/
│   │   ├── schemas/
│   │   └── tests/
│   ├── data/
│   │   └── eval/
│   │       └── gold_claims.jsonl
│   ├── scripts/
│   │   ├── eval_local.sh
│   │   ├── generate_pivot_eval_report.py
│   │   └── run_pivot_eval_api.py
│   └── docker-compose.yml
└── frontend/
```

The exact structure may evolve as frontend, deployment, self-learning, and claim correction modules are added.

---

## 5. Quick Start

### 5.1 Prerequisites

Recommended environment:

- Python 3.11
- Conda or virtualenv
- Docker and Docker Compose
- PostgreSQL / pgvector through Docker
- Node.js for frontend development, if the frontend is used
- LLM API key, such as Gemini or OpenAI
- Optional search API key, such as Tavily or Brave Search

---

### 5.2 Clone the Repository

```bash
git clone git@github.com:UtGong/deltamind-investigation-engine.git
cd deltamind-verify
```

If your local folder name is different, use that folder instead.

---

### 5.3 Start PostgreSQL

```bash
cd backend
docker compose up -d postgres
```

Check that the database is running:

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
```

---

### 5.4 Configure Environment Variables

Create or update `backend/.env`:

```env
APP_ENV=local
LOG_LEVEL=INFO

LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

SEARCH_PLANNER_PROVIDER=llm

FREE_SEARCH_PROVIDER=duckduckgo
PAID_SEARCH_PROVIDER=tavily
ALLOW_PAID_SEARCH=false
MAX_PAID_SEARCH_CALLS_PER_CASE=0

TAVILY_API_KEY=your_tavily_api_key_if_used
TAVILY_MAX_RESULTS=3
TAVILY_SEARCH_DEPTH=basic

VERIFIED_CLAIM_DB_PATH=data/verified_claims.sqlite3

LLM_CACHE_ENABLED=true
LLM_CACHE_DB_PATH=data/llm_cache.sqlite3

DATABASE_BACKEND=postgres
DATABASE_URL=postgresql+psycopg://deltamind:deltamind_dev_password@localhost:5432/deltamind
EMBEDDING_DIMENSION=768

DEV_LLM_FALLBACK_ENABLED=false
```

For local deterministic testing, `make eval-local` will temporarily enable:

```env
DEV_LLM_FALLBACK_ENABLED=true
```

and restore the original `.env` afterward.

---

### 5.5 Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

If the project uses Conda:

```bash
conda activate deltamind-verify
pip install -r requirements.txt
```

---

### 5.6 Run Database Migrations

```bash
cd backend
alembic upgrade head
```

---

### 5.7 Start the Backend

```bash
cd backend
uvicorn app.main:app --reload
```

The API should be available at:

```text
http://127.0.0.1:8000
```

Check system status:

```bash
curl -s http://127.0.0.1:8000/api/v1/system/status | python -m json.tool
```

---

### 5.8 Run Local Evaluation

From the project root:

```bash
make eval-local
```

This command will:

1. Temporarily enable local deterministic LLM fallback.
2. Start the backend.
3. Run API-based evaluation.
4. Generate prediction files.
5. Generate a Markdown report.
6. Restore `.env`.
7. Stop the temporary backend.

Expected smoke-test result:

```json
{
  "accuracy": 1.0,
  "completed": 6,
  "correct": 6,
  "errors": 0,
  "total": 6
}
```

Generated files:

```text
backend/data/eval/predictions.jsonl
backend/data/eval/predictions.summary.json
backend/data/eval/reports/latest_eval_report.md
```

These are runtime outputs and should not be committed.

---

### 5.9 Run Tests

From the project root:

```bash
make test-backend
```

Or from the backend directory:

```bash
python -m compileall app scripts
python -m pytest --cache-clear
```

---

## 6. Example API Workflow

### Create a Case

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/cases \
  -H "Content-Type: application/json" \
  -d '{
    "title": "NBA Finals claim",
    "description": "Testing claim verification",
    "claim_text": "The Denver Nuggets won the 2023 NBA Finals."
  }' | python -m json.tool
```

### Run Investigation

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/cases/<CASE_ID>/investigate | python -m json.tool
```

### Get Investigation Result

```bash
curl -s http://127.0.0.1:8000/api/v1/cases/<CASE_ID>/investigation | python -m json.tool
```

---

## 7. Current Evaluation Status

The current local smoke-test evaluation includes 6 cases:

- 2 supported claims
- 2 contradicted claims
- 2 unverifiable claims

Current local result:

```text
accuracy: 1.0
completed: 6
correct: 6
errors: 0
```

This should be treated as a smoke test, not a real-world generalization benchmark. The next step is to expand the gold set to 20–30 cases, then later 50–100+ cases across different domains and claim types.

---

## 8. Development Roadmap

### 1-Month Goal

- Finish core system architecture and MVP.
- Stabilize backend pipeline.
- Add initial claim correction.
- Expand local evaluation.
- Prepare documentation and handoff boundaries.

### 3-Month Goal

- Improve AI reasoning with peer support.
- Build frontend investigation dashboard.
- Add source reliability self-learning v0.
- Compare search APIs.
- Evaluate deployment options.
- Expand benchmark to 50–100 cases.

### 6-Month Goal

- Deploy a pilot-ready system.
- Add advanced claim correction.
- Add source reliability learning and calibration.
- Add cost and safety controls.
- Build polished frontend and stakeholder demo.
- Evaluate on 200+ cases.

---

## 9. Collaboration Notes

The current system is backend-heavy and still in MVP development. The following areas would benefit from peer collaboration:

- **AI / model design:** prompt design, stance classification, claim correction, confidence calibration, self-learning.
- **Frontend design:** investigation dashboard, evidence display, provenance graph, correction interface.
- **Backend deployment:** AWS EC2/RDS, Docker, Nginx, monitoring, API security, production cost evaluation.
- **Search API selection:** Tavily, Brave Search, direct source fetch, source coverage, cost-quality tradeoff.
- **Evaluation:** larger gold set, failure taxonomy, cross-domain benchmark.

Important note: I am not deeply familiar with real-world production deployment, so backend/server deployment choices should be reviewed by peers with deployment or DevOps experience.

---

## 10. Cost and Deployment Notes

The expected real-world cost comes from three main buckets:

1. LLM/token usage
2. Search API usage
3. Server/database/storage

Recommended pilot deployment:

```text
EC2 + Docker Compose + FastAPI + Next.js + PostgreSQL/pgvector + Nginx
```

Recommended cost controls:

- per-case token budget,
- per-case search budget,
- LLM cache,
- verified-claim cache,
- source-page cache,
- premium model escalation only when needed,
- cost logging per investigation.

---

## 11. Safety and Limitations

Current limitations:

- The local evaluation set is small.
- Some deterministic fallback behavior exists for reproducible local testing.
- Real-world search quality depends on external APIs and page availability.
- The current system should not be treated as a final authority.
- High-risk domains require stronger source policies, human review, and explicit uncertainty handling.

The intended output is an evidence-backed assessment, not an unqualified truth declaration.

---

## 12. License / Status

This project is currently an internal MVP / research prototype. Licensing, external release policy, and production deployment requirements should be decided before public deployment.
