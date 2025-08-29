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
import re
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Any

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

    # Hent dynamiske filter-data
    filter_catalog = get_filter_catalog()
    filter_data = await filter_catalog.load_all_filters()
    
    # Hent relevante filtre baseret på mål
    relevant_filters = filter_catalog.get_relevant_filters(goal, [])
    
    # Byg filter-katalog tekst til system prompt
    filter_catalog_text = ""
    if relevant_filters:
        filter_entries = []
        for rec in relevant_filters[:5]:  # Top 5 anbefalinger
            filter_entries.append(f"- **{rec.filter_type}**: {', '.join(rec.values)} (relevans: {rec.relevance_score:.2f})")
        filter_catalog_text = "\n".join(filter_entries)
    else:
        filter_catalog_text = "Ingen specifikke filter-anbefalinger fundet"

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
[SYSTEM PROMPT V3.4 - COMPREHENSIVE KM24 EXPERTISE WITH DYNAMIC FILTERS]

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
    4.  **BRUG DYNAMISKE FILTRE:** Du **SKAL** bruge de dynamisk hentede filtre nedenfor til at give konkrete og relevante filter-anbefalinger i hvert trin.

**3. DYNAMISKE FILTER-DATA (OBLIGATORISK AT BRUGE)**
Baseret på dit mål er følgende filtre identificeret som relevante:

{filter_catalog_text}

**FILTER-KATALOG STATUS:**
- Kommuner indlæst: {filter_data.get('municipalities', 0)}
- Branchekoder indlæst: {filter_data.get('branch_codes', 0)}
- Regioner indlæst: {filter_data.get('regions', 0)}
- Retskredse indlæst: {filter_data.get('court_districts', 0)}

**OBLIGATORISK FILTER-BRUG:**
- **Hvert trin SKAL indeholde konkrete filtre** baseret på de relevante filtre ovenfor
- **Kommuner**: Brug specifikke kommuner fra filter-anbefalingerne (f.eks. "Aarhus", "Vejle", "Horsens")
- **Branchekoder**: Brug relevante branchekoder fra filter-anbefalingerne (f.eks. "41.1", "41.2" for byggeri)
- **Regioner**: Brug regioner når geografisk fokus er bredere (f.eks. "midtjylland", "vestjylland")
- **Beløbsgrænser**: Brug konkrete beløbsgrænser for amount_selection moduler

**EKSEMPEL PÅ KORREKT FILTER-BRUG I JSON:**
```json
{{
  "details": {{
    "geografi": ["Aarhus", "Vejle", "Horsens"],
    "branchekode": ["41.1", "41.2", "43.3"],
    "periode": "24 mdr",
    "beløbsgrænse": "1000000"
  }}
}}
```

**VIGTIGT: Du SKAL bruge de konkrete værdier fra filter-anbefalingerne ovenfor i dine trin!**

**SPECIFIK INSTRUKTION:**
For hvert trin i din JSON-output skal du:
1. **Altid** inkludere `geografi` med kommuner fra filter-anbefalingerne
2. **Altid** inkludere `branchekode` med relevante branchekoder fra filter-anbefalingerne
3. **Altid** inkludere `periode` (f.eks. "24 mdr", "12 mdr")
4. **Altid** inkludere `beløbsgrænse` for amount_selection moduler
5. **Brug de eksakte værdier** fra filter-anbefalingerne ovenfor

**4. JOURNALISTISKE PRINCIPLER OG STRATEGIER**

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

**UFRAVIGELIGE KM24 REGLER - ALT OUTPUT SKAL VÆRE KØREKLART**

**1. STRUKTUR (MUST)**
• Strategi: 2-3 linjer i overview.strategy_summary
• Trin: Nummereret med Modul, Formål, Filtre, Søgestreng, Power-user, Notifikation, Hitlogik
• Pipeline: Find aktører → Bekræft handler → Følg pengene → Sæt i kontekst
• Næste niveau spørgsmål: Altid inkluderet
• Potentielle vinkler: Altid inkluderet  
• Pitfalls: 3-5 bullets med typiske fejl

**2. SØGESYNTAKS (MUST)**
• AND/OR: Altid med STORE bogstaver (AND, OR, NOT)
• Parallelle variationer: Brug semikolon ; (ikke komma)
• Eksempel: landbrug;landbrugsvirksomhed;agriculture
• Eksakt frase: ~kritisk sygdom~
• Positionel søgning: ~parkering
• INGEN uunderstøttede operatorer – kun ovenstående

