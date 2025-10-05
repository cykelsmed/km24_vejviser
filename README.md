# KM24 Vejviser

**En intelligent assistent til journalister, der skaber effektive overvågnings-opskrifter for KM24-platformen.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📋 Indholdsfortegnelse

- [Oversigt](#-oversigt)
- [Hovedfunktionalitet](#-hovedfunktionalitet)
- [Arkitektur](#-arkitektur)
- [Installation](#-installation)
- [Konfiguration](#-konfiguration)
- [Brug](#-brug)
- [Projektstruktur](#-projektstruktur)
- [Dokumentation](#-dokumentation)
- [Udvikling](#-udvikling)
- [Tests](#-tests)

---

## 🎯 Oversigt

KM24 Vejviser er en FastAPI-baseret applikation der hjælper journalister med at oprette datadrevne efterforskningsstrategier ved at:

1. **Modtage** et journalistisk mål fra brugeren
2. **Analysere** målet intelligent og foreslå relevante KM24-moduler
3. **Generere** en detaljeret "opskrift" med filtre, søgestrenge og pædagogisk vejledning
4. **Validere** og berige opskriften med live data fra KM24 API
5. **Præsentere** resultatet i en brugervenlig web-interface

Systemet bruger **Anthropic Claude 3.5 Sonnet** til intelligent analyse og **Knowledge Base pre-selection** til at optimere modul-valget.

---

## ⚡ Hovedfunktionalitet

### 1. Intelligent Modul-Selektion
- **Pre-analyse** af brugerens mål før LLM-kald
- **Relevans-scoring** baseret på:
  - Ekstraherede termer (10 point per match)
  - Tekst-overlap (max 50 point)
  - Prioritets-boost (5 bonus point)
- Reducerer prompt fra ~20 til 7 mest relevante moduler

### 2. Live API-Validering
- Validerer alle filtre mod KM24 API i realtid
- Auto-retter ugyldige filterværdier
- Tilføjer kritiske branchekoder automatisk
- Intelligent cache-system (7 dages levetid)

### 3. Pædagogisk Berigelse
- Kontekst-aware vejledning for hvert trin
- Module-specifikke tips og red flags
- CVR-first pipeline principper
- Forventede hit-volumener og kvalitetstjek

### 4. Robust Fejlhåndtering
- Fallback til cached data ved API-fejl
- Retry-mekanisme med exponential backoff
- Detaljeret fejl-logging og user-facing fejlmeddelelser

---

## 🏗️ Arkitektur

```
┌─────────────┐
│   Browser   │ ← User Interface (index_new.html)
└──────┬──────┘
       │ HTTP POST /generate_recipe
       ↓
┌─────────────────────────────────────────────────────┐
│                    FastAPI App                       │
│                    (main.py)                         │
├──────────────────────────────────────────────────────┤
│  1. Startup: Load filters & knowledge base          │
│  2. Receive goal from user                          │
│  3. Intelligent module pre-selection                │
│  4. Build focused system prompt                     │
│  5. Call LLM (Anthropic Claude)                     │
│  6. Validate & enrich recipe                        │
│  7. Return completed JSON recipe                    │
└───────┬──────────────────────────┬──────────────────┘
        │                          │
        ↓                          ↓
┌───────────────┐          ┌─────────────────┐
│  KnowledgeBase│          │ Recipe Processor│
│ (pre-selection)│          │  (enrichment)   │
└────────┬──────┘          └────────┬────────┘
         │                          │
         └──────────┬───────────────┘
                    ↓
          ┌──────────────────┐
          │   KM24 API Client │
          │   (validation)    │
          └─────────┬─────────┘
                    │
                    ↓
          ┌──────────────────┐
          │    KM24 API      │
          │  (live data)     │
          └──────────────────┘
```

### Nøglekomponenter

| Komponent | Fil | Ansvar |
|-----------|-----|--------|
| **API Server** | `main.py` | FastAPI endpoints, routing, LLM-kald |
| **Recipe Processor** | `recipe_processor.py` | Validering, berigelse, filtrering |
| **KM24 Client** | `km24_client.py` | API-kommunikation, caching |
| **Knowledge Base** | `knowledge_base.py` | Modul-selektion, relevans-scoring |
| **Filter Catalog** | `filter_catalog.py` | Filter-validering, anbefalinger |
| **Content Library** | `content_library.py` | Pædagogisk indhold |
| **Module Validator** | `module_validator.py` | Modul-metadata, validering |
| **Enrichment** | `enrichment.py` | Step-by-step berigelse |

---

## 🚀 Installation

### Forudsætninger

- Python 3.12 eller nyere
- pip eller poetry
- Virtuel environment (anbefalet)

### Trin-for-Trin

1. **Klon repository:**
```bash
git clone <repository-url>
cd km24_vejviser
```

2. **Opret virtuel environment:**
```bash
python -m venv venv
source venv/bin/activate  # På Windows: venv\Scripts\activate
```

3. **Installer afhængigheder:**
```bash
pip install -r km24_vejviser/requirements.txt
```

Eller brug requirements.lock for eksakte versioner:
```bash
pip install -r requirements.lock
```

4. **Konfigurer environment-variabler** (se næste sektion)

5. **Start applikationen:**
```bash
uvicorn km24_vejviser.main:app --reload --port 8000
```

6. **Åbn browser:**
```
http://localhost:8000
```

---

## ⚙️ Konfiguration

### Environment-Variabler

Opret en `.env` fil i `km24_vejviser/` mappen:

```env
# Anthropic Claude API (påkrævet for AI-funktionalitet)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# KM24 API (påkrævet for validering og live data)
KM24_API_KEY=your_km24_api_key_here

# Valgfri konfiguration
KM24_BASE=https://km24.dk/api
```

### Hvordan får jeg API-nøgler?

- **Anthropic API Key:** [https://console.anthropic.com/](https://console.anthropic.com/)
- **KM24 API Key:** Kontakt KM24 support

### Sikkerhed

⚠️ **VIGTIGT:** Commit ALDRIG `.env` filen til git. Den er allerede i `.gitignore`.

---

## 💻 Brug

### Web Interface

1. Åbn `http://localhost:8000` i din browser
2. Indtast dit journalistiske mål, f.eks.:
   - "Overvåg transport-virksomheder i Trekantsområdet der får arbejdsmiljø-påbud"
   - "Find konkursryttere i byggebranchen"
3. Klik "Generér Opskrift"
4. Gennemgå den genererede strategi med:
   - Undersøgelsespipeline (step-by-step guide)
   - Filtre og søgestrenge
   - Pædagogisk vejledning
   - AI-vurdering af strategien

### API Endpoints

#### POST `/generate_recipe`
Generér en KM24-opskrift baseret på brugerens mål.

**Request:**
```json
{
  "goal": "Overvåg transport-virksomheder med arbejdsmiljø-påbud"
}
```

**Response:**
```json
{
  "title": "Transport-virksomheder med arbejdsmiljø-påbud",
  "steps": [...],
  "context": {...},
  "ai_assessment": {...},
  "educational_content": {...}
}
```

#### GET `/health`
Tjek applikationens sundhedsstatus.

#### GET `/api/km24/status`
Få status på KM24 API forbindelse og cache.

---

## 📁 Projektstruktur

```
km24_vejviser/
├── km24_vejviser/              # Hovedapplikation
│   ├── main.py                 # FastAPI app & endpoints
│   ├── recipe_processor.py     # Recipe validering & berigelse
│   ├── km24_client.py          # KM24 API client
│   ├── knowledge_base.py       # Intelligent modul-selektion
│   ├── filter_catalog.py       # Filter validering & anbefalinger
│   ├── enrichment.py           # Step-by-step berigelse
│   ├── content_library.py      # Pædagogisk indhold
│   ├── module_validator.py     # Modul metadata & validering
│   ├── models/                 # Pydantic data models
│   │   └── usecase_response.py
│   ├── templates/              # HTML templates
│   │   └── index_new.html      # Frontend UI
│   ├── tests/                  # Test suite
│   │   ├── test_*.py           # Unit & integration tests
│   │   └── conftest.py         # Test configuration
│   └── cache/                  # API cache (auto-generated)
├── docs/                       # Dokumentation
│   ├── PROJECT_ARCHITECTURE.md
│   ├── API_DOKUMENTATION.md
│   └── ...
├── README.md                   # Denne fil
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Test configuration
└── .env                        # Environment variables (ikke i git)
```

---

## 📚 Dokumentation

### Detaljeret Dokumentation

- **[Projekt Arkitektur](docs/PROJECT_ARCHITECTURE.md)** - Dyb gennemgang af systemdesign
- **[API Dokumentation](docs/API_DOKUMENTATION.md)** - Endpoint dokumentation
- **[Intelligent Module Selection](INTELLIGENT_MODULE_SELECTION.md)** - Pre-selection system
- **[CLAUDE.md](CLAUDE.md)** - AI assistant instruktioner

### Teknisk Baggrund

- **LLM Integration:** Anthropic Claude 3.5 Sonnet med struktureret JSON output
- **Cache Strategy:** 7-dages cache med automatic refresh og fallback
- **Error Handling:** Multi-layer fejlhåndtering med graceful degradation
- **Type Safety:** Pydantic models for data validation
- **Testing:** 110+ tests med 84% pass rate

---

## 🛠️ Udvikling

### Setup Development Environment

1. Installer development dependencies:
```bash
pip install -r km24_vejviser/requirements.txt
pip install pytest pytest-asyncio black ruff
```

2. Kør tests:
```bash
pytest km24_vejviser/tests/
```

3. Kør linting:
```bash
ruff check km24_vejviser/
```

4. Format kode:
```bash
black km24_vejviser/
```

### Code Style

- **Formatter:** Black (line length: 100)
- **Linter:** Ruff
- **Type Checking:** Python type hints
- **Docstrings:** Google style

### Git Workflow

1. Opret feature branch
2. Lav ændringer
3. Kør tests: `pytest`
4. Commit med beskrivende message
5. Push og opret Pull Request

---

## 🧪 Tests

### Kør Tests

```bash
# Alle tests
pytest km24_vejviser/tests/

# Specifik test-fil
pytest km24_vejviser/tests/test_main.py

# Med coverage
pytest --cov=km24_vejviser km24_vejviser/tests/

# Verbose output
pytest -v km24_vejviser/tests/
```

### Test Coverage

Projektet har omfattende test coverage:

| Kategori | Tests | Status |
|----------|-------|--------|
| API Integration | 3 | ✅ |
| Deterministic Logic | 18 | ✅ |
| Educational Content | 20 | ✅ |
| Frontend Compatibility | 1 | ✅ |
| KM24 Validation | 11 | ✅ |
| Knowledge Base | 3 | ✅ |
| Normalization | 9 | ✅ |
| **Total** | **110** | **92 passing** |

---

## 🤝 Bidrag

Bidrag er velkomne! Læs venligst [CONTRIBUTING.md](CONTRIBUTING.md) for detaljer om vores code of conduct og proces for at indsende pull requests.

---

## 📄 Licens

Dette projekt er licenseret under MIT License - se [LICENSE](LICENSE) filen for detaljer.

---

## 🙏 Anerkendelser

- **KM24** for deres omfattende API og datakatalog
- **Anthropic** for Claude 3.5 Sonnet
- **FastAPI** community for deres fremragende framework
- **Alle bidragydere** der har hjulpet med at forbedre projektet

---

## 📞 Support

Har du spørgsmål eller problemer?

- **Issues:** Opret en issue på GitHub
- **Email:** [Din email]
- **Dokumentation:** Se `docs/` mappen

---

**Sidst opdateret:** Oktober 2025  
**Version:** 1.0.0  
**Python Version:** 3.12+

