"""
Test normalization functions for deterministic output.
"""
import pytest
from km24_vejviser.main import _normalize_notification, _get_default_sources_for_module, coerce_raw_to_target_shape, apply_min_defaults


class TestNotificationNormalization:
    """Test notification value normalization."""
    
    def test_danish_to_english_mapping(self):
        """Test mapping of Danish notification values to English."""
        assert _normalize_notification("løbende") == "instant"
        assert _normalize_notification("øjeblikkelig") == "instant"
        assert _normalize_notification("instant") == "instant"
        
        assert _normalize_notification("interval") == "weekly"
        assert _normalize_notification("periodisk") == "weekly"
        assert _normalize_notification("weekly") == "weekly"
        
        assert _normalize_notification("daily") == "daily"
        assert _normalize_notification("daglig") == "daily"
        assert _normalize_notification("") == "daily"
        assert _normalize_notification(None) == "daily"
    
    def test_case_insensitive(self):
        """Test that normalization is case insensitive."""
        assert _normalize_notification("LØBENDE") == "instant"
        assert _normalize_notification("Interval") == "weekly"
        assert _normalize_notification("DAILY") == "daily"


class TestCoerceRawToTargetShape:
    """Test raw LLM output normalization."""
    
    def test_scope_primary_focus_from_goal(self):
        """Test that scope.primary_focus is set from goal."""
        raw = {"title": "Test"}
        goal = "Undersøg store byggeprojekter i Aarhus"
        
        result = coerce_raw_to_target_shape(raw, goal)
        
        assert result["scope"]["primary_focus"] == goal
    
    def test_scope_primary_focus_truncated(self):
        """Test that long goals are truncated."""
        raw = {"title": "Test"}
        goal = "A" * 150  # Very long goal
        
        result = coerce_raw_to_target_shape(raw, goal)
        
        assert len(result["scope"]["primary_focus"]) <= 103  # 100 + "..."
        assert result["scope"]["primary_focus"].endswith("...")
    
    def test_notification_normalization_in_steps(self):
        """Test that step notifications are normalized."""
        raw = {
            "investigation_steps": [
                {
                    "step": 1,
                    "title": "Test Step",
                    "type": "search",
                    "module": "Test",
                    "rationale": "Test",
                    "details": {
                        "recommended_notification": "løbende"
                    }
                }
            ]
        }
        
        result = coerce_raw_to_target_shape(raw, "Test goal")
        
        assert result["steps"][0]["notification"] == "instant"


class TestDefaultSources:
    """Test default source selection for web source modules."""
    
    def test_default_sources_for_lokalpolitik(self):
        """Test default sources for Lokalpolitik module."""
        sources = _get_default_sources_for_module("Lokalpolitik")
        assert "Aarhus" in sources
        assert "København" in sources
        assert "Odense" in sources
        assert "Aalborg" in sources
    
    def test_default_sources_for_danske_medier(self):
        """Test default sources for Danske medier module."""
        sources = _get_default_sources_for_module("Danske medier")
        assert "DR" in sources
        assert "TV2" in sources
        assert "Berlingske" in sources
    
    def test_default_sources_for_unknown_module(self):
        """Test that unknown modules get empty source list."""
        sources = _get_default_sources_for_module("Unknown Module")
        assert sources == []


class TestApplyMinDefaults:
    """Test default application."""
    
    def test_notification_normalization_in_defaults(self):
        """Test that existing notifications are normalized during defaults."""
        recipe = {
            "steps": [
                {
                    "step_number": 1,
                    "title": "Test",
                    "type": "search",
                    "module": {"id": "test", "name": "Test", "is_web_source": False},
                    "rationale": "Test",
                    "notification": "løbende"  # Danish value
                }
            ]
        }
        
        apply_min_defaults(recipe)
        
        assert recipe["steps"][0]["notification"] == "instant"
    
    def test_missing_notification_gets_default(self):
        """Test that missing notifications get daily default."""
        recipe = {
            "steps": [
                {
                    "step_number": 1,
                    "title": "Test",
                    "type": "search",
                    "module": {"id": "test", "name": "Test", "is_web_source": False},
                    "rationale": "Test"
                    # No notification field
                }
            ]
        }
        
        apply_min_defaults(recipe)
        
        assert recipe["steps"][0]["notification"] == "daily"
    
    def test_web_source_gets_default_sources(self):
        """Test that web source modules get default sources."""
        recipe = {
            "steps": [
                {
                    "step_number": 1,
                    "title": "Test",
                    "type": "search",
                    "module": {"id": "lokalpolitik", "name": "Lokalpolitik", "is_web_source": True},
                    "rationale": "Test"
                    # No source_selection field
                }
            ]
        }
        
        apply_min_defaults(recipe)
        
        assert "source_selection" in recipe["steps"][0]
        sources = recipe["steps"][0]["source_selection"]
        assert "Aarhus" in sources
        assert "København" in sources
    
    def test_non_web_source_gets_empty_sources(self):
        """Test that non-web source modules get empty source list."""
        recipe = {
            "steps": [
                {
                    "step_number": 1,
                    "title": "Test",
                    "type": "search",
                    "module": {"id": "test", "name": "Test", "is_web_source": False},
                    "rationale": "Test"
                    # No source_selection field
                }
            ]
        }
        
        apply_min_defaults(recipe)
        
        assert recipe["steps"][0]["source_selection"] == []


if __name__ == "__main__":
    pytest.main([__file__])
