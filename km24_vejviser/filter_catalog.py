"""
Filter Catalog - Intelligent håndtering af KM24 filter-data

Denne modul håndterer dynamisk hentning og caching af alle filter-typer
fra KM24 API'et, samt intelligent matching mellem emner og relevante filtre.
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio
from pathlib import Path

from .km24_client import get_km24_client, KM24APIClient
from .knowledge_base import extract_terms_from_text, map_terms_to_parts

logger = logging.getLogger(__name__)

@dataclass
class FilterRecommendation:
    """En anbefaling af et specifikt filter baseret på relevans."""
    filter_type: str
    values: List[str]
    relevance_score: float
    reasoning: str
    module_id: Optional[int] = None
    module_part_id: Optional[int] = None
    part_name: Optional[str] = None

@dataclass
class Municipality:
    """Repræsentation af en dansk kommune."""
    id: int
    name: str
    region: str
    population: Optional[int] = None
    area_km2: Optional[float] = None

@dataclass
class BranchCode:
    """Repræsentation af en branchekode."""
    code: str
    description: str
    category: str
    level: int  # 1-5 (hvor 1 er mest generel)

class FilterCatalog:
    """Intelligent katalog over alle KM24 filtre med caching og relevans-scoring."""
    
    def __init__(self):
        self.client: KM24APIClient = get_km24_client()
        
        # Cache for filter-data
        self._municipalities: Dict[int, Municipality] = {}
        self._branch_codes: Dict[str, BranchCode] = {}
        self._generic_values: Dict[int, List[Dict[str, Any]]] = {}
        self._web_sources: Dict[int, List[Dict[str, Any]]] = {}
        self._regions: Dict[int, Dict[str, Any]] = {}
        self._court_districts: Dict[int, Dict[str, Any]] = {}
        # Map from module title/id to parts and helpful reverse lookups
        self._module_id_by_title: Dict[str, int] = {}
        self._parts_by_module_id: Dict[int, List[Dict[str, Any]]] = {}
        # Knowledge extracted from modules/basic longDescription
        self._module_knowledge_base: Dict[str, Dict[str, Any]] = {}
        
        # Cache timestamps
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_duration = timedelta(hours=24)  # 24 timer cache
        
        # Relevans keywords
        self._relevans_keywords = {
            'byggeri': ['bygge', 'byggeri', 'construction', 'ejendom', 'bolig', 'hus', 'bygning'],
            'detailhandel': ['detail', 'retail', 'butik', 'shop', 'handel', 'salg'],
            'sundhed': ['sundhed', 'health', 'hospital', 'læge', 'medicin', 'sygdom'],
            'transport': ['transport', 'logistik', 'fragt', 'shipping', 'bil', 'tog'],
            'finans': ['bank', 'finans', 'penge', 'kredit', 'lån', 'investering'],
            'landbrug': ['landbrug', 'agriculture', 'bonde', 'mark', 'dyr', 'korn'],
            'energi': ['energi', 'energy', 'strøm', 'vind', 'sol', 'gas', 'olie'],
            'miljø': ['miljø', 'environment', 'klima', 'forurening', 'natur'],
            'uddannelse': ['skole', 'education', 'universitet', 'læring', 'undervisning'],
            'politik': ['politik', 'politisk', 'valg', 'parti', 'regering', 'folketing']
        }

        # Build internal knowledge base from cached modules/basic
        try:
            self._extract_knowledge_from_modules()
        except Exception as e:
            logger.warning(f"Kunne ikke opbygge intern videnbase fra modules/basic: {e}")
    
    async def load_all_filters(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Hent alle filter-data fra KM24 API."""
        logger.info("Indlæser alle filter-data fra KM24 API")
        
        # Also pre-load modules basic to build id/title map for module-specific parts
        tasks = [
            self._load_municipalities(force_refresh),
            self._load_branch_codes(force_refresh),
            self._load_regions(force_refresh),
            self._load_court_districts(force_refresh),
            self._load_modules_basic(force_refresh)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Indlæst {success_count}/{len(tasks)} filter-kategorier")
        
        return {
            "municipalities": len(self._municipalities),
            "branch_codes": len(self._branch_codes),
            "regions": len(self._regions),
            "court_districts": len(self._court_districts),
            "modules": len(self._module_id_by_title),
            "cache_age": self._get_cache_age()
        }

    def _extract_knowledge_from_modules(self) -> None:
        """Indlæs `_api_modules_basic.json` og udtræk modul-viden.

        Opbygger `self._module_knowledge_base` som et mapping fra modul-slug
        til en struktur med udtrukne nøgleord og part-relationer.
        """

        cache_path = Path(__file__).parent / "cache" / "_api_modules_basic.json"
        if not cache_path.exists():
            logger.info("Ingen lokal modules/basic cache fundet – skipper videnudtræk")
            return

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # Cache format fra klienten: {'cached_at': ..., 'data': {...}}
            data = cached.get("data") if isinstance(cached, dict) and "data" in cached else cached
            items = data.get("items", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"Kunne ikke læse modules/basic cache: {e}")
            return

        knowledge: Dict[str, Dict[str, Any]] = {}

        for item in items:
            try:
                module_id = int(item.get("id")) if item.get("id") is not None else None
            except Exception:
                module_id = None
            slug = str(item.get("slug", "")).strip()
            title = str(item.get("title", "")).strip()
            long_description = str(item.get("longDescription", ""))
            parts = item.get("parts", []) or []

            if not slug:
                # Fald tilbage til titel som nøgle hvis slug mangler
                slug = title.casefold().replace(" ", "-") if title else "module-unknown"

            terms = extract_terms_from_text(long_description)
            # Map til parts – vi gemmer part-id/type og foreslåede værdier
            mappings = map_terms_to_parts(terms, parts, module_id or -1)

            knowledge[slug] = {
                "module_id": module_id,
                "title": title,
                "terms": sorted(terms),
                "mappings": [
                    {
                        "term": m.term,
                        "part_id": m.part_id,
                        "part_name": m.part_name,
                        "part_type": m.part_type,
                        "suggested_values": m.suggested_values,
                        "confidence": m.confidence,
                        "evidence": m.evidence,
                    }
                    for m in mappings
                ],
            }

            # Også prime `_module_id_by_title` og `_parts_by_module_id` hvis muligt
            if module_id is not None:
                if title:
                    self._module_id_by_title[title] = module_id
                if parts:
                    self._parts_by_module_id[module_id] = parts

        self._module_knowledge_base = knowledge
        logger.info(f"Opbygget intern videnbase for {len(self._module_knowledge_base)} moduler")

    async def _load_modules_basic(self, force_refresh: bool = False) -> None:
        """Indlæs moduler (basic) og bygg opslags-tabeller for parts."""
        try:
            resp = await self.client.get_modules_basic(force_refresh)
            if resp.success and resp.data:
                items = resp.data.get('items', [])
                self._module_id_by_title = {item.get('title', ''): int(item.get('id')) for item in items if item.get('id') is not None}
                # Prime parts cache with whatever basic response includes
                for item in items:
                    mid = int(item.get('id')) if item.get('id') is not None else None
                    if mid is None:
                        continue
                    if 'parts' in item:
                        self._parts_by_module_id[mid] = item.get('parts', [])
        except Exception as e:
            logger.warning(f"Kunne ikke indlæse modules basic i filter catalog: {e}")
    
    async def _load_municipalities(self, force_refresh: bool = False) -> None:
        """Indlæs kommuner fra API."""
        if not force_refresh and self._is_cache_valid("municipalities"):
            return
        
        try:
            response = await self.client.get_municipalities(force_refresh)
            if response.success and response.data:
                self._municipalities.clear()
                for item in response.data.get('items', []):
                    municipality = Municipality(
                        id=item.get('id'),
                        name=item.get('name'),
                        region=item.get('region', 'Ukendt'),
                        population=item.get('population'),
                        area_km2=item.get('area_km2')
                    )
                    self._municipalities[municipality.id] = municipality
                
                self._cache_timestamps["municipalities"] = datetime.now()
                logger.info(f"Indlæst {len(self._municipalities)} kommuner")
            else:
                logger.warning(f"Kunne ikke indlæse kommuner: {response.error}")
                # Fallback til test-data
                self._load_test_municipalities()
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af kommuner: {e}")
            # Fallback til test-data
            self._load_test_municipalities()
    
    def _load_test_municipalities(self) -> None:
        """Indlæs test-kommuner når API ikke er tilgængelig."""
        test_municipalities = [
            Municipality(1, "Aarhus", "midtjylland", 273000, 468.0),
            Municipality(2, "København", "hovedstaden", 602000, 86.4),
            Municipality(3, "Odense", "syddanmark", 175000, 304.3),
            Municipality(4, "Aalborg", "nordjylland", 119000, 137.7),
            Municipality(5, "Esbjerg", "syddanmark", 115000, 742.5),
            Municipality(6, "Randers", "midtjylland", 62500, 800.1),
            Municipality(7, "Kolding", "syddanmark", 57000, 605.8),
            Municipality(8, "Horsens", "midtjylland", 58000, 520.0),
            Municipality(9, "Vejle", "syddanmark", 55000, 1066.3),
            Municipality(10, "Herning", "midtjylland", 50000, 1321.1),
        ]
        
        self._municipalities.clear()
        for muni in test_municipalities:
            self._municipalities[muni.id] = muni
        
        self._cache_timestamps["municipalities"] = datetime.now()
        logger.info(f"Indlæst {len(self._municipalities)} test-kommuner")
    
    async def _load_branch_codes(self, force_refresh: bool = False) -> None:
        """Indlæs branchekoder fra API."""
        if not force_refresh and self._is_cache_valid("branch_codes"):
            return
        
        try:
            response = await self.client.get_branch_codes_detailed(force_refresh)
            if response.success and response.data:
                self._branch_codes.clear()
                for item in response.data.get('items', []):
                    branch_code = BranchCode(
                        code=item.get('code'),
                        description=item.get('description'),
                        category=item.get('category', 'Ukendt'),
                        level=item.get('level', 1)
                    )
                    self._branch_codes[branch_code.code] = branch_code
                
                self._cache_timestamps["branch_codes"] = datetime.now()
                logger.info(f"Indlæst {len(self._branch_codes)} branchekoder")
            else:
                logger.warning(f"Kunne ikke indlæse branchekoder: {response.error}")
                # Fallback til test-data
                self._load_test_branch_codes()
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af branchekoder: {e}")
            # Fallback til test-data
            self._load_test_branch_codes()
    
    def _load_test_branch_codes(self) -> None:
        """Indlæs test-branchekoder når API ikke er tilgængelig."""
        test_branch_codes = [
            BranchCode("41.1", "Byggearbejde til boliger", "byggeri", 3),
            BranchCode("41.2", "Byggearbejde til erhvervsejendomme", "byggeri", 3),
            BranchCode("41.3", "Byggearbejde til veje og jernbaner", "byggeri", 3),
            BranchCode("42.1", "Anlægsarbejde til veje og jernbaner", "byggeri", 3),
            BranchCode("42.2", "Anlægsarbejde til forsyningsanlæg", "byggeri", 3),
            BranchCode("43.1", "Tagdækning", "byggeri", 4),
            BranchCode("43.2", "Murerarbejde", "byggeri", 4),
            BranchCode("43.3", "Installation af bygningsinstallationer", "byggeri", 4),
            BranchCode("68.2", "Udlejning og drift af ejendomme", "ejendom", 3),
            BranchCode("68.3", "Ejendomsadministration", "ejendom", 3),
            BranchCode("47.1", "Detailhandel med ikke-specialiseret handel", "detailhandel", 3),
            BranchCode("47.2", "Detailhandel med fødevarer", "detailhandel", 3),
            BranchCode("86.1", "Sundhedsydelser", "sundhed", 3),
            BranchCode("86.2", "Praktiserende lægers og tandlægers virksomhed", "sundhed", 3),
            BranchCode("49.1", "Jernbanetransport", "transport", 3),
            BranchCode("49.2", "Anden landtransport", "transport", 3),
            BranchCode("64.1", "Geldinstitut", "finans", 3),
            BranchCode("64.2", "Holdingvirksomhed", "finans", 3),
            BranchCode("01.1", "Dyrkning af enårige afgrøder", "landbrug", 3),
            BranchCode("01.2", "Dyrkning af flerårige afgrøder", "landbrug", 3),
        ]
        
        self._branch_codes.clear()
        for code in test_branch_codes:
            self._branch_codes[code.code] = code
        
        self._cache_timestamps["branch_codes"] = datetime.now()
        logger.info(f"Indlæst {len(self._branch_codes)} test-branchekoder")
    
    async def _load_regions(self, force_refresh: bool = False) -> None:
        """Indlæs regioner fra API."""
        if not force_refresh and self._is_cache_valid("regions"):
            return
        
        try:
            response = await self.client.get_regions(force_refresh)
            if response.success and response.data:
                self._regions.clear()
                for item in response.data.get('items', []):
                    self._regions[item.get('id')] = item
                
                self._cache_timestamps["regions"] = datetime.now()
                logger.info(f"Indlæst {len(self._regions)} regioner")
            else:
                logger.warning(f"Kunne ikke indlæse regioner: {response.error}")
                # Fallback til test-data
                self._load_test_regions()
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af regioner: {e}")
            # Fallback til test-data
            self._load_test_regions()
    
    def _load_test_regions(self) -> None:
        """Indlæs test-regioner når API ikke er tilgængelig."""
        test_regions = {
            1: {"id": 1, "name": "hovedstaden", "description": "Region Hovedstaden"},
            2: {"id": 2, "name": "midtjylland", "description": "Region Midtjylland"},
            3: {"id": 3, "name": "syddanmark", "description": "Region Syddanmark"},
            4: {"id": 4, "name": "nordjylland", "description": "Region Nordjylland"},
            5: {"id": 5, "name": "sjælland", "description": "Region Sjælland"},
        }
        
        self._regions.clear()
        self._regions.update(test_regions)
        
        self._cache_timestamps["regions"] = datetime.now()
        logger.info(f"Indlæst {len(self._regions)} test-regioner")
    
    async def _load_court_districts(self, force_refresh: bool = False) -> None:
        """Indlæs retskredse fra API."""
        if not force_refresh and self._is_cache_valid("court_districts"):
            return
        
        try:
            response = await self.client.get_court_districts(force_refresh)
            if response.success and response.data:
                self._court_districts.clear()
                for item in response.data.get('items', []):
                    self._court_districts[item.get('id')] = item
                
                self._cache_timestamps["court_districts"] = datetime.now()
                logger.info(f"Indlæst {len(self._court_districts)} retskredse")
            else:
                logger.warning(f"Kunne ikke indlæse retskredse: {response.error}")
                # Fallback til test-data
                self._load_test_court_districts()
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af retskredse: {e}")
            # Fallback til test-data
            self._load_test_court_districts()
    
    def _load_test_court_districts(self) -> None:
        """Indlæs test-retskredse når API ikke er tilgængelig."""
        test_court_districts = {
            1: {"id": 1, "name": "Københavns Byret", "region": "hovedstaden"},
            2: {"id": 2, "name": "Aarhus Byret", "region": "midtjylland"},
            3: {"id": 3, "name": "Odense Byret", "region": "syddanmark"},
            4: {"id": 4, "name": "Aalborg Byret", "region": "nordjylland"},
            5: {"id": 5, "name": "Esbjerg Byret", "region": "syddanmark"},
        }
        
        self._court_districts.clear()
        self._court_districts.update(test_court_districts)
        
        self._cache_timestamps["court_districts"] = datetime.now()
        logger.info(f"Indlæst {len(self._court_districts)} test-retskredse")
    
    async def load_module_specific_filters(self, module_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """Indlæs modulspecifikke filtre (generic_values og web_sources)."""
        logger.info(f"Indlæser modulspecifikke filtre for modul {module_id}")
        
        try:
            # Hent modul detaljer for at få parts
            module_response = await self.client.get_module_details(int(module_id), force_refresh)
            if not module_response.success:
                return {"error": f"Kunne ikke hente modul {module_id}"}
            
            module_data = module_response.data
            parts = module_data.get('parts', [])
            # Cache parts
            self._parts_by_module_id[int(module_id)] = parts
            
            tasks = []
            for part in parts:
                if part.get('part') == 'generic_value':
                    part_id = part.get('id')
                    tasks.append(self._load_generic_values(part_id, force_refresh))
                elif part.get('part') == 'web_source':
                    tasks.append(self._load_web_sources(module_id, force_refresh))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "module_id": module_id,
                "parts_loaded": len(parts),
                "generic_values_loaded": len([p for p in parts if p.get('part') == 'generic_value']),
                "web_sources_loaded": len([p for p in parts if p.get('part') == 'web_source'])
            }
            
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af modulspecifikke filtre: {e}")
            return {"error": str(e)}
    
    async def _load_generic_values(self, module_part_id: int, force_refresh: bool = False) -> None:
        """Indlæs generic_values for en specifik modulpart."""
        cache_key = f"generic_values_{module_part_id}"
        if not force_refresh and self._is_cache_valid(cache_key):
            return
        
        try:
            response = await self.client.get_generic_values(module_part_id, force_refresh)
            if response.success and response.data:
                self._generic_values[module_part_id] = response.data.get('items', [])
                self._cache_timestamps[cache_key] = datetime.now()
                logger.info(f"Indlæst {len(self._generic_values[module_part_id])} generic_values for part {module_part_id}")
            else:
                logger.warning(f"Kunne ikke indlæse generic_values for part {module_part_id}: {response.error}")
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af generic_values: {e}")
    
    async def _load_web_sources(self, module_id: int, force_refresh: bool = False) -> None:
        """Indlæs web_sources for et specifikt modul."""
        cache_key = f"web_sources_{module_id}"
        if not force_refresh and self._is_cache_valid(cache_key):
            return
        
        try:
            response = await self.client.get_web_sources(module_id, force_refresh)
            if response.success and response.data:
                self._web_sources[module_id] = response.data.get('items', [])
                self._cache_timestamps[cache_key] = datetime.now()
                logger.info(f"Indlæst {len(self._web_sources[module_id])} web_sources for modul {module_id}")
            else:
                logger.warning(f"Kunne ikke indlæse web_sources for modul {module_id}: {response.error}")
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af web_sources: {e}")
    
    def get_relevant_filters(self, goal: str, modules: List[str]) -> List[FilterRecommendation]:
        """Returner relevante filtre baseret på mål og moduler."""
        recommendations: List[FilterRecommendation] = []
        goal_lower = goal.lower()
        
        # 1) Klassiske heuristikker (kommuner/brancher/regioner)
        recommendations.extend(self._get_relevant_municipalities(goal_lower))
        recommendations.extend(self._get_relevant_branch_codes(goal_lower))
        recommendations.extend(self._get_relevant_regions(goal_lower))

        # 2) Hyper-relevant viden fra modules/basic longDescription
        try:
            # Uddrag termer fra målet (samme heuristik som knowledge_base)
            goal_terms = set(extract_terms_from_text(goal))

            # Begrænsning til valgte moduler (hvis angivet)
            selected_titles_lower = {m.lower() for m in modules} if modules else None

            for slug, entry in self._module_knowledge_base.items():
                title = (entry.get("title") or "").strip()
                if selected_titles_lower is not None and title.lower() not in selected_titles_lower:
                    continue

                module_id = entry.get("module_id")
                mappings = entry.get("mappings", [])
                for m in mappings:
                    term = m.get("term")
                    if term and term in goal_terms:
                        values = [v.capitalize() if isinstance(v, str) else v for v in m.get("suggested_values", []) or [term]]
                        part_name = m.get("part_name")
                        # FilterRecommendation expects a filter_type; vi bruger part-navn hvis kendt
                        filter_type = part_name if part_name else "module_specific"
                        # Saml anbefaling
                        recommendations.append(
                            FilterRecommendation(
                                filter_type=filter_type,
                                values=values,
                                relevance_score=0.95,
                                reasoning=f"Match mellem mål-termen '{term}' og {title} ({filter_type})",
                                module_id=module_id,
                                module_part_id=m.get("part_id"),
                                part_name=part_name,
                            )
                        )

            # 3) Konkrete lokale medie-forslag for udvalgte kommuner (heuristik)
            local_media = self._suggest_local_media(goal_lower)
            if local_media:
                recommendations.append(
                    FilterRecommendation(
                        filter_type="web_source",
                        values=local_media,
                        relevance_score=0.92,
                        reasoning="Lokale medier identificeret via geografiske nøgleord i målet",
                    )
                )

            # 4) Fallback: Kendte stærke modulspecifikke termer uden longDescription-match
            # Hvis 'asbest' nævnes, foreslå Problem: Asbest for Arbejdstilsyn
            if "asbest" in goal_terms:
                # Undgå dubletter hvis allerede foreslået
                already_has_asbest = any(
                    any((isinstance(v, str) and v.lower() == "asbest") for v in r.values)
                    for r in recommendations
                )
                if not already_has_asbest:
                    filter_type = "Problem"
                    module_id = self._get_module_id("Arbejdstilsyn")
                    recommendations.append(
                        FilterRecommendation(
                            filter_type=filter_type,
                            values=["Asbest"],
                            relevance_score=0.94,
                            reasoning="Mål nævner asbest → foreslå Problem: Asbest (Arbejdstilsyn)",
                            module_id=module_id,
                            part_name="Problem",
                        )
                    )

            # 5) Målrettet indhentning af specifikke værdier flyttet til async metode

        except Exception as e:
            logger.warning(f"Fejl i hyper-relevant videnudtræk: {e}")
        
        return sorted(recommendations, key=lambda x: x.relevance_score, reverse=True)

    async def get_relevant_filters_with_values(self, goal: str, modules: List[str]) -> List[FilterRecommendation]:
        """Udvidede anbefalinger med dynamisk indhentede, konkrete værdier for relevante parts.

        Starter med basisanbefalinger og supplerer med semantisk udvalgte `generic_values`
        fra KM24 API for de moduler der er angivet i `modules`.
        """
        base_recs = self.get_relevant_filters(goal, modules)
        goal_lower = (goal or "").lower()

        if not modules:
            return base_recs

        augmented: List[FilterRecommendation] = list(base_recs)
        for module_name in modules:
            module_id = self._get_module_id(module_name)
            if not module_id:
                continue
            try:
                await self.load_module_specific_filters(module_id)
            except Exception:
                pass
            parts = self._parts_by_module_id.get(module_id, [])
            for part in parts:
                if part.get('part') != 'generic_value':
                    continue
                pid = part.get('id')
                pname = part.get('name') or ''
                values = self._generic_values.get(pid, [])
                if not values:
                    try:
                        await self._load_generic_values(pid)
                        values = self._generic_values.get(pid, [])
                    except Exception:
                        values = []
                if not values:
                    continue
                scored: List[Tuple[float, str]] = []
                for it in values:
                    name = str(it.get('name', '')).strip()
                    desc = str(it.get('description', '') or '')
                    score = self._semantic_match_score(goal_lower, f"{name} {desc}")
                    if score > 0:
                        scored.append((score, name))
                if not scored:
                    continue
                scored.sort(key=lambda x: x[0], reverse=True)
                top_values = [n for _, n in scored[:5]]
                filter_type = self._normalized_filter_type_from_part_name(pname) or (pname or "module_specific").strip().lower()
                augmented.append(
                    FilterRecommendation(
                        filter_type=filter_type,
                        values=top_values,
                        relevance_score=0.96,
                        reasoning=f"Semantisk match mellem mål og {pname} i {module_name}",
                        module_id=module_id,
                        module_part_id=pid,
                        part_name=pname,
                    )
                )

        return sorted(augmented, key=lambda x: x.relevance_score, reverse=True)

    def _suggest_local_media(self, goal_lower: str) -> List[str]:
        """Returnér konkrete lokale medier for udvalgte områder (heuristik)."""
        # Denne kan udvides gradvist; starter med 'Esbjerg'
        if "esbjerg" in goal_lower:
            return ["JydskeVestkysten", "Esbjerg Ugeavis"]
        return []
    
    def _get_relevant_municipalities(self, goal: str) -> List[FilterRecommendation]:
        """Find relevante kommuner baseret på mål."""
        recommendations = []
        
        # Keywords for forskellige regioner
        region_keywords = {
            'københavn': ['københavn', 'copenhagen', 'hovedstaden', 'storkøbenhavn'],
            'aarhus': ['aarhus', 'jylland', 'midtjylland', 'østjylland'],
            'odense': ['odense', 'fyn', 'sydfyn'],
            'aalborg': ['aalborg', 'nordjylland', 'nordjylland'],
            'vestjylland': ['vestjylland', 'esbjerg', 'herning', 'holstebro', 'struer'],
            'østjylland': ['østjylland', 'randers', 'horsens', 'vejle', 'kolding'],
            'sydjylland': ['sydjylland', 'sønderborg', 'aabenraa', 'tønder']
        }
        
        for region, keywords in region_keywords.items():
            if any(keyword in goal for keyword in keywords):
                # Find kommuner i denne region
                region_municipalities = [
                    m for m in self._municipalities.values() 
                    if region in m.region.lower() or any(keyword in m.name.lower() for keyword in keywords)
                ]
                
                if region_municipalities:
                    recommendations.append(FilterRecommendation(
                        filter_type="municipality",
                        values=[m.name for m in region_municipalities[:5]],  # Top 5
                        relevance_score=0.9,
                        reasoning=f"Relevante kommuner i {region}-regionen baseret på mål"
                    ))
        
        return recommendations
    
    def _get_relevant_branch_codes(self, goal: str) -> List[FilterRecommendation]:
        """Find relevante branchekoder baseret på mål."""
        recommendations = []
        
        for category, keywords in self._relevans_keywords.items():
            if any(keyword in goal for keyword in keywords):
                # Find branchekoder i denne kategori
                relevant_codes = [
                    bc for bc in self._branch_codes.values()
                    if any(keyword in bc.description.lower() for keyword in keywords)
                ]
                
                if relevant_codes:
                    # Gruppér efter kategori og vælg de mest relevante
                    codes_by_category = {}
                    for code in relevant_codes:
                        if code.category not in codes_by_category:
                            codes_by_category[code.category] = []
                        codes_by_category[code.category].append(code)
                    
                    for category_name, codes in codes_by_category.items():
                        # Vælg de mest specifikke koder (højeste level)
                        codes.sort(key=lambda x: x.level, reverse=True)
                        selected_codes = [c.code for c in codes[:3]]  # Top 3
                        
                        recommendations.append(FilterRecommendation(
                            filter_type="industry",
                            values=selected_codes,
                            relevance_score=0.85,
                            reasoning=f"Relevante branchekoder for {category_name} baseret på mål"
                        ))
        
        return recommendations
    
    def _get_relevant_regions(self, goal: str) -> List[FilterRecommendation]:
        """Find relevante regioner baseret på mål."""
        recommendations = []
        
        region_keywords = {
            'hovedstaden': ['københavn', 'hovedstaden', 'storkøbenhavn'],
            'midtjylland': ['aarhus', 'midtjylland', 'østjylland'],
            'syddanmark': ['fyn', 'sydfyn', 'odense', 'syddanmark'],
            'nordjylland': ['aalborg', 'nordjylland'],
            'sjælland': ['sjælland', 'roskilde', 'køge']
        }
        
        for region_name, keywords in region_keywords.items():
            if any(keyword in goal for keyword in keywords):
                recommendations.append(FilterRecommendation(
                    filter_type="region",
                    values=[region_name],
                    relevance_score=0.8,
                    reasoning=f"Relevant region baseret på geografiske keywords"
                ))
        
        return recommendations
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Tjek om cache er gyldig."""
        if cache_key not in self._cache_timestamps:
            return False
        
        cache_age = datetime.now() - self._cache_timestamps[cache_key]
        return cache_age < self._cache_duration
    
    def _get_cache_age(self) -> Optional[str]:
        """Hent alder af ældste cache."""
        if not self._cache_timestamps:
            return None
        
        oldest_timestamp = min(self._cache_timestamps.values())
        age = datetime.now() - oldest_timestamp
        return str(age)
    
    def get_municipalities_by_region(self, region: str) -> List[Municipality]:
        """Hent kommuner i en specifik region."""
        return [m for m in self._municipalities.values() if region.lower() in m.region.lower()]
    
    def get_branch_codes_by_category(self, category: str) -> List[BranchCode]:
        """Hent branchekoder i en specifik kategori."""
        return [bc for bc in self._branch_codes.values() if category.lower() in bc.category.lower()]
    
    def get_generic_values_for_module_part(self, module_part_id: int) -> List[Dict[str, Any]]:
        """Hent generic_values for en specifik modulpart."""
        return self._generic_values.get(module_part_id, [])
    
    def get_web_sources_for_module(self, module_id: int) -> List[Dict[str, Any]]:
        """Hent web_sources for et specifikt modul."""
        return self._web_sources.get(module_id, [])

    async def get_module_specific_recommendations(self, goal: str, module_name: str) -> List[FilterRecommendation]:
        """Hent modulspecifikke filter-anbefalinger."""
        recommendations = []
        
        # Indlæs modulspecifikke filtre hvis nødvendigt
        module_id = self._get_module_id(module_name)
        if module_id:
            await self.load_module_specific_filters(module_id)
            
            # Hent generic_values for modulet (med semantisk scoring)
            # Resolve all generic_value lists from cached module parts
            generic_parts = [p for p in self._parts_by_module_id.get(module_id, []) if p.get('part') == 'generic_value']
            generic_value_part_ids = [p.get('id') for p in generic_parts]
            goal_lower = (goal or "").lower()
            for part in generic_parts:
                pid = part.get('id')
                pname = part.get('name') or ''
                items = self._generic_values.get(pid, [])
                if not items:
                    continue
                # Semantisk scoring af hver værdi ud fra navn/beskrivelse
                scored: List[Tuple[float, str]] = []
                for it in items:
                    name = str(it.get('name', '')).strip()
                    desc = str(it.get('description', '') or '')
                    score = self._semantic_match_score(goal_lower, f"{name} {desc}")
                    if score > 0:
                        scored.append((score, name))
                # Hvis intet scorede positivt, vælg nogle repræsentative defaults (top N alfabetisk)
                selected: List[str] = []
                if scored:
                    scored.sort(key=lambda x: x[0], reverse=True)
                    selected = [n for _, n in scored[:5]]
                else:
                    selected = [str(it.get('name')) for it in items[:3] if it.get('name')]
                if selected:
                    filter_type = self._normalized_filter_type_from_part_name(pname)
                recommendations.append(FilterRecommendation(
                        filter_type=filter_type or "module_specific",
                        values=selected,
                        relevance_score=0.9 if scored else 0.7,
                        reasoning=f"Udvalgt fra {pname} for {module_name}",
                    module_id=module_id,
                        part_name=pname
                ))
            
            # Hent web_sources for modulet
            web_sources = self.get_web_sources_for_module(module_id)
            if web_sources:
                recommendations.append(FilterRecommendation(
                    filter_type="web_sources",
                    values=[source.get('name', '') for source in web_sources[:5]],  # Top 5 kilder
                    relevance_score=0.85,
                    reasoning=f"Webkilder for {module_name}",
                    module_id=module_id
                ))
        
        # Heuristics for specific modules when goal suggests severe violations
        g = goal.lower()
        if 'arbejdstilsyn' in module_name.lower() and any(k in g for k in ['alvorlig', 'alvorlige', 'overtrædelse', 'ulovlig', 'kritik']):
            recommendations.append(FilterRecommendation(
                filter_type="module_specific",
                values=["Forbud", "Strakspåbud"],
                relevance_score=0.95,
                reasoning="Ved alvorlige overtrædelser anbefales Reaktion: Forbud/Strakspåbud",
                part_name="Reaktion"
            ))
            if 'asbest' in g:
                recommendations.append(FilterRecommendation(
                    filter_type="module_specific",
                    values=["Asbest"],
                    relevance_score=0.92,
                    reasoning="Asbest relaterede sager: Problem = Asbest",
                    part_name="Problem"
                ))

        if 'tinglysning' in module_name.lower() and any(k in g for k in ['ejendom', 'ejendomshandel', 'handel']):
            recommendations.append(FilterRecommendation(
                filter_type="module_specific",
                values=["erhvervsejendom", "landbrugsejendom"],
                relevance_score=0.9,
                reasoning="Tinglysning: ejendomstyper via generic_value",
                part_name="Ejendomstype"
            ))

        return recommendations

    def _normalized_filter_type_from_part_name(self, part_name: Optional[str]) -> Optional[str]:
        if not part_name:
            return None
        n = part_name.lower()
        # Common normalizations across modules
        if 'gernings' in n or 'crime' in n:
            return 'crime_codes'
        if 'branche' in n or 'industry' in n:
            return 'branch_codes'
        if 'problem' in n:
            return 'problem'
        if 'reaktion' in n or 'reaction' in n:
            return 'reaction'
        if 'ejendom' in n or 'property' in n:
            return 'property_types'
        return None

    def _semantic_match_score(self, goal_lower: str, text: str) -> float:
        """Simpel semantisk scoring baseret på domæne-ordlister og substring-match."""
        if not goal_lower or not text:
            return 0.0
        t = text.lower()
        score = 0.0
        # Domain term buckets
        buckets = {
            'corruption': ['korruption', 'bestikkelse', 'bestikk', 'habilitet', 'inhabil', 'smørelse'],
            'fraud': ['bedrageri', 'svig', 'falsk', 'økonomisk kriminalitet'],
            'environment': ['miljø', 'forurening', 'udledning', 'tilladelse', 'asbest', 'klima'],
            'labour': ['arbejdstilsyn', 'forbud', 'strakspåbud', 'ulykke', 'sikkerhed'],
            'construction': ['bygge', 'byggeri', 'entrepren', 'udvikling', 'ejendom'],
            'procurement': ['udbud', 'kontrakt', 'tildeling', 'offentlig'],
            'media': ['medie', 'avis', 'ugeavis', 'nyhed']
        }
        for key, terms in buckets.items():
            bucket_hits = 0
            for term in terms:
                if term in goal_lower and term in t:
                    bucket_hits += 1
            if bucket_hits:
                # Weight by number of overlapping terms
                score += 0.4 + 0.2 * min(bucket_hits, 3)
        # Fallback: direct keyword overlap by tokens
        for token in set(goal_lower.split()):
            if len(token) > 4 and token in t:
                score += 0.1
        return score
    
    def _get_module_id(self, module_name: str) -> Optional[int]:
        """Hent modul ID baseret på modulnavn."""
        if self._module_id_by_title:
            # Direct title match first
            mid = self._module_id_by_title.get(module_name)
            if mid is not None:
                return mid
            # Try a case-insensitive match
            for title, mid in self._module_id_by_title.items():
                if title.lower() == module_name.lower():
                    return mid
        return None
    
    def get_generic_values_for_module(self, module_name: str) -> List[str]:
        """Deprecated: Brug get_module_specific_recommendations i stedet."""
        return []

# Global filter catalog instance
_filter_catalog: Optional[FilterCatalog] = None

def get_filter_catalog() -> FilterCatalog:
    """Få global filter catalog instance."""
    global _filter_catalog
    if _filter_catalog is None:
        _filter_catalog = FilterCatalog()
    return _filter_catalog
