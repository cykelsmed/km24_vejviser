"""
Educational content library for KM24 Vejviser.

Provides static educational content (syntax guides, common pitfalls, troubleshooting),
KM24 principles (CVR-first, hitlogik, notification strategy), and module-specific
quality checklists.

This content is hardcoded to ensure consistency and correctness, while allowing
the LLM to focus on case-specific strategy and pedagogy.
"""

from typing import Dict, List, Optional


# ============================================================================
# STATIC SECTIONS - Universal educational content
# ============================================================================

STATIC_SECTIONS: Dict[str, str] = {
    "syntax_guide": """
**Søgestreng Syntaks (for moduler med "Søgeord" filter):**

- **Boolean operatorer**: AND, OR, NOT (ALTID store bogstaver - aldrig lowercase!)
  - ✅ Korrekt: `vindmølle AND lokalplan`
  - ❌ Forkert: `vindmølle and lokalplan`

- **Parallelle variationer**: Semikolon (;) - ikke komma
  - ✅ Korrekt: `vindmølle;vindenergi;windmill`
  - ❌ Forkert: `vindmølle,vindenergi,windmill`

- **Kombineret**: `vindmølle;vindenergi AND lokalplan OR godkendelse`

- **Eksakt frase**: Tildes (~) omkring frasen
  - Eksempel: `~kritisk sygdom~`

- **Positionel søgning**: Prefix tilde (~) for ordstamme
  - Eksempel: `~parkering` matcher parking, parkerede, parkeringspladser

**Eksempler:**
- Mediemonitorering: `fødevareskandale;fødevaresikkerhed AND salmonella OR listeria`
- Lokalplaner: `vindmølle;vindenergi AND ~VVM-redegørelse~ OR miljøgodkendelse`
- Politiske sager: `interessekonflikt;habilitet AND borgmester;rådmand`
""",

    "common_pitfalls": """
**Typiske fejl ved opsætning af KM24-overvågning:**

1. **Søgeord i Registrering**: ❌ Brug ALDRIG søgeord til at identificere virksomheder. Brug branchekoder.
   - Forkert: Registrering med Søgeord: "byggeri"
   - Korrekt: Registrering med Branche: ["41.20", "43.11"]

2. **Lowercase boolean operatorer**: ❌ `vindmølle and lokalplan` virker IKKE
   - Korrekt: `vindmølle AND lokalplan` (store bogstaver)

3. **Komma i stedet for semikolon**: ❌ `vindmølle,vindenergi` virker IKKE
   - Korrekt: `vindmølle;vindenergi` (semikolon for parallelle variationer)

4. **Glemmer CVR-først princippet**: ❌ Starter med Arbejdstilsyn i stedet for Registrering
   - Korrekt: Step 1 = Registrering (find aktører), Step 2 = Arbejdstilsyn (overvåg kritik)

5. **"løbende" for højvolumen-moduler**: ❌ Registrering med løbende notifikation giver spam
   - Korrekt: Registrering med "interval" (dagligt/ugentligt sammendrag)

6. **Tomme filter-arrays**: ❌ `"Kommune": []` giver ingen filtrering
   - Korrekt: `"Kommune": ["Aarhus", "København"]` eller fjern filteret helt

7. **Engelske filter-navne**: ❌ `"municipality"`, `"industry"` eksisterer ikke
   - Korrekt: Brug danske navne fra modulets available_filters: "Kommune", "Branche"

8. **For brede søgeord**: ❌ `"virksomhed"` giver tusinder af irrelevante hits
   - Korrekt: Kombiner med specifikke termer: `konkurs;betalingsstandsning AND revisor;regnskab`
""",

    "troubleshooting": """
**Fejlfinding når overvågningen ikke virker som forventet:**

**Problem: For mange hits (inbox overload)**
- Løsning 1: Skift fra "løbende" til "interval" notifikation
- Løsning 2: Tilføj flere filtre (Kommune, Branche) for at indskrænke
- Løsning 3: Gør søgestrenge mere specifikke med AND-operatorer
- Løsning 4: Brug eksakt frase (~term~) i stedet for bred søgning

**Problem: For få hits (ingen resultater)**
- Løsning 1: Tjek om filtre er for restriktive (fjern nogle for at udvide)
- Løsning 2: Tilføj synonymer med semikolon: `vindmølle;vindenergi;windmill`
- Løsning 3: Brug OR i stedet for AND for bredere søgning
- Løsning 4: Tjek om branchekoder er korrekte (se Danmarks Statistiks branchekode-database)

**Problem: Irrelevante hits**
- Løsning 1: Tilføj NOT-operatorer: `byggeri NOT renovation NOT have`
- Løsning 2: Brug eksakt frase (~term~) i stedet for enkeltord
- Løsning 3: Kombiner flere filtre (Kommune + Branche + Søgeord)
- Løsning 4: Overvej om CVR-filter fra Registrering ville være bedre end søgeord

**Problem: Vigtige sager går igennem fingrene**
- Løsning 1: Tilføj parallelle søgetermer (synonmyer med semikolon)
- Løsning 2: Opret flere steps med forskellige filtervinkler
- Løsning 3: Brug bredere geografiske filtre (region i stedet for enkelt kommune)
- Løsning 4: Kombiner automatisk overvågning med periodiske manuelle søgninger
"""
}


