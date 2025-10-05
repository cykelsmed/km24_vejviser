"""
KM24 Vejviser: En intelligent assistent til journalister.

Dette FastAPI-program fungerer som backend for "KM24 Vejviser".
Det leverer en web-brugerflade, modtager et journalistisk mål,
og bruger Anthropic's Claude 3.5 Sonnet-model til at generere en
strategisk "opskrift" i et struktureret JSON-format.

Arkitekturen er designet til at være robust:
1.  En detaljeret systemprompt instruerer modellen til at returnere et JSON-objekt.
2.  Backend-koden kalder modellen og venter på det fulde svar.
3.  Svaret valideres og kompletteres programmatisk for at sikre, at kritiske
    pædagogiske felter altid er til stede.
4.  Det endelige, komplette JSON-objekt sendes til frontend for rendering.
"""
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, validator
import anthropic
from dotenv import load_dotenv
from pathlib import Path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import asyncio
import json
import logging
import re
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Any, List, Dict

# KM24 API Integration
from .km24_client import get_km24_client, KM24APIResponse, KM24APIClient
from .module_validator import get_module_validator, ModuleMatch
from .models.usecase_response import UseCaseResponse, ModuleRef
from .filter_catalog import get_filter_catalog

# Load environment variables from .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Konfigurer struktureret logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
logger = logging.getLogger("km24_vejviser")

# --- Configure Anthropic API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = None
if not ANTHROPIC_API_KEY or "YOUR_API_KEY_HERE" in ANTHROPIC_API_KEY:
    print("ADVARSEL: ANTHROPIC_API_KEY er ikke sat i .env. Applikationen vil ikke kunne kontakte Claude.")
else:
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Initialize FastAPI app and Templates
app = FastAPI(
    title="KM24 Vejviser",
    description="En intelligent assistent til at skabe effektive overvågnings-opskrifter for KM24-platformen.",
    version="1.0.r",
)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Intelligent pre-caching ved opstart ---
from .filter_catalog import get_filter_catalog  # tilføj import tæt på toppen

@app.on_event("startup")
async def startup_event() -> None:
    """Indlæs og cachér alle filter-data én gang ved applikationens opstart."""
    try:
        logger.info("Application startup: Pre-caching filterdata fra KM24 API …")
        fc = get_filter_catalog()
        status = await fc.load_all_filters(force_refresh=True)
        logger.info(f"Pre-caching færdig: {status}")
    except Exception as e:
        logger.error(f"Fejl under pre-caching ved startup: {e}")

# --- Data Models ---
class RecipeRequest(BaseModel):
    """Data model for indkommende anmodninger fra brugerfladen.

    Eksempel:
        {
            "goal": "Undersøg store byggeprojekter i Aarhus og konkurser i byggebranchen"
        }
    """
    goal: str = Field(
        ..., min_length=10, max_length=1000, description="Journalistisk mål",
        example="Undersøg store byggeprojekter i Aarhus og konkurser i byggebranchen"
    )

    @validator('goal')
    def validate_goal(cls, v):
        if not v or not v.strip():
            raise ValueError('Mål kan ikke være tomt eller kun whitespace')
        return v.strip()

# --- Helper Functions ---
def clean_json_response(raw_response: str) -> str:
    """
    Ekstrahér JSON-indhold fra et Claude-svar, selv hvis det er indlejret i
    markdown-codefence (```json ... ```) eller har præfikstekst før/efter.

    Args:
        raw_response: Den rå tekst fra modellen

    Returns:
        En streng, der forventes at være valid JSON eller så tæt på som muligt
        (mellem første '{' og sidste '}' hvis nødvendigt).
    """
    text = (raw_response or "").strip()

    # 1) Forsøg at finde ```json ... ```-blok
    if "```json" in text:
        try:
            start_marker = text.find("```json")
            if start_marker != -1:
                start = text.find("\n", start_marker)
                if start != -1:
                    start += 1
                    end = text.find("```", start)
                    if end != -1:
                        return text[start:end].strip()
        except Exception:
            pass

    # 2) Generisk ``` ... ```-blok
    if text.count("```") >= 2:
        try:
            first = text.find("```")
            if first != -1:
                start = text.find("\n", first)
                if start != -1:
                    start += 1
                    end = text.find("```", start)
                    if end != -1:
                        return text[start:end].strip()
        except Exception:
            pass

    # 3) Fald tilbage: Tag substring mellem første '{' og sidste '}'
    left = text.find("{")
    right = text.rfind("}")
    if left != -1 and right != -1 and right > left:
        return text[left : right + 1]

    # 4) Som sidste udvej, returnér original tekst
    return text

async def build_system_prompt(goal: str, modules_data: dict) -> str:
    """
    Build simplified system prompt using live API module data.

    Args:
        goal: The user's journalistic goal
        modules_data: Raw module data from KM24 API (get_modules_basic)

    Returns:
        Complete system prompt as string (~120 lines instead of 600)
    """
    # Extract just the essentials from API data
    # Use compact format to reduce token usage
    # IMPORTANT: Prioritize critical modules (Registrering, Status) for CVR-first approach
    all_modules = modules_data.get('items', [])

    # Priority modules that should always be included
    priority_names = {'Registrering', 'Status', 'Tinglysning', 'Arbejdstilsyn',
                     'Lokalpolitik', 'Retslister', 'Domme', 'Personbogen'}

    # Separate priority and other modules
    priority_modules = [m for m in all_modules if m.get('title') in priority_names]
    other_modules = [m for m in all_modules if m.get('title') not in priority_names]

    # Combine: priority first, then others (total ~20 modules)
    selected_modules = priority_modules + other_modules[:12]

    # Get KM24 client for fetching generic values
    km24_client = get_km24_client()
    
    # Define critical modules that need generic values enrichment
    critical_modules_for_values = {'Arbejdstilsyn', 'Status'}

    simplified_modules = []
    for module in selected_modules:
        module_title = module.get('title', '')
        module_id = module.get('id')
        parts = module.get('parts', [])
        
        # Build available_filters list with values for critical modules
        available_filters = []
        
        for part in parts:
            part_name = part.get('name', '')
            if not part_name:
                continue
            
            part_type = part.get('part')
            part_id = part.get('id')
            
            # For critical modules with generic_value parts, fetch actual values
            if (module_title in critical_modules_for_values and 
                part_type == 'generic_value' and 
                part_id):
                try:
                    values_response = await km24_client.get_generic_values(part_id, force_refresh=False)
                    if values_response.success:
                        items = values_response.data.get('items', [])
                        values = [item.get('name', '').strip() for item in items if item.get('name')]
                        if values:
                            # Include values for this filter
                            available_filters.append({
                                'name': part_name,
                                'values': values[:20]  # Limit to 20 values to save tokens
                            })
                        else:
                            # No values, just include name
                            available_filters.append({'name': part_name})
                    else:
                        # API call failed, just include name
                        available_filters.append({'name': part_name})
                except Exception as e:
                    logger.warning(f"Failed to fetch generic values for {module_title}.{part_name}: {e}")
                    available_filters.append({'name': part_name})
            else:
                # For non-critical modules or non-generic_value parts, just include name
                available_filters.append({'name': part_name})
        
        simplified_modules.append({
            'title': module_title,
            'description': module.get('shortDescription', ''),
            'available_filters': available_filters
        })

    # Format modules as compact JSON (still single line, but more informative)
    modules_json = json.dumps(simplified_modules, ensure_ascii=False, separators=(',', ':'))

    prompt = f"""Du er Vejviser, en KM24-ekspert der hjælper journalister med at planlægge datadrevne efterforskninger.

**BRUGERENS MÅL:**
{goal}

**TILGÆNGELIGE MODULER (fra live KM24 API):**
{modules_json}

**DIN OPGAVE:**
1. Vælg 3-5 relevante moduler fra listen ovenfor baseret på brugerens mål
2. VIGTIGT: Hvis målet handler om virksomheder, START ALTID med "Registrering" modul (branchekoder)
3. For hvert modul, brug filter-navne fra "available_filters" listen
4. Forklar strategien kort og pædagogisk, med fokus på CVR-pipeline hvor relevant

**VIGTIGE PRINCIPPER:**
- KM24 er en OVERVÅGNINGSTJENESTE - brug formuleringer som "opsæt overvågning NÅR..." ikke "find sager"
- Brug KUN filter-navne fra modulets "available_filters" liste
- KRITISK: For filtre med en 'values' liste, SKAL du bruge én eller flere af disse EKSAKTE værdier
  Eksempel: Arbejdstilsyn Problem har values → brug "Asbest", "Støj", etc. (præcist som angivet)
  Eksempel: Arbejdstilsyn Reaktion har values → brug "Forbud", "Påbud", etc. (præcist som angivet)
- For filtre uden 'values' liste:
  - Kommune-filtre: brug konkrete kommuner (fx "Aarhus", "København")
  - Branche-filtre: brug branchekoder (fx "41.20", "49.41")
  - Andre filtre: skriv logiske værdier, vi validerer dem bagefter via API
- VIGTIGT: Brug ALDRIG engelske type-navne som "municipality", "industry", "generic_value" som filter-nøgler

**SØGESTRENG SYNTAKS (når "Søgeord" filter er tilgængeligt):**
- Boolean operatorer: AND, OR, NOT (ALTID store bogstaver - ALDRIG lowercase!)
- Parallelle variationer: semikolon ; (ikke komma)
  Eksempel: landbrug;landbrugsvirksomhed;agriculture
  Eksempel: vindmølle;vindenergi;vindkraft
- Kombineret: vindmølle;vindenergi AND lokalplan OR godkendelse
- Eksakt frase: ~kritisk sygdom~ (tildes omkring)
- Positionel søgning: ~parkering (prefix tilde)
- Foreslå ALTID søgestrenge når modulet har "Søgeord" i available_filters

**JOURNALISTISKE STRATEGIER:**

**CVR FØRST-PRINCIP (vigtigt!):**
- START med Registrering: Identificer virksomheder via branchekoder (ikke søgeord!)
- DEREFTER overvåg: Brug CVR-numre fra step 1 i andre moduler (Arbejdstilsyn, Status, Tinglysning)
- Pipeline: Find aktører (Registrering) → Overvåg aktiviteter (fagmoduler) → Krydsreference

**MODULKOMBINATIONER (kritiske cases):**
- Interessekonflikter/politikere → Lokalpolitik + Personbogen + Tinglysning
- Konkursryttere (samme personer, gentagne konkurser) → Status + Registrering + Personbogen
- Social dumping/dårlige arbejdsforhold → Arbejdstilsyn + Retslister + Status
- Systematisk svindel → Regnskaber + Domme + Status

**NOTIFIKATIONSGUIDE:**
- "løbende": Få, kritiske hits (Tinglysning >50 mio., Arbejdstilsyn Forbud/Strakspåbud)
- "interval": Mange hits, mindre tidskritiske (Registrering, Lokalpolitik, Danske medier)

**BRANCHEMAPPING (eksempler):**
Byggeri → Branchekoder: 41.20 (Bygninger), 43.11 (Nedrivning), 43.99 (Specialiseret byggeri)
         Arbejdstilsyn Problem: Stilladser, Nedstyrtningsfare, Asbest
Fødevare → Branchekoder: 10.11 (Kød), 10.51 (Mejeri), 10.71 (Bagning)
          Arbejdstilsyn Problem: Fødevaresikkerhed, Hygiejne
Landbrug → Branchekoder: 01.11 (Korn), 01.21 (Druer), 01.41 (Mælkeproduktion)
Transport → Branchekoder: 49.41 (Godstransport), 49.42 (Flytning)

**VIGTIGT - FOKUS PÅ STRATEGI, IKKE SYNTAX:**
Du skal IKKE inkludere:
- ❌ Søgestreng syntaksguider (vi tilføjer automatisk)
- ❌ Generelle common pitfalls eller troubleshooting (vi tilføjer automatisk)
- ❌ Quality checklists eller "husk at tjekke" lister (vi tilføjer automatisk per modul)
- ❌ Generelle KM24-principper forklaringer (vi tilføjer automatisk)

Du skal UDELUKKENDE fokusere på:
- ✅ Den SPECIFIKKE strategi for DENNE efterforskning
- ✅ HVORFOR disse moduler og filtre er valgt til DETTE mål
- ✅ Pædagogisk forklaring af tilgangen (rationale, explanation)
- ✅ Case-specifikke insights og journalistisk vinkling

**OUTPUT FORMAT (strict JSON):**
{{
  "title": "Kort titel for efterforskningen",
  "strategy_summary": "2-3 sætninger der forklarer den overordnede strategi og tilgang",
  "investigation_steps": [
    {{
      "step": 1,
      "title": "Beskrivende titel for dette trin",
      "module": "Arbejdstilsyn",
      "rationale": "Hvorfor dette modul? Hvorfor disse filtre? Hvad lærer brugeren?",
      "filters": {{
        "Problem": ["Asbest", "Stilladser"],
        "Kommune": ["Aarhus"]
      }},
      "recommended_notification": "løbende",
      "explanation": "Hvordan bruges dette trin konkret i KM24?"
    }},
    {{
      "step": 2,
      "title": "Næste trin",
      "module": "Arbejdstilsyn",
      "rationale": "Filtrer på reaktionstype for at fange de mest alvorlige sager",
      "filters": {{
        "Problem": ["Asbest"],
        "Reaktion": ["Forbud", "Strakspåbud"]
      }},
      "recommended_notification": "løbende",
      "explanation": "Fokuser på kritiske reaktioner fra Arbejdstilsynet"
    }},
    {{
      "step": 3,
      "title": "Medieopmærksomhed",
      "module": "Danske medier",
      "filters": {{
        "Medie": [],
        "Søgeord": ["asbest;asbestsag AND byggeri;entreprenør OR nedrivning"]
      }},
      "recommended_notification": "interval",
      "explanation": "Vælg lokale Aarhus-medier i Medie-filteret. Søgestrengen fanger variationer af asbest kombineret med byggerelaterede ord."
    }}
  ],
  "next_level_questions": [
    "Provokerende spørgsmål 1 der udvider efterforskningen",
    "Provokerende spørgsmål 2 der udfordrer antagelser"
  ],
  "potential_story_angles": [
    "Konkret historievinkel baseret på strategien",
    "Uventet sammenhæng der kan afdækkes"
  ]
}}

**KRITISKE REGLER:**
1. Modul-navne skal PRÆCIST matche "title" fra TILGÆNGELIGE MODULER
2. Filter-nøgler skal matche navne fra modulets "available_filters" liste
3. Alle filter-værdier skal være arrays (selv hvis kun én værdi)
4. Skriv logiske filter-værdier - vi validerer dem bagefter via API
5. "recommended_notification" skal være enten "løbende" (få kritiske hits) eller "interval" (mange hits)
6. Fokusér på HVORFOR og pædagogik i rationale, ikke tekniske detaljer
7. Brug konkrete eksempler og konkrete værdier (ikke generiske begreber)

**EKSEMPEL PÅ KORREKT CVR-PIPELINE:**
Mål: "Overvåg byggevirksomheder med asbest-problemer i Aarhus"

{{
  "title": "Asbest-risiko i Aarhus' byggeri",
  "strategy_summary": "CVR-først approach: Identificer byggevirksomheder i Aarhus, overvåg asbest-kritik, og track konkurser.",
  "investigation_steps": [
    {{
      "step": 1,
      "title": "Identificer byggevirksomheder",
      "module": "Registrering",
      "filters": {{"Branche": ["41.20", "43.11"], "Kommune": ["Aarhus"]}},
      "rationale": "CVR FØRST: Find alle bygge/nedrivningsvirksomheder i Aarhus via branchekoder",
      "recommended_notification": "interval"
    }},
    {{
      "step": 2,
      "title": "Overvåg asbest-kritik",
      "module": "Arbejdstilsyn",
      "filters": {{"Problem": ["Asbest"], "Kommune": ["Aarhus"]}},
      "rationale": "Find Arbejdstilsynets asbest-kritik af byggevirksomheder",
      "recommended_notification": "løbende"
    }},
    {{
      "step": 3,
      "title": "Track konkurser",
      "module": "Status",
      "filters": {{"Virksomhed": []}},
      "rationale": "Overvåg om kritiserede virksomheder går konkurs",
      "explanation": "Tilføj CVR-numre fra step 1+2",
      "recommended_notification": "løbende"
    }},
    {{
      "step": 4,
      "title": "Lokalplanændringer",
      "module": "Lokalpolitik",
      "filters": {{"Kommune": ["Aarhus"], "Søgeord": ["asbest;asbestsanering OR nedrivning;nedriver"]}},
      "rationale": "Fang politiske beslutninger om asbestsanering og nedrivning",
      "recommended_notification": "interval"
    }}
  ]
}}

**FORKERTE EKSEMPLER (undgå disse):**
❌ KRITISK: Step 1 bruger Arbejdstilsyn i stedet for Registrering til at identificere virksomheder
❌ Step 1 bruger søgeord i stedet for branchekoder i Registrering
❌ Filter key "municipality" - brug "Kommune" (fra available_filters)!
❌ Filter key "industry" - brug "Branche" (fra available_filters)!
❌ Step 2 kommer før step 1 (identificer virksomheder FØRST via Registrering)
❌ Alle steps bruger "løbende" - brug "interval" for Registrering (mange hits)
❌ Bruger Arbejdstilsynets Branche-filter til at "identificere" - det er IKKE det samme som CVR-data fra Registrering!
❌ Søgestreng med lowercase: "asbest and byggeri" - brug "asbest AND byggeri" (store bogstaver!)
❌ Søgestreng med komma: "asbest,asbestsag" - brug "asbest;asbestsag" (semikolon!)

Generér nu den komplette JSON-plan baseret på brugerens mål og de tilgængelige moduler.
"""

    return prompt


