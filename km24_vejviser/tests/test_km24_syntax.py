"""
Test KM24 syntax standardization functions.
"""
import pytest
from km24_vejviser.recipe_processor import _standardize_search_string, _apply_km24_syntax_improvements

class TestKM24SyntaxStandardization:
    """Test KM24 syntax standardization functions."""
    
    def test_registrering_landbrug_standardization(self):
        """Test standardization for registrering module with landbrug."""
        result = _standardize_search_string("landbrug OR agriculture", "Registrering")
        expected = "landbrug;landbrugsvirksomhed;agriculture"
        assert result == expected
    
    def test_registrering_ejendom_standardization(self):
        """Test standardization for registrering module with ejendom."""
        result = _standardize_search_string("ejendomsselskab", "Registrering")
        expected = "ejendomsselskab;ejendomsudvikling;real_estate"
        assert result == expected
    
    def test_tinglysning_landbrug_standardization(self):
        """Test standardization for tinglysning module with landbrug."""
        result = _standardize_search_string("landbrugsejendom", "Tinglysning")
        expected = "~landbrugsejendom~"
        assert result == expected
    
    def test_tinglysning_ejendom_standardization(self):
        """Test standardization for tinglysning module with ejendom."""
        result = _standardize_search_string("ejendomshandel", "Tinglysning")
        expected = "~ejendomshandel~"
        assert result == expected
    
    def test_kapitalændring_landbrug_standardization(self):
        """Test standardization for kapitalændring module with landbrug."""
        result = _standardize_search_string("kapitalfond landbrug", "Kapitalændring")
        expected = "kapitalfond;ejendomsselskab;landbrug"
        assert result == expected
    
    def test_lokalpolitik_default_standardization(self):
        """Test standardization for lokalpolitik module."""
        result = _standardize_search_string("lokalplan", "Lokalpolitik")
        expected = "lokalplan;landzone;kommunal;politisk"
        assert result == expected
    
    def test_miljøsager_default_standardization(self):
        """Test standardization for miljøsager module."""
        result = _standardize_search_string("miljøtilladelse", "Miljøsager")
        expected = "miljøtilladelse;husdyrgodkendelse;udvidelse;miljø"
        assert result == expected
    
    def test_regnskaber_default_standardization(self):
        """Test standardization for regnskaber module."""
        result = _standardize_search_string("regnskab", "Regnskaber")
        expected = "regnskab;årsrapport;økonomi;finansiel"
        assert result == expected
    
    def test_unknown_module_no_standardization(self):
        """Test that unknown modules don't get standardized."""
        original = "test-søgestreng"
        result = _standardize_search_string(original, "UkendtModul")
        # Should apply general improvements but not module-specific patterns
        assert result != original  # Should have some improvements
        assert "test" in result  # Should still contain original content
    
    def test_empty_search_string(self):
        """Test handling of empty search strings."""
        result = _standardize_search_string("", "Registrering")
        assert result == ""
    
    def test_none_search_string(self):
        """Test handling of None search strings."""
        result = _standardize_search_string(None, "Registrering")
        assert result == ""

class TestKM24SyntaxImprovements:
    """Test general KM24 syntax improvements."""
    
    def test_or_to_semicolon_conversion(self):
        """Test that OR is not converted (removed this functionality)."""
        result = _apply_km24_syntax_improvements("landbrug OR agriculture")
        assert "OR" in result  # OR should remain unchanged
        assert "landbrug" in result  # landbrug should remain unchanged
    
    def test_and_to_space_conversion(self):
        """Test that AND is not converted (removed this functionality)."""
        result = _apply_km24_syntax_improvements("landbrug AND ejendom")
        assert "AND" in result  # AND should remain unchanged
        assert "landbrug" in result  # landbrug should remain unchanged
        assert "ejendom" in result
    
    def test_exact_phrase_tilde_wrapping(self):
        """Test wrapping exact phrases with tildes."""
        result = _apply_km24_syntax_improvements('"landbrugsejendom"')
        assert result == "~landbrugsejendom~"
    
    def test_variation_handling(self):
        """Test handling of word variations."""
        result = _apply_km24_syntax_improvements("landbrug-ejendom")
        assert ";" in result
    
    def test_operator_spacing(self):
        """Test that operator spacing is not applied (removed this functionality)."""
        result = _apply_km24_syntax_improvements("landbrugANDejendom")
        assert "landbrugANDejendom" == result  # Should remain unchanged
    
    def test_multiple_semicolons_cleanup(self):
        """Test cleanup of multiple semicolons."""
        result = _apply_km24_syntax_improvements("landbrug;;;agriculture")
        assert result.count(";") <= 1
    
    def test_multiple_spaces_cleanup(self):
        """Test cleanup of multiple spaces."""
        result = _apply_km24_syntax_improvements("landbrug   agriculture")
        assert "   " not in result
        assert "landbrug agriculture" in result
    
    def test_empty_string_handling(self):
        """Test handling of empty strings."""
        result = _apply_km24_syntax_improvements("")
        assert result == ""
    
    def test_none_string_handling(self):
        """Test handling of None strings."""
        result = _apply_km24_syntax_improvements(None)
        assert result == ""

if __name__ == "__main__":
    pytest.main([__file__])
