"""
KM24 API Client med caching og fejlhåndtering.

Implementerer:
- Live modul-validering mod KM24 API
- Ugentlig cache-opdatering + manuel opdatering
- Robust fejlhåndtering når API er nede
- Forsigtig rate limiting
"""
import os
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

@dataclass
class KM24APIResponse:
    """Response wrapper for KM24 API calls."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cached: bool = False
    cache_age: Optional[timedelta] = None

class KM24APIClient:
    """KM24 API client med intelligent caching og fejlhåndtering."""
    
    def __init__(self):
        # Base URL can be configured; default to documented API base
        self.base_url = os.getenv("KM24_BASE", "https://km24.dk/api")
        self.api_key = os.getenv("KM24_API_KEY")
        self.cache_dir = Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms mellem requests
        
        if not self.api_key:
            logger.warning("KM24_API_KEY ikke sat - API funktionalitet vil være begrænset")
    
    def _rate_limit(self):
        """Implementer forsigtig rate limiting."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _get_cache_path(self, endpoint: str) -> Path:
        """Generer cache fil sti for et endpoint."""
        safe_endpoint = endpoint.replace("/", "_").replace("?", "_")
        return self.cache_dir / f"{safe_endpoint}.json"
    
    def _load_cache(self, cache_path: Path) -> Optional[Dict[str, Any]]:
        """Indlæs cache fra fil hvis den eksisterer og ikke er for gammel."""
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # Tjek om cache er for gammel (1 uge)
            cache_time = datetime.fromisoformat(cached_data.get('cached_at', '1970-01-01'))
            if datetime.now() - cache_time > timedelta(days=7):
                logger.info(f"Cache for {cache_path.name} er for gammel")
                return None
            
            return cached_data
        except Exception as e:
            logger.warning(f"Fejl ved indlæsning af cache {cache_path}: {e}")
            return None
    
    def _save_cache(self, cache_path: Path, data: Dict[str, Any]):
        """Gem data i cache."""
        try:
            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'data': data
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Cache gemt: {cache_path.name}")
        except Exception as e:
            logger.error(f"Fejl ved gemning af cache {cache_path}: {e}")
    
    async def _make_request(self, endpoint: str, force_refresh: bool = False) -> KM24APIResponse:
        """Lav API request med caching."""
        if not self.api_key:
            return KM24APIResponse(
                success=False,
                error="KM24_API_KEY ikke konfigureret"
            )
        
        cache_path = self._get_cache_path(endpoint)
        
        # Tjek cache først (medmindre force_refresh)
        if not force_refresh:
            cached_data = self._load_cache(cache_path)
            if cached_data:
                cache_time = datetime.fromisoformat(cached_data['cached_at'])
                cache_age = datetime.now() - cache_time
                return KM24APIResponse(
                    success=True,
                    data=cached_data['data'],
                    cached=True,
                    cache_age=cache_age
                )
        
        # Rate limiting
        self._rate_limit()
        
        # Lav API request
        try:
            headers = {
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}{endpoint}"
            logger.info(f"API request: {endpoint}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    error_msg = "API svarede med ikke-JSON indhold"
                    logger.error(error_msg)
                    return KM24APIResponse(success=False, error=error_msg)
                self._save_cache(cache_path, data)
                return KM24APIResponse(success=True, data=data)
            # Specific auth errors
            if response.status_code in (401, 403):
                error_msg = "Authentication fejlede (401/403). Tjek KM24_API_KEY og tilladelser."
                logger.error(error_msg)
                return KM24APIResponse(success=False, error=error_msg)
            # 404/405 commonly return HTML
            if response.status_code in (404, 405):
                logger.error(f"API fejl {response.status_code}: endpoint findes ikke eller metode ikke tilladt")
                return KM24APIResponse(success=False, error=f"API fejl {response.status_code}: endpoint ikke fundet / metode ikke tilladt")
            # Generic error
            error_msg = f"API fejl {response.status_code}: {response.text}"
            logger.error(error_msg)
            return KM24APIResponse(success=False, error=error_msg)
                
        except httpx.TimeoutException:
            error_msg = "API timeout - serveren svarede ikke inden for 30 sekunder"
            logger.error(error_msg)
            return KM24APIResponse(success=False, error=error_msg)
        except (httpx.ConnectError, httpx.NetworkError):
            error_msg = "API forbindelsesfejl - kunne ikke nå KM24 serveren"
            logger.error(error_msg)
            return KM24APIResponse(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Uventet API fejl: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return KM24APIResponse(success=False, error=error_msg)
    
    async def get_modules_basic(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent alle KM24 moduler (basic)."""
        return await self._make_request("/modules/basic", force_refresh)

    async def get_modules_detailed(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent detaljeret modul-liste."""
        return await self._make_request("/modules/detailed", force_refresh)
    
    async def get_module_details(self, module_id: int, force_refresh: bool = False) -> KM24APIResponse:
        """Hent detaljer for et specifikt modul (basic/{id})."""
        return await self._make_request(f"/modules/basic/{module_id}", force_refresh)
    
    async def get_branch_codes(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent branchekode-lister (basis)."""
        return await self._make_request("/branch-codes", force_refresh)
    
    async def get_filter_options(self, module_slug: str, filter_type: str, force_refresh: bool = False) -> KM24APIResponse:
        """Ikke dokumenteret i API. Returnerer fejl for at undgå falsk kontrakt."""
        return KM24APIResponse(success=False, error="Endpoint ikke dokumenteret: modules/{slug}/filters/{type}")
    
    async def get_media_sources(self, media_type: str = "danish", force_refresh: bool = False) -> KM24APIResponse:
        """Hent lister over mediekilder (hvis tilgængeligt)."""
        return await self._make_request(f"/media-sources/{media_type}", force_refresh)
    
    async def get_search_examples(self, module_slug: str, force_refresh: bool = False) -> KM24APIResponse:
        """Hent eksempel-søgestrenge for et specifikt modul (hvis tilgængeligt)."""
        return await self._make_request(f"/modules/{module_slug}/search-examples", force_refresh)
    
    async def get_generic_values(self, module_part_id: int, force_refresh: bool = False) -> KM24APIResponse:
        """Hent modulspecifikke kategorier (generic_values) for en specifik modulpart."""
        return await self._make_request(f"/generic-values/{module_part_id}", force_refresh)
    
    async def get_web_sources(self, module_id: int, force_refresh: bool = False) -> KM24APIResponse:
        """Hent webkilder for et specifikt modul."""
        return await self._make_request(f"/web-sources/categories/{module_id}", force_refresh)
    
    async def get_municipalities(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent alle danske kommuner."""
        return await self._make_request("/municipalities", force_refresh)
    
    async def get_branch_codes_detailed(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent detaljerede branchekoder med beskrivelser."""
        return await self._make_request("/branch-codes/detailed", force_refresh)
    
    async def get_court_districts(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent retskredse."""
        return await self._make_request("/court-districts", force_refresh)
    
    async def get_regions(self, force_refresh: bool = False) -> KM24APIResponse:
        """Hent danske regioner."""
        return await self._make_request("/regions", force_refresh)
    
    async def get_filter_options_for_module(self, module_id: int, force_refresh: bool = False) -> KM24APIResponse:
        """Ikke dokumenteret. Brug get_module_details + parts + generic-values/web-sources i stedet."""
        return KM24APIResponse(success=False, error="Endpoint ikke dokumenteret: modules/{id}/filter-options")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Tjek KM24 API status."""
        if not self.api_key:
            return {
                "status": "not_configured",
                "message": "KM24_API_KEY ikke sat",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        result = await self.get_modules_basic()
        
        if result.success:
            return {
                "status": "healthy",
                "modules_count": len(result.data.get('modules', [])),
                "cache_age": str(result.cache_age) if result.cache_age else None,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "error": result.error,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def clear_cache(self) -> Dict[str, Any]:
        """Ryd alle cache filer."""
        try:
            cache_files = list(self.cache_dir.glob("*.json"))
            for cache_file in cache_files:
                cache_file.unlink()
            
            return {
                "success": True,
                "message": f"Cache ryddet - {len(cache_files)} filer fjernet",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Fejl ved cache rydning: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }

# Global client instance
_km24_client: Optional[KM24APIClient] = None

def get_km24_client() -> KM24APIClient:
    """Få global KM24 client instance."""
    global _km24_client
    if _km24_client is None:
        _km24_client = KM24APIClient()
    return _km24_client
