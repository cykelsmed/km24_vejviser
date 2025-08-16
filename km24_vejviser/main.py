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
import yaml
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
import advisor
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
    version="1.0.0",
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
def load_knowledge_base() -> str:
    """
    Indlæser videnbasen fra den rensede YAML-fil.

    Returns:
        En streng med indholdet af videnbase-filen.
    """
    try:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        file_path = os.path.join(dir_path, "km24_knowledge_base_clean.yaml")
        with open(file_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Videnbase ikke fundet."

knowledge_base_content = load_knowledge_base()

# System prompt version 2.8: The final attempt with an explicit IF-THEN rule for the +1 trick.
system_prompt = """
[SYSTEM PROMPT V2.8 - FINAL ULTIMATUM]

**1. ROLLE OG MÅL**
Du er "Vejviser", en verdensklasse datajournalistisk sparringspartner og KM24-ekspert.
Din opgave er at omdanne et komplekst journalistisk mål til en **pædagogisk og struktureret efterforskningsplan i JSON-format**, der lærer brugeren at mestre KM24-platformens avancerede funktioner.

**2. KERNEREGLER (AFGØRENDE)**
- **TOP-REGLER:**
    1.  **HVIS-SÅ-REGEL FOR '+1'-TRICKET:** Dette er din mest specifikke regel. **HVIS** en brugerforespørgsel kræver to eller flere separate overvågninger, der bruger **forskellige typer af for-filtrering** (f.eks. én overvågning filtreret på geografi og en anden filtreret på branchekode), **SÅ SKAL** du dedikere et specifikt trin i din plan til at forklare og anbefale **"+1"-tricket** som den optimale løsning for at holde disse overvågninger adskilt og rene.
    2.  **KRÆV NOTIFIKATIONS-ANBEFALING:** Din næstvigtigste regel. For **hvert** overvågningstrin (`search` eller `cvr_monitoring`) **SKAL** du inkludere feltet `recommended_notification` (`løbende` eller `interval`) og kort begrunde dit valg.
    3.  **ADVAR OM KILDEVALG:** Hvis et modul har `requires_source_selection: true`, **SKAL** du tilføje en `strategic_note`, der advarer brugeren om, at de manuelt skal vælge kilder for at få resultater.
- **AVANCEREDE TEKNIKKER:**
    - **HITLOGIK:** Ved komplekse søgninger med flere kriterier, forklar brugeren om muligheden for at bruge `Hitlogik` (OG/ELLER) til at definere betingelserne for et hit.
- **GRUNDLÆGGENDE REGLER:**
    - **STRENGT VIDENSGRUNDLAG:** Baser alt på `KNOWLEDGE_BASE`. Ingen hallucination.
    - **ALTID JSON:** Returner kun et validt, komplet JSON-objekt.
    - **ANVEND AVANCERET SØGESYNTAKS:** Brug `~frase~`, `~ord`, og `;` korrekt og forklar hvorfor.
    - **GEOGRAFISK PRÆCISION:** Omsæt regioner til specifikke kommuner.
    - **MODULNAVNE:** Brug altid de eksakte modulnavne.

**3. OUTPUT-STRUKTUR (JSON-SKEMA)**
Du **SKAL** returnere dit svar i følgende JSON-struktur. Husk de **obligatoriske** advarsler og anbefalinger.

```json
{{
  "title": "Kort og fængende titel for efterforskningen",
  "strategy_summary": "En kort opsummering af den overordnede strategi, der fremhæver brugen af præcis kilde-målretning og søgesyntaks.",
  "investigation_steps": [
    {{
      "step": 1,
      "title": "Power-User Teknik: Opdel Overvågning med '+1'-Tricket",
      "type": "manual_research",
      "rationale": "Dit mål kræver to separate overvågninger med forskellige filtre (én geografisk, én på branchekode). For at undgå at disse filtre konflikter, er den bedste løsning at oprette en separat brugerprofil til hver overvågning.",
      "output": "Opret to nye bruger-profiler: 'dit.navn+byggeri@firma.dk' til byggetilladelser og 'dit.navn+konkurs@firma.dk' til konkurser. Alle notifikationer vil stadig lande i din normale indbakke. Brug de følgende trin for hver profil."
    }},
    {{
      "step": 2,
      "title": "Overvågning af Byggetilladelser i Aarhus (>10 mio.)",
      "type": "search",
      "module": "Lokalpolitik",
      "rationale": "På din '+byggeri'-profil: Opsæt en overvågning for store byggetilladelser. Da det er et web-modul, skal kilden vælges manuelt.",
      "details": {{
        "strategic_note": "ADVARSEL: På din '+byggeri' profil skal du manuelt udvælge 'Aarhus Kommune' som kilde i modulet for at få resultater.",
        "search_string": "byggetilladelse AND (>10.000.000 OR >10mio)",
        "explanation": "Vi kombinerer søgeordet med en søgning på beløb. Brug Hitlogik (OG) for at sikre, at begge betingelser er opfyldt.",
        "recommended_notification": "interval"
      }}
    }},
     {{
      "step": 3,
      "title": "Overvågning af Konkurser i Byggebranchen",
      "type": "search",
      "module": "Status",
      "rationale": "På din '+konkurs'-profil: Opsæt en landsdækkende overvågning af konkurser i byggebranchen ved at for-filtrere på branchekoder.",
      "details": {{
        "strategic_note": "På din '+konkurs' profil skal du bruge KM24's filter til at vælge de relevante branchekoder for byggeri før du søger.",
        "search_string": "~konkurs",
        "explanation": "Positionel søgning (`~ord`) sikrer, at kun sager, hvor 'konkurs' er hovedemnet, fanges.",
        "recommended_notification": "løbende"
      }}
    }}
  ],
  "next_level_questions": [
    "Hvilke firmaer går igen i både store byggeprojekter og efterfølgende konkurser?",
    "Er der specifikke under-brancher i byggeriet, der er overrepræsenteret i konkurser?"
  ]
}}
```

**4. KONTEKST**

**KNOWLEDGE_BASE (YAML):**
```yaml
{knowledge_base_content}
```

**USER_GOAL:**
"{user_goal}"

**5. UDFØRELSE**
Generér nu den komplette JSON-plan baseret på `USER_GOAL` og `KNOWLEDGE_BASE`.
"""

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

    full_system_prompt = system_prompt.format(
        knowledge_base_content=knowledge_base_content,
        user_goal=goal
    )
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
                # Strategic note
                if "strategic_note" not in step["details"]:
                    warning = advisor.get_warning(module) if module else None
                    step["details"]["strategic_note"] = warning or "Ingen specifik strategisk note til dette trin."
                
                # Recommended notification
                if "recommended_notification" not in step["details"]:
                    notif = advisor.determine_notification_type(module) if module else "interval"
                    step["details"]["recommended_notification"] = notif
                
                # Power tip (altid evaluer og tilføj hvis relevant)
                tip = advisor.get_power_tip(module, search_string)
                logger.debug(f"Power_tip for step '{step_title}': {tip}")
                if tip:
                    step["details"]["power_tip"] = tip
                
                # Warning (eksplicit felt hvis ønsket)
                warn = advisor.get_warning(module) if module else None
                logger.debug(f"Warning for step '{step_title}': {warn}")
                if warn:
                    step["details"]["warning"] = warn
                
                # Geo advice (altid evaluer og tilføj i trin 1 hvis relevant)
                if idx == 0:
                    geo = advisor.get_geo_advice(step_title)
                    logger.debug(f"Geo_advice for step '{step_title}': {geo}")
                    if geo:
                        step["details"]["geo_advice"] = geo
    
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
    
    # Supplementary modules (altid evaluer og tilføj hvis relevant)
    suggestions = advisor.get_supplementary_modules(recipe.get("goal", goal))
    logger.debug(f"Supplementary_modules: {suggestions}")
    recipe["supplementary_modules"] = suggestions
    
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