# ============================================================================
# KM24 PRINCIPLES - Core journalistic strategies
# ============================================================================

KM24_PRINCIPLES: Dict[str, Dict[str, str]] = {
    "cvr_first": {
        "title": "CVR-først princippet",
        "description": """
Start ALTID med at identificere virksomheder via Registrering-modulet (branchekoder),
før du overvåger dem i andre moduler (Arbejdstilsyn, Status, Tinglysning).

**Pipeline:**
1. Find aktører (Registrering + branchekoder) → Få CVR-numre
2. Overvåg aktiviteter (fagmoduler + CVR-filter fra step 1)
3. Krydsreference (kombiner data fra forskellige moduler)

**Hvorfor det virker:**
- Registrering giver den komplette population af relevante virksomheder
- CVR-filter i andre moduler sikrer præcis matching uden falske positiver
- Undgår at "lede i blinde" med søgeord der kan matche irrelevante tekster

**Eksempel:**
- ❌ Forkert: Arbejdstilsyn med Søgeord: "byggeri" (matcher tekster, ikke virksomheder)
- ✅ Korrekt: Step 1 = Registrering (Branche: 41.20), Step 2 = Arbejdstilsyn (Virksomhed: CVR fra step 1)
""",
        "when_to_apply": "Når målet involverer virksomheder (byggeri, fødevarer, transport, etc.)"
    },

    "hitlogik": {
        "title": "Hitlogik - Kombiner filtre intelligent",
        "description": """
Hitlogik-filteret styrer hvordan KM24 kombinerer dine filtre:

**AND (Standard)**: Alle filtre skal matche
- Eksempel: Kommune=Aarhus AND Branche=41.20 → Kun byggevirksomheder i Aarhus
- Brug når: Du vil indskrænke til præcis målgruppe

**OR**: Mindst ét filter skal matche
- Eksempel: Kommune=Aarhus OR Kommune=Odense → Begge kommuner
- Brug når: Du vil udvide geografisk/tematisk

**Avanceret kombination**: (A AND B) OR (C AND D)
- Eksempel: (Kommune=Aarhus AND Branche=41.20) OR (Kommune=Odense AND Branche=43.11)
- Brug når: Du overvåger forskellige typer aktører i forskellige områder

**Best practice:**
- Start med AND for præcision, skift til OR hvis for få hits
- Kombiner altid geografiske og tematiske filtre for fokuseret overvågning
- Brug separate steps hvis logikken bliver for kompleks
""",
        "when_to_apply": "Når du kombinerer flere filtre og skal styre matchningslogik"
    },

    "notification_strategy": {
        "title": "Notifikationsstrategi - Løbende vs. Interval",
        "description": """
Vælg notifikationsfrekvens baseret på hitvolumen og tidskritikalitet:

**Løbende (Real-time):**
- Få, kritiske hits (5-20 pr. måned)
- Tidskritiske sager hvor hurtig handling er vigtig
- Eksempler: Tinglysning >50 mio., Arbejdstilsyn Forbud/Strakspåbud, Status Konkurs
- Fordel: Øjeblikkelig besked når noget vigtigt sker
- Ulempe: Kan blive spam hvis for mange hits

**Interval (Dagligt/Ugentligt sammendrag):**
- Mange hits (20+ pr. måned)
- Mindre tidskritiske sager hvor overblik er vigtigere end hastighed
- Eksempler: Registrering (nye virksomheder), Lokalpolitik (dagsordener), Danske medier
- Fordel: Struktureret overblik, undgår inbox overload
- Ulempe: Mindre akut respons

**Hybrid-strategi (Anbefalet):**
- Step 1: Registrering (interval) → Find aktører ugentligt
- Step 2: Arbejdstilsyn Forbud (løbende) → Kritiske sager med det samme
- Step 3: Lokalpolitik (interval) → Dagligt sammendrag af politiske beslutninger

**Tommelfingerregel:**
- <10 hits/måned → Løbende
- 10-50 hits/måned → Interval (dagligt)
- >50 hits/måned → Interval (ugentligt) eller stram filtrene
""",
        "when_to_apply": "Ved ALLE steps - kritisk for brugervenlighed"
    }
}


