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
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Any, List, Dict

# KM24 API Integration
from .km24_client import get_km24_client, KM24APIClient
from .filter_catalog import get_filter_catalog
from .knowledge_base import get_knowledge_base

# Recipe processing functions (moved to recipe_processor.py)
from .recipe_processor import complete_recipe, enrich_recipe_with_api

# Researcher response models
from .models.researcher_response import ResearcherResponse, ResearcherStep

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Konfigurer struktureret logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("km24_vejviser")

# --- Configure Anthropic API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = None
if not ANTHROPIC_API_KEY or "YOUR_API_KEY_HERE" in ANTHROPIC_API_KEY:
    print(
        "ADVARSEL: ANTHROPIC_API_KEY er ikke sat i .env. Applikationen vil ikke kunne kontakte Claude."
    )
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


@app.on_event("startup")
async def startup_event() -> None:
    """Indlæs og cachér alle filter-data og knowledge base ved applikationens opstart."""
    try:
        logger.info("Application startup: Pre-caching filterdata fra KM24 API …")
        fc = get_filter_catalog()
        status = await fc.load_all_filters(force_refresh=True)
        logger.info(f"Pre-caching færdig: {status}")

        # Load knowledge base for intelligent module selection
        kb = get_knowledge_base()
        kb_status = await kb.load(force_refresh=False)
        logger.info(f"Knowledge base loaded: {kb_status}")
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
        ...,
        min_length=10,
        max_length=1000,
        description="Journalistisk mål",
        example="Undersøg store byggeprojekter i Aarhus og konkurser i byggebranchen",
    )

    @validator("goal")
    def validate_goal(cls, v):
        if not v or not v.strip():
            raise ValueError("Mål kan ikke være tomt eller kun whitespace")
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


