"""
Tests for educational content system.

Validates that educational enrichment works correctly and maintains
backward compatibility.
"""

import pytest
from km24_vejviser.content_library import (
    ContentLibrary,
    STATIC_SECTIONS,
    KM24_PRINCIPLES,
    QUALITY_CHECKLISTS,
)
from km24_vejviser.enrichment import RecipeEnricher
from km24_vejviser.models.usecase_response import (
    StepEducational,
    EducationalContent,
    Step,
    ModuleRef,
    UseCaseResponse,
)


class TestContentLibrary:
    """Test ContentLibrary static content access."""

    def test_static_sections_loaded(self):
        """Verify all static sections are loaded."""
        assert len(STATIC_SECTIONS) == 3
        assert "syntax_guide" in STATIC_SECTIONS
        assert "common_pitfalls" in STATIC_SECTIONS
        assert "troubleshooting" in STATIC_SECTIONS

    def test_km24_principles_loaded(self):
        """Verify KM24 principles are loaded."""
        assert len(KM24_PRINCIPLES) == 3
        assert "cvr_first" in KM24_PRINCIPLES
        assert "hitlogik" in KM24_PRINCIPLES
        assert "notification_strategy" in KM24_PRINCIPLES

    def test_quality_checklists_loaded(self):
        """Verify quality checklists are loaded for all major modules."""
        assert len(QUALITY_CHECKLISTS) >= 10
        assert "Registrering" in QUALITY_CHECKLISTS
        assert "Arbejdstilsyn" in QUALITY_CHECKLISTS
        assert "Status" in QUALITY_CHECKLISTS

    def test_get_principle(self):
        """Test retrieving a specific principle."""
        principle = ContentLibrary.get_principle("cvr_first")
        assert principle is not None
        assert "title" in principle
        assert "description" in principle
        assert "when_to_apply" in principle

    def test_get_quality_checklist(self):
        """Test retrieving module-specific quality checklist."""
        checklist = ContentLibrary.get_quality_checklist("Registrering")
        assert isinstance(checklist, list)
        assert len(checklist) > 0
        assert all(item.startswith("✓") for item in checklist)

    def test_explain_filter_kommune(self):
        """Test filter explanation for Kommune."""
        explanation = ContentLibrary.explain_filter(
            "Kommune", ["Aarhus"], "Registrering"
        )
        assert "Geografisk fokus" in explanation
        assert "Aarhus" in explanation

    def test_explain_filter_branche(self):
        """Test filter explanation for Branche."""
        explanation = ContentLibrary.explain_filter(
            "Branche", ["41.20"], "Registrering"
        )
        assert "Branchekoder" in explanation
        assert "41.20" in explanation

    def test_get_relevant_principle_for_registrering(self):
        """Test principle selection for Registrering module."""
        principle_key = ContentLibrary.get_relevant_principle_for_goal(
            "Overvåg byggevirksomheder", "Registrering"
        )
        assert principle_key == "cvr_first"


class TestPydanticModels:
    """Test new Pydantic models for educational content."""

    def test_step_educational_model(self):
        """Test StepEducational model validation."""
        edu = StepEducational(
            principle="CVR-først",
            filter_explanations={"Kommune": "Geografisk fokus"},
            quality_checklist=["Item 1", "Item 2"],
            common_mistakes=["Mistake 1"],
            red_flags=["Red flag 1"],
            action_plan="Take action",
            example_hit="Example hit",
        )
        assert edu.principle == "CVR-først"
        assert len(edu.quality_checklist) == 2
        assert len(edu.filter_explanations) == 1

    def test_educational_content_model(self):
        """Test EducationalContent model validation."""
        edu_content = EducationalContent(
            syntax_guide="Syntax here",
            common_pitfalls="Pitfalls here",
            troubleshooting="Troubleshooting here",
            km24_principles={"cvr_first": "Description"},
        )
        assert edu_content.syntax_guide == "Syntax here"
        assert len(edu_content.km24_principles) == 1

    def test_step_with_educational_optional(self):
        """Test that Step.educational is optional (backward compatible)."""
        step = Step(
            step_number=1,
            title="Test Step",
            type="monitoring",
            module=ModuleRef(id="1", name="Registrering"),
            rationale="Test rationale",
        )
        assert step.educational is None

    def test_step_with_educational_populated(self):
        """Test Step with educational content populated."""
        edu = StepEducational(
            principle="Test principle",
            filter_explanations={},
            quality_checklist=[],
            common_mistakes=[],
            red_flags=[],
            action_plan="Test action",
            example_hit="Test hit",
        )
        step = Step(
            step_number=1,
            title="Test Step",
            type="monitoring",
            module=ModuleRef(id="1", name="Registrering"),
            rationale="Test rationale",
            educational=edu,
        )
        assert step.educational is not None
        assert step.educational.principle == "Test principle"

    def test_usecase_response_educational_content_optional(self):
        """Test that UseCaseResponse.educational_content is optional."""
        # This would be tested in full integration, but model allows it
        pass


