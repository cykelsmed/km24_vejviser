# KM24 Vejviser (Version 3.0)

En avanceret, pædagogisk assistent, der lærer journalister at mestre KM24-overvågningsplatformen.

## Formål

KM24 Vejviser er en specialiseret datajournalistisk sparringspartner. Værktøjet tager et komplekst journalistisk mål formuleret i naturligt sprog (f.eks. "Jeg vil undersøge store byggeprojekter i Aarhus og konkurser i byggebranchen") og genererer en struktureret, trin-for-trin efterforskningsplan i JSON-format.

Vejviserens primære mål er ikke kun at levere en løsning, men at **undervise brugeren** i at tænke som en ekspert-researcher ved at demonstrere og forklare avancerede teknikker.

## Kernefunktioner

- **Struktureret JSON Output:** Genererer en robust og forudsigelig JSON-plan, der let kan integreres med andre systemer.
- **Pædagogisk Design:** Hvert trin i planen indeholder et `rationale`, en `strategic_note` og en `explanation`, der forklarer de strategiske og tekniske overvejelser.
- **Avanceret Videnbase:** Indeholder en dybdegående YAML-baseret videnbase om:
    - 45 officielle KM24-moduler.
    - Avanceret søgesyntaks (`~frase~`, `~ord`, `;`).
    - Strategiske principper for kilde- og branchefiltrering.
    - "Power-user" teknikker som `Hitlogik` og `+1`-tricket til parallelle overvågninger.
    - Almindelige fejlkilder og løsninger.
- **Robust Arkitektur:** Backend-logik validerer og kompletterer AI-modellens output for at garantere, at alle pædagogiske felter altid er til stede i det endelige svar.
- **Moderne Web UI:** En ren og simpel brugerflade bygget med FastAPI og Pico.css, der inkluderer "kopiér"-knapper og klikbare inspirations-prompts.

## Opsætning og Installation

Følg disse trin for at køre projektet lokalt:

**1. Klon Repository'et**
```bash
git clone <repository-url>
cd <projekt-mappe>
```

**2. Opret og Aktivér et Virtuelt Miljø**
```bash
python3 -m venv venv
source venv/bin/activate
```
*På Windows, brug `venv\Scripts\activate`*

**3. Installér Afhængigheder**
Fra projektets rodmappe, kør:
```bash
pip install -r km24_vejviser/requirements.txt
```

**4. Konfigurér API Nøgle**
Opret en fil ved navn `.env` inde i `km24_vejviser`-mappen. Filen skal indeholde din Anthropic API nøgle:
```
ANTHROPIC_API_KEY="din_api_nøgle_her"
```

**5. Kør Applikationen**
Fra projektets rodmappe, kør:
```bash
uvicorn km24_vejviser.main:app --reload --port 8001
```
Applikationen vil nu være tilgængelig på `http://127.0.0.1:8001`. 