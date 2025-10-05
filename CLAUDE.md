# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**KM24 Vejviser** is a specialized FastAPI application that helps Danish journalists create structured investigation plans for the KM24 monitoring platform. It accepts natural language goals (e.g., "Monitor construction bankruptcies in Aarhus") and generates detailed, pedagogical JSON investigation plans with dynamic filter recommendations.

**Key Innovation:** The system integrates real-time KM24 API data to provide context-aware, API-validated filter recommendations, ensuring that generated plans use only valid module configurations and filter values.

## High-Level Architecture

### Recipe Generation Pipeline

The core flow transforms user goals into validated investigation plans through these stages:

1. **LLM Generation** (`get_anthropic_response`): Sends user goal + KM24 API metadata to Claude, receives raw JSON plan
2. **Normalization** (`coerce_raw_to_target_shape`): Maps LLM output to target structure, handles incomplete responses
3. **Module Validation** (`module_validator.py`): Validates module names against KM24 API, enriches with metadata
4. **Filter Enrichment** (`_enrich_with_module_specific_filters`): Adds module-specific parts (generic_value, web_source, amount_selection)
5. **API Validation** (`validate_filters_against_api`): Aggressive whitelist-based validation, removes invalid filters
6. **Default Application** (`apply_min_defaults`): Ensures all required fields have sensible defaults
7. **KM24 Rule Validation** (`validate_km24_recipe`): Checks syntax, structure, notification cadence
8. **Final Output** (`UseCaseResponse`): Pydantic model validation and serialization

### Key Subsystems

**KM24 API Client** (`km24_client.py`)
- Thin wrapper around KM24 API with 7-day caching
- Rate limiting (100ms between requests)
- Graceful degradation when API is unavailable
- Endpoints: `/modules/basic`, `/modules/{id}`, `/generic-values/{id}`, `/web-sources/categories/{id}`

**Filter Catalog** (`filter_catalog.py`)
- Intelligent filter recommendation engine with 24-hour cache
- Pre-caches all filter data on startup (municipalities, branch codes, regions, generic values)
- Hyper-relevant recommendations: extracts domain knowledge from module descriptions
- Deep intelligence handlers for specific modules (Status, Arbejdstilsyn, etc.)

**Module Validator** (`module_validator.py`)
- Validates module selections against live KM24 API
- Provides enhanced module cards with available filters
- Validates filter names/values against module parts

**Knowledge Base** (`knowledge_base.py`)
- Extracts structured knowledge from module `longDescription` fields
- Maps user intent to specific module parts (Problem, Reaction, etc.)

## Common Development Commands

### Running the Application

```bash
# Activate virtual environment
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Run development server
uvicorn km24_vejviser.main:app --reload --host 127.0.0.1 --port 8000

# Run with specific port
uvicorn km24_vejviser.main:app --reload --port 8001
```

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest km24_vejviser/tests/test_km24_validation.py

# Run with verbose output
pytest -v

# Run specific test function
pytest km24_vejviser/tests/test_main.py::test_recipe_structure -v

