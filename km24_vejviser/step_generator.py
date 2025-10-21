"""
Step JSON Generator for KM24 API.

Generates API-ready step JSON from recipe steps, including:
- Complete step JSON for POST /api/steps/main
- cURL commands for easy testing
- Python code examples
"""

import json
import logging
from typing import Dict, List, Optional, Any
from .part_id_mapper import get_part_id_mapper, PartIdMapper

logger = logging.getLogger(__name__)


class StepJsonGenerator:
    """
    Generates KM24 API-ready step JSON.
    
    Converts recipe steps (with human-readable filter names) to complete
    step JSON ready for POST /api/steps/main endpoint.
    """
    
    def __init__(self, mapper: Optional[PartIdMapper] = None):
        """
        Initialize generator with part ID mapper.
        
        Args:
            mapper: PartIdMapper instance. If None, uses global mapper.
        """
        self.mapper = mapper or get_part_id_mapper()
    
    async def generate_step_json(
        self,
        step_data: Dict[str, Any],
        module_id: int,
        parts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate complete step JSON for KM24 API.
        
        Args:
            step_data: Recipe step dictionary
            module_id: KM24 module ID
            parts: List of parts with modulePartId (from PartIdMapper)
            
        Returns:
            Complete step JSON ready for POST /api/steps/main
        """
        # Extract step name (use title or generate from module)
        step_name = step_data.get("title", f"Step for module {module_id}")
        
        # Determine lookbackDays (default 30)
        lookback_days = step_data.get("lookback_days", 30)
        
        # Build complete step JSON
        step_json = {
            "name": step_name,
            "moduleId": module_id,
            "lookbackDays": lookback_days,
            "onlyActive": False,  # Usually false - include all companies
            "onlySubscribed": False,  # Usually false - not limited to subscribed
            "parts": parts
        }
        
        logger.info(f"Generated step JSON for module {module_id} with {len(parts)} parts")
        return step_json
    
    async def generate_all_steps(self, recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate step JSON for all steps in a recipe.
        
        Args:
            recipe: Complete recipe dictionary with investigation_steps
            
        Returns:
            List of step JSON objects ready for KM24 API
        """
        steps_json = []
        
        for step in recipe.get("investigation_steps", []):
            try:
                # Get module ID
                module_id = step.get("module_id")
                if not module_id:
                    logger.warning(f"Step '{step.get('title')}' missing module_id, skipping")
                    continue
                
                # Map filters to parts
                filters = step.get("filters", {})
                parts, warnings = await self.mapper.map_filters_to_parts(module_id, filters)
                
                if warnings:
                    logger.warning(f"Warnings for step '{step.get('title')}': {warnings}")
                
                # Generate step JSON
                step_json = await self.generate_step_json(step, module_id, parts)
                steps_json.append(step_json)
                
            except Exception as e:
                logger.error(f"Error generating step JSON for '{step.get('title')}': {e}")
                continue
        
        logger.info(f"Generated {len(steps_json)} step JSON objects from recipe")
        return steps_json
    
    def generate_curl_command(
        self, 
        step_json: Dict[str, Any],
        api_key_placeholder: str = "YOUR_API_KEY"
    ) -> str:
        """
        Generate cURL command to create step in KM24.
        
        Args:
            step_json: Complete step JSON
            api_key_placeholder: Placeholder for API key
            
        Returns:
            cURL command string
        """
        # Pretty-print JSON for readability
        json_str = json.dumps(step_json, ensure_ascii=False, indent=2)
        
        # Escape single quotes in JSON for shell
        json_str_escaped = json_str.replace("'", "'\\''")
        
        curl_command = f"""curl -X POST https://km24.dk/api/steps/main \\
  -H "X-API-Key: {api_key_placeholder}" \\
  -H "Content-Type: application/json" \\
  -d '{json_str_escaped}'"""
        
        return curl_command
    
    def generate_python_code(
        self,
        step_json: Dict[str, Any],
        api_key_placeholder: str = "YOUR_API_KEY"
    ) -> str:
        """
        Generate Python code to create step in KM24.
        
        Args:
            step_json: Complete step JSON
            api_key_placeholder: Placeholder for API key
            
        Returns:
            Python code string
        """
        # Pretty-print JSON for readability
        json_str = json.dumps(step_json, ensure_ascii=False, indent=2)
        
        # Indent JSON for Python string
        json_lines = json_str.split("\n")
        indented_json = "\n    ".join(json_lines)
        
        python_code = f"""import requests

API_KEY = "{api_key_placeholder}"
headers = {{"X-API-Key": API_KEY}}

step_data = {indented_json}

response = requests.post(
    "https://km24.dk/api/steps/main",
    headers=headers,
    json=step_data
)

if response.status_code == 201:
    step = response.json()
    print(f"Step created with ID: {{step['id']}}")
else:
    print(f"Error: {{response.status_code}} - {{response.text}}")"""
        
        return python_code
    
    async def generate_batch_script(
        self,
        recipe: Dict[str, Any],
        api_key_placeholder: str = "YOUR_API_KEY"
    ) -> str:
        """
        Generate Python script to create all steps from recipe.
        
        Args:
            recipe: Complete recipe dictionary
            api_key_placeholder: Placeholder for API key
            
        Returns:
            Complete Python script as string
        """
        steps_json = await self.generate_all_steps(recipe)
        
        if not steps_json:
            return "# No valid steps found in recipe"
        
        # Build batch script
        script_lines = [
            '"""',
            'Batch script to create KM24 steps from recipe.',
            'Generated by KM24 Vejviser.',
            '"""',
            '',
            'import requests',
            'import time',
            '',
            f'API_KEY = "{api_key_placeholder}"',
            'BASE_URL = "https://km24.dk/api"',
            'headers = {"X-API-Key": API_KEY}',
            '',
            '# Step definitions',
            'steps = ['
        ]
        
        # Add each step JSON
        for i, step_json in enumerate(steps_json):
            json_str = json.dumps(step_json, ensure_ascii=False, indent=4)
            # Indent for list
            indented = "\n    ".join(json_str.split("\n"))
            script_lines.append(f'    # Step {i+1}: {step_json.get("name", "Unnamed")}')
            script_lines.append(f'    {indented}')
            if i < len(steps_json) - 1:
                script_lines.append(',')
        
        script_lines.extend([
            ']',
            '',
            '# Create steps',
            'created_steps = []',
            '',
            'for i, step_data in enumerate(steps, 1):',
            '    print(f"Creating step {i}/{len(steps)}: {step_data[\'name\']}")',
            '    ',
            '    response = requests.post(',
            '        f"{BASE_URL}/steps/main",',
            '        headers=headers,',
            '        json=step_data',
            '    )',
            '    ',
            '    if response.status_code == 201:',
            '        step = response.json()',
            '        created_steps.append(step)',
            '        print(f"  ✓ Created with ID: {step[\'id\']}")',
            '    else:',
            '        print(f"  ✗ Error: {response.status_code} - {response.text}")',
            '    ',
            '    # Rate limiting - wait between requests',
            '    if i < len(steps):',
            '        time.sleep(0.5)',
            '',
            'print(f"\\nCreated {len(created_steps)}/{len(steps)} steps successfully")',
            '',
            '# Print created step IDs',
            'if created_steps:',
            '    print("\\nStep IDs:")',
            '    for step in created_steps:',
            '        print(f"  - {step[\'name\']}: {step[\'id\']}")',
        ])
        
        return '\n'.join(script_lines)


# Global instance
_generator: Optional[StepJsonGenerator] = None


def get_step_generator() -> StepJsonGenerator:
    """Get global StepJsonGenerator instance."""
    global _generator
    if _generator is None:
        _generator = StepJsonGenerator()
    return _generator

