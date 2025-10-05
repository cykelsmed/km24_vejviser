import pytest
from fastapi.testclient import TestClient
from km24_vejviser.main import app
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
    not os.getenv("ANTHROPIC_API_KEY")
    or "YOUR_API_KEY_HERE" in os.getenv("ANTHROPIC_API_KEY", ""),
    reason="Anthropic API-nøgle ikke sat. Integrationstest springes over.",
)
def test_generate_recipe_valid():
    response = client.post(
        "/generate-recipe/", json={"goal": "Undersøg solcelleprojekter i Aarhus"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "steps" in data or "error" in data
    if "steps" in data:
        assert isinstance(data["steps"], list)


def test_generate_recipe_no_api_key(monkeypatch):
    # Simuler at ANTHROPIC_API_KEY ikke er sat
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    # Tving reload af client
    response = client.post(
        "/generate-recipe/", json={"goal": "Dette er et langt testmål"}
    )
    assert response.status_code == 500
    data = response.json()
    assert "error" in data


def test_generate_recipe_invalid_json():
    # Ugyldig JSON (fx manglende quotes)
    response = client.post(
        "/generate-recipe/",
        data="{goal: test}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422 or response.status_code == 400


def test_internal_server_error(monkeypatch):
    # Simulerer exception i complete_recipe
    async def broken_complete_recipe(recipe, goal=""):
        raise RuntimeError("Simuleret fejl")

    monkeypatch.setattr("km24_vejviser.main.complete_recipe", broken_complete_recipe)
    response = client.post(
        "/generate-recipe/", json={"goal": "Dette er et langt testmål"}
    )
    assert response.status_code == 500
    data = response.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_coerce_raw_to_target_shape():
    """Test that coerce_raw_to_target_shape properly structures the output."""
    from km24_vejviser.recipe_processor import coerce_raw_to_target_shape

    # Test input
    input_recipe = {
        "goal": "Test mål med mere end ti tegn",
        "investigation_steps": [
            {
                "step": 1,
                "title": "Find relevante kommuner",
                "type": "search",
                "module": "Registrering",
                "details": {"search_string": "test;test2"},
            }
        ],
    }

    output = coerce_raw_to_target_shape(input_recipe, "Test mål")

    # Check that the output has the expected structure
    assert "steps" in output
    assert isinstance(output["steps"], list)
    assert len(output["steps"]) == 1

    step = output["steps"][0]
    assert "title" in step
    assert "module" in step
    assert "search_string" in step
    assert "filters" in step
    assert isinstance(step["filters"], dict)
