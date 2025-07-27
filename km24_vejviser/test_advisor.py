import pytest
from advisor import get_supplementary_modules, determine_notification_type, get_warning, get_power_tip, get_geo_advice

def test_get_supplementary_modules():
    prompt = "solcelle og energi i EU"
    result = get_supplementary_modules(prompt)
    assert any(s["module"] == "EU" for s in result)
    prompt2 = "miljø annoncering i kommunen"
    result2 = get_supplementary_modules(prompt2)
    assert any(s["module"] == "Miljø-annonceringer" for s in result2)
    prompt3 = "retslister og domstol"
    result3 = get_supplementary_modules(prompt3)
    assert any(s["module"] == "Domme" for s in result3)
    prompt4 = "intet match"
    assert get_supplementary_modules(prompt4) == []

def test_determine_notification_type():
    assert determine_notification_type("Tinglysning") == "løbende"
    assert determine_notification_type("Status") == "løbende"
    assert determine_notification_type("Domme") == "interval"

def test_get_warning():
    assert get_warning("Kommuner") is not None
    assert get_warning("Lokalpolitik") is not None
    assert get_warning("Domme") is None

def test_get_power_tip():
    assert get_power_tip("Tinglysning") == {
        "title": "+1-tricket",
        "explanation": "Opret brugere som navn+1@domæne.dk for at køre flere overvågninger parallelt."
    }
    assert get_power_tip("Status") == {
        "title": ";-tricket",
        "explanation": "Brug semikolon (;) til at overvåge navnevariationer, fx 'fragt;fragtfirma'."
    }
    assert get_power_tip("Domme") == {
        "title": "Hitlogik",
        "explanation": "Kombinér OG/ELLER for at styre præcist, hvilke domme der matches."
    }
    # Test for search_string med ;
    assert get_power_tip(None, search_string="solcellepark;solcelleanlæg") == {
        "title": "Power-tip",
        "explanation": "Brug `term1;term2` for at sikre, at du fanger begge begreber i ét modul – fx både 'solcellepark' og 'solcelleanlæg'."
    }
    assert get_power_tip("Kommuner") is None

def test_get_geo_advice():
    assert get_geo_advice("Find relevante kommuner") is not None
    assert get_geo_advice("Regionale energiplaner") is not None
    assert get_geo_advice("Overvågning af miljøsager") is not None
    assert get_geo_advice("Analyse af solcelleparker") is not None
    assert get_geo_advice("Virksomhedsopkøb") is None 