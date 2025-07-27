import pytest
from fastapi.testclient import TestClient
from main import app
from main import complete_recipe
import os

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "anthropic_configured" in data
    assert "timestamp" in data

def test_generate_recipe_missing_goal():
    # goal er påkrævet, så tom payload skal give 422
    response = client.post("/generate-recipe/", json={})
    assert response.status_code == 422

def test_generate_recipe_invalid_goal():
    # goal skal være en ikke-tom streng, test med tom streng
    response = client.post("/generate-recipe/", json={"goal": ""})
    assert response.status_code in (422, 500)

# Bemærk: For at teste et gyldigt flow kræves en gyldig Anthropic API-nøgle i .env
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") or "YOUR_API_KEY_HERE" in os.getenv("ANTHROPIC_API_KEY", ""),
    reason="Anthropic API-nøgle ikke sat. Integrationstest springes over."
)
def test_generate_recipe_valid():
    response = client.post("/generate-recipe/", json={"goal": "Undersøg solcelleprojekter i Aarhus"})
    assert response.status_code == 200
    data = response.json()
    assert "investigation_steps" in data or "error" in data
    if "investigation_steps" in data:
        assert isinstance(data["investigation_steps"], list)

def test_generate_recipe_no_api_key(monkeypatch):
    # Simuler at ANTHROPIC_API_KEY ikke er sat
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from main import client as anthropic_client
    # Tving reload af client
    anthropic_client = None
    response = client.post("/generate-recipe/", json={"goal": "Dette er et langt testmål"})
    assert response.status_code == 500
    data = response.json()
    assert "error" in data

def test_generate_recipe_invalid_json():
    # Ugyldig JSON (fx manglende quotes)
    response = client.post("/generate-recipe/", data="{goal: test}", headers={"Content-Type": "application/json"})
    assert response.status_code == 422 or response.status_code == 400

def test_internal_server_error(monkeypatch):
    # Simulerer exception i complete_recipe
    def broken_complete_recipe(recipe):
        raise RuntimeError("Simuleret fejl")
    monkeypatch.setattr("main.complete_recipe", broken_complete_recipe)
    response = client.post("/generate-recipe/", json={"goal": "Dette er et langt testmål"})
    assert response.status_code == 500
    data = response.json()
    assert "error" in data

def test_complete_recipe_adds_fields():
    # Minimal input med investigation_steps og detaljer
    input_recipe = {
        "goal": "Test mål med mere end ti tegn",
        "investigation_steps": [
            {
                "step": 1,
                "title": "Find relevante kommuner",
                "type": "search",
                "module": "Kommuner",
                "details": {
                    "search_string": "test;test2"
                }
            }
        ]
    }
    output = complete_recipe(input_recipe)
    step = output["investigation_steps"][0]
    # Tjek at felter er tilføjet
    assert "strategic_note" in step["details"]
    assert "recommended_notification" in step["details"]
    assert "power_tip" in step["details"]
    if "warning" in step["details"]:
        assert step["details"]["warning"] is not None
    # geo_advice kan være None, så kun check hvis feltet findes
    if "geo_advice" in step["details"]:
        assert step["details"]["geo_advice"] is not None
    assert "supplementary_modules" in output
    assert isinstance(output["supplementary_modules"], list) 