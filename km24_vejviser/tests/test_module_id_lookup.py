"""Test module ID lookup to debug whitelist issues."""
import pytest
from km24_vejviser.filter_catalog import get_filter_catalog

@pytest.mark.asyncio
async def test_module_id_cache_populated():
    """Test if _module_id_by_title is populated."""
    fc = get_filter_catalog()
    
    # Force load if needed
    await fc.load_all_filters(force_refresh=False)
    
    print(f"\n=== Module ID Cache ===")
    print(f"Total modules in cache: {len(fc._module_id_by_title)}")
    
    if fc._module_id_by_title:
        print(f"\nFirst 10 module titles:")
        for title, module_id in list(fc._module_id_by_title.items())[:10]:
            print(f"  - {title}: {module_id}")
    else:
        print("❌ Cache is EMPTY!")
    
    # Test specific lookups
    test_names = ["Kapitalændring", "Kapitalændringer", "Registrering", "Registreringer"]
    
    print(f"\n=== Testing Module Lookups ===")
    for name in test_names:
        module_id = fc._get_module_id(name)
        status = "✅" if module_id else "❌"
        print(f"{status} {name}: {module_id}")
    
    # Try case-insensitive search
    print(f"\n=== Case-insensitive search ===")
    for title in fc._module_id_by_title.keys():
        if "kapital" in title.lower():
            print(f"Found: {title}")
        if "registr" in title.lower():
            print(f"Found: {title}")

@pytest.mark.asyncio
async def test_actual_api_titles():
    """Get actual titles from API."""
    fc = get_filter_catalog()
    
    response = await fc.client.get_modules_basic()
    
    if response.success and response.data:
        items = response.data.get('items', [])
        print(f"\n=== Actual API Module Titles ({len(items)} total) ===")
        
        # Find relevant ones
        for item in items:
            title = item.get('title', '')
            module_id = item.get('id')
            if any(keyword in title.lower() for keyword in ['kapital', 'registr', 'status', 'tinglys', 'arbej']):
                print(f"  - {title}: {module_id}")


