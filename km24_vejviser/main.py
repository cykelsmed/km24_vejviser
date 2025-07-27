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
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv
from pathlib import Path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
from km24_vejviser import advisor

# Load environment variables from .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

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

# --- Data Models ---
class RecipeRequest(BaseModel):
    """Data model for indkommende anmodninger fra brugerfladen."""
    goal: str

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
            raw_json = response.content[0].text
            return json.loads(raw_json)

        except anthropic.APIError as e:
            print(f"Anthropic API error on attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Der opstod en fejl efter {retries} forsøg. Fejl: {e}"}
        except json.JSONDecodeError as e:
            print(f"JSON decode error on attempt {attempt + 1}: {e}")
            print(f"Raw response was: {raw_json}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return {"error": f"Kunne ikke parse JSON fra API'en. Svar: {raw_json}"}
    return {"error": "Ukendt fejl."}


def complete_recipe(recipe: dict) -> dict:
    import json as _json
    print("\nDEBUG RAW RECIPE INPUT:", _json.dumps(recipe, indent=2, ensure_ascii=False))
    if "investigation_steps" in recipe and isinstance(recipe["investigation_steps"], list):
        for idx, step in enumerate(recipe["investigation_steps"]):
            module = step.get("module") or (step.get("details", {}).get("module"))
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
                print(f"DEBUG power_tip for step '{step_title}':", tip)
                if tip:
                    step["details"]["power_tip"] = tip
                # Warning (eksplicit felt hvis ønsket)
                warn = advisor.get_warning(module) if module else None
                print(f"DEBUG warning for step '{step_title}':", warn)
                if warn:
                    step["details"]["warning"] = warn
                # Geo advice (altid evaluer og tilføj i trin 1 hvis relevant)
                if idx == 0:
                    geo = advisor.get_geo_advice(step_title)
                    print(f"DEBUG geo_advice for step '{step_title}':", geo)
                    if geo:
                        step["details"]["geo_advice"] = geo
    # Supplementary modules (altid evaluer og tilføj hvis relevant)
    suggestions = advisor.get_supplementary_modules(recipe.get("goal", ""))
    print("DEBUG supplementary_modules:", suggestions)
    if suggestions:
        recipe["supplementary_modules"] = suggestions
    print("\nDEBUG FINAL RECIPE OUTPUT:", _json.dumps(recipe, indent=2, ensure_ascii=False))
    return recipe

# --- API Endpoints ---
@app.post("/generate-recipe/")
async def generate_recipe_api(request: RecipeRequest):
    """
    API-endepunkt der orkestrerer genereringen af en opskrift.

    1. Modtager en POST-anmodning med et journalistisk mål.
    2. Kalder `get_anthropic_response` for at få et JSON-svar fra Claude.
    3. Validerer og kompletterer svaret med `complete_recipe`.
    4. Returnerer det endelige, komplette JSON-objekt til frontend.
    """
    raw_recipe = await get_anthropic_response(request.goal)

    if "error" in raw_recipe:
        return JSONResponse(status_code=500, content=raw_recipe)

    completed_recipe = complete_recipe(raw_recipe)
    return JSONResponse(content=completed_recipe)

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

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    """
    Serverer web-brugerfladen (index.html).

    Args:
        request: FastAPI Request-objekt.

    Returns:
        En TemplateResponse, der renderer HTML-siden.
    """
    return templates.TemplateResponse("index.html", {"request": request, "prompts": inspiration_prompts}) 