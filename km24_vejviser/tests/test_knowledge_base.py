import asyncio
from typing import Optional, Dict, Any

import pytest

from km24_vejviser.knowledge_base import (
    KnowledgeBase,
    extract_terms_from_text,
    map_terms_to_parts,
)
from km24_vejviser.km24_client import KM24APIResponse


class StubClient:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    async def get_modules_basic(self, force_refresh: bool = False) -> KM24APIResponse:
        return KM24APIResponse(success=True, data=self._data, cached=True)


@pytest.mark.asyncio
async def test_knowledge_base_builds_profiles_from_basic():
    payload = {
        "items": [
            {
                "id": 101,
                "title": "Arbejdstilsyn",
                "longDescription": "Ved alvorlige overtrædelser kan der gives Forbud og Strakspåbud. Asbest er et klassisk problem.",
                "parts": [
                    {"id": 5001, "name": "Reaktion", "part": "generic_value"},
                    {"id": 5002, "name": "Problem", "part": "generic_value"},
                ],
            },
            {
                "id": 102,
                "title": "Tinglysning",
                "longDescription": "Samlehandler er særlige handler. Der kan være beløbsgrænser og forskellige ejendomstyper, fx erhvervsejendom.",
                "parts": [
                    {"id": 5101, "name": "Amount selection", "part": "generic_value"},
                    {"id": 5102, "name": "Ejendomstype", "part": "generic_value"},
                ],
            },
        ]
    }

    kb = KnowledgeBase(client=StubClient(payload))
    result = await kb.load()
    assert result["success"] is True
    assert result["profiles"] == 2

    at = kb.get_profile_by_title("Arbejdstilsyn")
    assert at is not None
    # Terms
    assert {"forbud", "strakspåbud", "asbest"}.issubset(at.extracted_terms)
    # Mappings
    reaction_terms = {m.term for m in at.term_mappings if m.part_name and "reaktion" in m.part_name}
    assert {"forbud", "strakspåbud"}.issubset(reaction_terms)
    problem_terms = {m.term for m in at.term_mappings if m.part_name and "problem" in m.part_name}
    assert "asbest" in problem_terms

    ting = kb.get_profile_by_title("Tinglysning")
    assert ting is not None
    assert {"samlehandel", "beløbsgrænse", "erhvervsejendom"}.issubset(ting.extracted_terms)
    has_amount_map = any(m.term == "samlehandel" and m.part_id == 5101 for m in ting.term_mappings)
    assert has_amount_map
    has_property_map = any(m.term == "erhvervsejendom" and m.part_id == 5102 for m in ting.term_mappings)
    assert has_property_map


def test_extract_terms_from_text_basic():
    text = "Asbest kan føre til Forbud eller Strakspåbud. Samlehandel og beløbsgrænser nævnes også."
    terms = extract_terms_from_text(text)
    assert {"asbest", "forbud", "strakspåbud", "samlehandel", "beløbsgrænse"}.issubset(terms)


def test_map_terms_to_parts_by_names():
    terms = {"forbud", "asbest", "samlehandel", "erhvervsejendom"}
    parts = [
        {"id": 1, "name": "Reaktion", "part": "generic_value"},
        {"id": 2, "name": "Problem", "part": "generic_value"},
        {"id": 3, "name": "Amount selection", "part": "generic_value"},
        {"id": 4, "name": "Ejendomstype", "part": "generic_value"},
    ]
    mappings = map_terms_to_parts(terms, parts, module_id=999)
    assert any(m.term == "forbud" and m.part_id == 1 for m in mappings)
    assert any(m.term == "asbest" and m.part_id == 2 for m in mappings)
    assert any(m.term == "samlehandel" and m.part_id == 3 for m in mappings)
    assert any(m.term == "erhvervsejendom" and m.part_id == 4 for m in mappings)


