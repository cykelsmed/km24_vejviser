"""
Test whitelist verification - verificer at filtre faktisk er valid.
"""
import pytest
from km24_vejviser.filter_catalog import get_filter_catalog

@pytest.mark.asyncio
async def test_kapitalaendring_has_municipality():
    """
    Test om Kapitalændring-modulet har municipality filter.
    Hvis IKKE → whitelist fejler.
    """
    fc = get_filter_catalog()
    metadata = await fc.get_module_filter_metadata("Kapitalændring")
    
    available = metadata.get("available_filters", {})
    
    print("\n=== Kapitalændring Available Filters ===")
    print(f"Filter types: {list(available.keys())}")
    for filter_type, details in available.items():
        print(f"  - {filter_type}: {details}")
    
    has_municipality = "municipality" in available
    print(f"\nMunicipality filter: {'✅ EXISTS' if has_municipality else '❌ MISSING'}")
    
    # If missing, geografi should have been rejected
    if not has_municipality:
        print("\n⚠️ WARNING: 'geografi' filter on Kapitalændring should be REJECTED by whitelist")
        print("This indicates whitelist is NOT working correctly")
    
    return has_municipality

@pytest.mark.asyncio
async def test_lokalpolitik_has_municipality():
    """Test om Lokalpolitik har municipality filter."""
    fc = get_filter_catalog()
    metadata = await fc.get_module_filter_metadata("Lokalpolitik")
    
    available = metadata.get("available_filters", {})
    
    print("\n=== Lokalpolitik Available Filters ===")
    print(f"Filter types: {list(available.keys())}")
    for filter_type, details in available.items():
        print(f"  - {filter_type}: {details}")
    
    has_municipality = "municipality" in available
    print(f"\nMunicipality filter: {'✅ EXISTS' if has_municipality else '❌ MISSING'}")
    
    return has_municipality

@pytest.mark.asyncio
async def test_registrering_filters():
    """Test Registrering filter capabilities."""
    fc = get_filter_catalog()
    metadata = await fc.get_module_filter_metadata("Registrering")
    
    available = metadata.get("available_filters", {})
    
    print("\n=== Registrering Available Filters ===")
    print(f"Filter types: {list(available.keys())}")
    
    has_municipality = "municipality" in available
    has_industry = "industry" in available
    
    print(f"Municipality: {'✅' if has_municipality else '❌'}")
    print(f"Industry: {'✅' if has_industry else '❌'}")
    
    return available

@pytest.mark.asyncio
async def test_arbejdstilsyn_generic_values():
    """Test Arbejdstilsyn generic_value parts."""
    fc = get_filter_catalog()
    metadata = await fc.get_module_filter_metadata("Arbejdstilsyn")
    
    available = metadata.get("available_filters", {})
    
    print("\n=== Arbejdstilsyn Available Filters ===")
    print(f"Filter types: {list(available.keys())}")
    
    if "generic_value" in available:
        print("\nGeneric value parts:")
        for part in available["generic_value"]["parts"]:
            part_name = part["part_name"]
            values_count = len(part["values"])
            print(f"  - {part_name}: {values_count} values")
            print(f"    Sample values: {part['values'][:5]}")
    
    return available

@pytest.mark.asyncio
async def test_tinglysning_filters():
    """Test Tinglysning filter capabilities."""
    fc = get_filter_catalog()
    metadata = await fc.get_module_filter_metadata("Tinglysning")
    
    available = metadata.get("available_filters", {})
    
    print("\n=== Tinglysning Available Filters ===")
    print(f"Filter types: {list(available.keys())}")
    
    has_amount = "amount_selection" in available
    has_generic = "generic_value" in available
    
    print(f"Amount selection (beløbsgrænse): {'✅' if has_amount else '❌'}")
    print(f"Generic values: {'✅' if has_generic else '❌'}")
    
    if has_generic:
        print("\nGeneric value parts:")
        for part in available["generic_value"]["parts"]:
            print(f"  - {part['part_name']}")
    
    return available

@pytest.mark.asyncio  
async def test_periode_filter_support():
    """
    Test hvilke moduler faktisk har periode filter.
    Periode er typisk IKKE en API part, men en frontend convenience.
    """
    fc = get_filter_catalog()
    
    modules_to_test = ["Registrering", "Kapitalændring", "Tinglysning", "Lokalpolitik", "Status"]
    
    print("\n=== Periode Filter Support ===")
    print("Note: Periode is typically a date-range filter, not a module part")
    
    for module_name in modules_to_test:
        metadata = await fc.get_module_filter_metadata(module_name)
        available = metadata.get("available_filters", {})
        
        # Check if any part mentions periode/date/time
        has_date_filter = any(
            "date" in str(part).lower() or 
            "time" in str(part).lower() or
            "periode" in str(part).lower()
            for part in available.values()
        )
        
        status = "✅" if has_date_filter else "❌"
        print(f"{status} {module_name}: {'Has date filter' if has_date_filter else 'NO date filter in parts'}")
        
        # Periode is probably always allowed as it's a date range, not a module part
        print(f"   → But 'periode' may still be valid as date-range parameter")

@pytest.mark.asyncio
async def test_all_modules_summary():
    """Get comprehensive summary of all modules."""
    fc = get_filter_catalog()
    
    modules = ["Registrering", "Status", "Kapitalændring", "Tinglysning", 
               "Lokalpolitik", "Arbejdstilsyn", "Udbud", "Domme"]
    
    print("\n=== ALL MODULES FILTER SUMMARY ===\n")
    
    for module_name in modules:
        try:
            metadata = await fc.get_module_filter_metadata(module_name)
            available = metadata.get("available_filters", {})
            
            print(f"\n{module_name}:")
            print(f"  Module ID: {metadata.get('module_id', 'N/A')}")
            print(f"  Available filters: {len(available)}")
            
            # Standard filters
            std_filters = []
            if "municipality" in available:
                std_filters.append("municipality")
            if "industry" in available:
                std_filters.append("industry")
            if "company" in available:
                std_filters.append("company")
            if "amount_selection" in available:
                std_filters.append("amount_selection")
            if "web_source" in available:
                std_filters.append("web_source")
            
            if std_filters:
                print(f"  Standard: {', '.join(std_filters)}")
            
            # Generic values
            if "generic_value" in available:
                parts = available["generic_value"]["parts"]
                part_names = [p["part_name"] for p in parts]
                print(f"  Generic values ({len(parts)}): {', '.join(part_names)}")
        
        except Exception as e:
            print(f"\n{module_name}: ERROR - {e}")