# ============================================================================
# QUALITY CHECKLISTS - Module-specific validation
# ============================================================================

QUALITY_CHECKLISTS: Dict[str, List[str]] = {
    "Registrering": [
        "✓ Branchekoder er specificeret (ikke søgeord til at finde virksomheder)",
        "✓ Kommune-filter er sat hvis geografisk fokus",
        "✓ Notifikation er sat til 'interval' (Registrering giver mange hits)",
        "✓ CVR-numre fra dette step kan genbruges i andre moduler",
        "✓ Branchekoder matcher faktisk målgruppen (tjek Danmarks Statistiks database)"
    ],

    "Status": [
        "✓ Statustype er specificeret (Konkurs, Likvidation, Opløst, etc.)",
        "✓ Virksomhed-filter er sat (fra Registrering-step) eller Branche er specificeret",
        "✓ Notifikation er 'løbende' hvis konkurs/likvidation (tidskritisk)",
        "✓ Notifikation er 'interval' hvis mindre kritiske statusændringer",
        "✓ Overvej om Person-filter skal tilføjes (track personer på tværs af virksomheder)"
    ],

    "Arbejdstilsyn": [
        "✓ Problem-filter er sat (Asbest, Stilladser, Psykisk arbejdsmiljø, etc.)",
        "✓ Reaktion-filter er sat hvis kun kritiske sager (Forbud, Strakspåbud)",
        "✓ Kommune eller Branche er specificeret (undgå for brede søgninger)",
        "✓ Notifikation er 'løbende' hvis Forbud/Strakspåbud (meget alvorligt)",
        "✓ Virksomhed-filter fra Registrering er sat hvis CVR-først strategi"
    ],

    "Lokalpolitik": [
        "✓ Kommune/Region er specificeret (konkrete navne, ikke generiske begreber)",
        "✓ Søgeord er sat hvis tematisk fokus (brug semikolon for synonymer)",
        "✓ Udvalg-filter overvejes hvis kun visse politikområder er relevante",
        "✓ Dokumenttype er overvejet (Dagsorden vs. Referat)",
        "✓ Notifikation er 'interval' (Lokalpolitik giver mange hits)"
    ],

    "Tinglysning": [
        "✓ Beløbsgrænse er sat (Ejendomshandel eller Samlehandel filter)",
        "✓ Ejendomstype er overvejet (Ejerlejlighed, Enfamiliehus, Erhvervsejendom, etc.)",
        "✓ Kommune eller BFE-nummer er sat hvis geografisk fokus",
        "✓ Person eller Virksomhed filter er sat hvis specifik overvågning",
        "✓ Notifikation er 'løbende' hvis høj beløbsgrænse (>50 mio., meget relevant)",
        "✓ Notifikation er 'interval' hvis lavere beløbsgrænse (mange hits)"
    ],

    "Personbogen": [
        "✓ Person-filter er sat hvis track specifik person",
        "✓ Virksomhed-filter er sat hvis track virksomhedens ejere",
        "✓ Kommune-filter overvejes hvis geografisk fokus",
        "✓ Søgeord er sat hvis tematisk (fx 'virksomhedspant', 'løsørepant')",
        "✓ Notifikation typisk 'løbende' (pant indikerer økonomiske problemer)"
    ],

    "Domme": [
        "✓ Gerningskode er overvejet hvis specifik kriminalitet",
        "✓ Ret-filter er sat hvis kun visse domstole (Højesteret, Landsret, etc.)",
        "✓ Virksomhed eller Person filter er sat hvis specifik overvågning",
        "✓ Søgeord er sat hvis tematisk (kombiner med Gerningskode)",
        "✓ Notifikation typisk 'interval' (domme er ikke akut tidskritiske)"
    ],

    "Retslister": [
        "✓ Gerningskode er sat hvis specifik kriminalitet",
        "✓ Ret-filter er sat hvis kun visse geografiske områder",
        "✓ Søgeord kombinerer gerningstype med kontekst",
        "✓ Person eller Virksomhed filter overvejes",
        "✓ Notifikation typisk 'interval' (retslister kommer løbende)"
    ],

    "Danske medier": [
        "✓ Medie-filter er sat (konkrete medienavne fra dropdown)",
        "✓ Søgeord bruger semikolon for synonymer og AND for kombination",
        "✓ Boolean operatorer er i STORE bogstaver (AND, OR, NOT)",
        "✓ Virksomhed-filter overvejes hvis track specifik virksomhed",
        "✓ Notifikation er 'interval' (medier producerer meget indhold)"
    ],

    "Børsmeddelelser": [
        "✓ Marked-filter er sat (Nasdaq Copenhagen, First North, etc.)",
        "✓ Virksomhed-filter er sat hvis specifik virksomhed",
        "✓ Søgeord er sat hvis tematisk (fx 'kapitaludvidelse', 'direktion')",
        "✓ Notifikation typisk 'løbende' (børsmeddelelser er tidskritiske)",
        "✓ Branche-filter overvejes hvis track hele sektor"
    ]
}


