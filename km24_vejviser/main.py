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
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
import logging
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Any

# KM24 API Integration
from km24_client import get_km24_client, KM24APIResponse
from module_validator import get_module_validator, ModuleMatch

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

    full_system_prompt = """
[SYSTEM PROMPT V3.3 - COMPREHENSIVE KM24 EXPERTISE]

**1. ROLLE OG MÅL**
Du er "Vejviser", en verdensklasse datajournalistisk sparringspartner og KM24-ekspert.
Din opgave er at omdanne et komplekst journalistisk mål til en **pædagogisk og struktureret efterforskningsplan i JSON-format**, der lærer brugeren at mestre KM24-platformens avancerede funktioner.

**KREATIV OG NYSGERRIK TILGANG:**
Du skal tænke som en **erfaren og nysgerrig datajournalist, der leder efter skjulte sammenhænge, potentielle misbrug eller nye dagsordener**. Din rolle er ikke kun at give struktureret vejledning, men også at:
- **Identificere uventede vinkler** og potentielle historier der kan afdækkes
- **Foreslå kreative kombinationer** af moduler og filtre
- **Stille provokerende spørgsmål** der udfordrer brugerens oprindelige mål
- **Afdække systemiske mønstre** og strukturelle problemer
- **Inspirere til dybere undersøgelser** med "ud af boksen"-tilgang

**2. KERNEREGLER (AFGØRENDE)**
- **TOP-REGLER:**
    1.  **HVIS-SÅ-REGEL FOR '+1'-TRICKET:** Dette er din mest specifikke regel. **HVIS** en brugerforespørgsel kræver to eller flere separate overvågninger, der bruger **forskellige typer af for-filtrering** (f.eks. én overvågning filtreret på geografi og en anden filtreret på branchekode), **SÅ SKAL** du dedikere et specifikt trin i din plan til at forklare og anbefale **"+1"-tricket** som den optimale løsning for at holde disse overvågninger adskilt og rene.
    2.  **KRÆV NOTIFIKATIONS-ANBEFALING:** Din næstvigtigste regel. For **hvert** overvågningstrin (`search` eller `cvr_monitoring`) **SKAL** du inkludere feltet `recommended_notification` (`løbende` eller `interval`) og kort begrunde dit valg.
    3.  **ADVAR OM KILDEVALG:** Hvis et modul har `requires_source_selection: true`, **SKAL** du tilføje en `strategic_note`, der advarer brugeren om, at de manuelt skal vælge kilder for at få resultater.

**3. JOURNALISTISKE PRINCIPLER OG STRATEGIER**

**CVR FØRST-PRINCIP:**
- **Start altid med CVR-data**: Brug Registrering og Status moduler først for at identificere virksomheder
- **Branchekoder før søgeord**: Filtrer først på relevante branchekoder, derefter søgeord
- **Systematisk tilgang**: Identificer virksomheder → Overvåg deres aktiviteter → Krydsreference med andre kilder

**HITLOGIK OG AVANCEREDE FILTRERINGER:**
- **Hitlogik**: Forklar "både og / enten eller" logik for hver overvågning
- **Afgræns eller drukne**: Altid vælg kommuner/kilder for at undgå for mange hits
- **Virksomhed først**: Virksomhedsovervågning overrider alle andre filtre
- **Webkilder kræver kildevalg**: Centraladministrationen, Danske medier, EU, Forskning, Klima, Kommuner, Sundhed, Udenlandske medier, Webstedsovervågning

**+1-TRICKET (DETALJERET):**
- **Hvornår bruges**: Når du ikke kan lave forskellige regler i samme modul
- **Hvordan**: Opret bruger med +1 efter brugernavn (f.eks. line.jensen+1@firma.dk)
- **Praktiske eksempler**: Tinglysning: Landejendomme >10 mio. OG erhvervsejendomme >100 mio.

**MODULSPECIFIKKE STRATEGIER:**
- **Fødevaresmiley og Sø- og Handelsretten**: Sæt notifikationer til "Aldrig" for at fravælge
- **99/100 kommuner**: Christiansø og "andet" kategorier inkluderet
- **Fejlkilder**: CVR-nummer vs. tekstbaseret identificering - advær om stavemåder

**NOTIFIKATIONSSTRATEGIER:**
- **Løbende**: For tidskritiske overvågninger (få hits)
- **Interval**: For mindre presserende overvågninger (mange hits)
- **Aldrig**: For at fravælge specifikke moduler

**AVANCERET SØGESYNTAKS:**
- **`~frase~`**: Eksakt frasesøgning - fanger kun den præcise frase
- **`~ord`**: Positionel søgning - ordet skal være centralt i teksten
- **`term1;term2`**: Semikolon-separeret - fanger begge termer i ét modul
- **`AND`, `OR`, `NOT`**: Booleske operatorer for komplekse søgninger
- **`"eksakt frase"`**: Anførselstegn for præcis frasesøgning

**MODUL UNDERKATEGORIER:**
- **`company`**: Filtrer efter specifikke virksomheder (multi-select)
- **`industry`**: Filtrer efter virksomhedsbranche (multi-select) - **BRUG DETTE FØRST**
- **`municipality`**: Geografisk filtrering efter kommune (multi-select)
- **`search_string`**: Tekstbaseret søgning (multi-select) - **BRUG DETTE SIDST**
- **`hit_logic`**: Kontrol over notifikationer
- **`amount_selection`**: Beløbsfiltrering (kontraktværdi, ejendomshandel, etc.)
- **`generic_value`**: Modulspecifikke kategorier (multi-select)

**VIGTIGE MODULER OG DERES FUNKTIONER:**
- **Tinglysning**: Ejendomshandler, beløbsfiltrering mulig
- **Status**: Virksomhedsstatusændringer, konkurser, etc.
- **Registrering**: Nye virksomhedsregistreringer - **START HER**
- **Lokalpolitik**: Kommunale beslutninger, kræver kildevalg
- **Udbud**: Offentlige udbud, kontraktværdi filtrering
- **Miljøsager**: Miljøgodkendelser og -sager
- **Personbogen**: Pant i løsøre, årets høst, relevant for landbrug
- **Danske medier**: Lokale og landsdækkende medier
- **Udenlandske medier**: Internationale medier og EU-kilder

**STRATEGISKE PRINCIPLER:**
- **Geografisk præcision**: Omsæt regioner til specifikke kommuner
- **Branchefiltrering**: Brug branchekoder for præcis målretning - **KRITISK**
- **Beløbsgrænser**: Sæt relevante beløbsgrænser for at fokusere på større sager
- **Kildevalg**: Advær om nødvendighed af manuelt kildevalg
- **Hitlogik**: Forklar brugen af OG/ELLER for komplekse søgninger
- **Systematisk tilgang**: CVR → Aktivitet → Kontekst
- **Fejlhåndtering**: Advær om stavemåder og fejlkilder

**7. KREATIV MODULANVENDELSE:**
Du skal **overveje, hvordan tilsyneladende urelaterede moduler kan kaste nyt lys over et emne** og om der kan **krydsrefereres data fra meget forskellige kilder for at afdække mønstre, der ellers ville være skjulte**. Eksempler:
- **Kombiner Miljøsager med Tinglysning** for at afdække miljøkriminelle ejendomshandler
- **Krydsreference Arbejdstilsyn med Registrering** for at finde virksomheder der opretter nye selskaber efter kritik
- **Sammenlign Udbud med Status** for at identificere virksomheder der vinder kontrakter men går konkurs
- **Kombiner Personbogen med Lokalpolitik** for at afdække politiske interesser i ejendomshandler
- **Krydsreference Børsmeddelelser med Finanstilsynet** for at finde mønstre i finansielle sager

**4. OUTPUT-STRUKTUR (JSON-SKEMA)**
Du **SKAL** returnere dit svar i følgende JSON-struktur. Husk de **obligatoriske** advarsler og anbefalinger.

```json
{{
  "title": "Kort og fængende titel for efterforskningen",
  "strategy_summary": "En kort opsummering af den overordnede strategi, der fremhæver brugen af CVR først-princippet, branchekode-filtrering og systematisk tilgang.",
  "creative_approach": "Beskrivelse af den kreative og 'ud af boksen'-tilgang til målet",
  "investigation_steps": [
    {{
      "step": 1,
      "title": "CVR Først: Identificér Relevante Virksomheder",
      "type": "search",
      "module": "Registrering",
      "rationale": "Start med at identificere alle relevante virksomheder ved hjælp af branchekode-filtrering. Dette giver os et solidt grundlag for videre overvågning.",
      "details": {{
        "strategic_note": "Brug branchekode 47.11.10 (Slik og konfekture) som primært filter. Dette sikrer, at vi fanger alle relevante virksomheder uanset deres navn.",
        "search_string": "slik OR candy OR konfekture OR chokolade",
        "explanation": "Vi kombinerer branchekode-filtrering med søgeord som finjustering. Branchekoden fanger alle relevante virksomheder, mens søgeordet hjælper med at identificere specifikke typer.",
        "recommended_notification": "løbende",
        "hitlogik_note": "Brug 'OG' logik mellem branchekode og geografisk filter for præcision.",
        "creative_insights": "Kreative observationer og uventede vinkler for dette trin",
        "advanced_tactics": "Avancerede taktikker og kreative måder at kombinere filtre på"
      }}
    }},
    {{
      "step": 2,
      "title": "Overvåg Virksomhedsstatusændringer",
      "type": "search",
      "module": "Status",
      "rationale": "Hold øje med statusændringer for de identificerede virksomheder. Dette afdækker lukninger, flytninger og andre vigtige ændringer.",
      "details": {{
        "strategic_note": "Brug CVR-numre fra trin 1 som virksomhedsfilter. Dette sikrer præcis overvågning af de relevante virksomheder.",
        "search_string": "",
        "explanation": "Vi bruger kun virksomhedsfilter baseret på CVR-numre. Ingen søgeord nødvendige, da vi allerede har identificeret de relevante virksomheder.",
        "recommended_notification": "løbende"
      }}
    }},
    {{
      "step": 3,
      "title": "Krydsreference med Lokalpolitik",
      "type": "search",
      "module": "Lokalpolitik",
      "rationale": "Søg efter lokalpolitiske beslutninger, der kan påvirke detailhandel og erhvervsliv i området.",
      "details": {{
        "strategic_note": "ADVARSEL: Du skal manuelt vælge relevante kommuner som kilder. Brug branchekode-filtrering for at fokusere på detailhandel.",
        "search_string": "detailhandel AND (tilladelse OR regulering OR udvikling)",
        "explanation": "Vi kombinerer branchekode-filtrering med søgeord for at fange politiske beslutninger, der specifikt påvirker detailhandel.",
        "recommended_notification": "interval",
        "hitlogik_note": "Brug 'OG' logik mellem søgeord og geografisk filter for præcision."
      }}
    }}
  ],
  "next_level_questions": [
    "Hvordan kan vi identificere mønstre i åbning og lukning af virksomheder i specifikke brancher?",
    "Er der tegn på, at større kæder eller udenlandske aktører er ved at overtage markedet?",
    "Hvordan påvirker ændringer i lokalpolitik eller regulering virksomhedernes forretningsmodel?"
  ],
  "potential_story_angles": [
    "Konkrete, dristige hypoteser og narrative rammer der kan testes med data",
    "Worst-case scenarios og systemiske fejl der kan afdækkes",
    "Uventede sammenhænge og mønstre der kan udforskes"
  ],
  "creative_cross_references": [
    "Forslag til krydsreferering af data fra forskellige moduler",
    "Kreative kombinationer af filtre og søgekriterier",
    "Uventede vinkler og historier der kan afdækkes"
  ]
}}
```

**5. KONTEKST**

**USER_GOAL:**
"{user_goal}"

**6. UDFØRELSE**
Generér nu den komplette JSON-plan baseret på `USER_GOAL` og journalistiske principper som CVR først-princippet, branchekode-filtrering, hitlogik og systematisk tilgang.

**VIGTIGT:** Husk at inkludere alle nye felter:
- `creative_approach`: Beskriv den kreative tilgang til målet
- `creative_insights`: Kreative observationer for hvert trin
- `advanced_tactics`: Avancerede taktikker og kreative filtre
- `potential_story_angles`: Dristige hypoteser og worst-case scenarios
- `creative_cross_references`: Kreative krydsrefereringer mellem moduler
""".format(user_goal=goal)
    retries = 3
    delay = 2

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model="claude-3-5-sonnet-20240620",
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


