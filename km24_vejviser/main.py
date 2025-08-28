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
from .km24_client import get_km24_client, KM24APIResponse, KM24APIClient
from .module_validator import get_module_validator, ModuleMatch

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

    # Hent faktiske moduldata fra KM24 API
    km24_client: KM24APIClient = get_km24_client()
    modules_response = await km24_client.get_modules_basic()

    module_list_text = ""
    if modules_response.success and modules_response.data:
        modules = modules_response.data.get('items', [])
        logger.info(f"Hentet {len(modules)} moduler fra KM24 API")

        # Byg modul liste tekst til system prompt
        module_entries = []
        for module in modules[:20]:  # Begræns til første 20 for at holde prompten håndterbar
            title = module.get('title', 'Ukendt')
            description = module.get('shortDescription', 'Ingen beskrivelse')
            module_entries.append(f"- **{title}**: {description}")

        module_list_text = "\n".join(module_entries)
        logger.info(f"Moduler der sendes til Claude (første 5): {', '.join([m.get('title', '') for m in modules[:5]])}")
    else:
        logger.warning(f"Kunne ikke hente KM24 moduler: {modules_response.error}")
        # Fallback til hårdkodede moduler hvis API fejler
        module_list_text = """
- **Tinglysning**: Ejendomshandler, beløbsfiltrering mulig
- **Status**: Virksomhedsstatusændringer, konkurser, etc.
- **Registrering**: Nye virksomhedsregistreringer - START HER
- **Lokalpolitik**: Kommunale beslutninger, kræver kildevalg
- **Udbud**: Offentlige udbud, kontraktværdi filtrering
- **Miljøsager**: Miljøgodkendelser og -sager
- **Personbogen**: Pant i løsøre, årets høst, relevant for landbrug
- **Danske medier**: Lokale og landsdækkende medier
- **Udenlandske medier**: Internationale medier og EU-kilder
"""

    full_system_prompt = f"""
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
{module_list_text}

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
{goal}

**6. UDFØRELSE**
Generér nu den komplette JSON-plan baseret på `USER_GOAL` og journalistiske principper som CVR først-princippet, branchekode-filtrering, hitlogik og systematisk tilgang.

**VIGTIGT:** Husk at inkludere alle nye felter:
- `creative_approach`: Beskriv den kreative tilgang til målet
- `creative_insights`: Kreative observationer for hvert trin
- `advanced_tactics`: Avancerede taktikker og kreative filtre
- `potential_story_angles`: Dristige hypoteser og worst-case scenarios
- `creative_cross_references`: Kreative krydsrefereringer mellem moduler
"""
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


