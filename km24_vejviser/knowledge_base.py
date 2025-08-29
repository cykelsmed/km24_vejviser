"""
Knowledge Base - Modul-specifik viden udledt af longDescription

Formål:
- Ekstrahér domænespecifikke nøgleord og begreber fra hvert moduls
  `longDescription` i KM24's modules/basic-data.
- Byg strukturerede modul-profiler, der kan bruges til at foreslå
  konkrete filtre i andre komponenter (fx FilterCatalog og main.py).

Denne modul implementerer udelukkende fase 1 (Knowledge Extraction):
- Parser `longDescription`
- Uddrager nøglebegreber via simple, deterministiske heuristikker
- Forsøger at mappe begreber til moduldele (parts) baseret på delnavne

Bemærk: Selve indlæsning af konkrete `generic_values` for parts er ikke
et krav i fase 1. Vi matcher primært mod parts ved navn og type.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .km24_client import KM24APIClient, get_km24_client


logger = logging.getLogger(__name__)


@dataclass
class ModulePartMapping:
    """Mapping mellem et udledt begreb og en modul-del (part).

    Attributes
    ----------
    module_id : int
        ID for modulet, hvor part'en hører til.
    part_id : Optional[int]
        ID for part'en, hvis tilgængelig i modules/basic.
    part_name : Optional[str]
        Vist navn for part'en (fx "Reaktion", "Problem").
    part_type : Optional[str]
        KM24 part-type (fx "generic_value", "web_source").
    suggested_values : List[str]
        Konkrete værdier foreslået ud fra begrebet. I fase 1 ofte tom.
    confidence : float
        Heuristisk sikkerhed (0.0-1.0) for dette match.
    evidence : str
        Kort begrundelse/konkordans for hvorfor mapping er valgt.
    term : str
        Det udledte begreb, som mappes.
    """

    module_id: int
    part_id: Optional[int]
    part_name: Optional[str]
    part_type: Optional[str]
    suggested_values: List[str]
    confidence: float
    evidence: str
    term: str


@dataclass
class ModuleProfile:
    """Struktureret profil for et modul baseret på longDescription.

    Attributes
    ----------
    module_id : int
        Modul ID.
    title : str
        Modul titel.
    long_description : str
        Rå longDescription-tekst fra API'et (kan være tom).
    extracted_terms : Set[str]
        Normaliserede begreber udtrukket fra `long_description`.
    term_mappings : List[ModulePartMapping]
        Mapping-resultater for `extracted_terms` mod moduldele.
    summary : Optional[str]
        Eventuel kort opsummering (for fremtidig brug).
    """

    module_id: int
    title: str
    long_description: str
    extracted_terms: Set[str] = field(default_factory=set)
    term_mappings: List[ModulePartMapping] = field(default_factory=list)
    summary: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"ModuleProfile(module_id={self.module_id}, title={self.title!r}, "
            f"terms={sorted(self.extracted_terms)[:6]}...)"
        )


class KnowledgeBase:
    """Intern videnbase opbygget fra modules/basic.

    Denne klasse indlæser `modules/basic` (fra cache hvis muligt),
    udtrækker begreber fra `longDescription` og forsøger at mappe dem
    til moduldele (parts) for senere anvendelse i FilterCatalog og main.py.
    """

    def __init__(self, client: Optional[KM24APIClient] = None):
        self.client: KM24APIClient = client or get_km24_client()
        self._profiles_by_id: Dict[int, ModuleProfile] = {}
        self._profiles_by_title_lower: Dict[str, ModuleProfile] = {}

    async def load(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Indlæs modules/basic og byg profiler.

        Parameters
        ----------
        force_refresh : bool
            Hvis True, ignorer caches og forsøg at hente friskt data.

        Returns
        -------
        Dict[str, Any]
            Status for indlæsningen, inkl. antal profiler.
        """

        resp = await self.client.get_modules_basic(force_refresh)
        if not resp.success or not resp.data:
            # Selv hvis API fejler (fx manglende API-key), prøver vi at
            # læse fra cache via klientens mekanismer. Når klienten ikke
            # kan returnere data her, logger vi og returnerer tom status.
            logger.warning(f"Kunne ikke indlæse modules/basic: {resp.error}")
            return {"success": False, "profiles": 0, "error": resp.error}

        items: List[Dict[str, Any]] = resp.data.get("items", [])
        built_profiles: List[ModuleProfile] = []

        for item in items:
            try:
                module_id = int(item.get("id"))
            except Exception:
                # Spring defekte entries over
                continue

            title = str(item.get("title", "")).strip()
            long_description = str(item.get("longDescription", ""))
            parts = item.get("parts", []) or []

            terms = extract_terms_from_text(long_description)
            mappings = map_terms_to_parts(terms, parts, module_id)

            profile = ModuleProfile(
                module_id=module_id,
                title=title,
                long_description=long_description,
                extracted_terms=terms,
                term_mappings=mappings,
            )

            built_profiles.append(profile)
            self._profiles_by_id[module_id] = profile
            if title:
                self._profiles_by_title_lower[title.lower()] = profile

        logger.info(f"Bygget {len(built_profiles)} modul-profiler fra modules/basic")
        return {"success": True, "profiles": len(built_profiles)}

    def get_profile_by_id(self, module_id: int) -> Optional[ModuleProfile]:
        """Hent modulprofil via modul-ID."""

        return self._profiles_by_id.get(module_id)

    def get_profile_by_title(self, module_title: str) -> Optional[ModuleProfile]:
        """Hent modulprofil via modul-titel (case-insensitive)."""

        if not module_title:
            return None
        return self._profiles_by_title_lower.get(module_title.lower())

    def all_profiles(self) -> List[ModuleProfile]:
        """Returner alle kendte profiler."""

        return list(self._profiles_by_id.values())