# ============================================================================
# DYNAMIC GUIDES - Module-specific pedagogical content
# ============================================================================

DYNAMIC_GUIDES: Dict[str, str] = {
    "Registrering": """**Sådan bruger du Registrering effektivt:**

🎯 **Brug altid branchekoder** for at finde virksomheder - ALDRIG søgeord.

**Byggeri-branchekoder:**
- 41.20: Opførelse af bygninger
- 43.11: Nedrivning
- 43.12: Klargøring af byggegrunde
- 43.99: Anden specialiseret bygge- og anlægsvirksomhed

**Landbrug-branchekoder:**
- 01.11: Dyrkning af korn (undtagen ris), bælgfrugter og olieholdige frø
- 01.21: Dyrkning af druer
- 01.41: Mælkeproduktion

**Pro tip:** Eksportér CVR-numre fra dette step og brug dem som filter i andre moduler (Arbejdstilsyn, Status, Tinglysning) for præcis tracking.""",

    "Status": """**Forstå status-typerne:**

📊 **Under konkurs:** Konkursbegæring er indgivet, kurator er udpeget. Processen er startet.

📊 **Tvangsopløst:** Ofte pga. manglende regnskab eller manglende revisor. Indikerer dårlig administration.

📊 **Opløst efter konkurs:** Konkursbehandlingen er afsluttet. Virksomheden eksisterer ikke længere.

📊 **Under konkurs efter rekonstruktion:** Rekonstruktionsforsøg mislykkedes, nu konkurs.

**Pro tip:** Sammenlign konkurs-datoer med Arbejdstilsyn-kritik. Konkurs kort efter alvorlig kritik kan indikere årsagssammenhæng.""",

    "Arbejdstilsyn": """**Reaktionstyper - hvor alvorligt er det?**

🚨 **Forbud (mest alvorligt):** Arbejde skal standses øjeblikkeligt. Overtrædelsen er så alvorlig at den udgør umiddelbar fare.

🚨 **Strakspåbud:** Skal efterkommes straks - typisk inden for få dage. Alvorlig overtrædelse.

⚠️  **Påbud:** Skal efterkommes inden for fastsat frist (typisk uger/måneder). Mindre akut.

📝 **Rådgivningspåbud:** Virksomheden skal købe ekstern rådgivning til at løse problemet.

**Pro tip:** Filtrer på Forbud + Strakspåbud for de mest alvorlige sager. Track om virksomheder får gentagne påbud - indikerer systematiske problemer.""",

    "Tinglysning": """**Forstå beløbsgrænser:**

🏠 **Under 10 mio.:** Standard boliger, mindre erhvervsejendomme
🏢 **10-50 mio.:** Større erhvervsejendomme, ejendomskomplekser
🏗️  **Over 50 mio.:** Meget store handler - ofte interessante for historier

**Interessante købere:**
- Udenlandske selskaber (Malta, Luxembourg, Panama) → hvem står bag?
- Politikere eller embedsmænd → interessekonflikter?
- Selskaber med uklare ejerstrukturer → hvidvask?

**Pro tip:** Sammenlign Tinglysning med Lokalpolitik - blev lokalplan ændret kort før salg? Blev værdien kunstigt øget?""",

    "Personbogen": """**Brug Personbogen til at finde skjulte forbindelser:**

🔍 **Virksomhedspant:** Pant i virksomhedens aktiver. Indikerer økonomiske problemer eller stor gæld.

🔍 **Løsørepant:** Pant i maskiner, varelager, etc. Ofte sidste udvej før konkurs.

🔍 **Ejerskifte:** Hvem er de nye ejere? Tidligere konkurser? Relationer til andre overvågede virksomheder?

**Pro tip:** Når du får et hit, undersøg om personerne også optræder i dine andre overvågninger (Registrering, Status, Lokalpolitik). Find mønstre på tværs.""",

    "Lokalpolitik": """**Politiske dokumenter - hvad skal du kigge efter:**

📋 **Lokalplaner:** Ændringer i byggeret, zonestatus - hvem profiterer?

⚖️  **Habilitetserklæringer:** Politiker erklærer interessekonflikt - grænseoverskridende eller korrekt håndteret?

🚨 **Hastemøder:** Ekstraordinære beslutninger uden normal høring - hvorfor hastværket?

💰 **Store kontrakter:** Offentlige udbud over visse beløb - hvem vinder? Sammenhæng til donationer?

**Pro tip:** Deltag i møderne! Politikere er mere tilbageholdende med tvivlsomme beslutninger når pressen er til stede.""",

    "Domme": """**Forstå domstolshierarkiet:**

⚖️  **Byret:** Førsteinstans - kan ankes til landsret
⚖️  **Landsret:** Ankeinstans - kan ankes til Højesteret (kræver tilladelse)
⚖️  **Højesteret:** Sidste instans - skaber præcedens

**Interessante domme:**
- Frifindelser i miljøsager (virksomhed vs. myndighed)
- Økonomisk kriminalitet (bedrageri, momssvig, skattefusk)
- Arbejdsmiljø-ulykker med strafansvar

**Pro tip:** Kombiner med Retslister - følg sagen fra anmeldelse til dom.""",

    "Retslister": """**Retslister viser hvem der er sigtet:**

⚠️  **Vigtigt:** Sigtet = IKKE dømt. Uskyldspræsumtion gælder.

🔍 **Gerningskoder:**
- 100-199: Forbrydelser mod person (vold, drab)
- 200-299: Sædelighedsforbrydelser
- 280-289: Miljøkriminalitet
- 290-299: Økonomisk kriminalitet

**Pro tip:** Brug Retslister til at finde sager tidligt, følg op med Domme-modulet når dommen falder. Interview forsvar + anklager for baggrundshistorien.""",

    "Danske medier": """**Medieovervågning - udnyt konkurrentanalyse:**

📰 **Lokale medier** giver ofte tidligere signaler end landsdækkende - de er tættere på.

📡 **Fagmedier** (Byggebladet, Ingeniøren, etc.) rapporterer tekniske detaljer som landsdækkende springer over.

**Søgestreng best practices:**
- Brug semikolon for synonymer: `vindmølle;vindenergi;windmill`
- Kombiner tema + geografi: `asbest;asbestsag AND aarhus;østjylland`
- Filtrér støj: `byggeri NOT boligannoncer NOT stillingsannoncer`

**Pro tip:** Når konkurrent har en historie, lav en bedre follow-up med dine data fra KM24-moduler.""",

    "Kommuner": """**Kommunale hjemmesider - hvad ligger her:**

📢 **Pressemeddelelser:** Officiel kommunikation - hvad vil de fremhæve?
📋 **Politiske referater:** Faktiske beslutninger (se også Lokalpolitik-modul)
📊 **Rapporter:** Tunge dokumenter med detaljer der ikke kommer i pressemeddelelser

**Pro tip:** Sammenlign kommunens pressemeddelelser med faktiske data fra andre moduler - er der ting de ikke nævner?""",

    "Miljøsager": """**Miljøtilladelser og håndhævelser:**

✅ **Tilladelser:** Nye miljøgodkendelser - hvad får virksomheden lov til?
⚠️  **Tilsyn:** Myndigheden tjekker om virksomheden overholder reglerne
🚨 **Påbud/Forbud:** Virksomheden overtræder regler - skal rette op

**Interessante sager:**
- Afslag på miljøtilladelse (hvorfor? lokal modstand?)
- Gentagne påbud til samme virksomhed (systematiske problemer)
- Store udledningsændringer (øget forurening?)

**Pro tip:** Søg aktindsigt i fulde tilsynsrapporter - der står meget mere end i det offentliggjorte sammendrag.""",

    "Regnskaber": """**Årsrapporter - gravsignaler:**

📊 **Revisorpåtegning:** "Forbehold" eller "supplerende oplysninger" = problemer
💰 **Negativ egenkapital:** Virksomheden skylder mere end den ejer
📉 **Stor gæld til SKAT:** Indikerer betalingsproblemer
⚠️  **Uden revisor:** Små virksomheder behøver ikke revisor, men det kan skjule problemer

**Pro tip:** Sammenlign regnskaber over flere år - pludselig forværring kan forudsige konkurs.""",

    "Kapitalændring": """**Kapitalændringer - hvad sker der:**

📈 **Kapitalforhøjelse:** Nye penge ind - expansion eller redningsaktion?
📉 **Kapitalnedsættelse:** Betaling til ejere eller signaler om problemer?
🔄 **Fusion/spaltning:** Virksomhedsstruktur ændres - hvorfor? skatteoptimering?

**Pro tip:** Store kapitalændringer lige efter kritik (Arbejdstilsyn) eller før salg (Tinglysning) kan være interessante."""
}


