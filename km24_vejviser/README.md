# KM24 Vejviser (Version 1.0)

En intelligent assistent, der hjælper journalister med at skabe effektive overvågnings-opskrifter for KM24-platformen.

## Formål

KM24 Vejviser er en datajournalistisk sparringspartner. Værktøjet tager et journalistisk mål formuleret i naturligt sprog (f.eks. "Jeg vil undersøge tvangsauktioner i Frederikshavn") og genererer en konkret, trin-for-trin opskrift til, hvordan man mest effektivt kan dække emnet ved hjælp af de forskellige moduler i KM24.

Værktøjet er designet til at tænke som en erfaren journalist og foreslår proaktivt strategier, hypoteser og det korrekte fagsprog for det relevante domæne.

## Features

- **Intelligent Opskrift-Generering:** Bruger Claude 3.5 Sonnet til at analysere brugerens mål og generere en dybdegående journalistisk strategi.
- **Ekspert-viden:** Indeholder en omfattende videnbase om KM24's moduler, søgesyntaks og avancerede platform-logikker.
- **Kontekstuelt Fagsprog:** Tilpasser automatisk sin terminologi til det relevante fagområde (f.eks. "udlæg" og "tvangsrealisation" i sager om tvangsauktioner).
- **Streaming-interface:** Svaret fra assistenten streames i realtid til brugerfladen for en flydende oplevelse.
- **Simpel Web UI:** En ren og simpel brugerflade bygget med FastAPI og Pico.css.

## Opsætning og Installation

Følg disse trin for at køre projektet lokalt:

**1. Klon Repository'et**
```bash
git clone <repository-url>
cd km24_vejviser
```

**2. Opret og Aktivér et Virtuelt Miljø**
```bash
python3 -m venv venv
source venv/bin/activate
```
*På Windows, brug `venv\Scripts\activate`*

**3. Installér Afhængigheder**
```bash
pip install -r requirements.txt
```

**4. Konfigurér API Nøgle**
Opret en fil ved navn `.env` i `km24_vejviser` mappen. Filen skal indeholde din Anthropic API nøgle:
```
ANTHROPIC_API_KEY="din_api_nøgle_her"
```

**5. Kør Applikationen**
```bash
uvicorn main:app --reload
```
Applikationen vil nu være tilgængelig på `http://127.0.0.1:8000`. 