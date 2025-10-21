"""
Tests for PartIdMapper - modulePartId mapping functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from km24_vejviser.part_id_mapper import PartIdMapper
from km24_vejviser.km24_client import KM24APIResponse


@pytest.fixture
def mock_client():
    """Mock KM24 client with predefined responses."""
    client = MagicMock()
    return client


@pytest.fixture
def mapper(mock_client):
    """PartIdMapper instance with mocked client."""
    return PartIdMapper(km24_client=mock_client)


@pytest.fixture
def arbejdstilsyn_parts():
    """Mock Arbejdstilsyn module parts."""
    return {
        "parts": [
            {"id": 204, "name": "Oprindelsesland", "slug": "oprindelsesland"},
            {"id": 205, "name": "Problem", "slug": "problem"},
            {"id": 206, "name": "Reaktion", "slug": "reaktion"},
            {"id": 5, "name": "Branche", "slug": "branche"},
            {"id": 3, "name": "Virksomhed", "slug": "virksomhed"},
            {"id": 2, "name": "Kommune", "slug": "kommune"},
        ]
    }


@pytest.mark.asyncio
async def test_get_part_id_mapping_success(mapper, mock_client, arbejdstilsyn_parts):
    """Test successful part ID mapping retrieval."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    # Act
    mapping = await mapper.get_part_id_mapping(110)
    
    # Assert
    assert mapping["Kommune"] == 2
    assert mapping["Problem"] == 205
    assert mapping["Branche"] == 5
    assert mapping["kommune"] == 2  # Case-insensitive
    mock_client.get_module_details.assert_called_once_with(110, force_refresh=False)


@pytest.mark.asyncio
async def test_get_part_id_mapping_cached(mapper, mock_client, arbejdstilsyn_parts):
    """Test that mapping is cached after first fetch."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    # Act
    mapping1 = await mapper.get_part_id_mapping(110)
    mapping2 = await mapper.get_part_id_mapping(110)
    
    # Assert
    assert mapping1 == mapping2
    # Should only call API once due to caching
    mock_client.get_module_details.assert_called_once()


@pytest.mark.asyncio
async def test_get_part_id_mapping_api_failure(mapper, mock_client):
    """Test handling of API failure."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=False,
            error="API Error"
        )
    )
    
    # Act & Assert
    with pytest.raises(ValueError, match="Failed to fetch module 110"):
        await mapper.get_part_id_mapping(110)


@pytest.mark.asyncio
async def test_map_filters_to_parts_success(mapper, mock_client, arbejdstilsyn_parts):
    """Test successful filter to parts mapping."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    filters = {
        "Kommune": ["Aarhus"],
        "Problem": ["Asbest", "Støj"]
    }
    
    # Act
    parts, warnings = await mapper.map_filters_to_parts(110, filters)
    
    # Assert
    assert len(parts) == 2
    assert parts[0] == {"modulePartId": 2, "values": ["Aarhus"]}
    assert parts[1] == {"modulePartId": 205, "values": ["Asbest", "Støj"]}
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_map_filters_to_parts_case_insensitive(mapper, mock_client, arbejdstilsyn_parts):
    """Test case-insensitive filter mapping."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    filters = {
        "kommune": ["Aarhus"],  # lowercase
        "PROBLEM": ["Asbest"]   # uppercase
    }
    
    # Act
    parts, warnings = await mapper.map_filters_to_parts(110, filters)
    
    # Assert
    assert len(parts) == 2
    assert parts[0]["modulePartId"] == 2
    assert parts[1]["modulePartId"] == 205


@pytest.mark.asyncio
async def test_map_filters_to_parts_unknown_filter(mapper, mock_client, arbejdstilsyn_parts):
    """Test handling of unknown filter names."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    filters = {
        "Kommune": ["Aarhus"],
        "UnknownFilter": ["value"]  # This filter doesn't exist
    }
    
    # Act
    parts, warnings = await mapper.map_filters_to_parts(110, filters)
    
    # Assert
    assert len(parts) == 1  # Only valid filter mapped
    assert parts[0]["modulePartId"] == 2
    assert len(warnings) == 1
    assert "UnknownFilter" in warnings[0]


@pytest.mark.asyncio
async def test_map_filters_to_parts_empty_filters(mapper, mock_client):
    """Test handling of empty filters."""
    # Act
    parts, warnings = await mapper.map_filters_to_parts(110, {})
    
    # Assert
    assert len(parts) == 0
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_map_filters_to_parts_empty_values(mapper, mock_client, arbejdstilsyn_parts):
    """Test handling of filters with empty values."""
    # Arrange
    mock_client.get_module_details = AsyncMock(
        return_value=KM24APIResponse(
            success=True,
            data=arbejdstilsyn_parts
        )
    )
    
    filters = {
        "Kommune": [],  # Empty values
        "Problem": ["Asbest"]
    }
    
    # Act
    parts, warnings = await mapper.map_filters_to_parts(110, filters)
    
    # Assert
    assert len(parts) == 1  # Only non-empty filter
    assert parts[0]["modulePartId"] == 205


def test_validate_filter_names_success(mapper):
    """Test validation of filter names."""
    # Arrange
    part_mapping = {"Kommune": 2, "Problem": 205}
    filter_names = ["Kommune", "Problem"]
    
    # Act
    results = mapper.validate_filter_names(110, filter_names, part_mapping)
    
    # Assert
    assert results["Kommune"] is True
    assert results["Problem"] is True


def test_validate_filter_names_invalid(mapper):
    """Test validation catches invalid filter names."""
    # Arrange
    part_mapping = {"Kommune": 2, "Problem": 205}
    filter_names = ["Kommune", "InvalidFilter"]
    
    # Act
    results = mapper.validate_filter_names(110, filter_names, part_mapping)
    
    # Assert
    assert results["Kommune"] is True
    assert results["InvalidFilter"] is False


def test_get_part_id_for_filter_exact_match(mapper):
    """Test getting part ID with exact name match."""
    # Arrange
    part_mapping = {"Kommune": 2, "Problem": 205}
    
    # Act
    part_id = mapper.get_part_id_for_filter("Kommune", part_mapping)
    
    # Assert
    assert part_id == 2


def test_get_part_id_for_filter_case_insensitive(mapper):
    """Test getting part ID with case-insensitive match."""
    # Arrange
    part_mapping = {"Kommune": 2, "kommune": 2, "Problem": 205}
    
    # Act
    part_id = mapper.get_part_id_for_filter("kommune", part_mapping)
    
    # Assert
    assert part_id == 2


def test_get_part_id_for_filter_not_found(mapper):
    """Test getting part ID for non-existent filter."""
    # Arrange
    part_mapping = {"Kommune": 2}
    
    # Act
    part_id = mapper.get_part_id_for_filter("InvalidFilter", part_mapping)
    
    # Assert
    assert part_id is None