async def get_anthropic_response(goal: str) -> dict:
    """
    Kalder Anthropic API'en for at få en komplet JSON-plan.

    Funktionen sender den fulde systemprompt og brugerens mål til Claude,
    venter på det komplette svar og parser det som JSON.
    Implementerer en simpel retry-mekanisme for at håndtere midlertidige API-fejl.

    Args:
        goal: Det journalistiske mål fra brugeren.

    Returns:
        Et dictionary med det parsede JSON-svar fra Claude eller en fejlbesked.
    """
    if not client:
        return {"error": "ANTHROPIC_API_KEY er ikke konfigureret."}

    # Hent faktiske moduldata fra KM24 API
    km24_client: KM24APIClient = get_km24_client()
    modules_response = await km24_client.get_modules_basic()

    # Check if API call was successful
    if not modules_response.success or not modules_response.data:
        logger.error(f"Failed to fetch modules from API: {modules_response.error}")
        return {"error": f"Kunne ikke hente moduler fra KM24 API: {modules_response.error}"}

    # Build simplified system prompt using new API-first approach
    logger.info("Building simplified system prompt with API data...")
    full_system_prompt = await build_system_prompt(goal, modules_response.data)
    retries = 3
    delay = 2

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                system=full_system_prompt,
                messages=[
                    {"role": "user", "content": "Generér JSON-planen som anmodet."}
                ]
            )
            # Få fat i tekst-indholdet fra responsen
            raw_text = response.content[0].text
            logger.info(f"Anthropic API response received on attempt {attempt + 1}")

            cleaned = clean_json_response(raw_text)
            return json.loads(cleaned)

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error on attempt {attempt + 1}: {e}", exc_info=True)
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Anthropic API fejl efter {retries} forsøg: {e}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error on attempt {attempt + 1}: {e}", exc_info=True)
            logger.error(f"Raw response was: {locals().get('raw_text', '<no raw_text>')}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Kunne ikke parse JSON fra API'en. Svar: {locals().get('raw_text', '<no raw_text>')}"}
        except Exception as e:
            logger.error(f"Uventet fejl i get_anthropic_response på attempt {attempt + 1}: {e}", exc_info=True)
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Uventet fejl efter {retries} forsøg: {e}"}
    return {"error": "Ukendt fejl i get_anthropic_response."}


async def enrich_recipe_with_api(raw_recipe: dict) -> dict:
    """
    Validate and enrich Claude's recipe using live KM24 API data.

    This function:
    1. Validates module names exist in API
    2. Validates filter keys match module parts
    3. Validates filter values against FilterCatalog:
       - Municipality names (Kommune)
       - Branch codes (Branche)
       - Region names (Region)
       - Generic values from module-specific parts
    4. Returns enriched recipe with validated filters

    Args:
        raw_recipe: Raw JSON from Claude's response

    Returns:
        Enriched recipe with API-validated filters
    """
    km24_client: KM24APIClient = get_km24_client()
    enriched_steps = []

    # Get all modules for lookup
    modules_response = await km24_client.get_modules_basic()
    if not modules_response.success:
        logger.warning("Could not fetch modules for enrichment, returning raw recipe")
        return raw_recipe

    # Build module name to ID lookup
    module_lookup = {
        item.get('title', ''): int(item.get('id'))
        for item in modules_response.data.get('items', [])
        if item.get('id') is not None
    }

    for step in raw_recipe.get('investigation_steps', []):
        module_name = step.get('module', '')

        # Validate module exists
        module_id = module_lookup.get(module_name)
        if not module_id:
            logger.warning(f"Module '{module_name}' not found in API, skipping step {step.get('step')}")
            continue

        # Get module details to see available parts
        module_details_response = await km24_client.get_module_details(module_id)
        if not module_details_response.success:
            logger.warning(f"Could not fetch details for module {module_name}, using step as-is")
            enriched_steps.append({**step, 'module_id': module_id})
            continue

        module_parts = module_details_response.data.get('parts', [])

        # Build part name lookup (case-insensitive)
        parts_by_name = {
            part.get('name', '').lower(): part
            for part in module_parts
            if part.get('name')
        }

        # Validate and enrich filters
        validated_filters = {}
        raw_filters = step.get('filters', {})
        
        # Get FilterCatalog for value validation
        filter_catalog = get_filter_catalog()

        for filter_key, filter_values in raw_filters.items():
            # Find matching part (case-insensitive)
            matching_part = parts_by_name.get(filter_key.lower())

            if not matching_part:
                logger.warning(f"Filter '{filter_key}' not found in {module_name} parts, skipping")
                continue

            part_type = matching_part.get('part')
            part_id = matching_part.get('id')
            
            # Validate filter values against catalog
            validated_values = []
            
            # Normalize filter_key for comparison
            filter_key_lower = filter_key.lower()
            
            # Validate based on filter type
            if filter_key_lower == 'kommune':
                valid_municipalities = filter_catalog.get_all_municipality_names()
                for value in filter_values:
                    if value.lower() in valid_municipalities:
                        validated_values.append(value)
                    else:
                        logger.warning(f"Removed invalid municipality '{value}' for filter '{filter_key}' in module '{module_name}'")
            
            elif filter_key_lower == 'branche':
                valid_branch_codes = filter_catalog.get_all_branch_codes()
                for value in filter_values:
                    if value in valid_branch_codes:
                        validated_values.append(value)
                    else:
                        logger.warning(f"Removed invalid branch code '{value}' for filter '{filter_key}' in module '{module_name}'")
            
            elif filter_key_lower == 'region':
                valid_regions = filter_catalog.get_all_region_names()
                for value in filter_values:
                    if value.lower() in valid_regions:
                        validated_values.append(value)
                    else:
                        logger.warning(f"Removed invalid region '{value}' for filter '{filter_key}' in module '{module_name}'")
            
            # Handle generic_value parts - fetch and validate against API
            elif part_type == 'generic_value' and part_id:
                try:
                    valid_values = filter_catalog.get_valid_generic_values_for_part(part_id)
                    if not valid_values:
                        # Fallback to API call if not cached
                        values_response = await km24_client.get_generic_values(part_id)
                        if values_response.success:
                            valid_values = {
                                item.get('name', '').strip()
                                for item in values_response.data.get('items', [])
                                if item.get('name')
                            }
                    
                    if valid_values:
                        for value in filter_values:
                            if value in valid_values:
                                validated_values.append(value)
                            else:
                                logger.warning(f"Removed invalid value '{value}' for filter '{filter_key}' in module '{module_name}'")
                    else:
                        validated_values = filter_values  # No validation data available
                except Exception as e:
                    logger.error(f"Error validating generic values for {filter_key}: {e}")
                    validated_values = filter_values

            # Handle web_source parts - mark for manual selection
            elif part_type == 'web_source':
                validated_values = filter_values
                # Add note that user must select sources manually
                if 'details' not in step:
                    step['details'] = {}
                if 'strategic_note' not in step['details']:
                    step['details']['strategic_note'] = f"PÅKRÆVET: Vælg konkrete kilder manuelt for {module_name}"

            # Other filter types - accept as-is
            else:
                validated_values = filter_values
            
            # Add validated filter if it has values
            if validated_values:
                validated_filters[filter_key] = validated_values
            elif filter_values:
                logger.warning(f"All values removed for filter '{filter_key}' in module '{module_name}', skipping filter")

        # Add enriched step with validated filters and module_id
        enriched_steps.append({
            **step,
            'filters': validated_filters,
            'module_id': module_id
        })

    # Return enriched recipe
    return {
        **raw_recipe,
        'investigation_steps': enriched_steps
    }