# ============================================================================
# ContentLibrary - Main interface for accessing educational content
# ============================================================================

class ContentLibrary:
    """
    Static library for accessing educational content.

    Provides methods for retrieving KM24 principles, quality checklists,
    common pitfalls, syntax guides, and filter explanations.
    """

    @staticmethod
    def get_principle(principle_key: str) -> Optional[Dict[str, str]]:
        """
        Get a specific KM24 principle.

        Args:
            principle_key: Key for principle (cvr_first, hitlogik, notification_strategy)

        Returns:
            Dictionary with title, description, when_to_apply, or None if not found
        """
        return KM24_PRINCIPLES.get(principle_key)

    @staticmethod
    def get_all_principles() -> Dict[str, Dict[str, str]]:
        """Get all KM24 principles."""
        return KM24_PRINCIPLES

    @staticmethod
    def get_quality_checklist(module_name: str) -> List[str]:
        """
        Get pre-activation quality checklist for a module.

        Args:
            module_name: Name of KM24 module (e.g., "Registrering", "Status")

        Returns:
            List of checklist items, or empty list if module not found
        """
        return QUALITY_CHECKLISTS.get(module_name, [])

    @staticmethod
    def get_all_checklists() -> Dict[str, List[str]]:
        """Get all quality checklists."""
        return QUALITY_CHECKLISTS

    @staticmethod
    def get_pitfalls_for_module(module_name: str) -> str:
        """
        Get common pitfalls relevant to a specific module.

        Args:
            module_name: Name of KM24 module

        Returns:
            Relevant section from common_pitfalls, or full text if no specific match
        """
        # For now, return full pitfalls guide
        # Could be enhanced to filter based on module type
        return STATIC_SECTIONS["common_pitfalls"]

    @staticmethod
    def get_syntax_guide() -> str:
        """Get the search string syntax guide."""
        return STATIC_SECTIONS["syntax_guide"]

    @staticmethod
    def get_troubleshooting() -> str:
        """Get the troubleshooting guide."""
        return STATIC_SECTIONS["troubleshooting"]

    @staticmethod
    def get_static_section(section_key: str) -> Optional[str]:
        """
        Get a specific static section.

        Args:
            section_key: Key for section (syntax_guide, common_pitfalls, troubleshooting)

        Returns:
            Section content or None if not found
        """
        return STATIC_SECTIONS.get(section_key)

    @staticmethod
    def explain_filter(
        filter_name: str,
        filter_values: List[str],
        module_name: str
    ) -> str:
        """
        Generate explanation for why a filter is set to specific values.

        Args:
            filter_name: Name of filter (e.g., "Kommune", "Branche", "Problem")
            filter_values: List of values set for this filter
            module_name: Name of module this filter belongs to

        Returns:
            Human-readable explanation of the filter
        """
        if not filter_values:
            return f"{filter_name}-filteret er tomt (ingen filtrering på dette parameter)"

        # Generate contextual explanation based on filter type
        if filter_name == "Kommune":
            if len(filter_values) == 1:
                return f"Geografisk fokus: {filter_values[0]} kommune"
            else:
                return f"Geografisk fokus: {', '.join(filter_values)} kommuner"

        elif filter_name == "Branche":
            return f"Branchekoder {', '.join(filter_values)} filtrerer til virksomheder i disse specifikke brancher"

        elif filter_name == "Problem":
            if len(filter_values) == 1:
                return f"Fokuserer på Arbejdstilsynets kritik vedr. {filter_values[0]}"
            else:
                return f"Fokuserer på Arbejdstilsynets kritik vedr. {', '.join(filter_values)}"

        elif filter_name == "Reaktion":
            return f"Filtrerer til alvorlige reaktioner: {', '.join(filter_values)}"

        elif filter_name == "Statustype":
            return f"Overvåger virksomheder der ændrer status til: {', '.join(filter_values)}"

        elif filter_name == "Søgeord":
            search_string = filter_values[0] if filter_values else ""
            return f"Søgestreng '{search_string}' matcher dokumenter med disse termer"

        elif filter_name == "Person":
            if not filter_values:
                return "Person-filter skal udfyldes med konkrete navne"
            return f"Overvåger specifik person: {', '.join(filter_values)}"

        elif filter_name == "Virksomhed":
            if not filter_values:
                return "Virksomhed-filter skal udfyldes med CVR-numre (fx fra Registrering-step)"
            return f"Overvåger specifik virksomhed (CVR: {', '.join(filter_values)})"

        else:
            # Generic fallback
            return f"{filter_name}: {', '.join(filter_values)}"

    @staticmethod
    def get_relevant_principle_for_goal(goal: str, module_name: str) -> Optional[str]:
        """
        Determine which KM24 principle is most relevant for a given goal and module.

        Args:
            goal: User's investigation goal
            module_name: Current module being configured

        Returns:
            Principle key (cvr_first, hitlogik, notification_strategy) or None
        """
        goal_lower = goal.lower()

        # CVR-first is relevant when tracking virksomheder
        if module_name == "Registrering":
            return "cvr_first"

        # Hitlogik is relevant when combining multiple filters
        if any(term in goal_lower for term in ["kombiner", "både", "flere", "forskellige"]):
            return "hitlogik"

        # Notification strategy is always relevant
        return "notification_strategy"

    @staticmethod
    def get_dynamic_guide_for_module(module_name: str) -> Optional[str]:
        """
        Get dynamic pedagogical guide for a specific module.
        
        Args:
            module_name: Name of KM24 module (e.g., "Registrering", "Status")
        
        Returns:
            Module-specific pedagogical guide with concrete examples, or None if not found
        """
        return DYNAMIC_GUIDES.get(module_name)
