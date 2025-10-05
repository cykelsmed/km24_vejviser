
import pytest

from km24_vejviser.filter_catalog import get_filter_catalog


@pytest.mark.asyncio
async def test_hyper_relevance_concrete_values_asbest_esbjerg():
    goal = "Undersøg alvorlige asbest-sager i Esbjerg"

    catalog = get_filter_catalog()
    # Ensure base data is loaded (no-op if cached)
    await catalog.load_all_filters()

    recommendations = catalog.get_relevant_filters(
        goal, modules=["Arbejdstilsyn", "Danske medier"]
    )

    # Flatten for easy assertions
    rec_map = {}
    for r in recommendations:
        rec_map.setdefault(r.filter_type.lower(), set()).update({v for v in r.values})

    # Expect local media suggestions for Esbjerg
    assert "web_source" in rec_map
    assert {"JydskeVestkysten", "Esbjerg Ugeavis"}.issubset(rec_map["web_source"])

    # Expect problem=Asbest suggestion from Arbejdstilsyn knowledge
    # We accept either 'problem' (part name) or generic 'module_specific'
    problem_values = set()
    if "problem" in rec_map:
        problem_values |= rec_map["problem"]
    if "module_specific" in rec_map:
        problem_values |= rec_map["module_specific"]

    assert any(v.lower() == "asbest" for v in problem_values)