async def generate_search_optimization(module_card, goal: str, step: dict) -> dict:
    """Generer optimal søgekonfiguration baseret på modul og mål."""
    try:
        optimization = {
            "for_module": module_card.title,
            "your_goal": goal[:50] + "..." if len(goal) > 50 else goal,
            "optimal_config": {},
            "rationale": ""
        }
        
        # Analyze goal for specific keywords
        goal_lower = goal.lower()
        
        # Smart recommendations based on available filters and goal
        config = {}
        rationale_parts = []
        
        # Industry recommendations
        industry_filters = [f for f in module_card.available_filters if f['type'] == 'industry']
        if industry_filters:
            if any(word in goal_lower for word in ['bygge', 'byggeri', 'construction']):
                config["branche"] = ["41.20.00", "43.11.00"]
                rationale_parts.append("Branchekoder for byggeri giver præcis targeting")
            elif any(word in goal_lower for word in ['energi', 'strøm', 'elektricitet']):
                config["branche"] = ["35.11.00", "35.12.00"]
                rationale_parts.append("Energibranchekoder fokuserer på relevante selskaber")
            elif any(word in goal_lower for word in ['transport', 'logistik', 'fragt']):
                config["branche"] = ["49.41.00", "52.29.90"]
                rationale_parts.append("Transport-branchekoder rammer målgruppen præcist")
        
        # Municipality recommendations
        municipality_filters = [f for f in module_card.available_filters if f['type'] == 'municipality']
        if municipality_filters:
            # Extract municipality names from goal
            dansk_kommuner = ['københavn', 'aarhus', 'odense', 'aalborg', 'esbjerg', 'randers', 'kolding']
            found_municipalities = [kom for kom in dansk_kommuner if kom in goal_lower]
            if found_municipalities:
                config["kommune"] = found_municipalities
                rationale_parts.append(f"Geografisk fokus på {', '.join(found_municipalities)}")
        
        # Amount recommendations
        amount_filters = [f for f in module_card.available_filters if f['type'] == 'amount_selection']
        if amount_filters:
            if any(word in goal_lower for word in ['store', 'større', 'million', 'mio']):
                config["amount_min"] = "10000000"
                rationale_parts.append("Beløbsgrænse fokuserer på større sager")
        
        # Search string optimization
        search_filters = [f for f in module_card.available_filters if f['type'] == 'search_string']
        if search_filters and config:
            config["search_terms"] = "empty"
            rationale_parts.append("Filtre er mere præcise end fri tekstsøgning")
        
        if config:
            optimization["optimal_config"] = config
            optimization["rationale"] = ". ".join(rationale_parts)
        else:
            optimization["rationale"] = "Brug modulets standardkonfiguration"
            
        return optimization
        
    except Exception as e:
        logger.error(f"Error in generate_search_optimization: {e}")
        return {}


def _get_default_sources_for_module(module_name: str) -> list[str]:
    """
    Get default source selection for web source modules.
    
    Returns appropriate default sources for modules that require source selection.
    """
    module_lower = module_name.lower()
    
    # Default sources for different web source modules
    if "lokalpolitik" in module_lower:
        return ["Aarhus", "København", "Odense", "Aalborg"]  # Major cities
    elif "danske medier" in module_lower:
        return ["DR", "TV2", "Berlingske", "Politiken", "Jyllands-Posten"]
    elif "udenlandske medier" in module_lower:
        return ["Reuters", "AFP", "AP", "Bloomberg"]
    elif "eu" in module_lower:
        return ["EU Commission", "European Parliament", "EU Council"]
    elif "forskning" in module_lower:
        return ["Aarhus University", "Copenhagen University", "DTU"]
    elif "klima" in module_lower:
        return ["Danish Meteorological Institute", "European Environment Agency"]
    elif "sundhed" in module_lower:
        return ["Danish Health Authority", "WHO", "European Medicines Agency"]
    elif "webstedsovervågning" in module_lower:
        return ["Government websites", "Municipal websites"]
    else:
        return []  # No default sources for unknown modules

# DEACTIVATED: This function causes incorrect search strings
# def _get_default_search_string_for_module(module_name: str) -> str:
#     """Get default search string for module."""
#     module_name_lower = module_name.lower()
#     
#     # Modules where empty search string is BETTER (when using CVR/company filter)
#     if module_name_lower in ["fødevaresmiley", "arbejdstilsyn", "status", "kapitalændring"]:
#         return ""  # Empty is better when using virksomhedsfilter
#     
#     if "registrering" in module_name_lower:
#         return "landbrug;landbrugsvirksomhed;agriculture"
#     elif "tinglysning" in module_name_lower:
#         return "~landbrugsejendom~"
#     elif "lokalpolitik" in module_name_lower:
#         return "lokalplan;landzone;kommunal"
#     elif "miljøsager" in module_name_lower:
#         return "miljøtilladelse;husdyrgodkendelse;udvidelse"
#     elif "regnskaber" in module_name_lower:
#         return "regnskab;årsrapport;økonomi"
#     elif "børsmeddelelser" in module_name_lower:
#         return "børsmeddelelse;årsrapport;økonomi"
#     elif "udbud" in module_name_lower:
#         return "offentligt udbud;kontrakt;vinder"
#     elif "personbogen" in module_name_lower:
#         return "person;ejer;bestyrelse"
#     else:
#         # Default for unknown modules: empty string
#         return ""

# NEW: Always return empty string - let LLM handle search strings
def _get_default_search_string_for_module(module_name: str) -> str:
    """
    Return empty search string by default.
    LLM should provide context-appropriate search strings.
    """
    return ""  # Always empty - no hardcoded defaults

def _normalize_notification(notification: str) -> str:
    """
    Normalize notification values from Danish to English.
    
    Maps Danish notification values to the expected English literals.
    """
    if not notification:
        return "daily"
    
    notification_lower = notification.lower().strip()
    
    # Map Danish to English
    if notification_lower in ["løbende", "øjeblikkelig", "instant"]:
        return "instant"
    elif notification_lower in ["interval", "periodisk", "weekly"]:
        return "weekly"
    else:
        return "daily"  # Default fallback

