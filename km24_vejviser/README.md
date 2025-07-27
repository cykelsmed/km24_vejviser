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

## JSON Output – Eksempel

Et typisk svar fra Vejviseren indeholder nu følgende felter:

```json
{
  "title": "Solcelleprojekter og lokalpolitik i Danmark",
  "strategy_summary": "Vi kombinerer modulovervågning, avanceret søgesyntaks og geografisk vejledning for at afdække solcelleprojekter og deres politiske kontekst.",
  "investigation_steps": [
    {
      "step": 1,
      "title": "Identificér relevante kommuner med solcelleparker",
      "type": "manual_research",
      "rationale": "Før du opsætter overvågning, bør du identificere kommuner med aktive solcelleprojekter.",
      "details": {
        "geo_advice": "Overvej at bruge eksterne kilder som PlanEnergi, Energistyrelsen eller kommunale energiplaner som udgangspunkt for at finde kommuner med aktive solcelleparker.",
        "power_tip": {
          "title": "Power-tip",
          "explanation": "Brug `term1;term2` for at sikre, at du fanger begge begreber i ét modul – fx både 'solcellepark' og 'solcelleanlæg'."
        }
      }
    },
    {
      "step": 2,
      "title": "Overvågning af solcelleprojekter i udvalgte kommuner",
      "type": "search",
      "module": "Lokalpolitik",
      "rationale": "Opsæt overvågning for dagsordener og referater i relevante kommuner.",
      "details": {
        "strategic_note": "ADVARSEL: Du skal vælge relevante kommuner som kilde for at få resultater.",
        "search_string": "solcellepark;solcelleanlæg",
        "explanation": "Vi bruger semikolon (;) for at fange begge begreber.",
        "recommended_notification": "interval",
        "warning": "Du skal vælge en eller flere relevante kilder (fx kommuner eller retskredse) – ellers får du ingen hits.",
        "power_tip": {
          "title": "Power-tip",
          "explanation": "Brug `term1;term2` for at sikre, at du fanger begge begreber i ét modul – fx både 'solcellepark' og 'solcelleanlæg'."
        }
      }
    }
  ],
  "supplementary_modules": [
    {"module": "EU", "reason": "Hvis nogle solcelleprojekter er støttet via EU’s energifonde."},
    {"module": "Miljø-annonceringer", "reason": "Hvis kommuner annoncerer planer via miljøportaler."}
  ],
  "next_level_questions": [
    "Hvilke kommuner har flest nye solcelleprojekter?",
    "Er der sammenhæng mellem lokalpolitik og tildeling af EU-midler?"
  ]
}
```

**Felter:**
- `geo_advice`: Geografisk vejledning, fx forslag til eksterne datakilder
- `power_tip`: Power-user teknik, fx +1-tricket eller avanceret søgesyntaks (kan nu også afhænge af søgestreng)
- `supplementary_modules`: Liste over moduler, der også kan være relevante, med begrundelse (nu baseret på prompt/plan)

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