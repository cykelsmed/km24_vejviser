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
from km24_client import get_km24_client, KM24APIResponse

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

class ModuleValidator:
    """Validerer moduler mod KM24 API og giver intelligente forslag."""
    
    def __init__(self):
        self.client = get_km24_client()
        self._modules_cache: Optional[List[Dict[str, Any]]] = None
        self._module_titles: Optional[List[str]] = None
        self._module_slugs: Optional[List[str]] = None
    
    async def _load_modules(self) -> bool:
        """Indlæs alle KM24 moduler fra API."""
        try:
            result = await self.client.get_modules_basic()
            if result.success and result.data:
                self._modules_cache = result.data.get('items', [])
                self._module_titles = [mod.get('title', '') for mod in self._modules_cache]
                self._module_slugs = [mod.get('slug', '') for mod in self._modules_cache]
                logger.info(f"Indlæst {len(self._modules_cache)} moduler fra KM24 API")
                return True
            else:
                logger.warning(f"Kunne ikke indlæse moduler: {result.error}")
                return False
        except Exception as e:
            logger.error(f"Fejl ved indlæsning af moduler: {e}", exc_info=True)
            return False
    
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

# Global validator instance
_module_validator: Optional[ModuleValidator] = None

def get_module_validator() -> ModuleValidator:
    """Få global module validator instance."""
    global _module_validator
    if _module_validator is None:
        _module_validator = ModuleValidator()
    return _module_validator