def _fix_operators_in_search_string(search_string: str) -> str:
    """Fix lowercase and Danish operators to uppercase in search strings."""
    if not search_string:
        return search_string
    
    fixed = search_string
    
    # Fix English operators
    fixed = re.sub(r'\band\b', 'AND', fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\bor\b', 'OR', fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\bnot\b', 'NOT', fixed, flags=re.IGNORECASE)
    
    # Fix Danish operators
    fixed = re.sub(r'\bog\b', 'AND', fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\beller\b', 'OR', fixed, flags=re.IGNORECASE)
    
    # Replace commas with semicolons (common variation syntax mistake)
    fixed = fixed.replace(',', ';')
    
    return fixed

def _standardize_search_string(search_string: str, module_name: str) -> str:
    """
    Standardize search strings according to KM24 syntax standards.
    
    Fixes syntax errors without replacing the semantic content.
    
    Args:
        search_string: The raw search string from LLM
        module_name: The module name (kept for backward compatibility)
    
    Returns:
        Corrected search string following KM24 conventions
    """
    if not search_string:
        return ""
    
    search_string = search_string.strip()
    
    # Apply general KM24 syntax improvements (phrase syntax, etc.)
    improved = _apply_km24_syntax_improvements(search_string)
    
    # Fix operators to uppercase and handle Danish operators
    return _fix_operators_in_search_string(improved)

def _apply_km24_syntax_improvements(search_string: str) -> str:
    """
    Apply general KM24 syntax improvements to search strings.
    
    Args:
        search_string: The raw search string
    
    Returns:
        Improved search string with KM24 syntax
    """
    if not search_string:
        return ""
    
    # Apply improvements more carefully to avoid breaking words
    result = search_string
    
    # Handle exact phrases first
    result = re.sub(r'"([^"]+)"', r'~\1~', result)
    
    # Handle variations
    result = re.sub(r'(\w+)\s*[-_]\s*(\w+)', r'\1;\1_\2', result)
    

    
    # Clean up multiple semicolons and spaces
    result = re.sub(r';+', ';', result)
    result = re.sub(r'\s+', ' ', result)
    result = result.strip('; ')
    
    # Fix operators to uppercase
    result = _fix_operators_in_search_string(result)
    
    return result

def _ensure_filters_before_search_string(step: dict, goal: str = "") -> dict:
    """
    Ensures that filters are present in the step before search_string.
    If not, it adds default filters based on dynamic filter recommendations.
    """
    logger.info(f"Ensuring filters for step: {step.get('title', 'Unknown')}")
    logger.info(f"Goal: {goal}")
    logger.info(f"Current filters: {step.get('filters', {})}")
    
    if "filters" not in step:
        step["filters"] = {}
    
    # NOTE: Dynamic filter addition is now handled by enrich_recipe_with_api()
    # Legacy logic removed

    logger.info(f"Final filters: {step['filters']}")
    return step

async def _enrich_with_module_specific_filters(step: dict, goal: str) -> dict:
    """Berig et step med parts-baserede filtre og kilder baseret på modul og mål.

    - Anvender KM24 parts (generic_value, web_source, amount_selection)
    - Tilføjer defaults hvor passende
    """
    try:
        if not step or not isinstance(step, dict):
            return step
        module_name = step.get("module", {}).get("name") if isinstance(step.get("module"), dict) else step.get("module")
        if not module_name:
            return step
        step.setdefault("filters", {})

        # Hent modul-kort for at se tilgængelige parts
        module_validator = get_module_validator()
        module_card = await module_validator.get_enhanced_module_card(module_name)
        if not module_card:
            return step

        # amount_selection default (beløbsgrænse) hvis part findes
        has_amount = any(p.get('type') == 'amount_selection' for p in module_card.available_filters)
        if has_amount and not any('beløb' in k.lower() for k in step["filters"].keys()):
            # Heuristik: hvis mål nævner mio/store → højere default
            goal_l = (goal or "").lower()
            default_amount = "1000000" if not any(w in goal_l for w in ["stor", "større", "million", "mio", ">"] ) else "10000000"
            step["filters"]["beløbsgrænse"] = default_amount

        # NOTE: Module-specific enrichment now handled by enrich_recipe_with_api()
        # Legacy logic disabled - keeping web source selection logic only
        if module_card.requires_source_selection and (not step.get("source_selection")):
            logger.info(f"Web source module {module_name} - manual selection required")
            if not step.get("strategic_note"):
                step["strategic_note"] = "PÅKRÆVET: Dette modul kræver manuelt kildevalg (source_selection)."

        # Valider filtre mod parts og tilføj advarsler
        warnings = await module_validator.validate_filters_against_parts(module_card.title, step["filters"])  # type: ignore[arg-type]
        if warnings:
            quality = step.setdefault("quality", {})  # temporary container; will be lifted later
            q_w = quality.setdefault("warnings", [])
            q_w.extend(warnings)

        return step
    except Exception as e:
        logger.warning(f"Kunne ikke berige step med modulspecifikke filtre: {e}")
        return step

def coerce_raw_to_target_shape(raw: dict, goal: str) -> dict:
    """
    Normalize LLM JSON output to target structure.
    
    Handles incomplete LLM output by creating missing sections and mapping known fields.
    """
    logger.info("Normaliserer rå LLM-output til målstruktur")
    
    # Initialize target structure with defaults
    target = {
        "overview": {},
        "scope": {},
        "monitoring": {},
        "hit_budget": {},
        "notifications": {},
        "parallel_profile": {},
        "steps": [],
        "cross_refs": [],
        "syntax_guide": {},
        "quality": {},
        "artifacts": {},
        "next_level_questions": [],
        "potential_story_angles": [],
        "creative_cross_references": []
    }
    
    # Map known fields from raw LLM output
    if "title" in raw:
        target["overview"]["title"] = raw["title"]
    if "strategy_summary" in raw:
        target["overview"]["strategy_summary"] = raw["strategy_summary"]
    if "creative_approach" in raw:
        target["overview"]["creative_approach"] = raw["creative_approach"]
    
    # Set scope.primary_focus from goal if not present
    if goal:
        target["scope"]["primary_focus"] = goal[:100] + "..." if len(goal) > 100 else goal
    
    # Map investigation steps
    if "investigation_steps" in raw and isinstance(raw["investigation_steps"], list):
        for i, step in enumerate(raw["investigation_steps"], 1):
            normalized_step = {
                "step_number": step.get("step", i),
                "title": step.get("title", f"Step {i}"),
                "type": step.get("type", "search"),
                "module": {
                    "id": step.get("module", "").lower().replace(" ", "_"),
                    "name": step.get("module", "Unknown"),
                    "is_web_source": False  # Will be set by validator
                },
                "rationale": step.get("rationale", ""),
                "search_string": _standardize_search_string(
                    step.get("details", {}).get("search_string", ""),
                    step.get("module", "Unknown")
                ),
                # Filters can be at step level (Claude's new format) or under details (legacy)
                "filters": step.get("filters", step.get("details", {}).get("filters", {})),
                "notification": _normalize_notification(
                    step.get("recommended_notification") or step.get("details", {}).get("recommended_notification", "daily")
                ),
                "delivery": "email",
                "source_selection": step.get("source_selection", step.get("details", {}).get("source_selection", [])),
                "strategic_note": step.get("strategic_note") or step.get("details", {}).get("strategic_note"),
                "explanation": step.get("explanation", step.get("details", {}).get("explanation", "")),
                "creative_insights": step.get("details", {}).get("creative_insights"),
                "advanced_tactics": step.get("details", {}).get("advanced_tactics")
            }
            
            # Ensure filters are properly structured before search string
            normalized_step = _ensure_filters_before_search_string(normalized_step, goal)
            
            # VALIDATE: Remove meaningless search strings
            if normalized_step["search_string"] in ["søgning", "search", "søg", ""]:
                # Check if module has company/CVR filter
                if normalized_step.get("filters", {}).get("virksomhed") or \
                   normalized_step.get("filters", {}).get("cvr"):
                    # Empty is fine when using company filter
                    normalized_step["search_string"] = ""
                    module_name = normalized_step.get("module", {}).get("name", "Unknown")
                    logger.info(f"Cleared meaningless search string for {module_name} (using company filter)")
            
            target["steps"].append(normalized_step)
    
    # Map other fields
    if "next_level_questions" in raw:
        target["next_level_questions"] = raw["next_level_questions"]
    if "potential_story_angles" in raw:
        target["potential_story_angles"] = raw["potential_story_angles"]
    if "creative_cross_references" in raw:
        target["creative_cross_references"] = raw["creative_cross_references"]
    
    logger.info(f"Normalisering færdig: {len(target['steps'])} steps mapped")
    return target

def apply_min_defaults(recipe: dict) -> None:
    """
    Apply sensible defaults to recipe structure.
    
    Ensures all required fields have reasonable default values.
    """
    logger.info("Anvender minimum defaults")
    
    # Overview defaults
    if not recipe.get("overview", {}).get("title"):
        recipe.setdefault("overview", {})["title"] = "KM24 Investigation"
    if not recipe.get("overview", {}).get("strategy_summary"):
        recipe.setdefault("overview", {})["strategy_summary"] = "Systematic investigation using KM24 modules"
    if not recipe.get("overview", {}).get("creative_approach"):
        recipe.setdefault("overview", {})["creative_approach"] = "Data-driven approach with cross-referencing"
    
    # Monitoring defaults
    if not recipe.get("monitoring", {}).get("type"):
        recipe.setdefault("monitoring", {})["type"] = "keywords"
    
    # Notifications defaults
    if not recipe.get("notifications"):
        recipe["notifications"] = {
            "primary": "daily",
            "channels": ["email"]
        }
    
    # Quality checks
    quality = recipe.setdefault("quality", {})
    checks = quality.setdefault("checks", [])
    if "webkilder har valgte kilder" not in checks:
        checks.append("webkilder har valgte kilder")
    if "beløbsgrænser sat hvor muligt" not in checks:
        checks.append("beløbsgrænser sat hvor muligt")
    
    # Step defaults - modul-aware
    for step in recipe.get("steps", []):
        if not step.get("notification"):
            step["notification"] = "daily"
        else:
            # Normalize existing notification values
            step["notification"] = _normalize_notification(step["notification"])
        if not step.get("delivery"):
            step["delivery"] = "email"
        if not step.get("filters"):
            step["filters"] = {}
        
        # Get module info
        module_name = step.get("module", {}).get("name", "") if isinstance(step.get("module"), dict) else step.get("module", "")
        
        # REMOVE INVALID DEFAULTS - kun tilføj filtre som modulet faktisk understøtter
        filters = step["filters"]
        
        # Check if module has amount_selection (from module card)
        # For now, be conservative - only add defaults we KNOW work
        
        # Periode er kun relevant for nogle moduler
        if "periode" not in filters:
            # Kun tilføj hvis det er et tidssensitivt modul
            if module_name in ["Registrering", "Status", "Kapitalændring"]:
                filters["periode"] = "24 mdr"
        
        # Beløbsgrænse KUN for amount_selection moduler
        if "beløbsgrænse" in filters:
            # Verificer at modulet faktisk har amount_selection
            # Hvis ikke, FJERN det
            has_amount_selection = module_name in [
                "Tinglysning", "Udbud", "Boligsiden", "Regnskaber"
            ]
            if not has_amount_selection:
                del filters["beløbsgrænse"]
                logger.info(f"Removed beløbsgrænse from {module_name} (not supported)")
        
        # Generate search_string from filters or default
        if not step.get("search_string"):
            # FIRST: Check if there's a search string in filters (from Claude output)
            search_in_filters = filters.get("Søgeord") or filters.get("søgeord")
            if search_in_filters:
                # Convert array to string (join multiple search strings with space)
                if isinstance(search_in_filters, list):
                    # Join multiple search strings with space separator
                    step["search_string"] = " ".join(search_in_filters) if len(search_in_filters) > 1 else (search_in_filters[0] if search_in_filters else "")
                else:
                    step["search_string"] = str(search_in_filters)
                logger.info(f"Bruger søgestreng fra filters: {step['search_string']}")
            else:
                # Fallback to default search string
                module_name = step.get("module", {}).get("name", "Unknown") if isinstance(step.get("module"), dict) else step.get("module", "Unknown")
                step["search_string"] = _get_default_search_string_for_module(module_name)
                logger.info(f"Genereret default søgestreng for {module_name}: {step['search_string']}")
        else:
            # Standardize existing search strings
            module_name = step.get("module", {}).get("name", "Unknown") if isinstance(step.get("module"), dict) else step.get("module", "Unknown")
            step["search_string"] = _standardize_search_string(step["search_string"], module_name)
            logger.info(f"Standardiseret søgestreng for {module_name}: {step['search_string']}")
        
        # Handle source_selection for web source modules
        module = step.get("module", {})
        if isinstance(module, dict) and module.get("is_web_source", False):
            if not step.get("source_selection") or len(step.get("source_selection", [])) == 0:
                # Get default sources for web source module
                default_sources = _get_default_sources_for_module(module.get("name", ""))
                step["source_selection"] = default_sources
                logger.info(f"Tilføjet default sources for {module.get('name', '')}: {default_sources}")
        elif not step.get("source_selection"):
            step["source_selection"] = []
    
    logger.info("Defaults anvendt")

def validate_content_relevance(recipe: dict, goal: str) -> list[str]:
    """
    Validate that output sections are relevant to the user's goal.
    
    Checks for keyword overlap between goal and generated content sections
    to catch generic/irrelevant content.
    """
    warnings = []
    goal_lower = goal.lower()
    
    # Extract meaningful keywords (4+ characters) from goal
    goal_keywords = set(re.findall(r'\b\w{4,}\b', goal_lower))
    
    # Validate story angles
    for angle in recipe.get("potential_story_angles", []):
        angle_lower = angle.lower()
        angle_keywords = set(re.findall(r'\b\w{4,}\b', angle_lower))
        overlap = len(goal_keywords & angle_keywords)
        
        if overlap < 2:  # Less than 2 keywords in common
            warnings.append(
                f"Potentielt irrelevant story angle: '{angle[:60]}...'"
            )
    
    # Validate cross references mention actually used modules
    used_modules = {
        step.get("module", {}).get("name", "") 
        for step in recipe.get("steps", [])
    }
    used_modules = {m.lower() for m in used_modules if m}
    
    for xref in recipe.get("creative_cross_references", []):
        xref_lower = xref.lower()
        # Check if cross-reference mentions any used module
        has_relevant_module = any(
            module in xref_lower for module in used_modules
        )
        if not has_relevant_module and used_modules:
            warnings.append(
                f"Cross-reference nævner moduler der ikke bruges: '{xref[:60]}...'"
            )
    
    return warnings

def validate_module_logic(recipe: dict) -> List[str]:
    """
    Validate that modules are used correctly based on their purpose.
    
    Common mistakes:
    - Using Status module to identify active companies
    - Using monitoring modules for identification
    """
    warnings = []
    
    # Check first step specifically
    if recipe.get("steps") and len(recipe["steps"]) > 0:
        first_step = recipe["steps"][0]
        title_lower = first_step.get("title", "").lower()
        module_name = first_step.get("module", {}).get("name", "")
        search_string = first_step.get("search_string", "")
        
        # Pattern: Identification step
        is_identification = any(word in title_lower for word in [
            "identificer", "find", "kortlæg", "opbyg", "start med"
        ])
        
        if is_identification:
            # Check for wrong modules
            if module_name == "Status" and any(word in search_string.lower() for word in ["konkurs", "ophør", "likvidation"]):
                warnings.append(
                    f"KRITISK: Trin 1 bruger Status-modulet med konkurs-søgning til identifikation. "
                    f"Dette finder KUN lukkede virksomheder. Brug i stedet Registrering med branchekoder."
                )
            
            if module_name in ["Arbejdstilsyn", "Fødevaresmiley", "Kapitalændring"]:
                warnings.append(
                    f"ADVARSEL: Trin 1 bruger {module_name} til identifikation. "
                    f"Overvej om Registrering ville være bedre til at finde virksomheder."
                )
            
            # Recommend Registrering
            if module_name != "Registrering":
                warnings.append(
                    f"ANBEFALING: Trin 1 (identifikation) bør typisk bruge Registrering-modulet "
                    f"med branchekoder for at finde ALLE relevante virksomheder."
                )
    
    return warnings

async def validate_and_clean_filters(step: dict) -> dict:
    """
    Validate filters against module capabilities and remove unsupported ones.
    """
    module_name = step.get("module", {}).get("name", "")
    if not module_name:
        return step
    
    filters = step.get("filters", {})
    if not filters:
        return step
    
    # Get module capabilities
    from .module_validator import get_module_validator
    module_validator = get_module_validator()
    module_card = await module_validator.get_enhanced_module_card(module_name)
    
    if not module_card:
        return step
    
    # Check which filter types the module supports
    supported_types = {f["type"] for f in module_card.available_filters}
    
    # Remove unsupported filters
    to_remove = []
    for filter_key in filters.keys():
        # Map filter key to part type
        if filter_key in ["beløbsgrænse", "amount", "kontraktværdi"]:
            if "amount_selection" not in supported_types:
                to_remove.append(filter_key)
                logger.warning(f"Module {module_name} does not support {filter_key}")
        
        # Add more mappings as needed
    
    for key in to_remove:
        del filters[key]
    
    return step

def infer_likely_modules(goal: str) -> List[str]:
    """
    Heuristisk afledning af sandsynlige moduler baseret på mål.
    Bruges til at hente filter-metadata for relevante moduler.
    """
    goal_lower = goal.lower()
    likely = []
    
    # Mapping af nøgleord til moduler
    module_keywords = {
        "Tinglysning": ["tinglys", "ejendom", "ejendomshandel", "pant", "sælg"],
        "Status": ["konkurs", "likvidat", "ophør", "opløs", "svingdør", "lukk"],
        "Registrering": ["nyregistre", "nystarte", "etabler", "opstart"],
        "Arbejdstilsyn": ["arbejdstilsyn", "arbejdsmiljø", "asbest", "ulykke", "forbud", "påbud"],
        "Udbud": ["udbud", "kontrakt", "offentlig", "tildel"],
        "Domme": ["dom", "dømme", "retssag", "domsafsigelse"],
        "Retslister": ["retsliste", "tiltale", "sigte", "gerningskode"],
        "Lokalpolitik": ["lokalpoliti", "kommune", "beslutning", "dagsorden", "byråd"],
        "FødevareSmiley": ["fødevare", "smiley", "sur", "hygiejne", "restaurant", "cafe"],
        "Miljøsager": ["miljø", "forurening", "udledning", "tilladelse"],
        "Personbogen": ["pant", "løsøre", "pantebreve"],
    }
    
    for module, keywords in module_keywords.items():
        if any(kw in goal_lower for kw in keywords):
            likely.append(module)
    
    # Begræns til top 5
    return likely[:5]


async def validate_filters_against_api(recipe: dict) -> dict:
    """
    DEPRECATED: Filter validation now handled by enrich_recipe_with_api()
    This function is kept as a no-op for backward compatibility.
    """
    logger.info("validate_filters_against_api called (now handled by enrich_recipe_with_api, skipping)")
    return recipe

async def validate_filters_against_api_LEGACY(recipe: dict) -> dict:
    """
    OLD IMPLEMENTATION - DISABLED
    AGGRESSIVE whitelist-baseret validering.
    Fjerner ALT der ikke er eksplicit godkendt af API.
    """

    # KNOWN INVALID FILTERS (from test results)
    BLACKLIST = {
        "oprindelsesland",  # Doesn't exist in any module
        "virksomhedstype",  # Should be generic_value with correct name
        "statustype",       # Should be generic_value with correct name
        "dokumenttype",     # Invented
        "property_types",   # Invented
        "adressetype",      # Should be generic_value if it exists
        "ejendomstype",     # Should be checked against API
    }

    filter_catalog = get_filter_catalog()

    for step_idx, step in enumerate(recipe.get("steps", [])):
        module_name = step.get("module", {}).get("name", "")
        if not module_name:
            continue
        
        filters = step.get("filters", {})
        
        # FIRST PASS: Remove blacklisted
        for key in list(filters.keys()):
            if key.lower() in BLACKLIST:
                del filters[key]
                logger.warning(f"Step {step_idx+1}: BLACKLISTED filter removed: {key}")
        
        # Hent API metadata
        metadata = await filter_catalog.get_module_filter_metadata(module_name)
        if not metadata:
            logger.warning(f"No metadata for {module_name}, skipping validation")
            continue
        
        available = metadata.get("available_filters", {})
        
        # BUILD WHITELIST from API
        whitelist = set()
        
        # DEBUG: Log what API returned
        logger.info(f"=== Building whitelist for {module_name} (Step {step_idx+1}) ===")
        logger.info(f"Available filter types from API: {list(available.keys())}")
        
        # Standard filters
        if "municipality" in available:
            whitelist.add("geografi")
            whitelist.add("kommune")  # Alias
            logger.info("✅ Added 'geografi' to whitelist (municipality exists in API)")
        
        if "industry" in available:
            whitelist.add("branchekode")
            whitelist.add("branche")  # Alias
            logger.info("✅ Added 'branchekode' to whitelist (industry exists in API)")
        
        if "company" in available:
            whitelist.add("virksomhed")
            whitelist.add("cvr")  # Alias
            logger.info("✅ Added 'virksomhed' to whitelist (company exists in API)")
        
        if "amount_selection" in available:
            whitelist.add("beløbsgrænse")
            whitelist.add("kontraktværdi")  # Alias for Udbud
        
        if "search_string" in available:
            whitelist.add("søgeord")
        
        # Generic values - add exact part names
        if "generic_value" in available:
            for part in available["generic_value"]["parts"]:
                part_name = part["part_name"].lower()
                whitelist.add(part_name)
        
        # Web source
        if "web_source" in available:
            whitelist.add("source_selection")
            whitelist.add("kilde")  # Alias
        
        # Special cases (these are sometimes valid)
        # Only add if module actually supports them
        if module_name in ["Registrering", "Status", "Kapitalændring"]:
            whitelist.add("periode")
            logger.info("✅ Added 'periode' to whitelist (special case for date-based modules)")
        
        # Log final whitelist
        logger.info(f"Final whitelist for {module_name}: {sorted(whitelist)}")
        
        # Log what we're checking
        logger.info(f"Filters to validate: {list(filters.keys())}")
        
        # AGGRESSIVE FILTERING
        to_remove = []
        to_rename = {}
        
        for filter_key in list(filters.keys()):
            key_lower = filter_key.lower()
            
            # Check if in whitelist
            if key_lower not in whitelist:
                # Check for known aliases we should map
                alias_map = {
                    "kommune/region": "geografi",
                    "region": "geografi",
                    "cvr": "virksomhed",
                }
                
                if key_lower in alias_map:
                    # Rename instead of remove
                    target = alias_map[key_lower]
                    if target in whitelist:
                        to_rename[filter_key] = target
                        logger.info(f"Step {step_idx+1}: Renaming {filter_key} → {target}")
                    else:
                        to_remove.append(filter_key)
                        logger.warning(f"Step {step_idx+1}: REJECTED {filter_key} (module doesn't support target)")
                else:
                    # HARD REJECT
                    to_remove.append(filter_key)
                    logger.warning(f"Step {step_idx+1}: 🚫 REJECTED unknown filter '{filter_key}' for {module_name} (not in whitelist: {sorted(whitelist)})")
        
        # Apply renames
        for old_key, new_key in to_rename.items():
            if new_key in filters:
                # Merge if target already exists
                logger.warning(f"Step {step_idx+1}: Merging duplicate {old_key} into {new_key}")
            else:
                filters[new_key] = filters[old_key]
            del filters[old_key]
        
        # Apply removals
        for key in to_remove:
            del filters[key]
        
        # Log final state
        if to_remove or to_rename:
            logger.info(f"Step {step_idx+1} ({module_name}): Cleaned filters → {list(filters.keys())}")
    
    return recipe


def final_cleanup_pass(recipe: dict) -> dict:
    """
    Sidste cleanup - fanger alt der slap gennem.
    Denne kører EFTER API-validering som safety net.
    """
    
    # Common mistakes to fix
    CLEANUP_RULES = {
        # Delete these entirely
        "DELETE": {
            "oprindelsesland", "virksomhedstype", "statustype",
            "dokumenttype", "property_types", "adressetype", "ejendomstype"
        },
        # Rename these
        "RENAME": {
            "kommune/region": "geografi",
            "region": "geografi",
            "cvr": "virksomhed",
        }
    }
    
    for step in recipe.get("steps", []):
        filters = step.get("filters", {})
        
        # Delete invalid
        for key in list(filters.keys()):
            if key in CLEANUP_RULES["DELETE"]:
                del filters[key]
                logger.info(f"Final cleanup: Deleted {key}")
        
        # Rename
        for old, new in CLEANUP_RULES["RENAME"].items():
            if old in filters:
                if new in filters:
                    # Merge
                    logger.info(f"Final cleanup: Merging {old} into {new}")
                else:
                    filters[new] = filters[old]
                del filters[old]
    
    return recipe


def get_industry_branch_codes() -> Dict[str, List[str]]:
    """
    Map industry keywords to relevant branch codes.
    
    Returns:
        Dictionary of industry keywords to lists of branch codes
    """
    return {
        # Byggeri & Construction
        "byggeri": ["41.20", "43.11", "43.12", "43.99"],
        "bygge": ["41.20", "43.11", "43.12", "43.99"],
        "byggeprojekt": ["41.20", "43.11", "43.12", "43.99"],
        "entreprenør": ["41.20", "43.11", "43.99"],
        "nedrivning": ["43.11"],
        "construction": ["41.20", "43.11", "43.12", "43.99"],
        
        # Transport & Logistics
        "transport": ["49.41", "49.42", "53.10", "53.20"],
        "logistik": ["49.41", "52.29"],
        "vognmand": ["49.41"],
        "spedition": ["52.29"],
        "godstransport": ["49.41"],
        
        # Landbrug & Agriculture
        "landbrug": ["01.11", "01.21", "01.41", "01.50"],
        "landbrugs": ["01.11", "01.21", "01.41", "01.50"],
        "agriculture": ["01.11", "01.21", "01.41"],
        "bonde": ["01.11", "01.50"],
        "gård": ["01.11", "01.50"],
        
        # Fødevarer & Food
        "fødevare": ["10.11", "10.51", "10.71"],
        "bageri": ["10.71"],
        "mejeri": ["10.51"],
        "slagter": ["10.11", "10.13"],
        "restaurant": ["56.10"],
        "café": ["56.30"],
        
        # Detail & Retail
        "detailhandel": ["47.11", "47.19", "47.71"],
        "detail": ["47.11", "47.19", "47.71"],
        "butik": ["47.11", "47.19"],
        "retail": ["47.11", "47.19"],
        
        # Ejendom & Real Estate
        "ejendom": ["68.10", "68.20", "68.31"],
        "ejendomsselskab": ["68.10", "68.20"],
        "udlejning": ["68.20"],
        
        # Finans & Finance
        "finans": ["64.19", "64.20"],
        "bank": ["64.19"],
        "kapitalfond": ["64.20"],
        "investering": ["64.20"],
        
        # Teknologi & Tech
        "teknologi": ["62.01", "62.02"],
        "software": ["62.01"],
        "it": ["62.01", "62.02"],
        "tech": ["62.01"]
    }


def ensure_critical_filters(recipe: dict, goal: str) -> dict:
    """
    Ensure critical filters (especially Branche for Registrering) are present.
    
    Auto-adds missing Branche filters to Registrering steps if the user's goal
    clearly implies an industry.
    
    Args:
        recipe: Recipe dict to check and modify
        goal: User's original goal string
    
    Returns:
        Modified recipe dict with added filters
    """
    if not goal:
        return recipe
    
    goal_lower = goal.lower()
    industry_mapping = get_industry_branch_codes()
    
    # Find industry matches in goal
    matched_industries = []
    for keyword, branch_codes in industry_mapping.items():
        if keyword in goal_lower:
            matched_industries.append((keyword, branch_codes))
    
    if not matched_industries:
        logger.info("No industry keywords detected in goal - skipping auto-filter")
        return recipe
    
    # Use the first matched industry (most specific)
    detected_keyword, branch_codes = matched_industries[0]
    logger.info(f"Detected industry keyword '{detected_keyword}' in goal → branch codes: {branch_codes}")
    
    # Iterate through steps and fix Registrering steps
    for step in recipe.get("steps", []):
        module_name = step.get("module", {}).get("name", "")
        step_title = step.get("title", "").lower()
        
        # Check if this is a Registrering step about identifying companies
        if module_name == "Registrering":
            filters = step.get("filters", {})
            
            # Check if Branche filter is missing or empty
            if not filters.get("Branche") or filters.get("Branche") == []:
                # Auto-add branch codes
                filters["Branche"] = branch_codes
                logger.info(f"✓ Auto-added Branche filter {branch_codes} to Registrering step based on keyword '{detected_keyword}'")
                
                # Update rationale to mention auto-addition
                if "rationale" in step:
                    step["rationale"] += f" (Auto-tilføjet branchekoder for {detected_keyword})"
    
    return recipe


async def complete_recipe(raw_recipe: dict, goal: str = "") -> dict:
    """
    Complete recipe with deterministic output structure.
    
    Normalizes LLM output, validates modules, applies defaults, and returns
    structured response conforming to UseCaseResponse model.
    """
    logger.info("Starter deterministisk recipe komplettering")
    
    # Step 1: Normalize LLM JSON to target structure
    logger.info("Trin 1: Normaliserer rå LLM-output")
    recipe = coerce_raw_to_target_shape(raw_recipe, goal)
    
    # NEW: Validate content relevance
    relevance_warnings = validate_content_relevance(recipe, goal)
    if relevance_warnings:
        logger.warning(f"Content relevance issues detected: {relevance_warnings}")
        # Add to quality warnings
        quality = recipe.setdefault("quality", {})
        warnings_list = quality.setdefault("warnings", [])
        warnings_list.extend(relevance_warnings)
    
    # Step 2: Validate and enrich modules via KM24ModuleValidator
    logger.info("Trin 2: Validerer og beriger moduler")
    module_validator = get_module_validator()
    
    for step in recipe.get("steps", []):
        module_name = step.get("module", {}).get("name", "")
        if module_name:
            try:
                # Get module info from validator
                module_card = await module_validator.get_enhanced_module_card(module_name)
                if module_card:
                    step["module"]["id"] = module_card.slug
                    step["module"]["name"] = module_card.title
                    step["module"]["is_web_source"] = module_card.requires_source_selection
                    
                    # Add API example if available
                    if hasattr(module_card, 'api_example'):
                        step["api"] = {
                            "endpoint": f"/api/{module_card.slug}",
                            "method": "POST",
                            "body": module_card.api_example
                        }
                    # Enrich with module-specific filters and defaults
                    enriched = await _enrich_with_module_specific_filters(step, goal)
                    step.update(enriched)
            except Exception as e:
                logger.warning(f"Kunne ikke validere modul {module_name}: {e}")
    
    # NEW: Validate module logic
    logger.info("Trin 2.5: Validerer modul-logik")
    module_logic_warnings = validate_module_logic(recipe)
    if module_logic_warnings:
        logger.warning(f"Module logic issues: {module_logic_warnings}")
        quality = recipe.setdefault("quality", {})
        warnings_list = quality.setdefault("warnings", [])
        warnings_list.extend(module_logic_warnings)
    
    # NEW: Clean up invalid filters
    logger.info("Trin 2.6: Validerer og renser filtre")
    for i, step in enumerate(recipe.get("steps", [])):
        cleaned_step = await validate_and_clean_filters(step)
        recipe["steps"][i] = cleaned_step
    
    # NEW: Validate filters against API
    logger.info("Trin 2.8: Validerer filtre mod API")
    recipe = await validate_filters_against_api(recipe)
    
    # NEW: Final cleanup pass
    logger.info("Trin 2.9: Final filter cleanup")
    recipe = final_cleanup_pass(recipe)
    
    # NEW: Ensure critical filters are present
    logger.info("Trin 2.95: Sikrer kritiske filtre er til stede")
    recipe = ensure_critical_filters(recipe, goal)
    
    # Step 3: Apply sensible defaults (after module validation)
    logger.info("Trin 3: Anvender defaults")
    apply_min_defaults(recipe)

    # Step 3.5: Enrich with educational content
    logger.info("Trin 3.5: Beriger med pædagogisk indhold")
    from km24_vejviser.enrichment import RecipeEnricher
    enricher = RecipeEnricher()
    recipe = await enricher.enrich(recipe, goal)

    # Step 3.6: Generate context block and AI assessment
    logger.info("Trin 3.6: Genererer kontekst og AI vurdering")

    # Generate context block
    modules_list = [step.get("module", {}) for step in recipe.get("steps", [])]
    scope = recipe.get("scope", {})
    recipe["context"] = generate_context_block(goal, modules_list, scope)

    # Generate AI assessment
    recipe["ai_assessment"] = generate_ai_assessment(recipe, goal)

    # Add hit definitions and rationales to each step's educational content
    for idx, step in enumerate(recipe.get("steps", [])):
        if "educational" not in step:
            step["educational"] = {}

        # Generate hit definition
        module_info = step.get("module", {})
        hit_def = generate_hit_definition(step, module_info)
        step["educational"]["what_counts_as_hit"] = f"**Hit types:** {', '.join(hit_def['hit_types'])}\n\n**Indicators:** {'; '.join(hit_def['indicators'])}"

        # Generate step rationale
        step["educational"]["why_this_step"] = generate_step_rationale(step, goal, idx)

    # Step 4: Parse to UseCaseResponse and return dict
    logger.info("Trin 4: Parser til UseCaseResponse")
    
    # Debug: Log step details before validation
    for i, step in enumerate(recipe.get("steps", [])):
        module = step.get("module", {})
        logger.info(f"Step {i+1}: module={module.get('name', 'Unknown')}, is_web_source={module.get('is_web_source', False)}, source_selection={step.get('source_selection', [])}")
    
    try:
        # Move any step-level quality.warnings up to global recipe quality
        for s in recipe.get("steps", []):
            if isinstance(s, dict) and s.get("quality", {}).get("warnings"):
                quality = recipe.setdefault("quality", {})
                warn = quality.setdefault("warnings", [])
                warn.extend(s.get("quality", {}).get("warnings", []))
                # Clean up temporary quality on step
                s.pop("quality", None)

        # Validate against KM24 rules first (record warnings instead of raising)
        is_valid, km24_errors = validate_km24_recipe(recipe)
        if not is_valid:
            error_message = format_validation_error(km24_errors)
            logger.error(f"KM24 validation failed: {error_message}")
            # Record as quality warnings so frontend can surface issues without breaking
            quality = recipe.setdefault("quality", {})
            warnings_list = quality.setdefault("warnings", [])
            warnings_list.extend(km24_errors)
        
        # Validate the final recipe against Pydantic schema
        model = UseCaseResponse.model_validate(recipe)
        logger.info("Recipe valideret succesfuldt")
        return model.model_dump()
    except Exception as e:
        logger.error(f"Validation fejl: {e}")
        raise ValueError(f"Recipe validation failed: {e}")

def validate_km24_recipe(recipe: dict) -> tuple[bool, list[str]]:
    """
    Validate recipe against KM24 rules.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    # 1. Check structure
    required_sections = ["overview", "steps", "next_level_questions", "potential_story_angles"]
    for section in required_sections:
        if section not in recipe:
            errors.append(f"Mangler sektion: {section}")
    
    # Check overview has strategy
    if "overview" in recipe and "strategy_summary" not in recipe["overview"]:
        errors.append("Mangler strategi i overview")
    
    # 2. Validate each step
    if "steps" in recipe:
        for i, step in enumerate(recipe["steps"], 1):
            step_errors = validate_step(step, i)
            errors.extend(step_errors)
    
    # 3. Check pipeline structure
    if "steps" in recipe and len(recipe["steps"]) < 3:
        errors.append("Pipeline skal have mindst 3 trin")
    
    # 4. Check next level questions
    if "next_level_questions" in recipe and not recipe["next_level_questions"]:
        errors.append("Mangler næste niveau spørgsmål")
    
    # 5. Check potential angles
    if "potential_story_angles" in recipe and not recipe["potential_story_angles"]:
        errors.append("Mangler potentielle vinkler")
    
    # 6. Check pitfalls
    if "quality" not in recipe or "checks" not in recipe["quality"]:
        errors.append("Mangler pitfalls/quality checks")
    
    return len(errors) == 0, errors

def validate_step(step: dict, step_number: int) -> list[str]:
    """Validate a single step against KM24 rules."""
    errors = []
    
    # Check required fields
    required_fields = ["module", "search_string", "filters", "notification"]
    for field in required_fields:
        if field not in step:
            errors.append(f"Trin {step_number}: Mangler {field}")
    
    if "module" in step:
        module_errors = validate_module(step["module"], step_number)
        errors.extend(module_errors)
    
    if "search_string" in step:
        search_errors = validate_search_syntax(step["search_string"], step_number)
        errors.extend(search_errors)
    
    if "filters" in step:
        filter_errors = validate_filters(step["filters"], step_number)
        errors.extend(filter_errors)
    
    if "notification" in step:
        notification_errors = validate_notification(step["notification"], step_number)
        errors.extend(notification_errors)
    
    # Check web source modules have source selection
    if "module" in step and "is_web_source" in step["module"] and step["module"]["is_web_source"]:
        if "source_selection" not in step or not step["source_selection"]:
            errors.append(f"Trin {step_number}: Webkilde-modul kræver source_selection")
    
    return errors

def validate_module(module: dict, step_number: int) -> list[str]:
    """Validate module name and format."""
    errors = []
    
    if "name" not in module:
        errors.append(f"Trin {step_number}: Modul mangler navn")
        return errors
    
    name = module["name"]
    
    # Check official module names
    official_modules = {
        "Registrering": "📊 Registrering – nye selskaber fra VIRK",
        "Tinglysning": "📊 Tinglysning – nye ejendomshandler", 
        "Kapitalændring": "📊 Kapitalændring – selskabsændringer fra VIRK",
        "Lokalpolitik": "📊 Lokalpolitik – dagsordener/referater",
        "Miljøsager": "📊 Miljøsager – miljøtilladelser",
        "EU": "📊 EU – indhold fra EU-organer",
        "Kommuner": "📊 Kommuner – lokalpolitik og planer",
        "Danske medier": "📊 Danske medier – danske nyhedskilder",
        "Webstedsovervågning": "📊 Webstedsovervågning – konkurrentovervågning",
        "Udenlandske medier": "📊 Udenlandske medier – internationale kilder",
        "Forskning": "📊 Forskning – akademiske kilder",
        "Udbud": "📊 Udbud – offentlige udbud",
        "Regnskaber": "📊 Regnskaber – årsrapporter og regnskaber",
        "Personbogen": "📊 Personbogen – personlige oplysninger",
        "Status": "📊 Status – virksomhedsstatusændringer og konkurser",
        "Arbejdstilsyn": "📊 Arbejdstilsyn – arbejdsmiljøsager og kontrol",
        "Børsmeddelelser": "📊 Børsmeddelelser – børsnoterede selskaber"
    }
    
    # Check if module name matches official format
    if name not in official_modules and not any(official in name for official in official_modules.keys()):
        errors.append(f"Trin {step_number}: Ugyldigt modulnavn '{name}'. Skal være et af de officielle moduler.")
    
    return errors

def validate_search_syntax(search_string: str, step_number: int) -> list[str]:
    """Validate search string syntax."""
    errors = []
    
    # Allow empty search strings but warn
    if not search_string:
        # Don't add error, just return empty list - search strings can be empty
        return errors
    
    # Flag lowercase boolean operators; accept uppercase AND/OR/NOT
    operator_pattern = r"\b(and|or|not|og|eller|ikke)\b"
    for match in re.finditer(operator_pattern, search_string):
        token = match.group(0)
        if token != token.upper():
            errors.append(
                f"Trin {step_number}: Ugyldig operator '{token}'. Brug AND/OR/NOT med store bogstaver"
            )
    
    # Check for commas (should use semicolons)
    if "," in search_string:
        errors.append(f"Trin {step_number}: Brug semikolon ; i stedet for komma for parallelle variationer")
    
    # Check for unsupported operators
    unsupported = ["+", "-", "*", "/", "=", "!=", "<", ">"]
    for op in unsupported:
        if op in search_string:
            errors.append(f"Trin {step_number}: Uunderstøttet operator '{op}'")
    
    return errors

def validate_filters(filters: dict, step_number: int) -> list[str]:
    """Validate filters structure."""
    errors = []
    
    # Allow empty filters but warn
    if not filters:
        # Don't add error, just return empty list - filters can be empty
        return errors
    
    # Check for required filter categories
    required_categories = ["geografi", "branche", "beløb"]
    found_categories = []
    
    for key in filters.keys():
        if any(cat in key.lower() for cat in required_categories):
            found_categories.append(key)
    
    if not found_categories:
        errors.append(f"Trin {step_number}: Filtre skal indeholde mindst én kategori (geografi, branche, beløb)")
    
    return errors

def validate_notification(notification: str, step_number: int) -> list[str]:
    """Validate notification cadence."""
    errors = []
    
    valid_notifications = ["løbende", "daglig", "ugentlig", "interval", "instant", "daily", "weekly"]
    
    if notification.lower() not in valid_notifications:
        errors.append(f"Trin {step_number}: Ugyldig notifikationskadence '{notification}'. Skal være: løbende, daglig, ugentlig, interval")
    
    return errors

def format_validation_error(errors: list[str]) -> str:
    """Format validation errors as UGYLDIG OPSKRIFT message."""
    if not errors:
        return ""

    error_list = "\n".join([f"• {error}" for error in errors])
    return f"UGYLDIG OPSKRIFT – RET FØLGENDE:\n{error_list}"

# --- Helper Functions for Context and Assessment ---

def generate_context_block(goal: str, modules: list[dict], scope: dict) -> dict:
    """Generate intelligent context based on modules and domain."""
    from km24_vejviser.models.usecase_response import ContextBlock

    modules_used = [m.get("name", "") for m in modules if isinstance(m, dict)]
    goal_lower = goal.lower()

    # Domain detection and background facts
    background = []

    if any(m in modules_used for m in ["Registrering", "Status"]):
        if any(w in goal_lower for w in ["detail", "butik", "forretning", "shop"]):
            background.extend([
                "Detailhandlen i danske bymidter er under pres fra e-handel og huslejestigninger",
                "Konkursrytteri opstår når samme personer systematisk starter nye selskaber efter konkurser",
                "CVR-data gør det muligt at spore adresse-overlap og ejerskabsmønstre"
            ])
        elif any(w in goal_lower for w in ["transport", "vognm", "lastbil", "fragt"]):
            background.extend([
                "Transportsektoren har høj myndighedsaktivitet pga. arbejdsmiljø og sociale forhold",
                "Reaktioner fra Arbejdstilsynet kan forudgå økonomiske problemer",
                "Serielle mønstre kan identificeres ved at følge personer på tværs af selskaber"
            ])
        elif any(w in goal_lower for w in ["bygge", "entrepren", "håndværk", "asbest"]):
            background.extend([
                "Byggebranchen har høj omsætning af virksomheder og hyppige myndighedsreaktioner",
                "Asbest, stilladser og nedstyrtning er hyppige kritikpunkter fra Arbejdstilsynet",
                "Statusændringer efter påbud kan indikere systematiske problemer"
            ])

    if "Arbejdstilsyn" in modules_used:
        background.append("Arbejdstilsynet registrerer over 15.000 reaktioner årligt på tværs af alle brancher")

    if "Tinglysning" in modules_used:
        background.append("Ejendomsdata kan afsløre økonomiske relationer og ejerskabsstrukturer")

    # Specific expectations with numbers
    what_to_expect = []
    if "Registrering" in modules_used:
        what_to_expect.append("5-20 nye virksomheder pr. måned i udvalgte brancher (afhænger af geografisk område)")
    if "Status" in modules_used:
        what_to_expect.append("1-5 statusændringer pr. måned i målgruppen")
        what_to_expect.append("Mønstre udvikler sig typisk over 3-12 måneder, ikke dage eller uger")
    if "Arbejdstilsyn" in modules_used:
        what_to_expect.append("2-10 tilsynsreaktioner pr. måned afhængig af brancher og geografi")

    # Module-specific caveats
    caveats = [
        "CVR-data opdateres dagligt, men kan have 1-2 dages forsinkelse",
        "Offentlige registre dækker ikke interne virksomhedsbeslutninger eller -dokumenter"
    ]

    if "Arbejdstilsyn" in modules_used:
        caveats.append("Myndighedskampagner kan skabe kunstige toppe - vurder tidslige mønstre kritisk")
    if "Status" in modules_used:
        caveats.append("Ikke alle sammenfald mellem reaktioner og statusændringer er kausale")
    if any(m in modules_used for m in ["Registrering", "Personbogen"]):
        caveats.append("Adressematch kræver manuel verifikation (forskellige formater i registre)")

    # Coverage specifics
    coverage_parts = []
    coverage_parts.append(f"Kombinerer: {', '.join(m for m in modules_used if m)}")
    coverage_parts.append("Dækker kun offentligt tilgængelige kilder via KM24")

    if "Registrering" in modules_used:
        coverage_parts.append("CVR-data: Historik tilbage til 2010, opdateres dagligt")
    if "Arbejdstilsyn" in modules_used:
        coverage_parts.append("Arbejdstilsynsdata: Fra 2015 og frem, inkl. påbud og vejledninger")

    # Fallbacks if no domain detected
    if not background:
        background = [
            "Denne overvågning kombinerer offentlige registre for at spore mønstre",
            f"Pipeline med {len(modules_used)} moduler giver cross-reference mellem kilder"
        ]

    if not what_to_expect:
        what_to_expect = [
            "Hitvolumen afhænger af filtre og geografisk område",
            "Mønstre bliver tydeligere over tid (uger til måneder)"
        ]

    return {
        "background": "\n".join(f"• {b}" for b in background),
        "what_to_expect": "\n".join(f"• {w}" for w in what_to_expect),
        "caveats": caveats,
        "coverage": "\n".join(coverage_parts)
    }

def generate_ai_assessment(recipe: dict, goal: str) -> dict:
    """Generate concise AI assessment without repeating goal."""
    from km24_vejviser.models.usecase_response import AIAssessment

    steps = recipe.get("steps", [])
    modules_used = [s.get("module", {}).get("name", "") for s in steps]
    goal_lower = goal.lower()

    # Extract geographic area
    area = "Danmark"
    area_keywords = {
        "esbjerg": "Esbjerg",
        "aarhus": "Aarhus",
        "odense": "Odense",
        "aalborg": "Aalborg",
        "københavn": "København",
        "syddanmark": "Syddanmark",
        "midtjylland": "Midtjylland",
        "trekant": "Trekantsområdet"
    }
    for keyword, area_name in area_keywords.items():
        if keyword in goal_lower:
            area = area_name
            break

    # Extract focus from goal keywords - be specific
    focus = ""
    
    # Transport/arbejdsmiljø
    if any(w in goal_lower for w in ["vognm", "transport", "social dumping"]) and "arbejdstilsyn" in goal_lower:
        focus = "Social dumping og arbejdsmiljø i transportbranchen"
    
    # Detail/konkurs
    elif any(w in goal_lower for w in ["butik", "detail"]) and any(w in goal_lower for w in ["konkurs", "lukk", "ophør"]):
        focus = "Konkursrytteri i detailhandel"
    
    # Byggeri/arbejdsmiljø
    elif "bygge" in goal_lower and "arbejdstilsyn" in goal_lower:
        focus = "Arbejdsmiljø og sikkerhed i byggebranchen"
    
    # Ejendom/udvikling
    elif any(w in goal_lower for w in ["havn", "udvikling", "ejendom", "lokalplan"]):
        focus = "Ejendomsudvikling og kommunale beslutninger"
    
    # Fødevare/kontrol
    elif any(w in goal_lower for w in ["fødevare", "smiley", "restaurant"]):
        focus = "Fødevaresikkerhed og myndighedskontrol"
    
    # Fallback - use module combination if no keywords matched
    else:
        if "Status" in modules_used and "Registrering" in modules_used:
            if any(w in goal_lower for w in ["konkurs", "ophør", "lukk", "rytter"]):
                focus = "Konkursrytteri og virksomhedsgenstarter"
            elif any(w in goal_lower for w in ["fusion", "opkøb", "sammenlægning"]):
                focus = "Virksomhedskonsolidering og ejerskabsændringer"
            else:
                focus = "Virksomhedsmønstre og statusændringer"
        elif "Arbejdstilsyn" in modules_used:
            focus = "Myndighedskontrol og compliance"
        elif "Tinglysning" in modules_used:
            focus = "Ejendomshandler og økonomiske transaktioner"
        elif "Lokalpolitik" in modules_used:
            focus = "Politiske beslutninger og lokalplaner"
        else:
            focus = "Systematisk datadrevet overvågning"

    # Build concise summary
    summary = f"{len(steps)} monitorer i {area}. Fokus: {focus}."

    # Add pipeline if 3+ steps
    if len(steps) >= 3:
        step_modules = " → ".join(modules_used[:3])
        summary += f" Pipeline: {step_modules}."

    # Generate specific signals based on module combinations
    likely_signals = []

    if "Registrering" in modules_used and "Status" in modules_used:
        likely_signals.extend([
            "Nye virksomheder på samme adresser som konkursramte (geografisk proximity)",
            "Samme personer i ledelse på tværs af flere selskaber (seriel pattern)"
        ])
        if len([s for s in steps if s.get("module", {}).get("name") == "Registrering"]) > 1:
            likely_signals.append("Tidslig klyngedannelse: flere registreringer/konkurser i samme periode")

    if "Arbejdstilsyn" in modules_used and "Status" in modules_used:
        likely_signals.append("Statusændringer 3-9 måneder efter alvorlige tilsynsreaktioner")

    if "Arbejdstilsyn" in modules_used:
        likely_signals.append("Geografiske klynger af påbud i specifikke brancher/kommuner")

    if "Tinglysning" in modules_used and "Registrering" in modules_used:
        likely_signals.append("Ejendomshandler forud for nye virksomhedsregistreringer")

    if "Personbogen" in modules_used:
        likely_signals.append("Eskalerende økonomiske problemer hos personer forud for konkurser")

    # Fallback if no specific signals
    if not likely_signals:
        likely_signals = [
            "Mønstre vil udvikle sig gradvist over tid",
            "Gentagne hændelser hos samme aktører"
        ]

    # Module-specific quality checks
    quality_checks = [
        "Verificér nøglefund manuelt i primærkilder før publicering",
        "Dokumentér søgekriterier og fravalg for reproducerbarhed"
    ]

    if "Registrering" in modules_used and "Status" in modules_used:
        quality_checks.append("Tjek adressematch manuelt - CVR kan have forskellige formater (vej vs. gade)")

    if "Personbogen" in modules_used or ("Registrering" in modules_used and "Status" in modules_used):
        quality_checks.append("Verificér personidentitet via CPR hvis muligt - samme navn ≠ samme person")

    if "Arbejdstilsyn" in modules_used:
        quality_checks.append("Vær opmærksom på kampagneeffekter - tjek om toppe skyldes øget tilsyn i periode")

    return {
        "search_plan_summary": summary,
        "likely_signals": likely_signals[:5],  # Limit to 5
        "quality_checks": quality_checks
    }

def get_branch_code_description(code: str) -> str:
    """Get Danish description for a branch code.
    
    Common codes used in journalism investigations.
    Full list: https://www.dst.dk/da/Statistik/dokumentation/nomenklaturer/db07
    """
    descriptions = {
        # Transport (49.x)
        "49.41": "Godstransport ad vej",
        "49.41.00": "Godstransport ad vej",
        "49.42": "Flytteforretninger",
        "49.42.00": "Flytteforretninger",
        "53.10": "Postbefordring",
        "53.20": "Andre post- og kurertjenester",
        "52.29": "Andre serviceydelser i forbindelse med transport",
        
        # Detail (47.x)
        "47.11": "Dagligvarebutikker",
        "47.11.10": "Supermarkeder",
        "47.19": "Øvrige detailhandel med bredt varesortiment",
        "47.71": "Detailhandel med beklædning",
        "47.72": "Detailhandel med fodtøj og lædervarer",
        "47.59": "Detailhandel med møbler og boligudstyr",
        
        # Byggeri (41.x, 43.x)
        "41.10": "Udvikling af byggeprojekter",
        "41.20": "Opførelse af bygninger",
        "43.11": "Nedrivning",
        "43.12": "Klargøring af byggegrunde",
        "43.99": "Anden specialiseret bygge- og anlægsvirksomhed",
        
        # Fødevare (10.x)
        "10.11": "Forarbejdning af kød",
        "10.13": "Forarbejdning af fjerkræ",
        "10.51": "Mejerier",
        "10.71": "Bagning af brød og kager",
        
        # Restaurant (56.x)
        "56.10": "Restauranter",
        "56.21": "Catering",
        "56.30": "Serveringssteder",
        
        # Landbrug (01.x)
        "01.11": "Dyrkning af korn",
        "01.21": "Dyrkning af druer",
        "01.41": "Mælkeproduktion",
        "01.50": "Blandet landbrug",
        
        # Ejendom (68.x)
        "68.10": "Køb og salg af egen fast ejendom",
        "68.20": "Udlejning af egen eller lejet fast ejendom",
        "68.31": "Ejendomsmægling",
        
        # Finans (64.x)
        "64.19": "Anden pengeinstitutvirksomhed",
        "64.20": "Holdingselskaber",
        
        # IT (62.x)
        "62.01": "Computerprogrammering",
        "62.02": "Konsulentbistand vedrørende informationsteknologi",
    }
    
    # Try exact match first
    if code in descriptions:
        return descriptions[code]
    
    # Try parent code (first 4 chars for x.xx.yy format)
    if len(code) >= 4:
        parent = code[:4]
        if parent in descriptions:
            return descriptions[parent]
    
    # Fallback: return generic
    return "Branchekode"


def generate_hit_definition(step: dict, module_info: dict) -> dict:
    """Generate hit definition for a specific step."""
    from km24_vejviser.models.usecase_response import HitDefinition

    module_name = step.get("module", {}).get("name", "")
    filters = step.get("filters", {})

    hit_types = []
    indicators = []

    # Module-specific hit definitions
    if module_name == "Registrering":
        # Extract branchekoder from step filters
        branch_codes = filters.get("Branche", [])
        
        # Format branch codes WITH descriptions
        if branch_codes:
            formatted_codes = []
            for code in branch_codes[:3]:  # Max 3 to avoid clutter
                desc = get_branch_code_description(code)
                formatted_codes.append(f"{code} ({desc})")
            
            if len(branch_codes) > 3:
                branch_str = ", ".join(formatted_codes) + f" (+{len(branch_codes)-3} flere)"
            else:
                branch_str = ", ".join(formatted_codes)
        else:
            branch_str = "relevante brancher"
        
        # Get kommune info
        kommuner = filters.get("Kommune", [])
        geo_str = ", ".join(kommuner) if kommuner else "Danmark"
        
        hit_types.append("Ny virksomhed registreret i målområdet")
        indicators.extend([
            f"Branchekode: {branch_str}",
            f"Geografisk område: {geo_str}",
            "Aktiv status (ikke under konkurs/likvidation)"
        ])

    elif module_name == "Arbejdstilsyn":
        hit_types.append("Arbejdstilsynsbesøg med kritikpunkter")
        if "Problem" in filters:
            indicators.append(f"Problem type: {', '.join(filters['Problem'][:3])}")
        if "Reaktion" in filters:
            indicators.append(f"Reaktion niveau: {', '.join(filters['Reaktion'][:3])}")

    elif module_name == "Status":
        hit_types.append("Virksomhedsstatusændring")
        if "Statustype" in filters:
            indicators.append(f"Status: {', '.join(filters['Statustype'][:3])}")
        else:
            indicators.append("Alle statusændringer (konkurs, likvidation, osv.)")

    elif module_name == "Tinglysning":
        hit_types.append("Ejendomstransaktion tinglyst")
        indicators.append("Køber/sælger matcher overvågede aktører")
        if any("min_amount" in str(v) for v in filters.values()):
            indicators.append("Transaktionsbeløb over tærskel")

    elif module_name == "Personbogen":
        hit_types.append("Økonomisk ændring hos person")
        indicators.append("Pant, gæld eller økonomiske dispositioner")

    # Generic fallback
    if not hit_types:
        hit_types.append(f"{module_name}-begivenhed matcher filter")
    if not indicators:
        indicators.append("Se modulets filterkonfiguration")

    return {
        "hit_types": hit_types,
        "indicators": indicators
    }

def generate_step_rationale(step: dict, goal: str, step_index: int) -> str:
    """Generate brief, specific step rationale - max 2 sentences."""
    module_name = step.get("module", {}).get("name", "")

    # First step rationales (foundation)
    if step_index == 0:
        rationales = {
            "Registrering": "CVR FØRST: Dette trin giver CVR-basis for hele undersøgelsen. Ved at starte med branchekoder får vi ALLE aktører, ikke kun problematiske.",
            "Arbejdstilsyn": "Tilsynsreaktioner er ofte første synlige indikator på problemer. Start her giver tidlig varsling om systematiske udfordringer.",
            "Status": "Statusændringer identificerer virksomheder i økonomisk krise. Dette giver udgangspunkt for at spore årsager og konsekvenser.",
            "Tinglysning": "Ejendomstransaktioner afslører økonomiske bevægelser. Start her når penge- og ejerskabsstrømme er central fokus.",
            "Lokalpolitik": "Politiske beslutninger kan både forudgå og følge økonomiske bevægelser. Start her giver strategisk overblik."
        }
        return rationales.get(module_name, f"{module_name} danner fundamentet for analysen.")

    # Later step rationales (building on previous) - CONTEXT-AWARE
    later_rationales = {
        "Status": "Statusændringer viser økonomiske konsekvenser. Kobl til CVR fra tidligere step for at spore systematiske mønstre.",
        "Registrering": "Nye registreringer på kendte adresser kan indikere genstarter. Sammenlign adresser med konkurser fra tidligere step.",
        "Personbogen": "Personbogen afslører økonomiske relationer og pantsætninger. Kobl personer fra konkurser til nye selskaber.",
        "Tinglysning": "Ejendomsdata knytter aktører sammen gennem adresser og transaktioner. Verificér ejerskabsforhold fra tidligere trin.",
        "Lokalpolitik": "Politiske beslutninger giver kontekst til økonomiske bevægelser. Kan beslutninger forklare mønstre fra tidligere step?"
    }
    
    # Special handling for Arbejdstilsyn - depends on position
    if module_name == "Arbejdstilsyn":
        if step_index <= 1:  # Early in pipeline
            return ("Tilsynsreaktioner kan forklare efterfølgende statusændringer. "
                   "Dokumentér tidspunkter for at spore kausal rækkefølge.")
        else:  # Later in pipeline
            return ("Tilsynsreaktioner kan forklare statusændringer set tidligere. "
                   "Tjek om kritik forudgik konkurser.")

    return later_rationales.get(module_name, f"{module_name} tilføjer kontekst og verifikation til tidligere fund.")

# --- API Endpoints ---
@app.post(
    "/generate-recipe/",
    response_model=Any,
    responses={
        200: {"description": "Struktureret JSON-plan for journalistisk mål."},
        422: {"description": "Ugyldig input eller valideringsfejl."},
        429: {"description": "Rate limit exceeded."},
        500: {"description": "Intern serverfejl."}
    },
    summary="Generér strategisk opskrift for journalistisk mål",
    description="Modtag et journalistisk mål og returnér en pædagogisk, struktureret JSON-plan."
)
@limiter.limit("5/minute")
async def generate_recipe_api(request: Request, body: RecipeRequest):
    logger.info(f"Modtog generate-recipe request: {body}")
    # Ekstra defensiv sanitering
    goal = body.goal
    if not isinstance(goal, str):
        logger.warning("goal er ikke en streng")
        return JSONResponse(status_code=422, content={"error": "goal skal være en streng"})
    goal = goal.strip()
    if not goal:
        logger.warning("goal er tom efter strip")
        return JSONResponse(status_code=422, content={"error": "goal må ikke være tom"})
    
    try:
        # Return controlled error when Anthropic API key is not configured
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if not env_key or "YOUR_API_KEY_HERE" in env_key:
            logger.warning("ANTHROPIC_API_KEY not set in environment; returning error response")
            return JSONResponse(status_code=500, content={"error": "ANTHROPIC_API_KEY er ikke konfigureret."})
        if client is None:
            logger.warning("Anthropic client not configured; returning error response")
            return JSONResponse(status_code=500, content={"error": "ANTHROPIC_API_KEY er ikke konfigureret."})
        raw_recipe = await get_anthropic_response(goal)

        if "error" in raw_recipe:
            # Graceful fallback: synthesize minimal raw plan to keep UX/tests green
            logger.warning(f"Fejl fra get_anthropic_response: {raw_recipe['error']}")
            raw_recipe = {
                "title": "Offline fallback plan",
                "strategy_summary": "Deterministisk fallback pga. LLM-fejl",
                "investigation_steps": [
                    {
                        "step": 1,
                        "title": "Basis virksomhedsovervågning",
                        "type": "search",
                        "module": "Registrering",
                        "rationale": "Start med CVR-baseret identifikation",
                        "details": {"search_string": "", "recommended_notification": "interval"}
                    },
                    {
                        "step": 2,
                        "title": "Overvåg ejendomshandler",
                        "type": "search",
                        "module": "Tinglysning",
                        "rationale": "Verificer handler i tinglysningsdata",
                        "details": {"search_string": "~overdragelse~", "recommended_notification": "løbende"}
                    },
                    {
                        "step": 3,
                        "title": "Følg selskabsændringer",
                        "type": "search",
                        "module": "Kapitalændring",
                        "rationale": "Find kapitalændringer og fusioner",
                        "details": {"search_string": "kapitalforhøjelse OR fusion", "recommended_notification": "daglig"}
                    }
                ],
                "next_level_questions": [
                    "Hvilke aktører går igen?",
                    "Er der mønstre i geografi eller branche?"
                ],
                "potential_story_angles": [
                    "Systematiske mønstre i handler og ændringer"
                ],
                "creative_cross_references": []
            }

        # Enrich recipe with API validation (new API-first approach)
        logger.info("Enriching recipe with API validation...")
        enriched_recipe = await enrich_recipe_with_api(raw_recipe)

        completed_recipe = await complete_recipe(enriched_recipe, goal)
        logger.info("Returnerer completed_recipe til frontend")
        return JSONResponse(content=completed_recipe)
        
    except ValueError as e:
        logger.error(f"Recipe validation fejl: {e}")
        return JSONResponse(
            status_code=422, 
            content={"error": f"Recipe validation failed: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Uventet fejl i generate_recipe_api: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, 
            content={"error": "Intern serverfejl under recipe generering"}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint til monitoring."""
    logger.info("Health check endpoint kaldt")
    
    # Get KM24 API health status
    km24_client = get_km24_client()
    km24_status = await km24_client.get_health_status()
    
    return {
        "status": "healthy",
        "anthropic_configured": client is not None,
        "km24_api_status": km24_status,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/km24-status")
async def km24_status():
    """KM24 API connection status endpoint."""
    logger.info("KM24 status endpoint kaldt")
    km24_client = get_km24_client()
    status = await km24_client.get_health_status()
    return JSONResponse(content=status)

@app.post("/api/km24-refresh-cache")
async def refresh_km24_cache():
    """Manuel opdatering af KM24 cache."""
    logger.info("Manuel cache opdatering anmodet")
    km24_client = get_km24_client()
    
    # Force refresh modules
    result = await km24_client.get_modules_basic(force_refresh=True)
    
    if result.success:
        return JSONResponse(content={
            "success": True,
            "message": "Cache opdateret succesfuldt",
            "cached": result.cached,
            "cache_age": result.cache_age
        })
    else:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Fejl ved cache opdatering",
                "error": result.error
            }
        )