async def build_system_prompt(goal: str, selected_modules: List[Dict[str, Any]]) -> str:
    """
    Build focused system prompt using pre-selected candidate modules.

    Args:
        goal: The user's journalistic goal
        selected_modules: Pre-selected relevant modules (with longDescription)

    Returns:
        Complete system prompt with focused module information
    """
    # Get KM24 client for fetching generic values
    km24_client = get_km24_client()

    # Define critical modules that need generic values enrichment
    critical_modules_for_values = {"Arbejdstilsyn", "Status"}

    simplified_modules = []
    for module in selected_modules:
        module_title = module.get("title", "")
        module.get("id")
        parts = module.get("parts", [])

        # Build available_filters list with values for critical modules
        available_filters = []

        for part in parts:
            part_name = part.get("name", "")
            if not part_name:
                continue

            part_type = part.get("part")
            part_id = part.get("id")

            # For critical modules with generic_value parts, fetch actual values
            if (
                module_title in critical_modules_for_values
                and part_type == "generic_value"
                and part_id
            ):
                try:
                    values_response = await km24_client.get_generic_values(
                        part_id, force_refresh=False
                    )
                    if values_response.success:
                        items = values_response.data.get("items", [])
                        values = [
                            item.get("name", "").strip()
                            for item in items
                            if item.get("name")
                        ]
                        if values:
                            # Include values for this filter
                            available_filters.append(
                                {
                                    "name": part_name,
                                    "values": values[
                                        :20
                                    ],  # Limit to 20 values to save tokens
                                }
                            )
                        else:
                            # No values, just include name
                            available_filters.append({"name": part_name})
                    else:
                        # API call failed, just include name
                        available_filters.append({"name": part_name})
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch generic values for {module_title}.{part_name}: {e}"
                    )
                    available_filters.append({"name": part_name})
            else:
                # For non-critical modules or non-generic_value parts, just include name
                available_filters.append({"name": part_name})

        # Use longDescription instead of shortDescription for richer context
        simplified_modules.append(
            {
                "title": module_title,
                "description": module.get("longDescription", ""),
                "available_filters": available_filters,
            }
        )

    # Format modules as compact JSON (still single line, but more informative)
    modules_json = json.dumps(
        simplified_modules, ensure_ascii=False, separators=(",", ":")
    )

    prompt = f"""Du er en erfaren dansk data-journalist og researcher med dyb forståelse for:
- KM24's 44+ moduler og hvordan de kobler til danske offentlige registre
- Danske data-traditioner og myndighedsstrukturer (CVR, Arbejdstilsyn, Tinglysning, etc.)
- Journalistiske metoder og hvad der udgør en god historie

**BRUGERENS MÅL:**
{goal}

**ALLE TILGÆNGELIGE MODULER (alle 44 - vælg de bedste):**
{modules_json}

**DIN OPGAVE SOM RESEARCHER:**

1. **FORSTÅ brugerens journalistiske hensigt**
   - Hvad er det egentlige mål?
   - Hvilken type sager/mønstre søges?
   - Hvilke sammenhænge er vigtige?

2. **VÆLG de mest relevante moduler fra ALLE 44**
   - Du har adgang til ALLE moduler - vælg de bedste til formålet
   - Vær IKKE begrænset til "almindelige" moduler
   - Hvis Kystdirektoratet, Miljøstyrelsen eller nichemoduler er mest relevante - vælg dem!

3. **ANBEFAL 1-2 konkrete overvågninger (MAX 2!)**
   - Start med 1 overvågning, tilføj 2. kun hvis klart nødvendigt
   - For hver: Forklar dybt men KONCIST HVORFOR dette modul + disse filtre
   - Vær konkret om hvad den fanger og IKKE fanger
   - Hold forklaringer præcise - undgå gentagelser

4. **VÆR PÆDAGOGISK og KONKRET**
   - Forklar danske data-traditioner og myndighedsstrukturer
   - Brug KONKRETE tal og estimater (med disclaimer!)
   - Giv KONKRETE eksempler på hvad overvågningen fanger
   - Advar tydeligt om begrænsninger

**VIGTIGT OM ESTIMATER:**
Du kan ikke se historisk statistik, så når du estimerer "expected_volume":
- Basér det på logisk ræsonnement (byens størrelse, branchens aktivitet, etc.)
- Vær ÆRLIG om at det er et skøn
- Inkludér disclaimer
- Eksempel: "Estimeret 5-15 hits/måned for Aarhus (baseret på byens størrelse og typisk byggeaktivitet). Faktisk volumen afhænger af Arbejdstilsynets tilsynsfrekvens."

**FILTER-REGLER:**
- Brug KUN filter-navne fra modulets "available_filters" liste
- For filtre med 'values' liste: Brug EKSAKTE værdier fra listen
- For filtre uden 'values': Brug logiske værdier (kommuner, branchekoder, etc.)
- ALDRIG engelske type-navne som "municipality" eller "industry"

**SØGESTRENG SYNTAKS:**
- Boolean: AND, OR, NOT (store bogstaver!)
- Parallelle: semikolon (ikke komma) → "asbest;asbestsag"
- Kombineret: "asbest AND byggeri OR nedrivning"

**OUTPUT FORMAT (strict JSON):**
{{
  "understanding": "Brugeren vil overvåge... [konkret forståelse af det journalistiske mål]",

  "monitoring_setups": [
    {{
      "step_number": 1,
      "title": "Kort, beskrivende titel",
      "module": {{
        "name": "Arbejdstilsyn",
        "id": "110"
      }},

      "module_rationale": "Jeg anbefaler Arbejdstilsyn fordi... [DYBT niveau: Hvad er Arbejdstilsyn? Hvilke data registrerer de? Hvordan passer det til målet? Hvad er sammenhængen?]",

      "filters": {{
        "Problem": ["Asbest"],
        "Kommune": ["Aarhus"],
        "Branche": ["433200", "433300"]
      }},

      "filter_explanations": {{
        "Problem": "Asbest-filteret fanger alle sager hvor Arbejdstilsynet har registreret asbest som kritikpunkt. Dette inkluderer manglende sikkerhedsforanstaltninger, forkert bortskaffelse og eksponering.",
        "Kommune": "Indsnævrer til kun tilsyn i Aarhus kommune. Bemærk: Det er tilsynsstedet der tæller, ikke virksomhedens CVR-adresse.",
        "Branche": "Nedrivning (433200) og bygningsinstallation (433300) - brancher hvor asbest-risiko er størst."
      }},

      "monitoring_explanation": {{
        "what_it_catches": [
          "Alle påbud/strakspåbud/forbud med asbest-problematik i Aarhus",
          "Både enkeltsager og gentagne overtrædere",
          "Kritik til små og store firmaer"
        ],  // MAX 3-4 punkter
        "what_it_misses": [
          "Asbest-sager uden for Aarhus kommune",
          "Virksomheder i andre brancher (fx industri)",
          "Sager hvor asbest er til stede men ikke primær kritik"
        ],  // MAX 3-4 punkter
        "expected_volume": "Estimeret 5-15 hits/måned for Aarhus (baseret på byens størrelse og byggeaktivitet). Faktisk volumen kan variere med Arbejdstilsynets tilsynsfrekvens.",
        "false_positive_risk": "Lav - Problem=Asbest er specifik kategori og giver sjældent irrelevante hits"  // 1-2 sætninger MAX
      }},

      "journalistic_context": {{
        "story_angles": [
          "Gentagne overtrædere: Firmaer der får kritik flere gange",
          "Alvorlighedsgradering: Sammenlign påbud vs strakspåbud",
          "Tidsmønstre: Stiger sagerne i renoveringsæsonen?"
        ],  // MAX 3-4 punkter
        "investigative_tactics": "Krydsreferencér med CVR-data, tjek tidligere kritik, følg op på om påbud efterleves. Kombiner evt. med Status for at se om kritiserede firmaer går konkurs.",  // 2-3 sætninger MAX
        "red_flags": [
          "Gentagne kritikpunkter til samme virksomhed",
          "Strakspåbud/forbud - indikerer alvorlige forhold",
          "Store kendte virksomheder med kritik"
        ]  // MAX 3-4 punkter
      }},

      "rationale": "Arbejdstilsyn registrerer asbest-kritik",
      "explanation": "Overvåg asbest-påbud i Aarhus"
    }}
  ],

  "overall_strategy": "Fokuserer på Arbejdstilsyn. Kan kombineres med Status (konkurser) eller Lokalpolitik (politiske beslutninger).",

  "important_context": "Asbest forbudt i Danmark fra 1986, men findes stadig i ældre bygninger. Nedrivning/renovering kræver særlige forholdsregler. Arbejdstilsynet udsteder påbud ved overtrædelser."
}}

**KRITISKE REGLER:**
1. Modul-navne skal PRÆCIST matche "title" fra listen
2. Filter-nøgler skal matche "available_filters" fra modulet
3. Brug EKSAKTE værdier fra "values" liste når den findes
4. Forklar HVORFOR, ikke bare HVAD
5. Vær konkret: "5-15 hits/måned (estimat)" ikke "moderate hits"
6. Nævn ALTID begrænsninger (what_it_misses)
7. Tænk journalistisk - hvilke vinkler giver dette?
8. Estimater skal have disclaimer om usikkerhed
9. Vælg BEDSTE modul fra alle 44 - ikke kun populære
10. Typisk 1-2 overvågninger, max 3

**GOD vs. DÅRLIG FORKLARING:**

❌ DÅRLIG: "Filteret fanger relevante sager"
✅ GOD: "Problem=Asbest fanger alle sager hvor Arbejdstilsynet har registreret asbest som kritikpunkt. Dette inkluderer manglende sikkerhedsforanstaltninger ved nedrivning, forkert bortskaffelse, og eksponering af medarbejdere."

❌ DÅRLIG: "Mange hits"
✅ GOD: "Estimeret 5-15 hits/måned for Aarhus (baseret på byens størrelse og byggeaktivitet). Faktisk volumen kan variere - nogle måneder kan være stille, andre kan have 20+ hits."

Generér nu researcher response baseret på brugerens mål og alle tilgængelige moduler.
"""

    return prompt


