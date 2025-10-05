"""
Recipe enrichment with educational content.

Enriches KM24 Vejviser recipes with pedagogical content from the ContentLibrary,
adding step-specific educational fields and universal educational sections.

This separation allows the LLM to focus on case-specific strategy while we
ensure consistent, high-quality educational content through hardcoded knowledge.
"""

import logging
from typing import Dict, List, Optional, Any
from km24_vejviser.content_library import ContentLibrary
from km24_vejviser.models.usecase_response import StepEducational, EducationalContent

logger = logging.getLogger(__name__)


class RecipeEnricher:
    """
    Enriches recipes with educational content.

    Takes a validated recipe dict and adds:
    - Per-step educational content (principles, checklists, red flags, etc.)
    - Universal educational content (syntax guide, pitfalls, troubleshooting)

    All enrichment is based on static content from ContentLibrary, ensuring
    consistency and correctness.
    """

    def __init__(self):
        """Initialize enricher with ContentLibrary access."""
        self.content_lib = ContentLibrary()

    async def enrich(self, recipe: dict, goal: str = "") -> dict:
        """
        Enrich recipe with educational content.

        Args:
            recipe: Validated recipe dict (post-validation, pre-Pydantic)
            goal: User's original investigation goal

        Returns:
            Enriched recipe dict with educational fields populated
        """
        logger.info(f"Enriching recipe with educational content (goal: {goal[:50]}...)")

        # Enrich each step with educational content
        steps = recipe.get("steps", [])
        for idx, step in enumerate(steps):
            step["educational"] = await self._enrich_step(step, goal, idx)

        # Add universal educational content
        recipe["educational_content"] = self._create_universal_content()

        logger.info(f"Enrichment complete: {len(steps)} steps enriched")
        return recipe

    async def _enrich_step(self, step: dict, goal: str, step_index: int) -> dict:
        """
        Enrich a single step with educational content.

        Args:
            step: Step dict to enrich
            goal: User's investigation goal
            step_index: Zero-based step index

        Returns:
            StepEducational dict with all educational fields
        """
        module_name = step.get("module", {}).get("name", "")
        filters = step.get("filters", {})

        # Get relevant KM24 principle for this step
        principle = self._get_relevant_principle(goal, module_name)

        # Generate filter explanations
        filter_explanations = self._explain_filters(filters, module_name)

        # Get quality checklist for this module
        quality_checklist = self.content_lib.get_quality_checklist(module_name)

        # Get common mistakes for this module
        common_mistakes = self._get_module_mistakes(module_name)

        # Generate red flags (what to watch for in hits)
        red_flags = self._generate_red_flags(step)

        # Generate action plan (what to do when hits arrive)
        action_plan = self._generate_action_plan(step)

        # Generate example hit
        example_hit = self._generate_example_hit(step)

        # Get dynamic pedagogical guide for this module
        pedagogical_guide = self.content_lib.get_dynamic_guide_for_module(module_name)

        return {
            "principle": principle,
            "filter_explanations": filter_explanations,
            "quality_checklist": quality_checklist,
            "common_mistakes": common_mistakes,
            "red_flags": red_flags,
            "action_plan": action_plan,
            "example_hit": example_hit,
            "pedagogical_guide": pedagogical_guide
        }

    def _explain_filters(self, filters: Dict[str, Any], module_name: str) -> Dict[str, str]:
        """
        Generate human-readable explanations for each filter.

        Args:
            filters: Dict of filter_name -> filter_values
            module_name: Name of module filters belong to

        Returns:
            Dict of filter_name -> explanation string
        """
        explanations = {}

        for filter_name, filter_values in filters.items():
            # Convert to list if single value
            if not isinstance(filter_values, list):
                filter_values = [filter_values] if filter_values else []

            # Use ContentLibrary to generate explanation
            explanation = self.content_lib.explain_filter(
                filter_name=filter_name,
                filter_values=filter_values,
                module_name=module_name
            )
            explanations[filter_name] = explanation

        return explanations

    def _get_relevant_principle(self, goal: str, module_name: str) -> Optional[str]:
        """
        Determine which KM24 principle is most relevant for this step.

        Args:
            goal: User's investigation goal
            module_name: Current module being configured

        Returns:
            Principle key (cvr_first, hitlogik, notification_strategy) or None
        """
        # Use ContentLibrary's heuristic to determine relevant principle
        principle_key = self.content_lib.get_relevant_principle_for_goal(goal, module_name)

        if principle_key:
            # Return the full principle text
            principle_data = self.content_lib.get_principle(principle_key)
            if principle_data:
                return f"{principle_data['title']}: {principle_data['description']}"

        return None

    def _get_module_mistakes(self, module_name: str) -> List[str]:
        """
        Get common mistakes specific to this module.

        Args:
            module_name: Name of KM24 module

        Returns:
            List of common mistakes to avoid
        """
        # Get module-specific pitfalls
        pitfalls_text = self.content_lib.get_pitfalls_for_module(module_name)

        # Extract relevant mistakes from pitfalls text
        # For now, we return generic pitfalls parsed into list
        # Could be enhanced to be more module-specific
        mistakes = []

        # Parse numbered mistakes from pitfalls text
        lines = pitfalls_text.split('\n')
        for line in lines:
            line = line.strip()
            # Match lines starting with numbers (1. 2. etc.)
            if line and line[0].isdigit() and '.' in line[:3]:
                # Extract mistake title (before the colon or newline)
                mistake = line.split(':', 1)[0].strip()
                if mistake:
                    mistakes.append(mistake)

        return mistakes[:5]  # Return top 5 mistakes

    def _generate_red_flags(self, step: dict) -> List[str]:
        """
        Generate red flags (what to watch for in hits).

        Args:
            step: Step dict

        Returns:
            List of red flags specific to this step's configuration
        """
        module_name = step.get("module", {}).get("name", "")
        filters = step.get("filters", {})
        red_flags = []

        # Module-specific red flags
        if module_name == "Arbejdstilsyn":
            if "Forbud" in filters.get("Reaktion", []) or "Strakspåbud" in filters.get("Reaktion", []):
                red_flags.append("🚨 Alvorlige arbejdsmiljø-overtrædelser der kræver øjeblikkelig handling")
                red_flags.append("🚨 Gentagne kritikpunkter af samme virksomhed indikerer systematiske problemer")

        elif module_name == "Status":
            if "Konkurs" in filters.get("Statustype", []):
                red_flags.append("🚨 Konkurs inden for 6 måneder efter Arbejdstilsyn-kritik")
                red_flags.append("🚨 Samme personer bag flere konkurser (konkursryttere)")

        elif module_name == "Tinglysning":
            # Tinglysning filters are arrays, not dicts with min_amount
            # Just provide generic high-value transaction red flags
            red_flags.append("🚨 Uventede købere (politikere, embedsmænd) kan indikere interessekonflikter")
            red_flags.append("🚨 Udenlandske selskaber med uklare ejere")
            red_flags.append("🚨 Transaktioner med usædvanlige beløb eller timing")

        elif module_name == "Personbogen":
            red_flags.append("🚨 Pant i løsøre eller virksomhedspant indikerer økonomiske problemer")
            red_flags.append("🚨 Gentagne panteindførsler over kort periode")

        elif module_name == "Lokalpolitik":
            red_flags.append("🚨 Habilitetserklæringer eller inhabilitet ved afstemninger")
            red_flags.append("🚨 Hastemøder eller ekstraordinære beslutninger uden normal høring")

        # Generic fallback
        if not red_flags:
            red_flags.append(f"⚠️  Overvåg {module_name}-hits for uventede mønstre eller outliers")

        return red_flags

    def _generate_action_plan(self, step: dict) -> str:
        """
        Generate action plan (what to do when hits arrive).

        Args:
            step: Step dict

        Returns:
            Action plan text
        """
        module_name = step.get("module", {}).get("name", "")
        notification = step.get("notification", "daily")

        action_plan = f"**Når {module_name}-hits ankommer:**\n\n"

        # Notification-specific actions
        if notification == "instant":
            action_plan += "1. **Øjeblikkelig gennemgang** - Dette er konfigureret som kritisk/tidssensitiv overvågning\n"
            action_plan += "2. **Vurder nyhedsværdi** - Kan det blive til en breaking news-historie?\n"
        else:
            action_plan += "1. **Ugentlig/daglig gennemgang** - Læs hits i sammenhæng med andre data\n"
            action_plan += "2. **Identificer mønstre** - Enkelttilfælde vs. systematiske problemer\n"

        # Module-specific actions
        if module_name == "Registrering":
            action_plan += "3. **Eksportér CVR-numre** - Brug disse til at filtrere andre moduler (Arbejdstilsyn, Status, Tinglysning)\n"
            action_plan += "4. **Undersøg ejere** - Hvem står bag de nye virksomheder? Tidligere konkurser?\n"

        elif module_name == "Arbejdstilsyn":
            action_plan += "3. **Krydsreference med Status** - Er kritiserede virksomheder gået konkurs?\n"
            action_plan += "4. **Interview kilder** - Kontakt fagforeninger, tidligere ansatte, lokale beboere\n"

        elif module_name == "Status":
            action_plan += "3. **Track personer** - Tilføj personer bag konkursen til Personbogen-overvågning\n"
            action_plan += "4. **Undersøg årsrapporter** - Hvad førte til konkursen? Økonomisk kriminalitet?\n"

        elif module_name == "Tinglysning":
            action_plan += "3. **Undersøg købere/sælgere** - Hvem er de? Interessekonflikter? Udenlandske ejere?\n"
            action_plan += "4. **Sammenlign med lokalpolitik** - Er der politiske beslutninger relateret til ejendommen?\n"

        elif module_name == "Lokalpolitik":
            action_plan += "3. **Deltag i møder** - Overvej at møde op til politiske møder\n"
            action_plan += "4. **Interview politikere** - Få baggrundshistorien og modsatrettede synspunkter\n"

        action_plan += "5. **Dokumentér alt** - Gem PDFer, screenshots, og notater til senere reference\n"

        return action_plan

    def _generate_example_hit(self, step: dict) -> str:
        """
        Generate example of what a hit might look like.

        Args:
            step: Step dict

        Returns:
            Example hit text
        """
        module_name = step.get("module", {}).get("name", "")
        filters = step.get("filters", {})

        # Module-specific examples
        if module_name == "Arbejdstilsyn":
            problem = filters.get("Problem", ["Asbest"])[0] if filters.get("Problem") else "Asbest"
            return f"""**Eksempel på {module_name}-hit:**

📋 Virksomhed: Byggeentreprenør ApS (CVR: 12345678)
📍 Sted: Aarhus
⚠️  Problem: {problem}
🚨 Reaktion: Strakspåbud
📅 Dato: 2024-10-01

**Resumé:** Arbejdstilsynet gav strakspåbud om øjeblikkelig standsning af arbejde på nedrivningsplads i Aarhus centrum. Der blev konstateret mangelfuld kortlægning af asbest før nedrivning, hvilket udsætter arbejdere for sundhedsfarlige asbestfibre.
"""

        elif module_name == "Status":
            return f"""**Eksempel på {module_name}-hit:**

🏢 Virksomhed: Byggeri & Renoveringer ApS (CVR: 87654321)
📊 Statusændring: Aktiv → Konkurs
📅 Dato: 2024-10-03

**Bemærk:** Denne virksomhed modtog Arbejdstilsyn-kritik for 3 måneder siden (se step 2 hits). Konkurs kort efter alvorlig kritik kan indikere økonomiske konsekvenser eller eksisterende økonomiske problemer.
"""

        elif module_name == "Tinglysning":
            return f"""**Eksempel på {module_name}-hit:**

🏠 Ejendom: Erhvervsejendom, Banegårdspladsen 1, Aarhus
💰 Beløb: 75.000.000 kr
👤 Køber: Offshore Investment Ltd. (Malta)
📅 Tinglyst: 2024-10-02

**Interessant:** Udenlandsk selskab køber central erhvervsejendom. Undersøg: Hvem står bag? Politiske forbindelser? Lokalplanændringer der øger værdien?
"""

        elif module_name == "Registrering":
            branch_code = filters.get("Branche", ["41.20"])[0] if filters.get("Branche") else "41.20"
            return f"""**Eksempel på {module_name}-hit:**

🆕 Ny virksomhed registreret
🏢 Navn: Skandinavisk Entreprise ApS
🏷️  Branche: {branch_code} (Opførelse af bygninger)
📍 Adresse: Aarhus C
👤 Direktør: Lars Hansen (tidligere direktør i 2 konkursramte byggefirmaer)
📅 Stiftet: 2024-10-01

**Red flag:** Samme person bag flere konkurser - potentiel konkursrytter.
"""

        elif module_name == "Lokalpolitik":
            return f"""**Eksempel på {module_name}-hit:**

📋 Dokument: Dagsorden, Aarhus Byråd
📅 Mødedato: 2024-10-15
📌 Punkt: Lokalplan for erhvervsområde ved havnen

**Resumé:** Byrådet skal godkende lokalplan der tillader højere bygninger i erhvervsområde. Bemærk: Ejer af område er et maltesisk selskab (se Tinglysning-step). Potentiel interessekonflikt?
"""

        # Generic fallback
        return f"**Eksempel på {module_name}-hit:**\n\nHits fra {module_name} vises her med relevante felter og metadata."

    def _create_universal_content(self) -> dict:
        """
        Create universal educational content for entire recipe.

        Returns:
            EducationalContent dict with syntax guide, pitfalls, troubleshooting, principles
        """
        return {
            "syntax_guide": self.content_lib.get_syntax_guide(),
            "common_pitfalls": self.content_lib.get_static_section("common_pitfalls") or "",
            "troubleshooting": self.content_lib.get_troubleshooting(),
            "km24_principles": self._format_principles_for_output()
        }

    def _format_principles_for_output(self) -> Dict[str, str]:
        """
        Format KM24 principles for output in educational_content.

        Returns:
            Dict of principle_key -> formatted description
        """
        all_principles = self.content_lib.get_all_principles()
        formatted = {}

        for key, principle in all_principles.items():
            # Format as "Title: Description"
            formatted[key] = f"{principle['title']}\n\n{principle['description']}\n\nAnvend når: {principle['when_to_apply']}"

        return formatted