@app.delete("/api/km24-clear-cache")
async def clear_km24_cache():
    """Ryd KM24 cache."""
    logger.info("Cache rydning anmodet")
    km24_client = get_km24_client()
    result = await km24_client.clear_cache()
    
    if result["success"]:
        return JSONResponse(content=result)
    else:
        return JSONResponse(status_code=500, content=result)

@app.get("/api/filter-catalog/status")
async def get_filter_catalog_status():
    """Hent status for filter-kataloget."""
    try:
        filter_catalog = get_filter_catalog()
        status = await filter_catalog.load_all_filters()
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f"Fejl ved hentning af filter-katalog status: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Fejl ved hentning af filter-katalog status: {str(e)}"}
        )

@app.post("/api/filter-catalog/recommendations")
async def get_filter_recommendations(request: Request):
    """Hent filter-anbefalinger baseret på et mål."""
    try:
        body = await request.json()
        goal = body.get('goal', '')
        modules = body.get('modules', [])
        
        if not goal:
            return JSONResponse(
                status_code=422,
                content={"error": "goal er påkrævet"}
            )
        
        # NOTE: Deprecated endpoint - recommendations now handled by enrich_recipe_with_api()
        # Return empty recommendations
        rec_data = []
        
        return JSONResponse(content={
            "goal": goal,
            "modules": modules,
            "recommendations": rec_data,
            "total_recommendations": len(rec_data)
        })
    except Exception as e:
        logger.error(f"Fejl ved hentning af filter-anbefalinger: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Fejl ved hentning af filter-anbefalinger: {str(e)}"}
        )