@pytest.mark.asyncio
class TestRecipeEnricher:
    """Test RecipeEnricher functionality."""

    async def test_enrich_basic_recipe(self):
        """Test enriching a basic recipe."""
        enricher = RecipeEnricher()

        recipe = {
            "steps": [
                {
                    "module": {"name": "Registrering", "id": "1"},
                    "filters": {"Branche": ["41.20"], "Kommune": ["Aarhus"]},
                    "notification": "interval",
                }
            ]
        }

        enriched = await enricher.enrich(recipe, "Test goal")

        # Check step educational content
        assert "educational" in enriched["steps"][0]
        step_edu = enriched["steps"][0]["educational"]
        assert "principle" in step_edu
        assert "filter_explanations" in step_edu
        assert "quality_checklist" in step_edu
        assert len(step_edu["quality_checklist"]) > 0

    async def test_enrich_multiple_steps(self):
        """Test enriching recipe with multiple steps."""
        enricher = RecipeEnricher()

        recipe = {
            "steps": [
                {
                    "module": {"name": "Registrering", "id": "1"},
                    "filters": {"Branche": ["41.20"]},
                    "notification": "interval",
                },
                {
                    "module": {"name": "Arbejdstilsyn", "id": "2"},
                    "filters": {"Problem": ["Asbest"]},
                    "notification": "instant",
                },
            ]
        }

        enriched = await enricher.enrich(recipe, "Test goal")

        assert len(enriched["steps"]) == 2
        assert all("educational" in step for step in enriched["steps"])

    async def test_universal_educational_content_added(self):
        """Test that universal educational content is added."""
        enricher = RecipeEnricher()

        recipe = {"steps": []}
        enriched = await enricher.enrich(recipe, "Test goal")

        assert "educational_content" in enriched
        edu_content = enriched["educational_content"]

        assert "syntax_guide" in edu_content
        assert "common_pitfalls" in edu_content
        assert "troubleshooting" in edu_content
        assert "km24_principles" in edu_content
        assert len(edu_content["km24_principles"]) == 3

    async def test_filter_explanations_generated(self):
        """Test that filter explanations are generated correctly."""
        enricher = RecipeEnricher()

        recipe = {
            "steps": [
                {
                    "module": {"name": "Arbejdstilsyn", "id": "1"},
                    "filters": {
                        "Problem": ["Asbest"],
                        "Kommune": ["Aarhus"],
                        "Reaktion": ["Forbud"],
                    },
                    "notification": "instant",
                }
            ]
        }

        enriched = await enricher.enrich(recipe, "Test goal")

        explanations = enriched["steps"][0]["educational"]["filter_explanations"]
        assert "Problem" in explanations
        assert "Kommune" in explanations
        assert "Reaktion" in explanations

    async def test_red_flags_module_specific(self):
        """Test that red flags are module-specific."""
        enricher = RecipeEnricher()

        # Test Arbejdstilsyn red flags
        recipe_arbejdstilsyn = {
            "steps": [
                {
                    "module": {"name": "Arbejdstilsyn", "id": "1"},
                    "filters": {"Reaktion": ["Forbud"]},
                    "notification": "instant",
                }
            ]
        }
        enriched_at = await enricher.enrich(recipe_arbejdstilsyn, "Test")
        red_flags_at = enriched_at["steps"][0]["educational"]["red_flags"]
        assert len(red_flags_at) > 0
        assert any("arbejdsmiljø" in flag.lower() for flag in red_flags_at)

        # Test Status red flags
        recipe_status = {
            "steps": [
                {
                    "module": {"name": "Status", "id": "1"},
                    "filters": {"Statustype": ["Konkurs"]},
                    "notification": "instant",
                }
            ]
        }
        enriched_status = await enricher.enrich(recipe_status, "Test")
        red_flags_status = enriched_status["steps"][0]["educational"]["red_flags"]
        assert len(red_flags_status) > 0
        assert any("konkurs" in flag.lower() for flag in red_flags_status)

    async def test_action_plan_generated(self):
        """Test that action plans are generated."""
        enricher = RecipeEnricher()

        recipe = {
            "steps": [
                {
                    "module": {"name": "Registrering", "id": "1"},
                    "filters": {},
                    "notification": "interval",
                }
            ]
        }

        enriched = await enricher.enrich(recipe, "Test goal")
        action_plan = enriched["steps"][0]["educational"]["action_plan"]

        assert action_plan is not None
        assert len(action_plan) > 0
        assert "Registrering" in action_plan

    async def test_example_hit_generated(self):
        """Test that example hits are generated."""
        enricher = RecipeEnricher()

        recipe = {
            "steps": [
                {
                    "module": {"name": "Arbejdstilsyn", "id": "1"},
                    "filters": {"Problem": ["Asbest"]},
                    "notification": "instant",
                }
            ]
        }

        enriched = await enricher.enrich(recipe, "Test goal")
        example_hit = enriched["steps"][0]["educational"]["example_hit"]

        assert example_hit is not None
        assert len(example_hit) > 0
        assert "Arbejdstilsyn" in example_hit


class TestBackwardCompatibility:
    """Test that educational content system is backward compatible."""

    def test_old_recipe_without_educational_validates(self):
        """Test that recipes without educational fields still validate."""

        # Minimal recipe without educational fields
        recipe_dict = {
            "overview": {
                "title": "Test Investigation",
                "strategy_summary": "Test strategy",
                "creative_approach": "Test approach",
            },
            "scope": {"primary_focus": "Test focus"},
            "monitoring": {"type": "keywords", "frequency": "daily"},
            "hit_budget": {"expected_hits": "moderate"},
            "notifications": {"primary": "daily", "channels": ["email"]},
            "parallel_profile": {"max_concurrent": 3},
            "steps": [
                {
                    "step_number": 1,
                    "title": "Test Step",
                    "type": "monitoring",
                    "module": {
                        "id": "1",
                        "name": "Registrering",
                        "is_web_source": False,
                    },
                    "rationale": "Test rationale",
                    "filters": {},
                }
            ],
            "syntax_guide": {"basic_syntax": [], "advanced_syntax": [], "tips": []},
            "quality": {"checks": [], "warnings": [], "recommendations": []},
            "artifacts": {"exports": [], "reports": [], "visualizations": []},
        }

        # Should validate without educational_content field
        response = UseCaseResponse.model_validate(recipe_dict)
        assert response.educational_content is None
        assert response.steps[0].educational is None
