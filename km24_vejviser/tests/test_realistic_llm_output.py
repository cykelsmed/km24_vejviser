"""
Test realistic LLM output that was causing validation errors.
"""

import pytest
from km24_vejviser.recipe_processor import complete_recipe


class TestRealisticLLMOutput:
    """Test handling of realistic LLM output with Danish notification values."""

    @pytest.mark.asyncio
    async def test_realistic_llm_output_normalization(self):
        """Test that realistic LLM output is properly normalized."""
        # Simulate the actual LLM output that was causing errors
        raw_recipe = {
            "title": "Undersøgelse af store byggeprojekter i Aarhus",
            "strategy_summary": "Systematisk tilgang med CVR først-princippet",
            "creative_approach": "Data-driven approach med cross-referencing",
            "investigation_steps": [
                {
                    "step": 1,
                    "title": "CVR Først: Identificér Relevante Virksomheder",
                    "type": "search",
                    "module": "Registrering",
                    "rationale": "Start med at identificere alle relevante virksomheder",
                    "details": {
                        "search_string": "bygge OR construction",
                        "recommended_notification": "løbende",  # Danish value
                    },
                },
                {
                    "step": 2,
                    "title": "Overvåg Virksomhedsstatusændringer",
                    "type": "search",
                    "module": "Status",
                    "rationale": "Hold øje med statusændringer",
                    "details": {"recommended_notification": "interval"},  # Danish value
                },
                {
                    "step": 3,
                    "title": "Krydsreference med Lokalpolitik",
                    "type": "search",
                    "module": "Lokalpolitik",
                    "rationale": "Søg efter lokalpolitiske beslutninger",
                    "details": {
                        "search_string": "byggeprojekter",
                        "recommended_notification": "løbende",  # Danish value
                    },
                },
                {
                    "step": 4,
                    "title": "Tinglysning af Ejendomshandler",
                    "type": "search",
                    "module": "Tinglysning",
                    "rationale": "Overvåg store ejendomshandler",
                    "details": {"recommended_notification": "løbende"},  # Danish value
                },
            ],
            "next_level_questions": [
                "Hvordan kan vi identificere mønstre i byggeprojekter?"
            ],
            "potential_story_angles": ["Konkrete hypoteser om byggeprojekter"],
            "creative_cross_references": ["Krydsreferering mellem moduler"],
        }

        goal = "Undersøg store byggeprojekter i Aarhus og konkurser i byggebranchen"

        # This should not raise validation errors
        result = await complete_recipe(raw_recipe, goal)

        # Verify the result is valid
        assert "overview" in result
        assert "scope" in result
        assert "steps" in result

        # Verify scope.primary_focus is set
        assert "primary_focus" in result["scope"]
        assert result["scope"]["primary_focus"] == goal

        # Verify notifications are normalized to English
        assert len(result["steps"]) == 4
        assert result["steps"][0]["notification"] == "instant"  # løbende -> instant
        assert result["steps"][1]["notification"] == "weekly"  # interval -> weekly
        assert result["steps"][2]["notification"] == "instant"  # løbende -> instant
        assert result["steps"][3]["notification"] == "instant"  # løbende -> instant

        # Verify step numbers are sequential
        step_numbers = [step["step_number"] for step in result["steps"]]
        assert step_numbers == [1, 2, 3, 4]

        # Verify modules have proper structure
        for step in result["steps"]:
            assert "module" in step
            assert "id" in step["module"]
            assert "name" in step["module"]
            assert "is_web_source" in step["module"]

    @pytest.mark.asyncio
    async def test_minimal_llm_output_handling(self):
        """Test handling of minimal LLM output."""
        # Minimal LLM output that might be incomplete
        raw_recipe = {
            "title": "Minimal Test",
            "investigation_steps": [
                {
                    "step": 1,
                    "title": "Test Step",
                    "type": "search",
                    "module": "Test",
                    "rationale": "Test rationale",
                    # Missing details, notification, etc.
                }
            ],
        }

        goal = "Test goal"

        # Should not raise validation errors
        result = await complete_recipe(raw_recipe, goal)

        # Verify defaults are applied
        assert result["scope"]["primary_focus"] == goal
        assert result["steps"][0]["notification"] == "daily"  # Default
        assert result["steps"][0]["delivery"] == "email"  # Default
        assert result["steps"][0]["filters"] == {}  # Default
        assert result["steps"][0]["source_selection"] == []  # Default


if __name__ == "__main__":
    pytest.main([__file__])