# --- Inspiration Prompts ---
inspiration_prompts = [
    {
        "title": "🏗️ Konkursryttere i byggebranchen",
        "prompt": "Jeg har en mistanke om, at de samme personer står bag en række konkurser i byggebranchen i og omkring København. Jeg vil lave en overvågning, der kan afdække, om konkursramte ejere eller direktører dukker op i nye selskaber inden for samme branche."
    },
    {
        "title": "🚧 Underleverandør-karrusel i offentligt byggeri",
        "prompt": "Jeg vil undersøge store offentlige byggeprojekter i Jylland, som har vundet udbud. Opsæt en overvågning, der holder øje med, om hovedentreprenøren hyppigt skifter underleverandører, og om disse underleverandører pludselig går konkurs kort efter at have modtaget betaling."
    },
    {
        "title": "🏙️ Interessekonflikter ved byudvikling",
        "prompt": "Der er stor udvikling i gang på havneområdet i Aalborg. Jeg vil overvåge alle nye lokalplaner, større ejendomshandler (> 25 mio. kr) og nye byggetilladelser i området. Samtidig vil jeg se, om lokale byrådspolitikere har personlige økonomiske interesser i de selskaber, der bygger."
    },
    {
        "title": "🌾 Landzone-dispensationer i Nordsjælland",
        "prompt": "Jeg vil afdække, hvilke landbrugsejendomme i Nordsjælland der har fået dispensation til at udstykke grunde til byggeri. Overvågningen skal fange både de politiske beslutninger i kommunerne og de efterfølgende tinglysninger af ejendomssalg."
    },
    {
        "title": "⚠️ Asbest og nedstyrtningsfare",
        "prompt": "Jeg vil afdække et mønster af alvorlige arbejdsmiljøsager relateret til asbest og nedstyrtningsfare i nedrivningsbranchen (branchekode 43.11) på Fyn. Overvågningen skal fange de mest alvorlige påbud fra Arbejdstilsynet og efterfølgende følge med i, om sagerne omtales i lokale medier."
    },
    {
        "title": "🌱 Bæredygtigt byggeri - fakta eller facade",
        "prompt": "Jeg vil skrive en artikelserie om, hvilke byggevirksomheder der er førende inden for bæredygtigt byggeri. Opsæt en overvågning, der fanger omtale af 'bæredygtighed', 'DGNB-certificering' og 'træbyggeri' i fagmedier og på virksomhedernes egne hjemmesider. Krydsreference med virksomhedernes regnskabstal for at se, om der er økonomi i det."
    },
    {
        "title": "💼 Kapitalfonde i dansk tech",
        "prompt": "Jeg vil identificere og overvåge danske kapitalfondes investeringer i teknologivirksomheder. Opsæt en radar, der fanger kapitalændringer, fusioner og børsmeddelelser relateret til denne niche."
    },
    {
        "title": "📊 Insiderhandel i C25-selskaber",
        "prompt": "Overvåg handler med aktier foretaget af direktører og bestyrelsesmedlemmer (indberetninger om handler fra insidere) i alle C25-selskaber. Opret en alarm, der giver besked, når flere insidere i samme selskab sælger eller køber aktier inden for en kort periode (f.eks. en uge)."
    },
    {
        "title": "🌍 Greenwashing i energisektoren",
        "prompt": "Store energiselskaber markedsfører sig kraftigt på bæredygtighed. Jeg vil opsætte en overvågning, der sammenholder deres grønne udmeldinger i medierne med faktiske miljøsager eller kritik fra Miljøstyrelsen. Jeg vil fange søgeord som 'grøn omstilling', 'bæredygtig' og 'CO2-neutral' og krydsreferere med selskabernes CVR-numre i Miljøsager-modulet."
    },
    {
        "title": "💳 Kviklån og gældsinddrivelse",
        "prompt": "Jeg vil undersøge markedsføringen fra kviklånsvirksomheder. Overvåg deres omtale i sociale medier og landsdækkende medier. Samtidig vil jeg overvåge Retslister for at se, om disse firmaer optræder hyppigt i sager om gældsinddrivelse i fogedretten."
    }
]

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Uventet fejl: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Der opstod en intern serverfejl"}
    )

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    logger.info("Serverer index_new.html til bruger")
    return templates.TemplateResponse("index_new.html", {"request": request, "prompts": inspiration_prompts}) 