async def complete_recipe(recipe: dict, goal: str = "") -> dict:
    import json as _json
    logger.info("Modtog recipe til komplettering: %s", _json.dumps(recipe, ensure_ascii=False))

    # Helpers (goal-context analysis and value gates)
    def _norm(text: str) -> str:
        return (text or "").lower()

    goal_lc = _norm(goal)
    time_critical = any(k in goal_lc for k in ["konkurs", "akut", "haster", "kritisk", "varsling"])
    mentions_large_amounts = any(k in goal_lc for k in ["mio", "million", "kr", "beløb", "over ", "større", "stor"]) 
    mentions_politics = any(k in goal_lc for k in ["kommune", "kommunal", "byråd", "lokalpolitik", "politisk", "udvalg"]) 
    mentions_holding_capital = any(k in goal_lc for k in ["holding", "kapital", "capital", "fond", "ejerskab", "ejerkæde"]) 
    mentions_agri_env = any(k in goal_lc for k in ["landbrug", "svin", "kvæg", "gylle", "miljø", "forurening"]) 

    def _goal_keywords(maxn: int = 5) -> list[str]:
        import re
        words = re.findall(r"[a-zA-ZæøåÆØÅ0-9]{3,}", goal_lc)
        stop = {"jeg","vil","om","at","for","der","som","med","og","det","den","de","en","et","i","på","af","til","er","ikke"}
        uniq = []
        for w in words:
            if w not in stop and w not in uniq:
                uniq.append(w)
            if len(uniq) >= maxn:
                break
        return uniq

    def _notification_for(module_name: str) -> str:
        high_volume = module_name in {"Tinglysning", "Tingbogsattester", "Registrering", "Status", "Regnskaber"}
        if time_critical:
            return "løbende"
        return "interval" if high_volume else "interval"

    def _strategic_note_for(module_name: str) -> str | None:
        if module_name == "Lokalpolitik" and mentions_politics:
            return "ADVARSEL: Vælg manuelt de relevante kommuner som kilder for præcis dækning."
        if module_name in {"Tinglysning", "Tingbogsattester"} and mentions_large_amounts:
            return "Brug minimum-beløb filter (fx ≥ 10 mio. kr.) for at fokusere på væsentlige handler."
        if module_name == "Registrering" and mentions_holding_capital:
            return "Brug branchekoder 64.20.10 (Finansielle holdingselskaber) og 01.11.00 hvis relevant."
        if module_name == "Miljøsager" and mentions_agri_env:
            return "Vælg relevante miljøtyper (fx husdyrgodkendelser og landbrugssager)."
        return None

    def _power_tip_for(module_name: str) -> str | None:
        if module_name in {"Tinglysning", "Tingbogsattester"} and any(k in goal_lc for k in ["systematisk", "mønster", "serie", "+1"]):
            return "+1-trick: Opret parallelle overvågninger med forskellige thresholds/geografier for at splitte støj."
        if module_name == "Registrering" and any(k in goal_lc for k in ["udenlandsk", "foreign", "kapital", "fond", "ejerkæde"]):
            return "Kortlæg ejerkæder: Start i holdingselskaber, kryds med direktører/bestyrelse og fortsæt nedad."
        if module_name == "Status" and any(k in goal_lc for k in ["fusion", "spaltning", "merger", "sammenlægning"]):
            return "Timing-analyse: Overvåg koordinerede statusændringer på tværs af relaterede selskaber."
        return None

    def _contextual_search_examples(module_name: str) -> list[str]:
        kws = _goal_keywords(4)
        if not kws:
            return []
        examples: list[str] = []
        if len(kws) >= 2:
            examples.append(f"{kws[0]} AND {kws[1]}")
        examples.append(" OR ".join(kws[:3]))
        if module_name in {"Registrering","Status"} and mentions_holding_capital and kws:
            examples.append(f"{kws[0]} AND (holding OR kapital)")
        return [e for e in examples if len(e) >= 3]

    # Module validation and suggestion setup
    module_validator = get_module_validator()
    recommended_modules: list[str] = []

    if "investigation_steps" in recipe and isinstance(recipe.get("investigation_steps"), list):
        for step in recipe["investigation_steps"]:
            m = step.get("module") or (step.get("details", {}).get("module"))
            if m:
                recommended_modules.append(m)

    # Validate against KM24 API (keep, but only attach warnings when relevant)
    validation_warnings: list[dict] = []
    module_suggestions: list[dict] = []
    try:
        if recommended_modules:
            validation_result = await module_validator.validate_recommended_modules(recommended_modules)
            if validation_result.invalid_modules:
                validation_warnings.append({
                    "type": "invalid_modules",
                    "message": f"Følgende moduler blev ikke fundet i KM24: {', '.join(validation_result.invalid_modules)}",
                    "suggestions": [
                        {
                            "module": match.module_title,
                            "reason": match.match_reason,
                            "confidence": match.confidence
                        } for match in validation_result.suggestions
                    ]
                })
            logger.info(f"Module validation: {len(validation_result.valid_modules)}/{len(recommended_modules)} valid")

        if goal:
            suggested_matches = await module_validator.get_module_suggestions_for_goal(goal, limit=6)
            # Convert and later filter out already-included modules; cap at 3
            module_suggestions_raw = [{
                "module": m.module_title,
                "slug": m.module_slug,
                "reason": m.match_reason,
                "confidence": m.confidence,
                "description": m.description
            } for m in suggested_matches]
        else:
            module_suggestions_raw = []
    except Exception as e:
        logger.error(f"Error during module validation: {e}", exc_info=True)
        validation_warnings.append({
            "type": "validation_error",
            "message": "Kunne ikke validere moduler mod KM24 API"
        })
        module_suggestions_raw = []

    if validation_warnings:
        recipe["validation_warnings"] = validation_warnings

    # Enhanced per-step enrichment (value-driven only)
    try:
        if "investigation_steps" in recipe and isinstance(recipe.get("investigation_steps"), list):
            all_modules = [s.get("module") for s in recipe["investigation_steps"] if s.get("module")]
            cross_module_relationships = await module_validator.get_cross_module_intelligence(all_modules)

            for idx, step in enumerate(recipe["investigation_steps"]):
                if not isinstance(step.get("details"), dict):
                    step["details"] = {}

                module_name = step.get("module") or ""
                details = step["details"]

                # Strategic note (only if goal- and module-specific)
                note = _strategic_note_for(module_name)
                if note:
                    details["strategic_note"] = note

                # Notification intelligence
                details["recommended_notification"] = _notification_for(module_name)

                # Explanation fallback (only if missing/undefined)
                current_expl = details.get("explanation")
                if current_expl is None or str(current_expl).strip() == "" or str(current_expl) == "undefined":
                    rationale = (step.get("rationale") or "overvåge relevante ændringer").strip()
                    details["explanation"] = f"Vi bruger {module_name or 'dette modul'} til at {rationale.lower()}"

                # Enhanced module card + filters
                if module_name:
                    module_card = await module_validator.get_enhanced_module_card(module_name)
                    if module_card:
                        details["module_card"] = {
                            "emoji": module_card.emoji,
                            "color": module_card.color,
                            "short_description": module_card.short_description,
                            "long_description": module_card.long_description,
                            "data_frequency": module_card.data_frequency,
                            "requires_source_selection": module_card.requires_source_selection,
                            "total_filters": module_card.total_filters,
                            "complexity_level": module_card.complexity_level
                        }
                        details["available_filters"] = module_card.available_filters

                    # Filter recommendations (only if actionable)
                    rec = await module_validator.get_filter_recommendations(module_name, goal)
                    actionable_rec = bool(rec.optimal_sequence or rec.complexity_warning or rec.efficiency_tips)
                    if actionable_rec:
                        details["filter_recommendations"] = {
                            "optimal_sequence": rec.optimal_sequence,
                            "efficiency_tips": rec.efficiency_tips,
                            "complexity_warning": rec.complexity_warning
                        }

                    # Complexity analysis (only if actionable and consistent)
                    complexity = await module_validator.analyze_complexity(module_name, {})
                    if complexity and (complexity.optimization_suggestions or complexity.notification_recommendation):
                        details["complexity_analysis"] = {
                            "estimated_hits": complexity.estimated_hits,
                            "filter_efficiency": complexity.filter_efficiency,
                            "notification_recommendation": complexity.notification_recommendation,
                            "optimization_suggestions": [s for s in complexity.optimization_suggestions if s and s.strip()]
                        }

                    # Dynamic search optimization (skip placeholders)
                    if module_card:
                        opt_cfg = await generate_search_optimization(module_card, goal, step)
                        if opt_cfg and (opt_cfg.get("optimal_config") or "standardkonfiguration" not in _norm(opt_cfg.get("rationale", ""))):
                            # Only attach when there is non-empty config or non-generic rationale
                            details["search_optimization"] = opt_cfg

                    # Contextual search examples (goal-driven; remove generic)
                    examples = _contextual_search_examples(module_name)
                    if examples:
                        details["search_examples"] = examples[:3]

                    # Power tip (only when criteria match)
                    tip = _power_tip_for(module_name)
                    if tip:
                        details["power_tip"] = tip

            # Cross-module intelligence (keep if present)
            if cross_module_relationships:
                recipe["cross_module_intelligence"] = cross_module_relationships

        # Supplementary modules: filter out already-included and cap at 3
        if goal:
            included = {s.get("module") for s in recipe.get("investigation_steps", []) if s.get("module")}
            supp = [m for m in module_suggestions_raw if m["module"] not in included]
            recipe["km24_module_suggestions"] = supp[:3]

    except Exception as e:
        logger.error(f"Error adding streamlined API features: {e}", exc_info=True)

    logger.info("Returnerer kompletteret recipe (streamlined)")
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