def extract_terms_from_text(text: str) -> Set[str]:
    """Uddrag normaliserede begreber fra en beskrivelsestekst.

    Heuristik:
    - Casefold hele teksten
    - Se efter kendte domæne-termer via regex (kræver eksakte ordstammer)
    - Returnér et sæt af normaliserede tokens (små bogstaver)

    Parameters
    ----------
    text : str
        Kildetekst (longDescription).

    Returns
    -------
    Set[str]
        Sæt af detekterede begreber.
    """

    if not text:
        return set()

    haystack = text.casefold()

    # Kendte nøglebegreber (kan udvides løbende). Nøglen er det normaliserede
    # term; værdien er en liste af regex'er, der matcher ordvarianter.
    term_patterns: Dict[str, Iterable[str]] = {
        # Arbejdstilsynet / reaktioner / problemer
        "forbud": [r"\bforbud\b"],
        "strakspåbud": [r"\bstrakspåbud\b"],
        "påbud": [r"\bpåbud\b"],
        "vejledning": [r"\bvejledning\b"],
        "asbest": [r"\basbest\b"],

        # Tinglysning / ejendom
        # Samlehandel (singular/plural/stem)
        "samlehandel": [
            r"\bsamlehandel\b",
            r"\bsamlehandl\w*",  # matcher 'samlehandler', 'samlehandlen' mv.
        ],
        "beløbsgrænse": [r"\bbeløb(s)?græn(se|ser)\b", r"\bbeløbsgrænse\w*"],
        "erhvervsejendom": [r"\berhvervsejendom\w*"],
        "landbrugsejendom": [r"\blandbrugsejendom\w*"],

        # Medier / kilder
        "lokale medier": [r"\blokale medier\b", r"\blokale\b.*\bmedier\b"],
        "landsdækkende medier": [r"\blandsdækkende medier\b"],
    }

    detected: Set[str] = set()
    for term, patterns in term_patterns.items():
        for pattern in patterns:
            try:
                if re.search(pattern, haystack):
                    detected.add(term)
                    break
            except re.error:
                # Ignorér defekte patterns
                continue

    return detected