**3. FILTRE (MUST)**
• Alle trin skal angive Filtre først, før søgestrengen:
• Geografi (kommuner, regioner, områder – fx Vestjylland, Gentofte)
• Branche/instans (branchekoder, instanser, kildelister)
• Beløbsgrænser/perioder (fx >10 mio., "seneste 24 mdr.")

**4. MODULER (MUST match officielle)**
• Brug kun officielle modulnavne:
• 📊 Registrering – nye selskaber fra VIRK
• 📊 Tinglysning – nye ejendomshandler
• 📊 Kapitalændring – selskabsændringer fra VIRK
• 📊 Lokalpolitik – dagsordener/referater
• 📊 Miljøsager – miljøtilladelser
• 📊 EU – indhold fra EU-organer
• 📊 Kommuner – lokalpolitik og planer
• 📊 Danske medier – danske nyhedskilder
• 📊 Webstedsovervågning – konkurrentovervågning
• 📊 Udenlandske medier – internationale kilder
• 📊 Forskning – akademiske kilder
• 📊 Udbud – offentlige udbud
• 📊 Regnskaber – årsrapporter og regnskaber
• 📊 Personbogen – personlige oplysninger
• 📊 Status – virksomhedsstatusændringer og konkurser
• 📊 Arbejdstilsyn – arbejdsmiljøsager og kontrol
• 📊 Børsmeddelelser – børsnoterede selskaber

**5. NOTIFIKATIONSKADENCE (MUST)**
• Kun én kadence pr. trin:
• Løbende → få, men kritiske hits (fx Tinglysning, Kapitalændring)
• Daglig → moderate hits
• Ugentlig/Interval → mange hits/støj (fx Registrering, Lokalpolitik)

**6. WEBKILDE-MODULER (MUST)**
• For moduler som EU, Kommuner, Danske medier, Webstedsovervågning skal du altid angive konkrete kilder i Filtre.
• Hvis dette mangler → opskriften er ugyldig.

**7. CVR-FILTER**
• Når du overvåger en virksomhed via CVR-nummer, overstyrer CVR søgeord. Tilføj altid en ⚠️-advarsel i Pitfalls.

**8. SØGESTRENGE & FILTRE (MUST)**
• Alle trin skal have søgestrenge - brug modulspecifikke standarder
• Filtre kan være tomme men bør indeholde geografi, branche eller beløb
• Generer altid søgestrenge selv hvis LLM ikke giver dem

**9. AFVISNING**
• Hvis en opskrift bryder nogen regler → returnér kun: "UGYLDIG OPSKRIFT – RET FØLGENDE: [liste over fejl]"

**STANDARD SØGESTRENGE FOR MODULER:**
- **Registrering**: `landbrug;landbrugsvirksomhed;agriculture` (parallel-søgning)
- **Tinglysning**: `~landbrugsejendom~` (eksakt frase)
- **Kapitalændring**: `kapitalfond;ejendomsselskab;landbrug` (variationer)
- **Lokalpolitik**: `lokalplan;landzone;kommunal` (variationer)
- **Miljøsager**: `miljøtilladelse;husdyrgodkendelse;udvidelse` (variationer)
- **Regnskaber**: `regnskab;årsrapport;økonomi` (variationer)

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

def _get_default_search_string_for_module(module_name: str) -> str:
    """Get default search string for module."""
    module_name_lower = module_name.lower()
    
    if "registrering" in module_name_lower:
        return "landbrug;landbrugsvirksomhed;agriculture"
    elif "tinglysning" in module_name_lower:
        return "~landbrugsejendom~"
    elif "kapitalændring" in module_name_lower:
        return "kapitalfond;ejendomsselskab;landbrug"
    elif "lokalpolitik" in module_name_lower:
        return "lokalplan;landzone;kommunal"
    elif "miljøsager" in module_name_lower:
        return "miljøtilladelse;husdyrgodkendelse;udvidelse"
    elif "regnskaber" in module_name_lower:
        return "regnskab;årsrapport;økonomi"
    elif "status" in module_name_lower:
        return "konkurs;ophør;statusændring"
    elif "arbejdstilsyn" in module_name_lower:
        return "arbejdsmiljø;kontrol;forseelse"
    elif "børsmeddelelser" in module_name_lower:
        return "børsmeddelelse;årsrapport;økonomi"
    elif "udbud" in module_name_lower:
        return "offentligt udbud;kontrakt;vinder"
    elif "personbogen" in module_name_lower:
        return "person;ejer;bestyrelse"
    else:
        return "søgning"

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

