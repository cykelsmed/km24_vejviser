# DEBUG: Whitelist Verification Issues

## DISCOVERY: Whitelist Returns Empty Metadata

### Problem
Test viser at `get_module_filter_metadata()` returnerer tomt for ALLE moduler:

```
Kapitalændring:
  Module ID: N/A
  Available filters: 0

Registrering:
  Module ID: N/A
  Available filters: 0
```

### Root Cause Analysis

**Hypothesis:** `_get_module_id()` finder IKKE modulerne.

**Evidence:**
- `metadata = await filter_catalog.get_module_filter_metadata("Kapitalændring")`
- Returns: `{}`  (empty dict)
- Betyder: `module_id = None` → kan ikke hente module details

### Verificer Module Title Matching

File: `filter_catalog.py` → `_get_module_id()`

```python
def _get_module_id(self, module_name: str) -> Optional[int]:
    """Hent modul ID baseret på modulnavn."""
    if self._module_id_by_title:
        # Direct title match first
        mid = self._module_id_by_title.get(module_name)
        if mid is not None:
            return mid
        # Try a case-insensitive match
        for title, mid in self._module_id_by_title.items():
            if title.lower() == module_name.lower():
                return mid
    return None
```

**Potential Issues:**
1. `_module_id_by_title` er tom dict
2. Module titles ikke matcher præcist (fx "Kapitalændring" vs "Kapitalændringer")
3. Cache ikke loaded korrekt

### Test Module ID Lookup Directly

```python
# In test
fc = get_filter_catalog()
print(f"Available module titles: {list(fc._module_id_by_title.keys())[:10]}")
print(f"Kapitalændring ID: {fc._get_module_id('Kapitalændring')}")
print(f"Kapitalændringer ID: {fc._get_module_id('Kapitalændringer')}")
```

### FIX 1: Ensure modules_basic loaded

Problem: `_module_id_by_title` måske ikke populated.

**Check in `_load_modules_basic()`:**

```python
async def _load_modules_basic(self, force_refresh: bool = False) -> None:
    """Indlæs moduler (basic) og bygg opslags-tabeller for parts."""
    try:
        resp = await self.client.get_modules_basic(force_refresh)
        if resp.success and resp.data:
            items = resp.data.get('items', [])
            
            # DEBUG: Log what we got
            logger.info(f"Loading modules/basic: {len(items)} modules")
            
            self._module_id_by_title = {
                item.get('title', ''): int(item.get('id')) 
                for item in items 
                if item.get('id') is not None
            }
            
            # DEBUG: Log first 5 titles
            titles = list(self._module_id_by_title.keys())[:5]
            logger.info(f"Sample module titles: {titles}")
    except Exception as e:
        logger.warning(f"Kunne ikke indlæse modules basic: {e}")
```

### FIX 2: Add fallback module ID mapping

If API titles don't match recipe names exactly:

```python
# In FilterCatalog.__init__()
self._module_name_aliases = {
    "Kapitalændring": "Kapitalændringer",  # If plural in API
    "Registrering": "Registreringer",      # If plural in API
    "Tinglysning": "Tinglysninger",
    # etc.
}

def _get_module_id(self, module_name: str) -> Optional[int]:
    # Try direct match
    mid = self._module_id_by_title.get(module_name)
    if mid:
        return mid
    
    # Try alias
    alias = self._module_name_aliases.get(module_name)
    if alias:
        mid = self._module_id_by_title.get(alias)
        if mid:
            return mid
    
    # Try case-insensitive
    for title, mid in self._module_id_by_title.items():
        if title.lower() == module_name.lower():
            return mid
    
    return None
```

### FIX 3: Fallback to hardcoded IDs

If all else fails, use known module IDs from API:

```python
KNOWN_MODULE_IDS = {
    "Registrering": 610,
    "Kapitalændring": 630,
    "Status": 600,
    "Tinglysning": 102,
    "Lokalpolitik": 1500,
    "Arbejdstilsyn": 300,
    # etc.
}

def _get_module_id(self, module_name: str) -> Optional[int]:
    # Try cache first
    mid = self._module_id_by_title.get(module_name)
    if mid:
        return mid
    
    # Fallback to hardcoded
    mid = KNOWN_MODULE_IDS.get(module_name)
    if mid:
        logger.warning(f"Using hardcoded ID {mid} for {module_name}")
        return mid
    
    return None
```

---

## CRITICAL FINDING

**If `get_module_filter_metadata()` returns empty, whitelist becomes empty too!**

```python
# In validate_filters_against_api()
metadata = await filter_catalog.get_module_filter_metadata(module_name)
# Returns: {}

available = metadata.get("available_filters", {})
# Returns: {}

# BUILD WHITELIST
whitelist = set()

if "municipality" in available:  # False - ikke i {}
    whitelist.add("geografi")
# SKIPPED

if "industry" in available:  # False
    whitelist.add("branchekode")  
# SKIPPED

# Result: whitelist = set()  (EMPTY!)
```

**Med tom whitelist → ALLE filtre bliver rejected!**

Men wait... hvis whitelist er tom, hvorfor passerer filtre stadig gennem?

**AH! Period special case:**

```python
if module_name in ["Registrering", "Status", "Kapitalændring"]:
    whitelist.add("periode")
# This ALWAYS runs regardless of API
```

Så whitelist = {"periode"} for disse moduler.

Men i tidligere output så vi også "branchekode" osv. Så ENTEN:
1. Metadata ikke tom alligevel (test var i isolation)
2. Eller filtre tilføjes et andet sted

---

## ACTION PLAN

1. **Verificer _module_id_by_title populated**
   - Add logging to `_load_modules_basic()`
   - Print first 10 module titles
   - Check if "Kapitalændring" exists

2. **Test module ID lookup**
   - Create test that prints all available titles
   - Test exact match vs alias match

3. **Fix module name mismatch**
   - Add aliases if needed
   - Or use hardcoded IDs as fallback

4. **Re-test whitelist with proper metadata**
   - Once module lookup works, metadata should populate
   - Then whitelist should work correctly
   - Then test should show proper rejections

---

## NEXT STEPS

1. Fix `_get_module_id()` or `_load_modules_basic()`
2. Add debug logging to see what's in cache
3. Re-run tests to verify metadata loads
4. Then re-test whitelist filtering


