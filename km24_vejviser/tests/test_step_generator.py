"""
Tests for StepJsonGenerator - KM24 API step JSON generation.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from km24_vejviser.step_generator import StepJsonGenerator
from km24_vejviser.part_id_mapper import PartIdMapper


@pytest.fixture
def mock_mapper():
    """Mock PartIdMapper."""
    mapper = MagicMock(spec=PartIdMapper)
    return mapper


@pytest.fixture
def generator(mock_mapper):
    """StepJsonGenerator instance with mocked mapper."""
    return StepJsonGenerator(mapper=mock_mapper)


@pytest.mark.asyncio
async def test_generate_step_json_basic(generator):
    """Test basic step JSON generation."""
    # Arrange
    step_data = {
        "title": "Test Step",
        "lookback_days": 30
    }
    module_id = 110
    parts = [
        {"modulePartId": 2, "values": ["Aarhus"]},
        {"modulePartId": 205, "values": ["Asbest"]}
    ]
    
    # Act
    step_json = await generator.generate_step_json(step_data, module_id, parts)
    
    # Assert
    assert step_json["name"] == "Test Step"
    assert step_json["moduleId"] == 110
    assert step_json["lookbackDays"] == 30
    assert step_json["onlyActive"] is False
    assert step_json["onlySubscribed"] is False
    assert step_json["parts"] == parts


@pytest.mark.asyncio
async def test_generate_step_json_default_lookback(generator):
    """Test step JSON generation with default lookback days."""
    # Arrange
    step_data = {"title": "Test Step"}
    module_id = 110
    parts = []
    
    # Act
    step_json = await generator.generate_step_json(step_data, module_id, parts)
    
    # Assert
    assert step_json["lookbackDays"] == 30  # Default value


@pytest.mark.asyncio
async def test_generate_step_json_no_parts(generator):
    """Test step JSON generation with no parts (no filters)."""
    # Arrange
    step_data = {"title": "Test Step"}
    module_id = 110
    parts = []
    
    # Act
    step_json = await generator.generate_step_json(step_data, module_id, parts)
    
    # Assert
    assert step_json["parts"] == []
    assert "name" in step_json
    assert "moduleId" in step_json


def test_generate_curl_command_basic(generator):
    """Test cURL command generation."""
    # Arrange
    step_json = {
        "name": "Test Step",
        "moduleId": 110,
        "lookbackDays": 30,
        "parts": [{"modulePartId": 2, "values": ["Aarhus"]}]
    }
    
    # Act
    curl_cmd = generator.generate_curl_command(step_json, api_key_placeholder="TEST_KEY")
    
    # Assert
    assert "curl -X POST" in curl_cmd
    assert "https://km24.dk/api/steps/main" in curl_cmd
    assert "X-API-Key: TEST_KEY" in curl_cmd
    assert "Content-Type: application/json" in curl_cmd
    assert "Test Step" in curl_cmd
    assert "moduleId" in curl_cmd


def test_generate_curl_command_special_characters(generator):
    """Test cURL command generation with special characters in name."""
    # Arrange
    step_json = {
        "name": "Test's \"Step\"",
        "moduleId": 110,
        "parts": []
    }
    
    # Act
    curl_cmd = generator.generate_curl_command(step_json)
    
    # Assert
    # Should not cause syntax errors in shell
    assert "curl -X POST" in curl_cmd


def test_generate_python_code_basic(generator):
    """Test Python code generation."""
    # Arrange
    step_json = {
        "name": "Test Step",
        "moduleId": 110,
        "parts": []
    }
    
    # Act
    python_code = generator.generate_python_code(step_json, api_key_placeholder="TEST_KEY")
    
    # Assert
    assert "import requests" in python_code
    assert 'API_KEY = "TEST_KEY"' in python_code
    assert "https://km24.dk/api/steps/main" in python_code
    assert "step_data =" in python_code
    assert "Test Step" in python_code


def test_generate_python_code_proper_indentation(generator):
    """Test that generated Python code has proper indentation."""
    # Arrange
    step_json = {
        "name": "Test Step",
        "moduleId": 110,
        "parts": [{"modulePartId": 2, "values": ["Aarhus"]}]
    }
    
    # Act
    python_code = generator.generate_python_code(step_json)
    
    # Assert
    # Code should be valid Python (no syntax errors when compiled)
    try:
        compile(python_code, '<string>', 'exec')
    except SyntaxError:
        pytest.fail("Generated Python code has syntax errors")


@pytest.mark.asyncio
async def test_generate_all_steps_success(generator, mock_mapper):
    """Test generating step JSON for all steps in recipe."""
    # Arrange
    recipe = {
        "investigation_steps": [
            {
                "title": "Step 1",
                "module_id": 110,
                "filters": {"Kommune": ["Aarhus"]}
            },
            {
                "title": "Step 2",
                "module_id": 280,
                "filters": {"Søgeord": ["test"]}
            }
        ]
    }
    
    # Mock mapper responses
    mock_mapper.map_filters_to_parts = AsyncMock(
        side_effect=[
            ([{"modulePartId": 2, "values": ["Aarhus"]}], []),
            ([{"modulePartId": 136, "values": ["test"]}], [])
        ]
    )
    
    # Act
    steps_json = await generator.generate_all_steps(recipe)
    
    # Assert
    assert len(steps_json) == 2
    assert steps_json[0]["name"] == "Step 1"
    assert steps_json[0]["moduleId"] == 110
    assert steps_json[1]["name"] == "Step 2"
    assert steps_json[1]["moduleId"] == 280


@pytest.mark.asyncio
async def test_generate_all_steps_skip_missing_module_id(generator, mock_mapper):
    """Test that steps without module_id are skipped."""
    # Arrange
    recipe = {
        "investigation_steps": [
            {
                "title": "Step 1",
                # Missing module_id
                "filters": {}
            },
            {
                "title": "Step 2",
                "module_id": 110,
                "filters": {}
            }
        ]
    }
    
    mock_mapper.map_filters_to_parts = AsyncMock(return_value=([], []))
    
    # Act
    steps_json = await generator.generate_all_steps(recipe)
    
    # Assert
    assert len(steps_json) == 1  # Only one valid step
    assert steps_json[0]["name"] == "Step 2"


@pytest.mark.asyncio
async def test_generate_all_steps_with_warnings(generator, mock_mapper):
    """Test that warnings are logged but don't stop generation."""
    # Arrange
    recipe = {
        "investigation_steps": [
            {
                "title": "Step 1",
                "module_id": 110,
                "filters": {"InvalidFilter": ["value"]}
            }
        ]
    }
    
    # Mock mapper to return warning
    mock_mapper.map_filters_to_parts = AsyncMock(
        return_value=([], ["Unknown filter 'InvalidFilter'"])
    )
    
    # Act
    steps_json = await generator.generate_all_steps(recipe)
    
    # Assert
    assert len(steps_json) == 1
    # Step should still be generated even with warnings