@app.get("/generate-recipe-stream/")
async def generate_recipe_stream(goal: str):
    async def event_stream():
        try:
            # Step 1: Analyze goal
            yield f"data: {json.dumps({'progress': 10, 'message': 'Analyserer dit journalistiske mål...', 'details': 'Uddrager nøgleord og fokus'})}\n\n"
            await asyncio.sleep(0.5)

            # Step 2: Load modules and filters
            yield f"data: {json.dumps({'progress': 25, 'message': 'Henter KM24 moduler og filtre...', 'details': 'Indlæser modules/basic og initialiserer filterkatalog'})}\n\n"
            km24_client: KM24APIClient = get_km24_client()
            modules_response = await km24_client.get_modules_basic()
            filter_catalog = get_filter_catalog()
            await filter_catalog.load_all_filters()

            # Step 3: Prepare for recipe generation
            yield f"data: {json.dumps({'progress': 35, 'message': 'Forbereder opskrift...', 'details': 'Analyserer moduler'})}\n\n"
            await asyncio.sleep(0.3)

            # Step 4: Generate recipe with AI
            yield f"data: {json.dumps({'progress': 75, 'message': 'Genererer opskrift med AI...', 'details': 'Kalder Claude for fuld strategi'})}\n\n"
            raw = await get_anthropic_response(goal)

            # Step 5: Enrich with API validation
            yield f"data: {json.dumps({'progress': 85, 'message': 'Validerer filtre mod KM24 API...', 'details': 'API-baseret validering'})}\n\n"
            enriched = await enrich_recipe_with_api(raw) if isinstance(raw, dict) else raw

            # Step 6: Final validation and optimization
            yield f"data: {json.dumps({'progress': 90, 'message': 'Optimerer strategien...', 'details': 'Normalisering og validering'})}\n\n"
            completed = await complete_recipe(enriched, goal) if isinstance(enriched, dict) else {"error": "Ugyldigt AI-svar"}

            # Step 7: Done
            yield f"data: {json.dumps({'progress': 100, 'message': 'Klar til brug!', 'details': 'Opskrift genereret'})}\n\n"
            yield f"data: {json.dumps({'result': completed})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'progress': 100, 'message': 'Fejl', 'details': str(e)})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")