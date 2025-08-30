### Guidance for Claude Code (claude.ai/code)

This document aligns Claude Code with the current repository layout and conventions.

## Project Overview

KM24 Vejviser is a specialized assistant that helps Danish journalists create structured investigation plans for the KM24 platform. It accepts a natural language goal and produces a pedagogical, step-by-step JSON plan with dynamic filter recommendations.

## Codebase Layout (current)

- `km24_vejviser/main.py`: FastAPI app and LLM orchestration
- `km24_vejviser/km24_client.py`: Thin client for KM24 API access
- `km24_vejviser/filter_catalog.py`: Dynamic and hyper-relevant filter recommendations
- `km24_vejviser/knowledge_base.py`: Extraction of module knowledge from longDescription
- `km24_vejviser/module_validator.py`: Validation of module selections and structure
- `km24_vejviser/models/`: Pydantic models (e.g., `usecase_response.py`)
- `km24_vejviser/templates/`: HTML templates (`index.html`, `index_new.html`)
- `km24_vejviser/cache/`: Cache files
- `tests/`: Pytest suite
- `docs/`: Project documentation

Non-existent in this codebase (avoid referencing): `advisor.py`, `core/settings.py`, YAML knowledge base files.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r km24_vejviser/requirements.txt

# Optional: configure Anthropic key
echo 'ANTHROPIC_API_KEY="your_key_here"' > km24_vejviser/.env

uvicorn km24_vejviser.main:app --reload --host 127.0.0.1 --port 8000
```

## Tests

```bash
pytest
pytest -v
```

## API endpoints (app)

- `POST /generate-recipe/` – Generate investigation plan
- `GET /health` – Health check
- `GET /api/km24-status` – KM24 API status
- Filter catalog:
  - `GET /api/filter-catalog/status`
  - `POST /api/filter-catalog/recommendations`
  - `GET /api/filter-catalog/municipalities`
  - `GET /api/filter-catalog/branch-codes`
  - `DELETE /api/clear-cache`

## Notes for edits

- Prefer Pydantic models under `km24_vejviser/models/` for typed contracts
- Keep endpoints deterministic for tests in `km24_vejviser/tests`
- Follow README in `docs/README.md` for setup and usage
- Improvement ideas live in `docs/improvements.md`

## Style and quality

- Python: PEP 8, type hints, f-strings, descriptive names
- Tests: pytest, keep endpoints stable, avoid network in unit tests
- File ops: use `pathlib` where possible