async def complete_recipe(recipe: dict, goal: str = "") -> dict:
    import json as _json
    logger.info("Modtog recipe til komplettering: %s", _json.dumps(recipe, ensure_ascii=False))
    
    # Module validation with KM24 API
    module_validator = get_module_validator()
    recommended_modules = []
    
    if "investigation_steps" in recipe and isinstance(recipe["investigation_steps"], list):
        for idx, step in enumerate(recipe["investigation_steps"]):
            module = step.get("module") or (step.get("details", {}).get("module"))
            if module:
                recommended_modules.append(module)
            
            step_title = step.get("title", "")
            search_string = step.get("details", {}).get("search_string") if step.get("details") else None
            
            if "details" in step and isinstance(step["details"], dict):
                # Strategic note - only add if not already present
                if "strategic_note" not in step["details"]:
                    step["details"]["strategic_note"] = "Ingen specifik strategisk note til dette trin."
                
                # Recommended notification - only add if not already present
                if "recommended_notification" not in step["details"]:
                    step["details"]["recommended_notification"] = "interval"
    
    # Validate recommended modules against KM24 API
    validation_warnings = []
    module_suggestions = []
    
    try:
        if recommended_modules:
            validation_result = await module_validator.validate_recommended_modules(recommended_modules)
            
            # Add warnings for invalid modules
            if validation_result.invalid_modules:
                validation_warnings.append({
                    "type": "invalid_modules",
                    "message": f"Følgende moduler blev ikke fundet i KM24: {', '.join(validation_result.invalid_modules)}",
                    "suggestions": [
                        {
                            "module": match.module_title,
                            "reason": match.match_reason,
                            "confidence": match.confidence
                        }
                        for match in validation_result.suggestions
                    ]
                })
            
            # Log validation results
            logger.info(f"Module validation: {len(validation_result.valid_modules)}/{len(recommended_modules)} valid")
        
        # Get intelligent module suggestions for the goal
        if goal:
            suggested_matches = await module_validator.get_module_suggestions_for_goal(goal, limit=3)
            module_suggestions = [
                {
                    "module": match.module_title,
                    "slug": match.module_slug,
                    "reason": match.match_reason,
                    "confidence": match.confidence,
                    "description": match.description
                }
                for match in suggested_matches
            ]
    
    except Exception as e:
        logger.error(f"Error during module validation: {e}", exc_info=True)
        validation_warnings.append({
            "type": "validation_error",
            "message": "Kunne ikke validere moduler mod KM24 API - fortsætter med statiske anbefalinger"
        })
    
    # Add validation results to recipe
    if validation_warnings:
        recipe["validation_warnings"] = validation_warnings
    
    if module_suggestions:
        recipe["km24_module_suggestions"] = module_suggestions
    
    # Get supplementary modules from KM24 API
    try:
        if goal:
            supplementary_matches = await module_validator.get_module_suggestions_for_goal(goal, limit=5)
            recipe["supplementary_modules"] = [
                {
                    "module": match.module_title,
                    "reason": match.match_reason
                }
                for match in supplementary_matches[3:]  # Skip first 3 (already in main suggestions)
            ]
    except Exception as e:
        logger.error(f"Error getting supplementary modules: {e}", exc_info=True)
        recipe["supplementary_modules"] = []
    
    # Add dynamic search examples and live data
    try:
        if "investigation_steps" in recipe and isinstance(recipe["investigation_steps"], list):
            for step in recipe["investigation_steps"]:
                if "details" in step and isinstance(step["details"], dict):
                    module = step.get("module")
                    if module:
                        # Add search examples for the module
                        search_examples = module_validator.get_search_examples_for_module(module)
                        if search_examples:
                            step["details"]["search_examples"] = search_examples
                        
                        # Add live data indicators
                        step["details"]["live_data_available"] = True
                        step["details"]["data_source"] = "KM24 API"
    except Exception as e:
        logger.error(f"Error adding dynamic data: {e}", exc_info=True)
    
    logger.info("Returnerer kompletteret recipe")
    return recipe