def map_terms_to_parts(
    terms: Set[str], parts: List[Dict[str, Any]], module_id: int
) -> List[ModulePartMapping]:
    """Map udledte begreber til moduldele (parts) baseret på delnavne.

    Strategi (fase 1):
    - Vi bruger primært delnavne (fx "Reaktion", "Problem", "Samlehandel")
      og part-typen (fx "generic_value").
    - Vi opbygger simple regler for, hvilke part-navne der passer til
      bestemte begreber. Hvis en part matcher, oprettes en mapping med
      moderat confidence.

    Parameters
    ----------
    terms : Set[str]
        Udledte begreber.
    parts : List[Dict[str, Any]]
        Modulets dele fra modules/basic.
    module_id : int
        ID for modulet.

    Returns
    -------
    List[ModulePartMapping]
        Mappings fra begreb til part.
    """

    mappings: List[ModulePartMapping] = []
    if not parts or not terms:
        return mappings

    # Normalisér part metadata for nem sammenligning
    normalized_parts: List[Tuple[int, str, str]] = []  # (id, name_lower, part_type)
    for part in parts:
        pid = part.get("id")
        try:
            part_id = int(pid) if pid is not None else None
        except Exception:
            part_id = None
        name = str(part.get("name", ""))
        part_type = str(part.get("part", ""))
        normalized_parts.append((part_id, name.casefold(), part_type))

    def find_part_by_name_keywords(keywords: Iterable[str]) -> Optional[Tuple[int, str, str]]:
        for part_id, name_lower, part_type in normalized_parts:
            if any(kw in name_lower for kw in keywords):
                return part_id, name_lower, part_type
        return None

    for term in terms:
        term_lower = term.casefold()
        if term_lower in {"forbud", "strakspåbud", "påbud", "vejledning"}:
            candidate = find_part_by_name_keywords(["reaktion"])  # fx "Reaktion"
            if candidate:
                part_id, name_lower, part_type = candidate
                mappings.append(
                    ModulePartMapping(
                        module_id=module_id,
                        part_id=part_id,
                        part_name=name_lower,
                        part_type=part_type,
                        suggested_values=[term],
                        confidence=0.8,
                        evidence="Begrebet matcher Reaktion-parten",
                        term=term,
                    )
                )
                continue

        if term_lower in {"asbest"}:
            candidate = find_part_by_name_keywords(["problem", "emne", "kategori"])
            if candidate:
                part_id, name_lower, part_type = candidate
                mappings.append(
                    ModulePartMapping(
                        module_id=module_id,
                        part_id=part_id,
                        part_name=name_lower,
                        part_type=part_type,
                        suggested_values=[term],
                        confidence=0.8,
                        evidence="Begrebet matcher Problem/Emne-part",
                        term=term,
                    )
                )
                continue

        if term_lower in {"samlehandel", "beløbsgrænse"}:
            candidate = find_part_by_name_keywords(["samlehandel", "beløb", "amount"])  # dækker DK/EN
            if candidate:
                part_id, name_lower, part_type = candidate
                mappings.append(
                    ModulePartMapping(
                        module_id=module_id,
                        part_id=part_id,
                        part_name=name_lower,
                        part_type=part_type,
                        suggested_values=[term],
                        confidence=0.75,
                        evidence="Begrebet matcher Samlehandel/Beløb-part",
                        term=term,
                    )
                )
                continue

        if term_lower in {"erhvervsejendom", "landbrugsejendom"}:
            candidate = find_part_by_name_keywords(["ejendom", "property"])  # dækker DK/EN
            if candidate:
                part_id, name_lower, part_type = candidate
                mappings.append(
                    ModulePartMapping(
                        module_id=module_id,
                        part_id=part_id,
                        part_name=name_lower,
                        part_type=part_type,
                        suggested_values=[term],
                        confidence=0.7,
                        evidence="Begrebet matcher Ejendomstype-part",
                        term=term,
                    )
                )
                continue

        # Medie-relaterede termer kan pege på web_source parts
        if term_lower in {"lokale medier", "landsdækkende medier"}:
            candidate = find_part_by_name_keywords(["kilde", "medie", "web", "source"])  # dækker DK/EN
            if candidate:
                part_id, name_lower, part_type = candidate
                mappings.append(
                    ModulePartMapping(
                        module_id=module_id,
                        part_id=part_id,
                        part_name=name_lower,
                        part_type=part_type,
                        suggested_values=[],
                        confidence=0.6,
                        evidence="Begrebet matcher web/medie-kilde part",
                        term=term,
                    )
                )
                continue

    return mappings


# Global singleton ligesom i øvrige moduler
_knowledge_base: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    """Returner global KnowledgeBase-instans."""

    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base