def _standardize_search_string(search_string: str, module_name: str) -> str:
    """
    Standardize search strings according to KM24 syntax standards.
    
    Args:
        search_string: The raw search string from LLM
        module_name: The module name to determine appropriate syntax
    
    Returns:
        Standardized search string following KM24 conventions
    """
    if not search_string:
        return ""
    
    module_lower = module_name.lower()
    search_string = search_string.strip()
    
    # Standard search patterns for different modules
    module_patterns = {
        "registrering": {
            "landbrug": "landbrug;landbrugsvirksomhed;agriculture",
            "ejendom": "ejendomsselskab;ejendomsudvikling;real_estate",
            "bygge": "byggefirma;byggevirksomhed;construction",
            "detail": "detailhandel;retail;butik",
            "restaurant": "restaurant;café;cafe;spisested",
            "transport": "transport;logistik;spedition",
            "finans": "finans;bank;kapitalfond",
            "teknologi": "teknologi;tech;software;it"
        },
        "tinglysning": {
            "landbrug": "~landbrugsejendom~",
            "ejendom": "~ejendomshandel~",
            "bygge": "~byggegrund~",
            "erhverv": "~erhvervsejendom~",
            "bolig": "~boligejendom~"
        },
        "kapitalændring": {
            "landbrug": "kapitalfond;ejendomsselskab;landbrug",
            "ejendom": "ejendomsselskab;kapitalfond;udvikling",
            "bygge": "byggefirma;kapitalfond;udvikling",
            "finans": "kapitalfond;finansselskab;investering"
        },
        "lokalpolitik": {
            "default": "lokalplan;landzone;kommunal;politisk"
        },
        "miljøsager": {
            "default": "miljøtilladelse;husdyrgodkendelse;udvidelse;miljø"
        },
        "regnskaber": {
            "default": "regnskab;årsrapport;økonomi;finansiel"
        }
    }
    
    # Check if we have a pattern for this module
    if module_lower in module_patterns:
        patterns = module_patterns[module_lower]
        
        # For registrering, try to match content
        if module_lower == "registrering":
            for key, pattern in patterns.items():
                if key in search_string.lower():
                    return pattern
        
        # For tinglysning, use default pattern if it exists
        elif module_lower == "tinglysning":
            for key, pattern in patterns.items():
                if key in search_string.lower():
                    return pattern
        
        # For kapitalændring, use default pattern if it exists
        elif module_lower == "kapitalændring":
            for key, pattern in patterns.items():
                if key in search_string.lower():
                    return pattern
            # If no specific match, return default landbrug pattern
            if "landbrug" in search_string.lower():
                return "kapitalfond;ejendomsselskab;landbrug"
        
        # For other modules, use default pattern
        elif "default" in patterns:
            return patterns["default"]
    
    # If no specific pattern found, apply general KM24 syntax improvements
    return _apply_km24_syntax_improvements(search_string)

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
    
    # Hvis filtre mangler, tilføj dynamiske filtre baseret på mål
    if not step["filters"] and goal:
        logger.info("Adding dynamic filters based on goal")
        filter_catalog = get_filter_catalog()
        relevant_filters = filter_catalog.get_relevant_filters(goal, [])
        logger.info(f"Found {len(relevant_filters)} relevant filters")
        
        # Tilføj relevante filtre til step
        for rec in relevant_filters:
            if rec.filter_type == "municipality":
                step["filters"]["geografi"] = rec.values
                logger.info(f"Added geography filter: {rec.values}")
            elif rec.filter_type == "industry":
                step["filters"]["branchekode"] = rec.values
                logger.info(f"Added industry filter: {rec.values}")
            elif rec.filter_type == "region":
                step["filters"]["region"] = rec.values
                logger.info(f"Added region filter: {rec.values}")
        
        # Tilføj standard periode og beløbsgrænse hvis de mangler
        if "periode" not in step["filters"]:
            step["filters"]["periode"] = "24 mdr"
            logger.info("Added default period: 24 mdr")
        if "beløbsgrænse" not in step["filters"]:
            step["filters"]["beløbsgrænse"] = "1000000"
            logger.info("Added default amount limit: 1000000")
    else:
        logger.info("Filters already present or no goal provided")
    
    logger.info(f"Final filters: {step['filters']}")
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
                "filters": step.get("details", {}).get("filters", {}),
                "notification": _normalize_notification(step.get("details", {}).get("recommended_notification", "daily")),
                "delivery": "email",
                "source_selection": step.get("details", {}).get("source_selection", []),
                "strategic_note": step.get("details", {}).get("strategic_note"),
                "explanation": step.get("details", {}).get("explanation", ""),
                "creative_insights": step.get("details", {}).get("creative_insights"),
                "advanced_tactics": step.get("details", {}).get("advanced_tactics")
            }
            
            # Ensure filters are properly structured before search string
            normalized_step = _ensure_filters_before_search_string(normalized_step, goal)
            
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
    
    # Step defaults
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
        
        # Generate default search string if empty
        if not step.get("search_string"):
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
            except Exception as e:
                logger.warning(f"Kunne ikke validere modul {module_name}: {e}")
    
    # Step 3: Apply sensible defaults (after module validation)
    logger.info("Trin 3: Anvender defaults")
    apply_min_defaults(recipe)
    
    # Step 4: Parse to UseCaseResponse and return dict
    logger.info("Trin 4: Parser til UseCaseResponse")
    
    # Debug: Log step details before validation
    for i, step in enumerate(recipe.get("steps", [])):
        module = step.get("module", {})
        logger.info(f"Step {i+1}: module={module.get('name', 'Unknown')}, is_web_source={module.get('is_web_source', False)}, source_selection={step.get('source_selection', [])}")
    
    try:
        # Validate against KM24 rules first
        is_valid, km24_errors = validate_km24_recipe(recipe)
        if not is_valid:
            error_message = format_validation_error(km24_errors)
            logger.error(f"KM24 validation failed: {error_message}")
            raise ValueError(error_message)
        
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
    
    # Check for invalid operators (only standalone words with word boundaries)
    invalid_operators = ["and", "or", "not", "og", "eller", "ikke"]
    for operator in invalid_operators:
        # Use word boundaries to match only standalone operators
        pattern = r'\b' + re.escape(operator) + r'\b'
        if re.search(pattern, search_string.lower()):
            errors.append(f"Trin {step_number}: Ugyldig operator '{operator}'. Brug AND/OR/NOT med store bogstaver")
    
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
        raw_recipe = await get_anthropic_response(goal)

        if "error" in raw_recipe:
            logger.warning(f"Fejl fra get_anthropic_response: {raw_recipe['error']}")
            return JSONResponse(status_code=500, content=raw_recipe)

        completed_recipe = await complete_recipe(raw_recipe, goal)
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
        
        filter_catalog = get_filter_catalog()
        await filter_catalog.load_all_filters()
        recommendations = filter_catalog.get_relevant_filters(goal, modules)
        
        # Konverter til JSON-serializable format
        rec_data = []
        for rec in recommendations:
            rec_data.append({
                "filter_type": rec.filter_type,
                "values": rec.values,
                "relevance_score": rec.relevance_score,
                "reasoning": rec.reasoning,
                "module_id": rec.module_id,
                "module_part_id": rec.module_part_id
            })
        
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
        "title": "🎯 Offshore ejendomsspekulation",
        "prompt": "Undersøg om danske ejendomsselskaber systematisk flytter ejendomme til offshore-selskaber i skattely, og om dette sker samtidig med store ejendomshandler eller kommunale planer."
    },
    {
        "title": "🏭 Miljøkriminalitet & konkurser",
        "prompt": "Afdæk mønstre hvor virksomheder der er involveret i miljøkriminalitet eller miljøsager, pludselig går konkurs eller opretter nye selskaber for at undgå ansvar og bøder."
    },
    {
        "title": "💰 Udbud & interessekonflikter",
        "prompt": "Undersøg om kommunale embedsmænd eller politikere der arbejder med udbud, har personlige økonomiske interesser i virksomheder der vinder disse udbud, eller om deres familie/venner ejer sådanne virksomheder."
    },
    {
        "title": "🌾 Landbrug & kapitalfonde",
        "prompt": "Afdæk om internationale kapitalfonde systematisk opkøber danske landbrugsejendomme gennem komplekse selskabsstrukturer, og om dette sker i områder med kommende infrastrukturprojekter eller byudvikling."
    },
    {
        "title": "🏢 Ejendomsspekulation & politik",
        "prompt": "Undersøg om lokale politikere eller deres familie systematisk køber ejendomme i områder hvor kommunen senere planlægger store udviklingsprojekter, infrastruktur eller ændringer i lokalplaner."
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