async def get_anthropic_response(goal: str) -> dict:
    """
    Kalder Anthropic API'en med intelligent modul pre-selektion.

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
        return {
            "error": f"Kunne ikke hente moduler fra KM24 API: {modules_response.error}"
        }

    all_modules = modules_response.data.get("items", [])

    # Send ALLE moduler til researcher-LLM (ubias'd selection)
    selected_modules = all_modules
    logger.info(
        f"Sending all {len(all_modules)} modules to researcher-LLM for unbiased selection"
    )

    # Build system prompt with ALL modules
    logger.info("Building researcher prompt with all modules...")
    full_system_prompt = await build_system_prompt(goal, selected_modules)
    retries = 3
    delay = 2

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=8192,
                system=full_system_prompt,
                messages=[
                    {"role": "user", "content": "Generér JSON-planen som anmodet."}
                ],
            )
            # Få fat i tekst-indholdet fra responsen
            raw_text = response.content[0].text
            logger.info(f"Anthropic API response received on attempt {attempt + 1}")

            cleaned = clean_json_response(raw_text)
            return json.loads(cleaned)

        except anthropic.APIError as e:
            logger.error(
                f"Anthropic API error on attempt {attempt + 1}: {e}", exc_info=True
            )
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Anthropic API fejl efter {retries} forsøg: {e}"}
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON decode error on attempt {attempt + 1}: {e}", exc_info=True
            )
            logger.error(
                f"Raw response was: {locals().get('raw_text', '<no raw_text>')}"
            )
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {
                    "error": f"Kunne ikke parse JSON fra API'en. Svar: {locals().get('raw_text', '<no raw_text>')}"
                }
        except Exception as e:
            logger.error(
                f"Uventet fejl i get_anthropic_response på attempt {attempt + 1}: {e}",
                exc_info=True,
            )
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Uventet fejl efter {retries} forsøg: {e}"}
    return {"error": "Ukendt fejl i get_anthropic_response."}


def map_researcher_response_to_recipe(researcher_data: dict) -> dict:
    """
    Map ResearcherResponse format til det eksisterende investigation_steps format.

    Konverterer den nye researcher-baserede structure tilbage til det format
    som resten af pipelinen forventer.
    """
    logger.info("Mapper ResearcherResponse til legacy recipe format")

    try:
        # Parse til ResearcherResponse model for validation
        researcher_response = ResearcherResponse(**researcher_data)

        # Build investigation_steps fra monitoring_setups
        investigation_steps = []
        for setup in researcher_response.monitoring_setups:
            step = {
                "step": setup.step_number,
                "title": setup.title,
                "type": "search",
                "module": setup.module.name,
                "rationale": setup.module_rationale[:200] + "..." if len(setup.module_rationale) > 200 else setup.module_rationale,  # Shorten for compatibility
                "explanation": setup.explanation if setup.explanation else setup.module_rationale[:150],
                "details": {
                    "filters": setup.filters,
                    "search_string": "",  # Will be populated by normalization
                    "recommended_notification": "løbende",  # Default
                },
                # Include researcher fields for potential frontend use
                "researcher_context": {
                    "module_rationale": setup.module_rationale,
                    "filter_explanations": setup.filter_explanations,
                    "monitoring_explanation": setup.monitoring_explanation.dict(),
                    "journalistic_context": setup.journalistic_context.dict(),
                }
            }
            investigation_steps.append(step)

        # Build legacy recipe structure
        legacy_recipe = {
            "title": f"Researcher-genereret plan: {researcher_response.understanding[:50]}...",
            "strategy_summary": researcher_response.understanding,
            "investigation_steps": investigation_steps,
            "overall_strategy": researcher_response.overall_strategy or "",
            "important_context": researcher_response.important_context or "",
            "next_level_questions": [],  # Kan udvides senere
            "potential_story_angles": [
                angle for setup in researcher_response.monitoring_setups
                for angle in setup.journalistic_context.story_angles
            ][:5],  # Tag top 5
            "creative_cross_references": [],
        }

        logger.info(f"Mapped {len(investigation_steps)} researcher setups til investigation_steps")
        return legacy_recipe

    except Exception as e:
        logger.error(f"Fejl i mapping af researcher response: {e}", exc_info=True)
        # Return error structure
        return {"error": f"Kunne ikke parse researcher response: {str(e)}"}


# Note: enrich_recipe_with_api has been moved to recipe_processor.py
async def generate_search_optimization(module_card, goal: str, step: dict) -> dict:
    """Generer optimal søgekonfiguration baseret på modul og mål."""
    try:
        optimization = {
            "for_module": module_card.title,
            "your_goal": goal[:50] + "..." if len(goal) > 50 else goal,
            "optimal_config": {},
            "rationale": "",
        }

        # Analyze goal for specific keywords
        goal_lower = goal.lower()

        # Smart recommendations based on available filters and goal
        config = {}
        rationale_parts = []

        # Industry recommendations
        industry_filters = [
            f for f in module_card.available_filters if f["type"] == "industry"
        ]
        if industry_filters:
            if any(word in goal_lower for word in ["bygge", "byggeri", "construction"]):
                config["branche"] = ["41.20.00", "43.11.00"]
                rationale_parts.append(
                    "Branchekoder for byggeri giver præcis targeting"
                )
            elif any(
                word in goal_lower for word in ["energi", "strøm", "elektricitet"]
            ):
                config["branche"] = ["35.11.00", "35.12.00"]
                rationale_parts.append(
                    "Energibranchekoder fokuserer på relevante selskaber"
                )
            elif any(word in goal_lower for word in ["transport", "logistik", "fragt"]):
                config["branche"] = ["49.41.00", "52.29.90"]
                rationale_parts.append(
                    "Transport-branchekoder rammer målgruppen præcist"
                )

        # Municipality recommendations
        municipality_filters = [
            f for f in module_card.available_filters if f["type"] == "municipality"
        ]
        if municipality_filters:
            # Extract municipality names from goal
            dansk_kommuner = [
                "københavn",
                "aarhus",
                "odense",
                "aalborg",
                "esbjerg",
                "randers",
                "kolding",
            ]
            found_municipalities = [kom for kom in dansk_kommuner if kom in goal_lower]
            if found_municipalities:
                config["kommune"] = found_municipalities
                rationale_parts.append(
                    f"Geografisk fokus på {', '.join(found_municipalities)}"
                )

        # Amount recommendations
        amount_filters = [
            f for f in module_card.available_filters if f["type"] == "amount_selection"
        ]
        if amount_filters:
            if any(
                word in goal_lower for word in ["store", "større", "million", "mio"]
            ):
                config["amount_min"] = "10000000"
                rationale_parts.append("Beløbsgrænse fokuserer på større sager")

        # Search string optimization
        search_filters = [
            f for f in module_card.available_filters if f["type"] == "search_string"
        ]
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


# Note: _get_default_sources_for_module has been moved to recipe_processor.py
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
# --- Helper Functions for Context and Assessment ---


# Note: generate_context_block has been moved to recipe_processor.py

# Note: generate_ai_assessment has been moved to recipe_processor.py

# Note: get_branch_code_description has been moved to recipe_processor.py

# Note: generate_hit_definition has been moved to recipe_processor.py


# Note: generate_step_rationale has been moved to recipe_processor.py
# --- API Endpoints ---
@app.post(
    "/generate-recipe/",
    response_model=Any,
    responses={
        200: {"description": "Struktureret JSON-plan for journalistisk mål."},
        422: {"description": "Ugyldig input eller valideringsfejl."},
        429: {"description": "Rate limit exceeded."},
        500: {"description": "Intern serverfejl."},
    },
    summary="Generér strategisk opskrift for journalistisk mål",
    description="Modtag et journalistisk mål og returnér en pædagogisk, struktureret JSON-plan.",
)
@limiter.limit("5/minute")
async def generate_recipe_api(request: Request, body: RecipeRequest):
    logger.info(f"Modtog generate-recipe request: {body}")
    # Ekstra defensiv sanitering
    goal = body.goal
    if not isinstance(goal, str):
        logger.warning("goal er ikke en streng")
        return JSONResponse(
            status_code=422, content={"error": "goal skal være en streng"}
        )
    goal = goal.strip()
    if not goal:
        logger.warning("goal er tom efter strip")
        return JSONResponse(status_code=422, content={"error": "goal må ikke være tom"})

    try:
        # Return controlled error when Anthropic API key is not configured
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if not env_key or "YOUR_API_KEY_HERE" in env_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set in environment; returning error response"
            )
            return JSONResponse(
                status_code=500,
                content={"error": "ANTHROPIC_API_KEY er ikke konfigureret."},
            )
        if client is None:
            logger.warning("Anthropic client not configured; returning error response")
            return JSONResponse(
                status_code=500,
                content={"error": "ANTHROPIC_API_KEY er ikke konfigureret."},
            )
        raw_recipe = await get_anthropic_response(goal)

        # Check if we got researcher response and map it to legacy format
        if "monitoring_setups" in raw_recipe and "error" not in raw_recipe:
            logger.info("Detected researcher response format - mapping to legacy format")
            raw_recipe = map_researcher_response_to_recipe(raw_recipe)

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
                        "details": {
                            "search_string": "",
                            "recommended_notification": "interval",
                        },
                    },
                    {
                        "step": 2,
                        "title": "Overvåg ejendomshandler",
                        "type": "search",
                        "module": "Tinglysning",
                        "rationale": "Verificer handler i tinglysningsdata",
                        "details": {
                            "search_string": "~overdragelse~",
                            "recommended_notification": "løbende",
                        },
                    },
                    {
                        "step": 3,
                        "title": "Følg selskabsændringer",
                        "type": "search",
                        "module": "Kapitalændring",
                        "rationale": "Find kapitalændringer og fusioner",
                        "details": {
                            "search_string": "kapitalforhøjelse OR fusion",
                            "recommended_notification": "daglig",
                        },
                    },
                ],
                "next_level_questions": [
                    "Hvilke aktører går igen?",
                    "Er der mønstre i geografi eller branche?",
                ],
                "potential_story_angles": [
                    "Systematiske mønstre i handler og ændringer"
                ],
                "creative_cross_references": [],
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
            status_code=422, content={"error": f"Recipe validation failed: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Uventet fejl i generate_recipe_api: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Intern serverfejl under recipe generering"},
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
        "timestamp": datetime.utcnow().isoformat(),
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
        return JSONResponse(
            content={
                "success": True,
                "message": "Cache opdateret succesfuldt",
                "cached": result.cached,
                "cache_age": result.cache_age,
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Fejl ved cache opdatering",
                "error": result.error,
            },
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
            content={"error": f"Fejl ved hentning af filter-katalog status: {str(e)}"},
        )


@app.post("/api/filter-catalog/recommendations")
async def get_filter_recommendations(request: Request):
    """Hent filter-anbefalinger baseret på et mål."""
    try:
        body = await request.json()
        goal = body.get("goal", "")
        modules = body.get("modules", [])

        if not goal:
            return JSONResponse(status_code=422, content={"error": "goal er påkrævet"})

        # NOTE: Deprecated endpoint - recommendations now handled by enrich_recipe_with_api()
        # Return empty recommendations
        rec_data = []

        return JSONResponse(
            content={
                "goal": goal,
                "modules": modules,
                "recommendations": rec_data,
                "total_recommendations": len(rec_data),
            }
        )
    except Exception as e:
        logger.error(f"Fejl ved hentning af filter-anbefalinger: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Fejl ved hentning af filter-anbefalinger: {str(e)}"},
        )


# --- Inspiration Prompts ---
inspiration_prompts = [
    {
        "title": "🏗️ Konkursryttere i byggebranchen",
        "prompt": "Jeg har en mistanke om, at de samme personer står bag en række konkurser i byggebranchen i og omkring København. Jeg vil lave en overvågning, der kan afdække, om konkursramte ejere eller direktører dukker op i nye selskaber inden for samme branche.",
    },
    {
        "title": "🚧 Underleverandør-karrusel i offentligt byggeri",
        "prompt": "Jeg vil undersøge store offentlige byggeprojekter i Jylland, som har vundet udbud. Opsæt en overvågning, der holder øje med, om hovedentreprenøren hyppigt skifter underleverandører, og om disse underleverandører pludselig går konkurs kort efter at have modtaget betaling.",
    },
    {
        "title": "🏙️ Interessekonflikter ved byudvikling",
        "prompt": "Der er stor udvikling i gang på havneområdet i Aalborg. Jeg vil overvåge alle nye lokalplaner, større ejendomshandler (> 25 mio. kr) og nye byggetilladelser i området. Samtidig vil jeg se, om lokale byrådspolitikere har personlige økonomiske interesser i de selskaber, der bygger.",
    },
    {
        "title": "🌾 Landzone-dispensationer i Nordsjælland",
        "prompt": "Jeg vil afdække, hvilke landbrugsejendomme i Nordsjælland der har fået dispensation til at udstykke grunde til byggeri. Overvågningen skal fange både de politiske beslutninger i kommunerne og de efterfølgende tinglysninger af ejendomssalg.",
    },
    {
        "title": "⚠️ Asbest og nedstyrtningsfare",
        "prompt": "Jeg vil afdække et mønster af alvorlige arbejdsmiljøsager relateret til asbest og nedstyrtningsfare i nedrivningsbranchen (branchekode 43.11) på Fyn. Overvågningen skal fange de mest alvorlige påbud fra Arbejdstilsynet og efterfølgende følge med i, om sagerne omtales i lokale medier.",
    },
    {
        "title": "🌱 Bæredygtigt byggeri - fakta eller facade",
        "prompt": "Jeg vil skrive en artikelserie om, hvilke byggevirksomheder der er førende inden for bæredygtigt byggeri. Opsæt en overvågning, der fanger omtale af 'bæredygtighed', 'DGNB-certificering' og 'træbyggeri' i fagmedier og på virksomhedernes egne hjemmesider. Krydsreference med virksomhedernes regnskabstal for at se, om der er økonomi i det.",
    },
    {
        "title": "💼 Kapitalfonde i dansk tech",
        "prompt": "Jeg vil identificere og overvåge danske kapitalfondes investeringer i teknologivirksomheder. Opsæt en radar, der fanger kapitalændringer, fusioner og børsmeddelelser relateret til denne niche.",
    },
    {
        "title": "📊 Insiderhandel i C25-selskaber",
        "prompt": "Overvåg handler med aktier foretaget af direktører og bestyrelsesmedlemmer (indberetninger om handler fra insidere) i alle C25-selskaber. Opret en alarm, der giver besked, når flere insidere i samme selskab sælger eller køber aktier inden for en kort periode (f.eks. en uge).",
    },
    {
        "title": "🌍 Greenwashing i energisektoren",
        "prompt": "Store energiselskaber markedsfører sig kraftigt på bæredygtighed. Jeg vil opsætte en overvågning, der sammenholder deres grønne udmeldinger i medierne med faktiske miljøsager eller kritik fra Miljøstyrelsen. Jeg vil fange søgeord som 'grøn omstilling', 'bæredygtig' og 'CO2-neutral' og krydsreferere med selskabernes CVR-numre i Miljøsager-modulet.",
    },
    {
        "title": "💳 Kviklån og gældsinddrivelse",
        "prompt": "Jeg vil undersøge markedsføringen fra kviklånsvirksomheder. Overvåg deres omtale i sociale medier og landsdækkende medier. Samtidig vil jeg overvåge Retslister for at se, om disse firmaer optræder hyppigt i sager om gældsinddrivelse i fogedretten.",
    },
]


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Uventet fejl: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500, content={"error": "Der opstod en intern serverfejl"}
    )


@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    logger.info("Serverer index_new.html til bruger")
    return templates.TemplateResponse(
        "index_new.html", {"request": request, "prompts": inspiration_prompts}
    )


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
            await km24_client.get_modules_basic()
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
            enriched = (
                await enrich_recipe_with_api(raw) if isinstance(raw, dict) else raw
            )

            # Step 6: Final validation and optimization
            yield f"data: {json.dumps({'progress': 90, 'message': 'Optimerer strategien...', 'details': 'Normalisering og validering'})}\n\n"
            completed = (
                await complete_recipe(enriched, goal)
                if isinstance(enriched, dict)
                else {"error": "Ugyldigt AI-svar"}
            )

            # Step 7: Done
            yield f"data: {json.dumps({'progress': 100, 'message': 'Klar til brug!', 'details': 'Opskrift genereret'})}\n\n"
            yield f"data: {json.dumps({'result': completed})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'progress': 100, 'message': 'Fejl', 'details': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