# --- API Endpoints ---
@app.post(
    "/generate-recipe/",
    response_model=Any,
    responses={
        200: {"description": "Struktureret JSON-plan for journalistisk mål."},
        422: {"description": "Ugyldig input."},
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
    raw_recipe = await get_anthropic_response(goal)

    if "error" in raw_recipe:
        logger.warning(f"Fejl fra get_anthropic_response: {raw_recipe['error']}")
        return JSONResponse(status_code=500, content=raw_recipe)

    completed_recipe = await complete_recipe(raw_recipe, goal)
    logger.info("Returnerer completed_recipe til frontend")
    return JSONResponse(content=completed_recipe)

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

# --- Inspiration Prompts ---
inspiration_prompts = [
    {
        "title": "Systematisk opkøb",
        "prompt": "Jeg vil undersøge, om en specifik udenlandsk kapitalfond systematisk opkøber og sammenlægger landbrugsejendomme i Vestjylland for at omgå reglerne."
    },
    {
        "title": "Inhabilitet i kommunen",
        "prompt": "Undersøg om byrådsmedlemmer i [indsæt by] kommune har personlige økonomiske interesser i sager, de stemmer om, specifikt inden for byudvikling og salg af kommunale grunde."
    },
    {
        "title": "Social dumping",
        "prompt": "Afdæk om der er et mønster, hvor specifikke transportfirmaer, der vinder offentlige udbud, systematisk er involveret i sager om social dumping eller konkurser."
    },
    {
        "title": "Forurening",
        "prompt": "Er der en sammenhæng mellem klager over lugtgener fra en bestemt fabrik og fabrikkens ansøgninger om nye miljøgodkendelser eller ændringer i produktionen?"
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
    logger.info("Serverer index.html til bruger")
    return templates.TemplateResponse("index.html", {"request": request, "prompts": inspiration_prompts}) 