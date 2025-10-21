"""
Part ID Mapper for KM24 API.

Maps human-readable filter names to numeric modulePartId values required by KM24 API.
Handles case-insensitive matching and provides validation warnings for unknown filters.
"""

import logging
from typing import Dict, List, Optional, Any
from .km24_client import get_km24_client, KM24APIClient

logger = logging.getLogger(__name__)


class PartIdMapper:
    """
    Maps filter names to modulePartId for KM24 API.
    
    The KM24 API requires filters to be sent as:
    {"modulePartId": 205, "values": ["Asbest"]}
    
    But our LLM generates human-readable format:
    {"Problem": ["Asbest"]}
    
    This class handles the translation using live module data from KM24 API.
    """
    
    def __init__(self, km24_client: Optional[KM24APIClient] = None):
        """
        Initialize mapper with KM24 client.
        
        Args:
            km24_client: KM24 API client instance. If None, uses global client.
        """
        self.client = km24_client or get_km24_client()
        self._cache: Dict[int, Dict[str, int]] = {}  # module_id -> {name: part_id}
    
    async def get_part_id_mapping(self, module_id: int) -> Dict[str, int]:
        """
        Get mapping of filter names to part IDs for a module.
        
        Args:
            module_id: KM24 module ID
            
        Returns:
            Dictionary mapping filter names to part IDs.
            Example: {"Kommune": 2, "Problem": 205, "Branche": 5}
            
        Raises:
            ValueError: If module data cannot be fetched
        """
        # Check cache first
        if module_id in self._cache:
            logger.debug(f"Using cached part mapping for module {module_id}")
            return self._cache[module_id]
        
        # Fetch from API
        logger.info(f"Fetching part mapping for module {module_id} from API")
        response = await self.client.get_module_details(module_id, force_refresh=False)
        
        if not response.success or not response.data:
            error_msg = f"Failed to fetch module {module_id}: {response.error}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Build mapping
        parts = response.data.get("parts", [])
        mapping = {}
        
        for part in parts:
            part_id = part.get("id")
            part_name = part.get("name")
            
            if part_id and part_name:
                # Store with exact name
                mapping[part_name] = part_id
                # Also store lowercase for case-insensitive lookup
                mapping[part_name.lower()] = part_id
        
        # Cache the mapping
        self._cache[module_id] = mapping
        logger.info(f"Cached part mapping for module {module_id}: {len(mapping)//2} parts")
        
        return mapping
    
    async def map_filters_to_parts(
        self, 
        module_id: int, 
        filters: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Map filter dictionary to KM24 API parts format.
        
        Args:
            module_id: KM24 module ID
            filters: Dictionary of filter_name -> filter_values
                    Example: {"Kommune": ["Aarhus"], "Problem": ["Asbest"]}
        
        Returns:
            Tuple of (parts_list, warnings)
            - parts_list: List of part dicts for KM24 API
              Example: [{"modulePartId": 2, "values": ["Aarhus"]}]
            - warnings: List of warning messages for unknown filters
        """
        if not filters:
            return [], []
        
        # Get part ID mapping
        try:
            part_mapping = await self.get_part_id_mapping(module_id)
        except ValueError as e:
            logger.error(f"Cannot map filters without part mapping: {e}")
            return [], [f"Could not fetch module {module_id} parts: {str(e)}"]
        
        parts = []
        warnings = []
        
        for filter_name, filter_values in filters.items():
            # Normalize filter values to list
            if not isinstance(filter_values, list):
                filter_values = [filter_values] if filter_values else []
            
            # Skip empty filter values
            if not filter_values:
                logger.debug(f"Skipping empty filter: {filter_name}")
                continue
            
            # Find part ID (case-insensitive)
            part_id = part_mapping.get(filter_name) or part_mapping.get(filter_name.lower())
            
            if part_id:
                parts.append({
                    "modulePartId": part_id,
                    "values": filter_values
                })
                logger.debug(f"Mapped '{filter_name}' -> part ID {part_id} with {len(filter_values)} values")
            else:
                warning = f"Unknown filter '{filter_name}' for module {module_id}"
                warnings.append(warning)
                logger.warning(warning)
        
        return parts, warnings
    
    def validate_filter_names(
        self, 
        module_id: int, 
        filter_names: List[str],
        part_mapping: Optional[Dict[str, int]] = None
    ) -> Dict[str, bool]:
        """
        Validate that filter names exist in module's parts.
        
        Args:
            module_id: KM24 module ID
            filter_names: List of filter names to validate
            part_mapping: Optional pre-fetched part mapping (to avoid async call)
            
        Returns:
            Dictionary mapping filter_name -> is_valid boolean
        """
        if part_mapping is None:
            # Cannot validate without mapping
            logger.warning(f"Cannot validate filter names for module {module_id} without part mapping")
            return {name: False for name in filter_names}
        
        validation_results = {}
        
        for filter_name in filter_names:
            # Check both exact match and lowercase match
            is_valid = (
                filter_name in part_mapping or 
                filter_name.lower() in part_mapping
            )
            validation_results[filter_name] = is_valid
            
            if not is_valid:
                logger.warning(f"Invalid filter name '{filter_name}' for module {module_id}")
        
        return validation_results
    
    def get_part_id_for_filter(
        self, 
        filter_name: str, 
        part_mapping: Dict[str, int]
    ) -> Optional[int]:
        """
        Get part ID for a single filter name.
        
        Args:
            filter_name: Filter name to look up
            part_mapping: Part mapping dictionary
            
        Returns:
            Part ID if found, None otherwise
        """
        # Try exact match first
        part_id = part_mapping.get(filter_name)
        if part_id:
            return part_id
        
        # Try case-insensitive match
        return part_mapping.get(filter_name.lower())


# Global instance
_mapper: Optional[PartIdMapper] = None


def get_part_id_mapper() -> PartIdMapper:
    """Get global PartIdMapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = PartIdMapper()
    return _mapper

