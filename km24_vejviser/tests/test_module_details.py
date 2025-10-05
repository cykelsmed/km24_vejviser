"""Test module details API call."""

import pytest
from km24_vejviser.filter_catalog import get_filter_catalog


@pytest.mark.asyncio
async def test_get_module_details():
    """Test getting module details for Kapitalændring."""
    fc = get_filter_catalog()

    # Force load modules first
    await fc.load_all_filters(force_refresh=False)

    # Get module ID
    module_id = fc._get_module_id("Kapitalændring")
    print(f"\n=== Kapitalændring Module ID: {module_id} ===")

    if not module_id:
        print("❌ Could not find module ID!")
        return

    # Get module details
    details = await fc.client.get_module_details(module_id)

    print(f"\nAPI call success: {details.success}")
    print(f"Error: {details.error if not details.success else 'None'}")

    if details.success and details.data:
        parts = details.data.get("parts", [])
        print(f"\nNumber of parts: {len(parts)}")

        print("\nParts breakdown:")
        for part in parts:
            part_type = part.get("part")
            part_name = part.get("name")
            part_id = part.get("id")
            print(f"  - {part_type}: {part_name} (ID: {part_id})")


@pytest.mark.asyncio
async def test_get_module_filter_metadata_direct():
    """Test get_module_filter_metadata directly."""
    fc = get_filter_catalog()

    # Load cache first (like server does at startup)
    await fc.load_all_filters(force_refresh=False)

    module_name = "Kapitalændring"
    print(f"\n=== Testing get_module_filter_metadata for {module_name} ===")

    metadata = await fc.get_module_filter_metadata(module_name)

    print(f"\nMetadata keys: {list(metadata.keys())}")
    print(f"Module ID: {metadata.get('module_id', 'N/A')}")
    print(f"Module title: {metadata.get('module_title', 'N/A')}")

    available = metadata.get("available_filters", {})
    print(f"\nAvailable filter types: {list(available.keys())}")

    if available:
        for filter_type, details in available.items():
            print(f"\n{filter_type}:")
            print(f"  {details}")


@pytest.mark.asyncio
async def test_tinglysning_filters():
    """Test Tinglysning which should have amount_selection."""
    fc = get_filter_catalog()

    print("\n=== Testing Tinglysning Filters ===")

    metadata = await fc.get_module_filter_metadata("Tinglysning")

    available = metadata.get("available_filters", {})
    print(f"Available filter types: {list(available.keys())}")

    has_amount = "amount_selection" in available
    has_municipality = "municipality" in available

    print(f"\nAmount selection: {'✅' if has_amount else '❌'}")
    print(f"Municipality: {'✅' if has_municipality else '❌'}")
