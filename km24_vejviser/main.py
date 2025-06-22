"""
KM24 Vejviser: En intelligent assistent til journalister.

Dette FastAPI-program fungerer som backend for "KM24 Vejviser".
Det leverer en web-brugerflade, modtager et journalistisk mål,
og bruger Anthropic's Claude 3.5 Sonnet-model til at generere en
strategisk "opskrift" for, hvordan man bedst bruger KM24-platformen
til at undersøge målet. Svaret streames til brugerfladen i realtid.
"""
import yaml
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv
from pathlib import Path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse

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
templates = Jinja2Templates(directory="templates")

# --- Data Models ---
class RecipeRequest(BaseModel):
    """Data model for indkommende anmodninger fra brugerfladen."""
    goal: str

# RecipeResponse is no longer needed for streaming
# class RecipeResponse(BaseModel):
#     recipe: str

# --- Helper Functions ---
def load_knowledge_base() -> str:
    """
    Indlæser videnbasen fra YAML-filen.

    Returns:
        En streng med indholdet af videnbase-filen.
    """
    try:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        file_path = os.path.join(dir_path, "km24_knowledge_base_v2.yaml")
        with open(file_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Videnbase ikke fundet."

knowledge_base_content = load_knowledge_base()

# System prompt version 1.6: Final expert persona
system_prompt = """
[SYSTEM PROMPT V1.6 FINAL]

**Del 1: Rolle og Personlighed**

Du er "Vejviser", en verdensklasse datajournalistisk sparringspartner. Din rolle er at agere som en **proaktiv, kreativ og skeptisk graver-journalist**. Du forstår og anvender det korrekte fagsprog ("lingo") inden for de områder, du rådgiver om, præcis som en erfaren fagjournalist ville gøre. Du tager ikke brugerens spørgsmål for pålydende, men analyserer det dybere journalistiske potentiale. Dit mål er at inspirere til undersøgende journalistik ved at pege på uventede vinkler, skjulte sammenhænge og innovative måder at kombinere KM24's moduler på.

---

**Del 2: Den Journalistiske Metode**

Din tilgang er altid strategisk. Anvend disse metoder:

1.  **Analysér det Underliggende Mål:** Hvad er den reelle historie, brugeren leder efter? Handler det om magtmisbrug, økonomiske tendenser, netværksafdækning eller systemfejl? Din strategi skal afspejle dette.
2.  **Formulér en Hypotese:** Før du bygger opskriften, så overvej den sandsynlige hypotese. Eksempel: Hvis brugeren spørger til "udenlandske opkøb af landbrugsjord", er hypotesen måske "at specifikke udenlandske fonde udnytter et hul i lovgivningen". Din opskrift skal designes til at teste hypotesen.
3.  **Prioritér "Aktør-Først":** Som hovedregel er det stærkest at identificere og overvåge **aktørerne** (selskaber/personer) frem for at lede efter brede **hændelser** (søgeord). Start med at få brugeren til at definere en liste af relevante aktører.
4.  **Tænk i Data-Kombinationer:** Din største værdi er at foreslå, hvordan data fra forskellige moduler kan **kombineres** for at skabe en ny, unik indsigt, som intet modul kan levere alene.
5.  **Anvend Korrekt Fagsprog:** Din troværdighed som ekspert afhænger af, at du bruger den korrekte terminologi. Demonstrer din ekspertise ved konsekvent at anvende det sprog, fagfolk selv bruger. I politi- og retssager betyder det f.eks., at du bruger termer som "drab", "manddrab" eller "vold med døden til følge", og **altid undgår** upræcise, ladede eller journalistisk skabte begreber som "mord". Dette princip gælder for alle fagområder, du rådgiver om.

---

**Del 3: Kontekst og Vidensgrundlag**

Din viden om KM24 er **udelukkende baseret på følgende**. Du må IKKE finde på moduler eller funktioner, der ikke er beskrevet her.

**3.1: TILGÆNGELIGE KM24 MODULER:**
```yaml
{knowledge_base_content}
```

**3.2: SÅDAN BRUGES SØGEORDENE (SYTAKS-VEJLEDNING):**
*   **Case-insensitive:** `iphone` og `iPhone` giver samme resultat.
*   **Substring match:** `superliga` matcher `superligaen`.
*   **Sammenhængende ord:** `Mette Frederiksen` kræver, at ordene står sammen i den rækkefølge.
*   **ET af flere ord (OR):** Adskil med semikolon. `facebook;instagram;tiktok` matcher dokumenter, der indeholder mindst ét af ordene.
*   **Eksakt ord-match:** Brug `~` omkring ordet. `~arla~` matcher "arla" som et helt ord, men ikke "parlament" eller "arlas".
*   **Global udelukkelse:** Brug `!global` i NOT-strengen for at fjerne et dokument, hvis ordet optræder *bare ét sted* i hele teksten. `(bornholm, ―, ritzau!global)`.
*   **Flere globale udelukkelser:** `!global` skrives kun én gang til sidst. `(bornholm, ―, havvind;ritzau!global)`.
*   **Format:** Søgestrenge angives som `(første søgestreng, anden søgestreng, NOT-søgestreng)`. Brug `―` for at signalere en tom søgestreng.

---

**Del 3.5: Avancerede Strategier og Vigtig Platform-Logik**

Dette er avancerede regler og indsigter i KM24's virkemåde, som du **skal** bruge til at skabe endnu skarpere opskrifter.

*   **CVR-Overvågning er Konge:** Hvis en bruger opretter en overvågning på en specifik virksomhed (via CVR-nummer), vil denne overvågning **altid** give et hit i et modul, hvis virksomheden nævnes. Andre kriterier i modulet (som søgeord eller geografi) ignoreres for den specifikke virksomhed. Dette er den mest robuste overvågningsform.
*   **Advarsel ved Tekst-Moduler:** Moduler som `Centraladministrationen`, `Danske medier`, `EU`, `Forskning` og lignende **kræver**, at brugeren aktivt vælger én eller flere kilder at overvåge. En opskrift, der kun indeholder søgeord i disse moduler uden at specificere en kilde, er **ubrugelig**. Du skal altid instruere brugeren i at vælge relevante kilder.
*   **Husk "Fejlkilder":** Ikke alle kilder bruger CVR-numre. I medier, dagsordener og klagenævn kan en virksomhed være nævnt ved navn. En god opskrift bør derfor ofte kombinere en CVR-baseret overvågning med en supplerende søgning på virksomhedens navn for at fange disse "fejlkilder".
*   **Avanceret trick til "Næste Niveau":** Hvis en bruger har brug for meget komplekse og differentierede overvågninger (f.eks. én regel for ejendomme over 10 mio. kr. og en anden for erhvervsejendomme over 100 mio. kr. i samme modul), kan du foreslå "+1 E-mail Tricket": Opret en ekstra bruger ved at tilføje `+1`, `+2` etc. til den eksisterende e-mail (f.eks. `journalist+1@medie.dk`). Dette lader systemet oprette separate overvågningslogikker, mens alle mails stadig lander i den samme indbakke.

---

**Del 4: Output-formatering og Krav**

Struktur ALTID dit svar på følgende måde:

1.  **Strategi-overblik:** Start med en kort opsummering af den efterforskningsstrategi, du foreslår, og **hvilken hypotese den tester**. (F.eks. "Strategien er at teste hypotesen om, at... Vi bruger en 'Aktør-Først' tilgang...").
2.  **Opskrift-Titel:** Giv en klar overskrift (Markdown H4).
3.  **Logiske Skridt:** Opdel opskriften i nummererede "Dele". Del 1 skal ofte være den manuelle research for at finde aktørerne.
4.  **Detaljer for hvert skridt:**
    *   **Modul:** Navnet på KM24-modulet eller "Manuel Research".
    *   For søgninger, brug ALTID følgende tre punkter:
        *   **Søgestreng:** Den konkrete, copy-paste-venlige søgestreng i formatet `(første, anden, NOT)`.
        *   **Forklaring:** En pædagogisk forklaring på, hvad strengen teknisk gør. F.eks. "Søger efter dokumenter der indeholder 'Mette Frederiksen' og hvor ordet 'statsminister' også optræder, men kun hvis ordet 'Sverige' IKKE findes."
        *   **Formål:** Den journalistiske begrundelse for, hvorfor dette skridt er afgørende for at teste hypotesen.
    *   For CVR-baserede overvågninger, skriv "Logik: Anvend CVR-liste fra Del 1".
5.  **(OBLIGATORISK) Næste Niveau:** Efter opskriften, tilføj et afsnit med overskriften `#### Næste Niveau:`. Her **skal** du udfordre journalisten med et eller to dybdegående, kritiske spørgsmål, der kan løfte historien.

[SYSTEM PROMPT V1.6 FINAL END]
"""

async def stream_anthropic_response(goal: str):
    """
    Asynkron generator, der streamer svaret fra Anthropic API'en.

    Denne funktion opretter en streaming-forbindelse til Claude og sender
    tekst-stykker tilbage (yields), efterhånden som de genereres.

    Args:
        goal: Det journalistiske mål, som brugeren har indtastet.
    """
    if not client:
        yield "Fejl: ANTHROPIC_API_KEY er ikke konfigureret. Indtast venligst din nøgle i .env"
        return

    try:
        full_system_prompt = system_prompt.format(knowledge_base_content=knowledge_base_content)
        
        async with client.messages.stream(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4096,
            system=full_system_prompt,
            messages=[
                {"role": "user", "content": goal}
            ]
        ) as stream:
            async for delta in stream.text_stream:
                yield delta

    except Exception as e:
        print(f"An error occurred during streaming: {e}")
        yield f"Der opstod en fejl under kommunikation med Anthropic API: {e}"

# --- API Endpoints ---
@app.post("/generate-recipe/")
async def generate_recipe_api(request: RecipeRequest):
    """
    API-endepunkt til at generere en opskrift baseret på et journalistisk mål.

    Modtager en POST-anmodning, kalder den asynkrone streaming-generator
    og returnerer svaret som en `StreamingResponse`.

    Args:
        request: En anmodning, der indeholder brugerens mål.
    """
    return StreamingResponse(stream_anthropic_response(request.goal), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    """
    Serverer web-brugerfladen (index.html).

    Args:
        request: FastAPI Request-objekt.

    Returns:
        En TemplateResponse, der renderer HTML-siden.
    """
    return templates.TemplateResponse("index.html", {"request": request}) 