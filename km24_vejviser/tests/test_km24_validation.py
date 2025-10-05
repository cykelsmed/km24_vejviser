"""
Test KM24 validation rules.
"""
import pytest
from km24_vejviser.recipe_processor import (
    validate_km24_recipe, 
    validate_step, 
    validate_module, 
    validate_search_syntax,
    validate_filters,
    validate_notification,
    format_validation_error
)


class TestKM24Validation:
    """Test KM24 validation rules."""
    
    def test_valid_recipe_structure(self):
        """Test that a valid recipe passes validation."""
        valid_recipe = {
            "overview": {
                "strategy_summary": "Test strategi"
            },
            "steps": [
                {
                    "module": {"name": "Registrering"},
                    "search_string": "landbrug;landbrugsvirksomhed",
                    "filters": {"geografi": ["Vestjylland"]},
                    "notification": "løbende"
                },
                {
                    "module": {"name": "Tinglysning"},
                    "search_string": "~landbrugsejendom~",
                    "filters": {"beløb": [">10 mio"]},
                    "notification": "løbende"
                },
                {
                    "module": {"name": "Kapitalændring"},
                    "search_string": "kapitalfond;ejendomsselskab",
                    "filters": {"branche": ["ejendom"]},
                    "notification": "løbende"
                }
            ],
            "next_level_questions": ["Hvad sker der?"],
            "potential_story_angles": ["Vinkel 1"],
            "quality": {"checks": ["Check 1"]}
        }
        
        is_valid, errors = validate_km24_recipe(valid_recipe)
        assert is_valid, f"Valid recipe failed validation: {errors}"
    
    def test_invalid_recipe_missing_sections(self):
        """Test that missing sections are caught."""
        invalid_recipe = {
            "overview": {"strategy_summary": "Test"},
            "steps": []
        }
        
        is_valid, errors = validate_km24_recipe(invalid_recipe)
        assert not is_valid
        assert "Mangler sektion: next_level_questions" in errors
        assert "Mangler sektion: potential_story_angles" in errors
    
    def test_invalid_search_syntax_lowercase_operators(self):
        """Test that lowercase operators are caught."""
        invalid_step = {
            "module": {"name": "Registrering"},
            "search_string": "landbrug and ejendom",
            "filters": {"geografi": ["Vestjylland"]},
            "notification": "løbende"
        }
        
        errors = validate_step(invalid_step, 1)
        assert any("Ugyldig operator 'and'" in error for error in errors)
    
    def test_invalid_search_syntax_commas(self):
        """Test that commas are caught."""
        invalid_step = {
            "module": {"name": "Registrering"},
            "search_string": "landbrug,ejendom,agriculture",
            "filters": {"geografi": ["Vestjylland"]},
            "notification": "løbende"
        }
        
        errors = validate_step(invalid_step, 1)
        assert any("Brug semikolon ; i stedet for komma" in error for error in errors)
    
    def test_invalid_module_name(self):
        """Test that invalid module names are caught."""
        invalid_step = {
            "module": {"name": "UgyldigtModul"},
            "search_string": "test",
            "filters": {"geografi": ["Vestjylland"]},
            "notification": "løbende"
        }
        
        errors = validate_step(invalid_step, 1)
        assert any("Ugyldigt modulnavn" in error for error in errors)
    
    def test_invalid_notification(self):
        """Test that invalid notifications are caught."""
        invalid_step = {
            "module": {"name": "Registrering"},
            "search_string": "test",
            "filters": {"geografi": ["Vestjylland"]},
            "notification": "ugyldig"
        }
        
        errors = validate_step(invalid_step, 1)
        assert any("Ugyldig notifikationskadence" in error for error in errors)
    
    def test_empty_filters(self):
        """Test that empty filters are allowed (not an error)."""
        valid_step = {
            "module": {"name": "Registrering"},
            "search_string": "test",
            "filters": {},
            "notification": "løbende"
        }
        
        errors = validate_step(valid_step, 1)
        # Empty filters should not cause an error
        assert not any("Filtre kan ikke være tomme" in error for error in errors)
    
    def test_web_source_missing_source_selection(self):
        """Test that web source modules without source selection are caught."""
        invalid_step = {
            "module": {"name": "EU", "is_web_source": True},
            "search_string": "test",
            "filters": {"geografi": ["Vestjylland"]},
            "notification": "løbende"
        }
        
        errors = validate_step(invalid_step, 1)
        assert any("Webkilde-modul kræver source_selection" in error for error in errors)
    
    def test_format_validation_error(self):
        """Test that validation errors are formatted correctly."""
        errors = ["Fejl 1", "Fejl 2"]
        formatted = format_validation_error(errors)
        
        assert "UGYLDIG OPSKRIFT – RET FØLGENDE:" in formatted
        assert "• Fejl 1" in formatted
        assert "• Fejl 2" in formatted
    
    def test_minimum_pipeline_steps(self):
        """Test that pipeline has minimum 3 steps."""
        invalid_recipe = {
            "overview": {"strategy_summary": "Test"},
            "steps": [
                {
                    "module": {"name": "Registrering"},
                    "search_string": "test",
                    "filters": {"geografi": ["Vestjylland"]},
                    "notification": "løbende"
                }
            ],
            "next_level_questions": ["Test"],
            "potential_story_angles": ["Test"],
            "quality": {"checks": ["Test"]}
        }
        
        is_valid, errors = validate_km24_recipe(invalid_recipe)
        assert not is_valid
        assert "Pipeline skal have mindst 3 trin" in errors
