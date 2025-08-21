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
from typing import Any, List

# KM24 API Integration
from km24_client import get_km24_client, KM24APIResponse
from module_validator import get_module_validator, ModuleMatch

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
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

    # Hent live KM24 data før LLM-kald
    km24_client = get_km24_client()
    module_validator = get_module_validator()
    
    # Byg dynamisk kontekst fra KM24 API
    km24_context = await _build_km24_context(goal, km24_client, module_validator)

    full_system_prompt = f"""
[SYSTEM PROMPT V3.4 - LIVE KM24 INTEGRATION]

{km24_context}

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
- **`"eksakt frase"`**: Anførselstegn for præcis frasesøgning
- **`AND`, `OR`, `NOT`**: Booleske operatorer for komplekse søgninger (brug VERSALER)
- **`-ord`**: Kortform for NOT - ekskluder ord (fx energi -olie -gas)
- **`(gruppe)`**: Parenteser til gruppering af komplekse søgninger
- **`*`**: Wildcard/trunkering for ordstammer (fx klima*)
- **`~frase~`**: Eksakt frasesøgning - fanger kun den præcise frase
- **`~ord`**: Positionel søgning - ordet skal være centralt i teksten
- **`term1;term2`**: Semikolon-separeret - fanger begge termer i ét modul

**KM24 API SØGEFORMAT EKSEMPLER:**
- **Eksakt frase:** `"Copenhagen Infrastructure Partners"`
- **Booleske operatorer:** `(vind OR sol) AND energi`
- **Ekskludering:** `"Energinet" -job -stillingsopslag`
- **Gruppering:** `(udbud OR licitation) AND energi`
- **Wildcard:** `klima*` (fanger klima, klimatilpasning, klimapolitik, etc.)
- **Kompleks søgning:** `(Hellerup OR 2900) AND ejendom*`

**SØGESTRATEGIER:**
- **Start smalt:** Brug præcise termer og anførselstegn
- **Udvid gradvist:** Tilføj OR og wildcards hvis du mangler træf
- **Ekskluder støj:** Brug minus (-) for at fjerne irrelevante resultater
- **Grupper logisk:** Brug parenteser for komplekse kombinationer
- **Hold tidsfiltre i API:** Brug from/to parametre, ikke i søgestrengen

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
"{goal}"

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


async def _build_km24_context(goal: str, km24_client, module_validator) -> str:
    """
    Byg dynamisk kontekst fra KM24 API til system prompt.
    
    Args:
        goal: Det journalistiske mål
        km24_client: KM24 API client
        module_validator: Module validator instance
        
    Returns:
        Formateret kontekst-streng til system prompt
    """
    context_parts = []
    
    try:
        # 1. Hent alle tilgængelige moduler
        modules_result = await km24_client.get_modules_basic()
        if modules_result.success and modules_result.data:
            modules = modules_result.data.get('items', [])
            total_modules = len(modules)
            
            context_parts.append(f"**AKTUELLE KM24 MODULER (Live Data - {total_modules} tilgængelige):**")
            
            # Kategoriser moduler for bedre overblik
            categories = {
                "Virksomhedsdata": [],
                "Offentlige sager": [],
                "Medier": [],
                "Domstole": [],
                "Miljø & Arbejdsmiljø": [],
                "Finans": [],
                "Andre": []
            }
            
            for module in modules:
                title = module.get('title', '').lower()
                if any(word in title for word in ['registrering', 'status', 'cvr']):
                    categories["Virksomhedsdata"].append(module)
                elif any(word in title for word in ['udbud', 'lokalpolitik', 'kommune']):
                    categories["Offentlige sager"].append(module)
                elif any(word in title for word in ['medier', 'nyheder']):
                    categories["Medier"].append(module)
                elif any(word in title for word in ['domstol', 'ret']):
                    categories["Domstole"].append(module)
                elif any(word in title for word in ['miljø', 'arbejd', 'tilsyn']):
                    categories["Miljø & Arbejdsmiljø"].append(module)
                elif any(word in title for word in ['finans', 'økonomi']):
                    categories["Finans"].append(module)
                else:
                    categories["Andre"].append(module)
            
            # Tilføj kategoriserede moduler til kontekst
            for category, category_modules in categories.items():
                if category_modules:
                    context_parts.append(f"\n**{category}:**")
                    for module in category_modules[:5]:  # Max 5 per kategori
                        context_parts.append(f"- **{module.get('title', '')}**: {module.get('description', '')}")
                    if len(category_modules) > 5:
                        context_parts.append(f"- ... og {len(category_modules) - 5} flere")
        
        # 2. Få modul-forslag specifikt for målet
        if goal:
            suggested_modules = await module_validator.get_module_suggestions_for_goal(goal, limit=8)
            if suggested_modules:
                context_parts.append(f"\n\n**HØJEST RELEVANTE MODULER FOR DIT MÅL:**")
                for match in suggested_modules:
                    context_parts.append(f"- **{match.module_title}** (Confidence: {match.confidence:.1%}): {match.match_reason}")
        
        # 3. Hent relevante branchekoder
        branch_codes_result = await km24_client.get_branch_codes()
        if branch_codes_result.success and branch_codes_result.data:
            keywords = module_validator._extract_keywords_from_goal(goal)
            relevant_codes = []
            
            for keyword in keywords[:3]:  # Top 3 keywords
                matching_codes = [
                    code for code in branch_codes_result.data.get('codes', [])
                    if keyword.lower() in code.get('description', '').lower()
                ]
                relevant_codes.extend(matching_codes[:2])  # Top 2 per keyword
            
            if relevant_codes:
                context_parts.append(f"\n\n**RELEVANTE BRANCHEKODER FOR PRÆCIS MÅLRETNING:**")
                for code in relevant_codes[:6]:  # Max 6 koder
                    context_parts.append(f"- **{code.get('code', '')}**: {code.get('description', '')}")
        
        # 4. Tilføj kritiske instruktioner
        context_parts.append("""
        
