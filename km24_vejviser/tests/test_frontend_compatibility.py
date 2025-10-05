"""
Test frontend compatibility with deterministic output.
"""
import pytest
from km24_vejviser.recipe_processor import complete_recipe


class TestFrontendCompatibility:
    """Test that deterministic output is compatible with frontend."""
    
    @pytest.mark.asyncio
    async def test_frontend_compatible_structure(self):
        """Test that output structure is compatible with frontend expectations."""
        # Simulate realistic LLM output
        raw_recipe = {
            "title": "Test Investigation",
            "strategy_summary": "Test strategy",
            "creative_approach": "Test approach",
            "investigation_steps": [
                {
                    "step": 1,
                    "title": "Test Step",
                    "type": "search",
                    "module": "Test Module",
                    "rationale": "Test rationale",
                    "details": {
                        "search_string": "test search",
                        "recommended_notification": "daily"
                    }
                }
            ],
            "next_level_questions": ["Test question"],
            "potential_story_angles": ["Test angle"],
            "creative_cross_references": ["Test cross-ref"]
        }
        
        goal = "Test goal for investigation"
        
        # Process through complete_recipe
        result = await complete_recipe(raw_recipe, goal)
        
        # Verify frontend-compatible structure
        assert "overview" in result
        assert "steps" in result
        assert "next_level_questions" in result
        assert "potential_story_angles" in result
        assert "creative_cross_references" in result
        
        # Verify overview has expected fields
        overview = result["overview"]
        assert "title" in overview
        assert "strategy_summary" in overview
        assert "creative_approach" in overview
        
        # Verify steps have expected structure
        steps = result["steps"]
        assert len(steps) == 1
        step = steps[0]
        assert "step_number" in step
        assert "title" in step
        assert "type" in step
        assert "module" in step
        assert "rationale" in step
        
        # Verify module structure
        module = step["module"]
        assert "id" in module
        assert "name" in module
        assert "is_web_source" in module
        
        print("Frontend compatibility test passed!")
        print("Result structure:", list(result.keys()))
        print("Steps structure:", list(steps[0].keys()) if steps else "No steps")
        print("Module structure:", list(module.keys()) if module else "No module")


if __name__ == "__main__":
    pytest.main([__file__])
