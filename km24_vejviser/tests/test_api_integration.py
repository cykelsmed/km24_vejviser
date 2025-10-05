import os
import pytest

from km24_vejviser.km24_client import KM24APIClient


@pytest.mark.asyncio
async def test_modules_basic_and_details():
    client = KM24APIClient()
    if not os.getenv("KM24_API_KEY"):
        pytest.skip("KM24_API_KEY not set")
    basic = await client.get_modules_basic(force_refresh=True)
    if not basic.success and basic.error and "Authentication" in basic.error:
        pytest.skip("KM24 API authentication failed – skipping integration test")
    assert basic.success, f"modules/basic failed: {basic.error}"
    items = basic.data.get("items", []) if basic.data else []
    assert items, "No modules returned"
    first_id = items[0].get("id")
    assert isinstance(first_id, int), "Module id should be int"

    details = await client.get_module_details(first_id, force_refresh=True)
    assert details.success, f"module details failed: {details.error}"
    assert details.data.get("id") == first_id


@pytest.mark.asyncio
async def test_generic_values_and_web_sources_if_present():
    client = KM24APIClient()
    if not os.getenv("KM24_API_KEY"):
        pytest.skip("KM24_API_KEY not set")
    basic = await client.get_modules_basic()
    if not basic.success and basic.error and "Authentication" in basic.error:
        pytest.skip("KM24 API authentication failed – skipping integration test")
    assert basic.success
    for module in basic.data.get("items", [])[:5]:
        module_id = module.get("id")
        parts = module.get("parts", [])
        # generic_values
        for part in parts:
            if part.get("part") == "generic_value":
                part_id = part.get("id")
                gv = await client.get_generic_values(part_id)
                assert gv.success, f"generic-values failed: {gv.error}"
                break
        # web_sources
        if any(p.get("part") == "web_source" for p in parts):
            ws = await client.get_web_sources(module_id)
            assert ws.success, f"web-sources failed: {ws.error}"
            break


@pytest.mark.asyncio
async def test_fallback_on_connection_error(monkeypatch):
    client = KM24APIClient()

    async def fake_make_request(*args, **kwargs):
        from km24_vejviser.km24_client import KM24APIResponse

        return KM24APIResponse(
            success=False, error="API forbindelsesfejl - kunne ikke nå KM24 serveren"
        )

    # Monkeypatch the _make_request method to simulate down API
    monkeypatch.setattr(client, "_make_request", fake_make_request)

    res = await client.get_modules_basic(force_refresh=True)
    assert not res.success and "forbindelsesfejl" in (res.error or "")