**KRITISKE INSTRUKTIONER FOR MODULANVENDELSE:**
1. **Du SKAL overveje ALLE ovenstående moduler** når du planlægger din strategi
2. **Ikke kun de åbenlyse moduler** - tænk kreativt om hvordan tilsyneladende urelaterede moduler kan kaste nyt lys over dit mål
3. **Brug branchekoder først** for præcis målretning af virksomheder
4. **Kombiner moduler kreativt** for at afdække skjulte sammenhænge
5. **Overvej krydsreferering** mellem forskellige datakilder for at finde mønstre
""")
        
    except Exception as e:
        logger.error(f"Error building KM24 context: {e}", exc_info=True)
        context_parts.append("\n**ADVARSEL:** Kunne ikke hente live KM24 data - bruger statiske anbefalinger")
    
    return "\n".join(context_parts)


async def complete_recipe(recipe: dict, goal: str = "") -> dict:
    import json as _json
    logger.info("Modtog recipe til komplettering: %s", _json.dumps(recipe, ensure_ascii=False))
    
    # Module validation with KM24 API
    module_validator = get_module_validator()
    km24_client = get_km24_client()
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
                        
                        # Generate optimized search string if not present
                        if not step["details"].get("search_string"):
                            keywords = module_validator._extract_keywords_from_goal(goal)
                            module_type = _get_module_type(module)
                            optimized_search = module_validator.generate_optimized_search_string(keywords, module_type)
                            if optimized_search:
                                step["details"]["search_string"] = optimized_search
                                step["details"]["search_string_optimized"] = True
                        
                        # Add search refinements
                        current_search = step["details"].get("search_string", "")
                        if current_search:
                            refinements = module_validator.suggest_search_refinements(current_search, _get_module_type(module))
                            if refinements:
                                step["details"]["search_refinements"] = refinements
                        
                        # Add live data indicators
                        step["details"]["live_data_available"] = True
                        step["details"]["data_source"] = "KM24 API"
    except Exception as e:
        logger.error(f"Error adding dynamic data: {e}", exc_info=True)
    
    # Efter-berigelse: geo-råd, tinglysning-fritekst, supplement-rens
    try:
        if isinstance(recipe.get("investigation_steps"), list):
            for step in recipe["investigation_steps"]:
                if not isinstance(step, dict): continue
                details = step.setdefault("details", {})
                # Simpelt geo-råd ud fra mål/step-titel
                low = (goal or step.get("title","")).lower()
                if any(k in low for k in ["københavn","frederiksberg","vestjylland","aarhus","odense","aalborg","gentofte","sjælland","fyn","jylland"]):
                    details.setdefault("geo_advice", "Vælg relevante kommuner/kilder for dit område.")
                # Tinglysning: brug filtre, ikke fritekst
                if step.get("module") == "Tinglysning":
                    details["search_string"] = ""
                    details.setdefault("recommended_notification", "løbende")
        if isinstance(recipe.get("supplementary_modules"), list):
            recipe["supplementary_modules"] = [m for m in recipe["supplementary_modules"] if m.get("module") != "Registrering"]
    except Exception as e:
        logger.warning(f"Efter-berigelse fejlede: {e}")
    
    # Tilføj modul-anvendelse statistikker og forbedringsforslag
    try:
        # Hent alle tilgængelige moduler for sammenligning
        modules_result = await km24_client.get_modules_basic()
        if modules_result.success and modules_result.data:
            all_modules = [mod.get('title') for mod in modules_result.data.get('items', [])]
            total_modules = len(all_modules)
            used_modules = list(set(recommended_modules))  # Fjern duplikater
            
            # Beregn dækningsgrad
            coverage_percentage = (len(used_modules) / total_modules * 100) if total_modules > 0 else 0
            
            # Find moduler der IKKE bruges men kunne være relevante
            unused_modules = [mod for mod in all_modules if mod not in used_modules]
            
            # Få forslag til yderligere moduler baseret på målet
            additional_suggestions = []
            if goal:
                additional_matches = await module_validator.get_module_suggestions_for_goal(goal, limit=10)
                additional_suggestions = [
                    {
                        "module": match.module_title,
                        "reason": f"Kunne supplere din strategi: {match.match_reason}",
                        "confidence": match.confidence,
                        "description": match.description
                    }
                    for match in additional_matches
                    if match.module_title not in used_modules
                ][:5]  # Top 5 yderligere forslag
            
            # Tilføj modul-anvendelse feedback
            recipe["km24_module_usage"] = {
                "total_modules_available": total_modules,
                "modules_used_in_plan": len(used_modules),
                "coverage_percentage": f"{coverage_percentage:.1f}%",
                "unused_modules_count": len(unused_modules),
                "assessment": _get_coverage_assessment(coverage_percentage),
                "suggestions": _get_usage_suggestions(coverage_percentage, len(used_modules)),
                "additional_module_suggestions": additional_suggestions
            }
            
            # Tilføj kreative modul-kombinationsforslag
            if additional_suggestions:
                recipe["creative_module_combinations"] = _generate_creative_combinations(
                    used_modules, additional_suggestions, goal
                )
    
    except Exception as e:
        logger.error(f"Error adding module usage statistics: {e}", exc_info=True)
        recipe["km24_module_usage"] = {
            "error": "Kunne ikke beregne modul-anvendelse statistikker",
            "suggestion": "Tjek KM24 API forbindelse"
        }
    
    logger.info("Returnerer kompletteret recipe")
    return recipe


def _get_coverage_assessment(coverage_percentage: float) -> str:
    """Vurder dækningsgraden af moduler i planen."""
    if coverage_percentage >= 25:
        return "Ekscellent - Du bruger mange forskellige moduler til en omfattende strategi"
    elif coverage_percentage >= 15:
        return "God - Du har en solid tilgang med flere relevante moduler"
    elif coverage_percentage >= 8:
        return "Acceptabel - Du dækker de vigtigste moduler, men overvej at udvide"
    else:
        return "Begrænset - Du bruger kun få moduler. Overvej at udvide din strategi"


def _get_usage_suggestions(coverage_percentage: float, modules_used: int) -> List[str]:
    """Generer forslag baseret på modul-anvendelse."""
    suggestions = []
    
    if coverage_percentage < 10:
        suggestions.extend([
            "Overvej at tilføje flere moduler for en mere omfattende strategi",
            "Kombiner virksomhedsdata med medieovervågning for fuld dækning",
            "Tilføj lokalpolitiske eller miljømæssige aspekter til din undersøgelse"
        ])
    elif modules_used < 3:
        suggestions.extend([
            "Din strategi kunne styrkes med flere datakilder",
            "Overvej at krydsreferere data fra forskellige moduler",
            "Tilføj overvågning af relaterede områder for dybere indsigt"
        ])
    else:
        suggestions.extend([
            "God brug af flere moduler - overvej kreative kombinationer",
            "Krydsreferer data mellem dine valgte moduler for mønstre",
            "Din strategi dækker godt - fokuser nu på avancerede filtre"
        ])
    
    return suggestions


def _generate_creative_combinations(used_modules: List[str], additional_suggestions: List[dict], goal: str) -> List[dict]:
    """Generer kreative forslag til modul-kombinationer."""
    combinations = []
    
    # Kombiner brugte moduler med nye forslag
    for used_module in used_modules[:3]:  # Top 3 brugte moduler
        for suggestion in additional_suggestions[:3]:  # Top 3 forslag
            combination_reason = _get_combination_reason(used_module, suggestion["module"], goal)
            if combination_reason:
                combinations.append({
                    "primary_module": used_module,
                    "secondary_module": suggestion["module"],
                    "combination_reason": combination_reason,
                    "potential_insight": f"Kombiner {used_module} med {suggestion['module']} for at {combination_reason.lower()}",
                    "confidence": suggestion.get("confidence", 0.0)
                })
    
    # Sortér efter confidence og returnér top 5
    combinations.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return combinations[:5]


def _get_combination_reason(module1: str, module2: str, goal: str) -> str:
    """Generer en begrundelse for hvorfor to moduler kan kombineres."""
    goal_lower = goal.lower()
    
    # Virksomhedsdata kombinationer
    if any(word in module1.lower() for word in ['registrering', 'status']) and \
       any(word in module2.lower() for word in ['udbud', 'lokalpolitik']):
        return "afdække virksomheder der vinder offentlige kontrakter"
    
    if any(word in module1.lower() for word in ['registrering', 'status']) and \
       any(word in module2.lower() for word in ['miljø', 'arbejd']):
        return "finde virksomheder med miljø- eller arbejdsmiljøproblemer"
    
    # Medieovervågning kombinationer
    if any(word in module1.lower() for word in ['medier', 'nyheder']) and \
       any(word in module2.lower() for word in ['udbud', 'lokalpolitik']):
        return "sammenligne medieomtale med faktiske beslutninger"
    
    # Miljø og ejendom kombinationer
    if any(word in module1.lower() for word in ['miljø', 'forurening']) and \
       any(word in module2.lower() for word in ['tinglysning', 'ejendom']):
        return "afdække miljøproblematiske ejendomshandler"
    
    # Generisk begrundelse
    return f"kombinere {module1} og {module2} for dybere indsigt i {goal[:50]}..."


def _get_module_type(module_title: str) -> str:
    """
    Bestem modul type baseret på titel for søgeoptimering.
    
    Args:
        module_title: Titlen på modulet
        
    Returns:
        Modul type (company, media, politics, property, etc.)
    """
    module_lower = module_title.lower()
    
    if any(word in module_lower for word in ['registrering', 'status', 'cvr']):
        return "company"
    elif any(word in module_lower for word in ['medier', 'nyheder', 'medie']):
        return "media"
    elif any(word in module_lower for word in ['lokalpolitik', 'kommune', 'politik']):
        return "politics"
    elif any(word in module_lower for word in ['tinglysning', 'ejendom', 'ejendomshandel']):
        return "property"
    elif any(word in module_lower for word in ['miljø', 'forurening']):
        return "environment"
    elif any(word in module_lower for word in ['arbejd', 'tilsyn']):
        return "workplace"
    elif any(word in module_lower for word in ['finans', 'økonomi']):
        return "finance"
    elif any(word in module_lower for word in ['domstol', 'ret', 'dom']):
        return "legal"
    else:
        return "general"

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

@app.get("/api/km24-module-overview")
async def get_module_overview():
    """Få overblik over alle tilgængelige KM24 moduler."""
    km24_client = get_km24_client()
    
    try:
        # Hent alle moduler
        modules_result = await km24_client.get_modules_basic()
        
        if modules_result.success:
            modules = modules_result.data.get('items', [])
            
            # Kategoriser moduler
            categories = {
                "virksomhedsdata": {
                    "title": "Virksomhedsdata",
                    "description": "CVR-registreringer, statusændringer og virksomhedsoplysninger",
                    "modules": []
                },
                "offentlige_sager": {
                    "title": "Offentlige sager",
                    "description": "Udbud, lokalpolitik og kommunale beslutninger",
                    "modules": []
                },
                "medier": {
                    "title": "Medier",
                    "description": "Danske og udenlandske medier, nyheder og medieomtale",
                    "modules": []
                },
                "domstole": {
                    "title": "Domstole",
                    "description": "Retssager, domme og juridiske afgørelser",
                    "modules": []
                },
                "miljø_arbejdsmiljø": {
                    "title": "Miljø & Arbejdsmiljø",
                    "description": "Miljøsager, arbejdstilsyn og sikkerhed",
                    "modules": []
                },
                "finans": {
                    "title": "Finans",
                    "description": "Finanstilsynet, økonomiske sager og børsmeddelelser",
                    "modules": []
                },
                "andre": {
                    "title": "Andre",
                    "description": "Diverse andre datakilder og moduler",
                    "modules": []
                }
            }
            
            for module in modules:
                title = module.get('title', '').lower()
                if any(word in title for word in ['registrering', 'status', 'cvr']):
                    categories["virksomhedsdata"]["modules"].append(module)
                elif any(word in title for word in ['udbud', 'lokalpolitik', 'kommune']):
                    categories["offentlige_sager"]["modules"].append(module)
                elif any(word in title for word in ['medier', 'nyheder']):
                    categories["medier"]["modules"].append(module)
                elif any(word in title for word in ['domstol', 'ret']):
                    categories["domstole"]["modules"].append(module)
                elif any(word in title for word in ['miljø', 'arbejd', 'tilsyn']):
                    categories["miljø_arbejdsmiljø"]["modules"].append(module)
                elif any(word in title for word in ['finans', 'økonomi']):
                    categories["finans"]["modules"].append(module)
                else:
                    categories["andre"]["modules"].append(module)
            
            # Beregn statistikker
            total_modules = len(modules)
            category_stats = {}
            for key, category in categories.items():
                category_stats[key] = {
                    "count": len(category["modules"]),
                    "percentage": f"{(len(category['modules']) / total_modules * 100):.1f}%" if total_modules > 0 else "0%"
                }
            
            return JSONResponse(content={
                "success": True,
                "total_modules": total_modules,
                "categories": categories,
                "category_statistics": category_stats,
                "cache_age": str(modules_result.cache_age) if modules_result.cache_age else None,
                "last_updated": datetime.utcnow().isoformat()
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": modules_result.error}
            )
    except Exception as e:
        logger.error(f"Error in module overview: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

@app.get("/api/km24-module-suggestions")
async def get_module_suggestions(goal: str):
    """Få modul-forslag baseret på et journalistisk mål."""
    if not goal or len(goal.strip()) < 10:
        return JSONResponse(
            status_code=400,
            content={"error": "Mål skal være mindst 10 tegn langt"}
        )
    
    module_validator = get_module_validator()
    
    try:
        # Få modul-forslag
        suggested_matches = await module_validator.get_module_suggestions_for_goal(goal, limit=10)
        
        suggestions = [
            {
                "module": match.module_title,
                "slug": match.module_slug,
                "description": match.description,
                "reason": match.match_reason,
                "confidence": match.confidence,
                "search_examples": module_validator.get_search_examples_for_module(match.module_title)
            }
            for match in suggested_matches
        ]
        
        return JSONResponse(content={
            "success": True,
            "goal": goal,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions),
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting module suggestions: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

@app.get("/api/km24-search-test")
async def test_search_functionality(goal: str, module: str = "general"):
    """Test den nye søgefunktionalitet med KM24 API format."""
    if not goal or len(goal.strip()) < 10:
        return JSONResponse(
            status_code=400,
            content={"error": "Mål skal være mindst 10 tegn langt"}
        )
    
    module_validator = get_module_validator()
    
    try:
        # Ekstraher nøgleord
        keywords = module_validator._extract_keywords_from_goal(goal)
        
        # Generer optimeret søgestreng
        optimized_search = module_validator.generate_optimized_search_string(keywords, module)
        
        # Få søgeforbedringer
        refinements = module_validator.suggest_search_refinements(optimized_search, module)
        
        # Få søgeeksempler for modulet
        search_examples = module_validator.get_search_examples_for_module(module)
        
        return JSONResponse(content={
            "success": True,
            "goal": goal,
            "module": module,
            "keywords": keywords,
            "optimized_search": optimized_search,
            "search_refinements": refinements,
            "search_examples": search_examples,
            "search_format_info": {
                "exact_phrases": "Brug anførselstegn for præcise fraser: \"eksakt frase\"",
                "boolean_operators": "Brug AND, OR, NOT i versaler: (term1 OR term2) AND term3",
                "exclusion": "Brug minus for ekskludering: term -støj",
                "wildcards": "Brug * for ordstammer: klima*",
                "grouping": "Brug parenteser for gruppering: (gruppe1 OR gruppe2)"
            },
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error testing search functionality: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

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