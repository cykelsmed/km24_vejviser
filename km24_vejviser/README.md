# KM24 Vejviser (Version 3.4)

En avanceret, pædagogisk assistent, der lærer journalister at mestre KM24-overvågningsplatformen med dynamisk filter-anbefaling.

## Formål

KM24 Vejviser er en specialiseret datajournalistisk sparringspartner. Værktøjet tager et komplekst journalistisk mål formuleret i naturligt sprog (f.eks. "Jeg vil undersøge store byggeprojekter i Aarhus og konkurser i byggebranchen") og genererer en struktureret, trin-for-trin efterforskningsplan i JSON-format med dynamisk filter-anbefaling.

Vejviserens primære mål er ikke kun at levere en løsning, men at **undervise brugeren** i at tænke som en ekspert-researcher ved at demonstrere og forklare avancerede teknikker.

## Kernefunktioner

- **Struktureret JSON Output:** Genererer en robust og forudsigelig JSON-plan, der let kan integreres med andre systemer.
- **Dynamisk Filter-Anbefaling:** Automatisk generering af relevante filtre (geografi, branchekoder, perioder, beløbsgrænser) baseret på målbeskrivelsen.
- **Pædagogisk Design:** Hvert trin i planen indeholder et `rationale`, en `strategic_note` og en `explanation`, der forklarer de strategiske og tekniske overvejelser.
- **Avanceret Videnbase:** Indeholder en dybdegående YAML-baseret videnbase om:
    - 45 officielle KM24-moduler.
    - Avanceret søgesyntaks (`~frase~`, `~ord`, `;`).
    - Strategiske principper for kilde- og branchefiltrering.
    - "Power-user" teknikker som `Hitlogik` og `+1`-tricket til parallelle overvågninger.
    - Almindelige fejlkilder og løsninger.
- **Robust Arkitektur:** Backend-logik validerer og kompletterer AI-modellens output for at garantere, at alle pædagogiske felter altid er til stede i det endelige svar.
- **Moderne Web UI:** En ren og simpel brugerflade bygget med FastAPI og Pico.css, der inkluderer "kopiér"-knapper og klikbare inspirations-prompts.

## Projektstruktur

```
km24_vejviser/
├── km24_vejviser/          # Hovedpakke
│   ├── __init__.py
│   ├── main.py             # FastAPI applikation og LLM integration
│   ├── km24_client.py      # KM24 API klient
│   ├── filter_catalog.py   # Dynamisk filter-anbefaling
│   ├── module_validator.py # Modul validering
│   ├── models/             # Pydantic modeller
│   ├── templates/          # HTML templates
│   └── cache/              # Cache filer
├── tests/                  # Testfiler
│   ├── __init__.py
│   ├── test_main.py
│   ├── test_km24_validation.py
│   ├── test_km24_syntax.py
│   └── ...
├── requirements.txt        # Python afhængigheder
├── pytest.ini            # Pytest konfiguration
└── README.md             # Denne fil
```

## JSON Output – Eksempel

Et typisk svar fra Vejviseren indeholder nu følgende felter med dynamiske filtre:

```json
{
  "overview": {
    "title": "Undersøgelse af nye virksomheder i Aarhus",
    "strategy_summary": "Systematisk overvågning af nye virksomheder i Aarhus med fokus på ejendom og byggeri."
  },
  "steps": [
    {
      "step_number": 1,
      "title": "Basis virksomhedsovervågning",
      "type": "search",
      "module": {
        "id": "registrering",
        "name": "Registrering",
        "is_web_source": false
      },
      "rationale": "Etabler grundlæggende overvågning af nye virksomheder",
      "search_string": "ejendomsselskab;ejendomsudvikling;real_estate",
      "filters": {
        "geografi": ["Aarhus"],
        "branchekode": ["68.2", "68.3"],
        "region": ["midtjylland"],
        "periode": "24 mdr",
        "beløbsgrænse": "1000000"
      },
      "notification": "løbende",
      "delivery": "email"
    }
  ],
  "next_level_questions": [
    "Hvilke brancher dominerer blandt nye virksomheder i Aarhus?",
    "Er der sammenhæng mellem byggesager og nye virksomheder?"
  ],
  "potential_story_angles": [
    "Byudvikling: Nye virksomheder som indikator for byens udvikling",
    "Brancheanalyse: Hvilke sektorer vokser i Aarhus?"
  ]
}
```

