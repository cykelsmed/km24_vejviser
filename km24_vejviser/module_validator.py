"""
Module Validator for KM24 API integration.

Validerer AI-foreslåede moduler mod faktiske KM24 moduler
og giver intelligente forslag til alternative moduler.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from .km24_client import get_km24_client, KM24APIResponse

logger = logging.getLogger(__name__)

@dataclass
class ModuleMatch:
    """Repræsenterer et match mellem foreslået og faktisk modul."""
    module_title: str
    module_slug: str
    description: str
    match_reason: str
    confidence: float  # 0.0 til 1.0

@dataclass
class ValidationResult:
    """Resultat af modul-validering."""
    valid_modules: List[str]
    invalid_modules: List[str]
    suggestions: List[ModuleMatch]
    total_checked: int

@dataclass
class EnhancedModuleCard:
    """Udvidet modul-information med API metadata."""
    title: str
    slug: str
    emoji: str
    color: str
    short_description: str
    long_description: str
    data_frequency: str
    available_filters: List[Dict[str, Any]]
    requires_source_selection: bool
    total_filters: int
    complexity_level: str

@dataclass
class FilterRecommendation:
    """Smart anbefalinger for filter-rækkefølge."""
    optimal_sequence: List[str]
    efficiency_tips: List[str]
    complexity_warning: Optional[str]

@dataclass
class ComplexityAnalysis:
    """Analyse af forventet kompleksitet og hit-mængde."""
    estimated_hits: str
    filter_efficiency: str
    notification_recommendation: Dict[str, str]
    optimization_suggestions: List[str]

class ModuleValidator:
    """Validerer moduler mod KM24 API og giver intelligente forslag."""
    
    def __init__(self):
        self.client = get_km24_client()
        self._modules_cache: Optional[List[Dict[str, Any]]] = None
        self._module_titles: Optional[List[str]] = None
        self._module_slugs: Optional[List[str]] = None
        # Cache for detailed module parts by module id
        self._module_parts_by_id: Dict[int, List[Dict[str, Any]]] = {}
        self._module_id_by_title: Dict[str, int] = {}
    
    async def _load_modules(self) -> bool:
        """Indlæs alle KM24 moduler fra API."""
        try:
            result = await self.client.get_modules_basic()
            if result.success and result.data:
                self._modules_cache = result.data.get('items', [])
                self._module_titles = [mod.get('title', '') for mod in self._modules_cache]
                self._module_slugs = [mod.get('slug', '') for mod in self._modules_cache]
                self._module_id_by_title = {mod.get('title', ''): int(mod.get('id')) for mod in self._modules_cache if mod.get('id') is not None}
                logger.info(f"Indlæst {len(self._modules_cache)} moduler fra KM24 API")
                return True
            else:
                logger.warning(f"Kunne ikke indlæse moduler: {result.error}")
                return False
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af moduler: {e}", exc_info=True)
            return False

    async def _ensure_module_parts(self, module_id: int) -> List[Dict[str, Any]]:
        """Sørg for at parts for et modul er cachet og returnér dem.

        Args:
            module_id: ID for modulet

        Returns:
            Liste af parts-objekter fra API (kan være tom liste)
        """
        if module_id in self._module_parts_by_id:
            return self._module_parts_by_id[module_id]
        try:
            details = await self.client.get_module_details(int(module_id))
            if details.success and details.data:
                parts = details.data.get('parts', [])
                self._module_parts_by_id[module_id] = parts
                return parts
            logger.warning(f"Kunne ikke hente parts for modul {module_id}: {details.error}")
            self._module_parts_by_id[module_id] = []
            return []
        except Exception as e:
            logger.error(f"Fejl ved hentning af module details for {module_id}: {e}")
            self._module_parts_by_id[module_id] = []
            return []

    async def get_module_parts_by_title(self, module_title: str) -> List[Dict[str, Any]]:
        """Hent parts for modulnavn via cache/API."""
        if not await self._load_modules():
            return []
        module_id = self._module_id_by_title.get(module_title)
        if module_id is None:
            return []
        return await self._ensure_module_parts(module_id)

    @staticmethod
    def _map_friendly_filter_key_to_part_type(key: str) -> Optional[str]:
        """Map danske filter-nøgler til KM24 part-typer."""
        k = key.lower().strip()
        if k in {"geografi", "kommune", "kommuner"}:
            return "municipality"
        if k in {"branche", "branchekode", "branchekoder"}:
            return "industry"
        if any(term in k for term in ["beløb", "beløbsgrænse", "amount", "kontraktværdi", "ejendomshandel"]):
            return "amount_selection"
        if k in {"virksomhed", "company", "cvr"}:
            return "company"
        # Domain specific generic_value groups (e.g., Arbejdstilsyn)
        # Will be validated by comparing against generic_value part names
        return None

    async def validate_filters_against_parts(self, module_title: str, filters: Dict[str, Any]) -> List[str]:
        """Valider at angivne filtre matcher faktiske parts for modulet.

        Returnerer advarsler for filtre, der ikke kan understøttes af modulet.
        """
        warnings: List[str] = []
        if not filters:
            return warnings

        parts = await self.get_module_parts_by_title(module_title)
        if not parts:
            return warnings  # Kan ikke validere uden parts

        part_types = {p.get('part'): p for p in parts}
        generic_names = {p.get('name', '').lower(): p for p in parts if p.get('part') == 'generic_value'}
        has_web_source = 'web_source' in part_types

        for key in list(filters.keys()):
            mapped = self._map_friendly_filter_key_to_part_type(key)
            if mapped:
                if mapped not in part_types:
                    warnings.append(f"Modul '{module_title}' understøtter ikke filter '{key}' ({mapped})")
                continue
            # Check domain-specific generic_value names e.g. 'reaktion', 'problem'
            if key.lower() in generic_names:
                continue
            # Unknown key not directly mappable; if module has no matching part names, warn
            if key.lower() not in {"periode", "hitlogik", "region"}:
                warnings.append(f"Filter-nøgle '{key}' matcher ingen kendt part for modulet '{module_title}'")

        # Validate that web source modules include sources in filters/selection handled elsewhere
        if has_web_source and not filters.get('source_selection'):
            # Not a direct filter field, but provide a guiding warning here
            warnings.append(f"Webkilde-modul '{module_title}' kræver 'source_selection' (kildevalg)")

        return warnings
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Beregn lighed mellem to tekster."""
        if not text1 or not text2:
            return 0.0
        
        # Normaliser tekster
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()
        
        # Eksakt match
        if text1 == text2:
            return 1.0
        
        # Sequence matcher
        similarity = SequenceMatcher(None, text1, text2).ratio()
        
        # Bonus for delvise matches
        if text1 in text2 or text2 in text1:
            similarity += 0.2
        
        return min(similarity, 1.0)
    
    def _find_best_matches(self, query: str, limit: int = 3) -> List[ModuleMatch]:
        """Find de bedste matches for et modul-navn."""
        if not self._modules_cache:
            return []
        
        matches = []
        query_lower = query.lower().strip()
        
        for module in self._modules_cache:
            title = module.get('title', '')
            slug = module.get('slug', '')
            description = module.get('description', '')
            
            # Beregn lighed med titel
            title_similarity = self._calculate_similarity(query, title)
            
            # Beregn lighed med slug
            slug_similarity = self._calculate_similarity(query, slug)
            
            # Tag den højeste lighed
            similarity = max(title_similarity, slug_similarity)
            
            if similarity > 0.3:  # Minimum tærskel
                match_reason = self._generate_match_reason(query, title, slug, similarity)
                matches.append(ModuleMatch(
                    module_title=title,
                    module_slug=slug,
                    description=description,
                    match_reason=match_reason,
                    confidence=similarity
                ))
        
        # Sortér efter confidence og tag top matches
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches[:limit]
    
    def _generate_match_reason(self, query: str, title: str, slug: str, similarity: float) -> str:
        """Generer en forklaring på hvorfor modulet matcher."""
        query_lower = query.lower()
        title_lower = title.lower()
        slug_lower = slug.lower()
        
        # Kreative begrundelser baseret på modul type og funktionalitet
        if "udbud" in query_lower and "udbud" in title_lower:
            return "Relevant for at følge offentlige kontrakter og udbudsprocesser"
        elif "konkurs" in query_lower and "status" in title_lower:
            return "Relevant for at følge om firmaerne går konkurs eller skifter status"
        elif "miljø" in query_lower and "miljø" in title_lower:
            return "Relevant for at overvåge miljøsager og -godkendelser"
        elif "politik" in query_lower and "lokalpolitik" in title_lower:
            return "Relevant for at følge kommunale beslutninger og politiske processer"
        elif "medier" in query_lower and "medier" in title_lower:
            return "Relevant for at overvåge medieomtale og nyhedsdækning"
        elif "virksomhed" in query_lower and "registrering" in title_lower:
            return "Relevant for at følge nye virksomhedsregistreringer"
        elif "ejendom" in query_lower and "tinglysning" in title_lower:
            return "Relevant for at overvåge ejendomshandler og tinglysninger"
        elif "arbejde" in query_lower and "arbejdstilsyn" in title_lower:
            return "Relevant for at følge arbejdsmiljøkontrol og kritik"
        elif "finans" in query_lower and "finanstilsynet" in title_lower:
            return "Relevant for at overvåge finansiel regulering og tilsyn"
        elif similarity >= 0.9:
            return "Næsten eksakt match med modulnavn"
        elif similarity >= 0.7:
            return "Høj lighed med modulnavn og funktionalitet"
        elif query_lower in title_lower or query_lower in slug_lower:
            return f"Modulnavn indeholder søgeterm '{query}'"
        elif title_lower in query_lower or slug_lower in query_lower:
            return f"Søgeterm indeholder modulnavn '{title}'"
        else:
            return "Delvis lighed med modulnavn og potentielt relevant funktionalitet"
    
    async def validate_recommended_modules(self, modules: List[str]) -> ValidationResult:
        """Valider en liste af foreslåede moduler."""
        if not await self._load_modules():
            return ValidationResult(
                valid_modules=[],
                invalid_modules=modules,
                suggestions=[],
                total_checked=len(modules)
            )
        
        valid_modules = []
        invalid_modules = []
        all_suggestions = []
        
        for module in modules:
            if not module:
                continue
            
            # Tjek om modulet eksisterer
            if module in self._module_titles or module in self._module_slugs:
                valid_modules.append(module)
            else:
                invalid_modules.append(module)
                # Find forslag til alternative moduler
                suggestions = self._find_best_matches(module)
                all_suggestions.extend(suggestions)
        
        return ValidationResult(
            valid_modules=valid_modules,
            invalid_modules=invalid_modules,
            suggestions=all_suggestions,
            total_checked=len(modules)
        )
    
    async def get_module_suggestions_for_goal(self, goal: str, limit: int = 3) -> List[ModuleMatch]:
        """Få modul-forslag baseret på et journalistisk mål."""
        if not await self._load_modules():
            return []
        
        # Ekstraher nøgleord fra målet
        keywords = self._extract_keywords_from_goal(goal)
        
        best_matches = []
        for keyword in keywords:
            matches = self._find_best_matches(keyword, limit=2)
            best_matches.extend(matches)
        
        # Sortér og fjern duplikater
        unique_matches = {}
        for match in best_matches:
            if match.module_slug not in unique_matches:
                unique_matches[match.module_slug] = match
            else:
                # Opdater confidence hvis denne match er bedre
                if match.confidence > unique_matches[match.module_slug].confidence:
                    unique_matches[match.module_slug] = match
        
        # Returnér top matches
        sorted_matches = sorted(unique_matches.values(), key=lambda x: x.confidence, reverse=True)
        return sorted_matches[:limit]
    
    def get_search_examples_for_module(self, module_title: str) -> List[str]:
        """Få eksempel-søgestrenge for et specifikt modul."""
        module_lower = module_title.lower()
        
        # Modulspecifikke søge-eksempler
        search_examples = {
            "udbud": [
                "vinder OR tildelt OR valgt",
                "kontraktværdi > 1000000",
                "offentlig OR kommunal OR statlig"
            ],
            "miljøsager": [
                "forurening OR miljøskade",
                "godkendelse OR tilladelse",
                "kritik OR påbud"
            ],
            "registrering": [
                "ny OR oprettet OR registreret",
                "branchekode: 47.11.10",
                "~holding~ OR ~capital~"
            ],
            "status": [
                "konkurs OR opløst",
                "statusændring OR ophør",
                "tvangsopløsning OR likvidation"
            ],
            "tinglysning": [
                "ejendomshandel OR salg",
                "beløb > 5000000",
                "~landbrugsejendom~ OR ~gård~"
            ],
            "lokalpolitik": [
                "byrådsbeslutning OR kommunal",
                "politisk OR beslutning",
                "udvikling OR planlægning"
            ],
            "arbejdstilsyn": [
                "kritik OR påbud",
                "arbejdsmiljø OR sikkerhed",
                "overtrædelse OR bøde"
            ],
            "finanstilsynet": [
                "advarsel OR påbud",
                "finansiel OR økonomisk",
                "tilsyn OR kontrol"
            ]
        }
        
        # Find relevante eksempler
        examples = []
        for key, value in search_examples.items():
            if key in module_lower:
                examples.extend(value)
        
        # Generiske eksempler hvis ingen specifikke fundet
        if not examples:
            examples = [
                "relevant OR vigtig OR central",
                "~søgeterm~ OR ~nøgleord~",
                "AND (kritisk OR problem)"
            ]
        
        return examples[:5]  # Returnér max 5 eksempler
    
    def _extract_keywords_from_goal(self, goal: str) -> List[str]:
        """Ekstraher relevante nøgleord fra et journalistisk mål."""
        # Fjern almindelige ord og fokuser på nøgleord
        common_words = {
            'og', 'i', 'på', 'til', 'for', 'med', 'om', 'af', 'fra', 'ved', 'under',
            'over', 'efter', 'før', 'mellem', 'gennem', 'uden', 'mod', 'efter',
            'den', 'det', 'der', 'som', 'at', 'en', 'et', 'har', 'er', 'var',
            'vil', 'kan', 'skal', 'må', 'bør', 'kunne', 'ville', 'skulle'
        }
        
        # Tokenize og filtrer
        words = re.findall(r'\b\w+\b', goal.lower())
        keywords = [word for word in words if word not in common_words and len(word) > 2]
        
        # Fjern duplikater og returnér
        return list(set(keywords))

    async def get_enhanced_module_card(self, module_title: str) -> Optional[EnhancedModuleCard]:
        """Få udvidet modul-information med alle API metadata."""
        logger.info(f"Getting enhanced card for: {module_title}")

        if not await self._load_modules():
            logger.warning(f"Could not load modules for {module_title}")
            return None

        for module in self._modules_cache:
            if module.get('title') == module_title:
                logger.info(f"Found module: {module.get('title')}")
                logger.info(f"Module data: {module.get('longDescription', 'NO LONG DESC')[:100]}...")

                # Process filters with detailed info
                available_filters = []
                requires_source = False

                for part in module.get('parts', []):
                    filter_info = {
                        'type': part.get('part'),
                        'name': part.get('name'),
                        'info': part.get('info', ''),
                        'multiple': part.get('canSelectMultiple', False),
                        'order': part.get('order', 999),
                        'practical_use': self._get_practical_filter_use(part.get('part'), part.get('name'))
                    }
                    available_filters.append(filter_info)

                    # Check if web_source (requires manual selection)
                    if part.get('part') == 'web_source':
                        requires_source = True

                # Sort filters by order
                available_filters.sort(key=lambda x: x['order'])

                # Calculate NEW FIELDS
                total_filters = len(available_filters)
                complexity_level = self._calculate_complexity_level(total_filters, requires_source)

                # Extract data frequency from description
                data_freq = self._extract_data_frequency(module.get('longDescription', ''))

                logger.info(f"Module stats - Filters: {total_filters}, Complexity: {complexity_level}")

                return EnhancedModuleCard(
                    title=module.get('title', ''),
                    slug=module.get('slug', ''),
                    emoji=module.get('emoji', '📊'),
                    color=f"#{module.get('colorHex', '666666')}",
                    short_description=module.get('shortDescription', ''),
                    long_description=module.get('longDescription', ''),
                    data_frequency=data_freq,
                    available_filters=available_filters,
                    requires_source_selection=requires_source,
                    total_filters=total_filters,
                    complexity_level=complexity_level
                )

        logger.warning(f"Module not found: {module_title}")
        return None

    def _get_practical_filter_use(self, filter_type: str, filter_name: str) -> str:
        """Generer praktiske anvendelses-tips for filtre."""
        tips = {
            'industry': 'Brug specifikke branchekoder for præcision - fx 41.20.00 for byggeri',
            'municipality': 'Vælg 1-3 kommuner for fokuseret overvågning',
            'amount_selection': 'Sæt minimum-beløb for at fokusere på større sager',
            'company': 'Brug CVR-numre fra andre moduler for præcis targeting',
            'web_source': 'PÅKRÆVET: Vælg specifikke mediekilder manuelt',
            'generic_value': f'Filtrer på specifikke {filter_name.lower()} kategorier',
            'search_string': 'Brug som sidste filter efter branche/geografi',
            'hit_logic': 'Vælg OG for præcision, ELLER for bredde'
        }
        return tips.get(filter_type, f'Konfigurer {filter_name} efter behov')

    def _extract_data_frequency(self, description: str) -> str:
        """Udtræk data-opdateringshyppighed fra beskrivelse."""
        if 'dagligt' in description.lower():
            return 'flere gange dagligt'
        elif 'ugentlig' in description.lower():
            return 'ugentligt'
        elif 'månedlig' in description.lower():
            return 'månedligt'
        else:
            return 'løbende opdatering'

    def _calculate_complexity_level(self, total_filters: int, requires_source: bool) -> str:
        """Beregn kompleksitetsniveau baseret på filter-antal og kildekrav."""
        if total_filters <= 2 and not requires_source:
            return "Simpel"
        elif total_filters <= 4 and not requires_source:
            return "Medium"
        else:
            return "Kompleks"

    async def get_filter_recommendations(self, module_title: str, goal: str = "") -> FilterRecommendation:
        """Generer smarte anbefalinger for filter-rækkefølge."""
        card = await self.get_enhanced_module_card(module_title)
        if not card:
            return FilterRecommendation([], [], "Modul ikke fundet")
        
        # Build optimal sequence based on filter order and type
        sequence = []
        tips = []
        warning = None
        
        # Priority order: industry -> municipality -> amount -> company -> search
        priority_map = {
            'industry': 1,
            'municipality': 2, 
            'amount_selection': 3,
            'company': 4,
            'generic_value': 5,
            'web_source': 6,
            'search_string': 7,
            'hit_logic': 8
        }
        
        # Sort filters by priority
        sorted_filters = sorted(card.available_filters, 
                              key=lambda x: priority_map.get(x['type'], 9))
        
        for idx, filter_info in enumerate(sorted_filters):
            if filter_info['type'] == 'hit_logic':
                continue  # Skip hit_logic in sequence
            
            step = f"{idx + 1}. {filter_info['name']}"
            if filter_info['type'] == 'industry':
                step += " (742 tilgængelige branchekoder)"
            elif filter_info['type'] == 'municipality':
                step += " (98 kommuner + Christiansø)"
            
            sequence.append(step)
            
            # Add practical tips
            if filter_info['multiple']:
                tips.append(f"Multi-select mulig på {filter_info['name']}")
            
            if filter_info['info']:
                tips.append(f"{filter_info['name']}: {filter_info['info'][:100]}...")
        
        # Add complexity warnings
        if len([f for f in card.available_filters if f['type'] == 'web_source']) > 0:
            warning = "PÅKRÆVET: Manuel kildevalg nødvendig for dette modul"
        elif not any(f['type'] == 'industry' for f in card.available_filters):
            warning = "Ingen branche-filtrering tilgængelig - kan give mange hits"
        
        return FilterRecommendation(sequence, tips, warning)

    async def analyze_complexity(self, module_title: str, filters: Dict[str, Any]) -> ComplexityAnalysis:
        """Analysér forventet kompleksitet baseret på filter-kombination."""
        card = await self.get_enhanced_module_card(module_title)
        if not card:
            return ComplexityAnalysis("Ukendt", "Lav", {}, [])
        
        # Estimate hit volume based on filters
        complexity_score = 0
        optimizations = []
        
        # Check if industry filter is used
        if 'industry' in filters and filters['industry']:
            complexity_score -= 30  # Industry filter reduces hits significantly
        else:
            if any(f['type'] == 'industry' for f in card.available_filters):
                optimizations.append("Tilføj branche-filter for færre og mere relevante hits")
                complexity_score += 50
        
        # Check municipality filter
        if 'municipality' in filters and filters['municipality']:
            complexity_score -= 20
        else:
            if any(f['type'] == 'municipality' for f in card.available_filters):
                optimizations.append("Begræns geografisk for mere fokuseret overvågning")
                complexity_score += 30
        
        # Check amount filter
        if any(f['type'] == 'amount_selection' for f in card.available_filters):
            if 'amount' not in filters:
                optimizations.append("Overvej beløbsgrænse for at fokusere på større sager")
                complexity_score += 20
        
        # Determine estimated hits
        if complexity_score > 60:
            estimated = "Meget høj (>500/dag)"
            notification = "interval"
            reason = "For mange hits til løbende notifikationer"
        elif complexity_score > 30:
            estimated = "Høj (100-500/dag)" 
            notification = "interval"
            reason = "Mange hits - overvej interval-notifikationer"
        elif complexity_score > 0:
            estimated = "Medium (20-100/dag)"
            notification = "løbende"
            reason = "Håndterbart antal hits for løbende overvågning"
        else:
            estimated = "Lav (1-20/dag)"
            notification = "løbende"
            reason = "Få, relevante hits - perfekt til løbende notifikationer"
        
        # Filter efficiency
        if complexity_score > 40:
            efficiency = "Lav - tilføj flere filtre"
        elif complexity_score > 20:
            efficiency = "Medium - overvej yderligere filtrering"
        else:
            efficiency = "Høj - godt konfigureret"
        
        notification_rec = {
            "type": notification,
            "reason": reason,
            "optimization": optimizations[0] if optimizations else "Konfiguration ser god ud"
        }
        
        return ComplexityAnalysis(estimated, efficiency, notification_rec, optimizations)

    async def get_module_availability_matrix(self) -> Dict[str, Any]:
        """Generer matrix over tilgængelige funktioner på tværs af moduler."""
        if not await self._load_modules():
            return {}
        
        matrix = {
            "total_modules": len(self._modules_cache),
            "has_industry_filter": 0,
            "has_municipality_filter": 0,
            "has_company_filter": 0,
            "has_amount_filter": 0,
            "requires_source_selection": 0,
            "modules_without_company_filter": [],
            "modules_without_industry_filter": [],
            "specialized_filters": {}
        }
        
        for module in self._modules_cache:
            title = module.get('title', '')
            parts = {part.get('part') for part in module.get('parts', [])}
            
            if 'industry' in parts:
                matrix["has_industry_filter"] += 1
            else:
                matrix["modules_without_industry_filter"].append(title)
            
            if 'municipality' in parts:
                matrix["has_municipality_filter"] += 1
            
            if 'company' in parts:
                matrix["has_company_filter"] += 1
            else:
                matrix["modules_without_company_filter"].append(title)
            
            if 'amount_selection' in parts:
                matrix["has_amount_filter"] += 1
            
            if 'web_source' in parts:
                matrix["requires_source_selection"] += 1
            
            # Track specialized filters
            for part in module.get('parts', []):
                if part.get('part') == 'generic_value':
                    filter_name = part.get('name', 'Unknown')
                    if filter_name not in matrix["specialized_filters"]:
                        matrix["specialized_filters"][filter_name] = []
                    matrix["specialized_filters"][filter_name].append(title)
        
        return matrix

    async def get_cross_module_intelligence(self, modules: List[str]) -> List[Dict[str, Any]]:
        """Generer intelligent vejledning til krydsmodulære workflows."""
        if not await self._load_modules():
            return []
        
        relationships = []
        
        # Define common workflows
        workflows = [
            {
                "primary": "Registrering",
                "connects_to": ["Status", "Tinglysning", "Arbejdstilsyn", "Børsmeddelelser"],
                "workflow": "CVR-numre → Aktivitet → Kontekst",
                "timing": "Start med Registrering for at få CVR-numre til andre moduler",
                "rationale": "CVR-først princippet giver præcise virksomhedsfiltre"
            },
            {
                "primary": "Udbud",
                "connects_to": ["Status", "Arbejdstilsyn", "Miljøsager"],
                "workflow": "Vundne kontrakter → Virksomhedsstatus → Problemer",
                "timing": "Følg udbudsvindere gennem deres efterfølgende aktiviteter",
                "rationale": "Afdæk om udbudsvindere efterfølgende får problemer eller går konkurs"
            },
            {
                "primary": "Tinglysning",
                "connects_to": ["Miljøsager", "Lokalpolitik", "Registrering"],
                "workflow": "Ejendomshandler → Miljøgodkendelser → Politiske beslutninger",
                "timing": "Store ejendomshandler kan indikere kommende udviklingsprojekter",
                "rationale": "Følg pengestrømme fra ejendom til projekter til godkendelser"
            }
        ]
        
        # Filter workflows based on provided modules
        for workflow in workflows:
            if workflow["primary"] in modules:
                relevant_connections = [mod for mod in workflow["connects_to"] if mod in modules]
                if relevant_connections:
                    relationships.append({
                        "primary": workflow["primary"],
                        "connects_to": relevant_connections,
                        "workflow": workflow["workflow"],
                        "timing": workflow["timing"],
                        "rationale": workflow["rationale"]
                    })
        
        return relationships

# Global validator instance
_module_validator: Optional[ModuleValidator] = None

def get_module_validator() -> ModuleValidator:
    """Få global module validator instance."""
    global _module_validator
    if _module_validator is None:
        _module_validator = ModuleValidator()
    return _module_validator