# Run tests matching pattern
pytest -k "test_filter" -v
```

**Note:** Tests are located in `km24_vejviser/tests/`, not `tests/`. The pytest.ini file configures this path.

### Cache Management

```bash
# Clear all cache files
rm km24_vejviser/cache/*.json

# View cache status (via API when running)
curl http://127.0.0.1:8000/api/filter-catalog/status
```

## Architecture Deep Dive

### Filter Validation: The Whitelist System

One of the most critical aspects is **filter validation**. The system implements aggressive whitelist-based validation to prevent "hallucinated" filters:

**Flow:**
1. LLM generates filters (may include invalid names)
2. `validate_filters_against_api()` fetches actual parts from KM24 API
3. Builds whitelist from API response (municipality → "geografi", industry → "branchekode", etc.)
4. Removes any filter not in whitelist
5. `final_cleanup_pass()` catches remaining issues

**Blacklist** (filters that NEVER exist):
- `oprindelsesland`, `virksomhedstype`, `statustype`, `dokumenttype`, `property_types`, `adressetype`

**Why this matters:** The LLM sometimes invents plausible-sounding filter names. The whitelist ensures only API-validated filters reach the output.

### Async/Await Patterns

Most I/O operations are async:
- `get_anthropic_response()` - LLM API calls
- `complete_recipe()` - Orchestrates async validation steps
- KM24 client methods - All API calls use `asyncio`
- Filter catalog loading - Parallel API requests for different filter types

### Caching Strategy

**KM24 API Cache:**
- Location: `km24_vejviser/cache/`
- Duration: 7 days
- Format: JSON files with `cached_at` timestamp
- Invalidation: Manual refresh endpoint or time-based

**Filter Catalog Cache:**
- Duration: 24 hours
- Pre-cached on startup via `@app.on_event("startup")`
- Includes: municipalities, branch codes, regions, generic values, web sources

### Error Handling Philosophy

The system prioritizes **graceful degradation**:
- If LLM fails → Returns fallback recipe with 3 basic steps
- If KM24 API is down → Uses cached data (warns if stale)
- If filter validation fails → Logs warnings but doesn't break the pipeline
- Missing module data → Uses hardcoded defaults

This ensures the application remains functional even with partial failures.

## Important Code Patterns

### Reading Module Data

```python
# Get module validator singleton
from km24_vejviser.module_validator import get_module_validator

module_validator = get_module_validator()

# Get enhanced module card (includes parts, filters)
module_card = await module_validator.get_enhanced_module_card("Arbejdstilsyn")

# Access available filters
for filter_info in module_card.available_filters:
    print(filter_info["type"], filter_info.get("part_name"))
```

### Adding Filter Recommendations

```python
# In filter_catalog.py
from km24_vejviser.filter_catalog import get_filter_catalog

fc = get_filter_catalog()
await fc.load_all_filters()  # Ensure data is loaded

# Get recommendations for a goal
recommendations = fc.get_relevant_filters(
    goal="Monitor construction in Aarhus",
    modules=["Registrering", "Tinglysning"]
)

# Recommendations include: filter_type, values, relevance_score, reasoning
```

### Search String Standardization

Search strings follow KM24 syntax rules:
- Boolean operators: `AND`, `OR`, `NOT` (uppercase only)
- Parallel variations: `landbrug;agriculture;farming` (semicolon-separated)
- Exact phrases: `~building permit~` (tilde-wrapped)
- Positional search: `~parkering` (prefix tilde)

The `_standardize_search_string()` function enforces these rules.

## API Endpoints Reference

**Main Endpoints:**
- `POST /generate-recipe/` - Generate investigation plan from goal
- `GET /` - Web UI (serves `templates/index_new.html`)
- `GET /health` - Health check (includes KM24 API status)

**Filter Catalog Endpoints:**
- `GET /api/filter-catalog/status` - Cache status and counts
- `POST /api/filter-catalog/recommendations` - Get filter recommendations for goal

**KM24 Integration Endpoints:**
- `GET /api/km24-status` - KM24 API health
- `POST /api/km24-refresh-cache` - Force cache refresh
- `DELETE /api/km24-clear-cache` - Clear all cache

**Streaming (Experimental):**
- `GET /generate-recipe-stream/` - Server-sent events for progress updates

## Environment Configuration

Required environment variables in `km24_vejviser/.env`:

```bash
ANTHROPIC_API_KEY="sk-ant-..."  # Required for LLM generation
KM24_API_KEY="..."              # Optional: for KM24 API access
KM24_BASE="https://km24.dk/api" # Optional: override API base URL
```

**Fallback behavior:**
- No `ANTHROPIC_API_KEY` → Returns 500 error with message
- No `KM24_API_KEY` → Uses cached data only, warns on startup

## Testing Strategy

The test suite validates multiple layers:

**Integration Tests** (`test_api_integration.py`)
- End-to-end recipe generation
- KM24 API connectivity

**Deterministic Output** (`test_deterministic.py`)
- Recipe structure consistency
- Field presence validation

**Filter Validation** (`test_whitelist_verification.py`)
- Whitelist-based filter validation
- Rejection of invalid filter names

**Syntax Validation** (`test_km24_syntax.py`)
- Search string syntax rules
- Boolean operator casing

**Normalization** (`test_normalization.py`)
- LLM output → target structure mapping
- Incomplete response handling

**Run single test category:**
```bash
pytest km24_vejviser/tests/test_deterministic.py -v
```

## Key Files and Their Roles

- `main.py` (2344 lines) - FastAPI app, LLM orchestration, recipe pipeline
- `km24_client.py` - KM24 API wrapper with caching
- `filter_catalog.py` - Intelligent filter recommendations
- `module_validator.py` - Module and filter validation
- `knowledge_base.py` - Domain knowledge extraction
- `models/usecase_response.py` - Pydantic response models
- `templates/index_new.html` - Web UI (Pico.css)

## Common Tasks

### Add a new module validation rule

Edit `validate_module()` in `main.py`:
```python
def validate_module(module: dict, step_number: int) -> list[str]:
    errors = []
    # Add new validation logic here
    return errors
```

### Add a new filter type

1. Update KM24 client to fetch new filter endpoint
2. Add cache loading in `filter_catalog.py` → `load_all_filters()`
3. Add relevance keywords in `FilterCatalog._relevans_keywords`
4. Add deep intelligence handler if module-specific

### Debug filter validation failures

Enable detailed logging:
```python
# In main.py, around line 1620
logger.info(f"Available filter types from API: {list(available.keys())}")
logger.info(f"Final whitelist for {module_name}: {sorted(whitelist)}")
```

Check logs for rejected filters and whitelist contents.

## Dependencies

Core dependencies (from `requirements.txt`):
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `anthropic` - Claude API client
- `pydantic` - Data validation
- `pytest`, `pytest-asyncio` - Testing
- `slowapi` - Rate limiting
- `requests` - HTTP client for KM24 API

## Development Notes

- **Run from project root:** All commands assume you're in `/Users/adamh/Projects/km24_vejviser/`
- **Virtual environment:** Always activate `.venv` before running
- **Port conflicts:** If 8000 is busy, use `--port 8001`
- **Cache invalidation:** Delete cache files if KM24 API schema changes
- **Test isolation:** Tests use `conftest.py` fixtures for shared setup

## Troubleshooting

**"ModuleNotFoundError: No module named 'km24_vejviser'"**
→ Run from project root, not from inside `km24_vejviser/` directory

**Tests fail with import errors**
→ Check `pytest.ini` points to correct testpath: `km24_vejviser/tests`

**Recipe validation fails with filter warnings**
→ Check `/api/filter-catalog/status` to verify filter data is loaded
→ Review logs for whitelist vs. attempted filter names

**KM24 API connection fails**
→ Check `.env` has `KM24_API_KEY`
→ Verify `KM24_BASE` URL is correct
→ Application will use cached data as fallback