@pytest.mark.asyncio
async def test_generate_batch_script(generator, mock_mapper):
    """Test batch script generation."""
    # Arrange
    recipe = {
        "investigation_steps": [
            {
                "title": "Step 1",
                "module_id": 110,
                "filters": {"Kommune": ["Aarhus"]}
            }
        ]
    }
    
    mock_mapper.map_filters_to_parts = AsyncMock(
        return_value=([{"modulePartId": 2, "values": ["Aarhus"]}], [])
    )
    
    # Act
    script = await generator.generate_batch_script(recipe, api_key_placeholder="TEST_KEY")
    
    # Assert
    assert "import requests" in script
    assert "API_KEY = \"TEST_KEY\"" in script
    assert "steps = [" in script
    assert "Step 1" in script
    assert "for i, step_data in enumerate(steps, 1):" in script
    assert "Created {len(created_steps)}/{len(steps)}" in script


@pytest.mark.asyncio
async def test_generate_batch_script_empty_recipe(generator, mock_mapper):
    """Test batch script generation with no valid steps."""
    # Arrange
    recipe = {"investigation_steps": []}
    
    # Act
    script = await generator.generate_batch_script(recipe)
    
    # Assert
    assert "No valid steps found in recipe" in script


@pytest.mark.asyncio
async def test_generate_batch_script_valid_python(generator, mock_mapper):
    """Test that generated batch script is valid Python code."""
    # Arrange
    recipe = {
        "investigation_steps": [
            {
                "title": "Test Step",
                "module_id": 110,
                "filters": {}
            }
        ]
    }
    
    mock_mapper.map_filters_to_parts = AsyncMock(return_value=([], []))
    
    # Act
    script = await generator.generate_batch_script(recipe)
    
    # Assert
    # Script should be valid Python (no syntax errors)
    try:
        compile(script, '<string>', 'exec')
    except SyntaxError:
        pytest.fail("Generated batch script has syntax errors")