**Nye Filter-felter:**
- `geografi`: Automatisk anbefalede kommuner baseret på mål
- `branchekode`: Relevante branchekoder for emnet
- `region`: Geografisk region
- `periode`: Standard overvågningsperiode
- `beløbsgrænse`: Beløbsgrænse for relevante transaktioner

## Opsætning og Installation

Følg disse trin for at køre projektet lokalt:

**1. Klon Repository'et**
```bash
git clone <repository-url>
cd <projekt-mappe>
```

**2. Opret og Aktivér et Virtuelt Miljø**
```bash
python3 -m venv .venv
source .venv/bin/activate
```
*På Windows, brug `.venv\Scripts\activate`*

**3. Installér Afhængigheder**
Fra projektets rodmappe, kør:
```bash
pip install -r km24_vejviser/requirements.txt
```
`pytest-asyncio` er inkluderet i `requirements.txt` for at understøtte `@pytest.mark.asyncio` tests.

**4. Konfigurér API Nøgle**
Opret en fil ved navn `.env` inde i `km24_vejviser`-mappen. Filen skal indeholde din Anthropic API nøgle:
```
ANTHROPIC_API_KEY="din_api_nøgle_her"
```

**5. Kør Applikationen**
Fra projektets rodmappe, kør:
```bash
uvicorn km24_vejviser.main:app --reload --port 8001
```
Applikationen vil nu være tilgængelig på `http://127.0.0.1:8001`.

## Testning

Projektet indeholder omfattende tests organiseret i `tests/` mappen:

**Kør alle tests:**
```bash
pytest
```

**Kør specifikke tests:**
```bash
pytest tests/test_km24_validation.py
pytest tests/test_main.py
```

**Kør tests med detaljeret output:**
```bash
pytest -v
```

## API Endpoints

### Hovedendpoints
- `POST /generate-recipe/` - Generer efterforskningsplan
- `GET /health` - Health check
- `GET /api/km24-status` - KM24 API status

### Filter-katalog endpoints
- `GET /api/filter-catalog/status` - Status for filter-katalog
- `POST /api/filter-catalog/recommendations` - Få filter-anbefalinger
- `GET /api/filter-catalog/municipalities` - Kommuner
- `GET /api/filter-catalog/branch-codes` - Branchekoder
- `DELETE /api/clear-cache` - Ryd cache

## Udvikling

### Tilføj nye tests
1. Opret ny testfil i `tests/` mappen
2. Brug `test_` prefix for filnavn
3. Brug `Test` prefix for klasser
4. Brug `test_` prefix for funktioner

### Opdater filter-katalog
Filter-anbefalinger kan opdateres i `filter_catalog.py`:
- Tilføj nye relevans-nøgleord
- Opdater testdata
- Tilføj nye filter-typer

## Fejlfinding

**Problem:** "ModuleNotFoundError: No module named 'km24_vejviser'"
**Løsning:** Kør fra projektets rodmappe, ikke fra `km24_vejviser/` mappen

**Problem:** Tests fejler med import fejl
**Løsning:** Tests er nu organiseret i `tests/` mappen med korrekte imports

**Problem:** Filter-anbefalinger virker ikke
**Løsning:** Tjek `/api/filter-catalog/status` for at se om filter-data er indlæst

## Licens

Dette projekt er udviklet til intern brug i journalistisk kontekst. 