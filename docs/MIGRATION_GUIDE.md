# 🔄 KM24 API Migration Guide

## 🚨 Hvad Skal Ændres?

### Hovedproblemet

Din nuværende kode antager at KM24 API'et fungerer som en **search API** hvor du kan sende filtre direkte.

I virkeligheden er det en **subscription API** hvor du opretter overvågninger (steps) der kører automatisk.

---

## ❌ Forkert Tilgang (Din Nuværende Kode)

```python
# Dette virker IKKE i KM24
def get_hits(module_id, filters):
    response = requests.get(
        f"{BASE_URL}/hits",
        headers={"X-API-Key": API_KEY},
        params={
            "module": module_id,
            "kommune": filters.get("kommune"),
            "virksomhed": filters.get("virksomhed"),
            "soegeord": filters.get("soegeord")
        }
    )
    return response.json()

# Brug
hits = get_hits(280, {
    "kommune": ["Aarhus"],
    "soegeord": ["transport"]
})
```

**Problemer:**
1. `GET /api/hits` understøtter IKKE filter parameters
2. Du kan ikke sende `kommune`, `virksomhed` osv. som query params
3. Filtre håndteres gennem `parts` i step-oprettelse, ikke som URL params

---

## ✅ Korrekt Tilgang (Ny Kode)

```python
# Step 1: Hent modulePartId værdier først
def get_part_ids(module_id):
    """Hent parts for et modul og returner en mapping af slug -> id"""
    response = requests.get(
        f"{BASE_URL}/modules/basic/{module_id}",
        headers={"X-API-Key": API_KEY}
    )
    module = response.json()
    return {part['slug']: part['id'] for part in module['parts']}

# Step 2: Opret step med korrekt parts format
def create_monitoring(module_id, name, filters):
    """
    Opret en overvågning med filtre
    
    filters format:
    {
        'kommune': ['Aarhus', 'København'],
        'soegeord': ['transport', 'logistik'],
        'virksomhed': ['12345678']  # CVR numre!
    }
    """
    # Hent de rigtige part IDs
    part_ids = get_part_ids(module_id)
    
    # Byg parts array
    parts = []
    for filter_name, values in filters.items():
        if filter_name in part_ids:
            parts.append({
                "modulePartId": part_ids[filter_name],
                "values": values
            })
        else:
            print(f"⚠️ Warning: '{filter_name}' findes ikke i modul {module_id}")
    
    # Opret step
    step_data = {
        "name": name,
        "moduleId": module_id,
        "lookbackDays": 30,
        "onlyActive": False,
        "onlySubscribed": False,
        "parts": parts
    }
    
    response = requests.post(
        f"{BASE_URL}/steps/main",
        headers={"X-API-Key": API_KEY},
        json=step_data
    )
    
    return response.json()

# Step 3: Hent hits fra step'et
def get_step_hits(step_id, page=1, page_size=25):
    """Hent hits fra et eksisterende step"""
    response = requests.get(
        f"{BASE_URL}/steps/main/hits/{step_id}",
        headers={"X-API-Key": API_KEY},
        params={
            "page": page,
            "pageSize": page_size,
            "ordering": "-hitDatetime"  # Nyeste først
        }
    )
    return response.json()

# Brug:
# Opret step
step = create_monitoring(
    module_id=280,  # Udbud
    name="Udbud i Aarhus - Transport",
    filters={
        'kommune': ['Aarhus'],
        'soegeord': ['transport']
    }
)

print(f"Step oprettet med ID: {step['id']}")

# Hent hits
hits = get_step_hits(step['id'], page_size=50)
print(f"Fandt {hits['count']} hits")
```

---

## 🔧 Specifikke Ændringer per Projekt

### Projekt 1: Hvis du har en funktion der "søger" direkte

**Før:**
```python
def search_arbejdstilsyn(kommune, branche):
    return requests.get(
        f"{BASE_URL}/hits",
        params={"module": 110, "kommune": kommune, "branche": branche}
    ).json()
```

**Efter:**
```python
def create_arbejdstilsyn_monitoring(name, kommune=None, branche=None):
    parts = []
    part_ids = get_part_ids(110)  # Arbejdstilsyn
    
    if kommune:
        parts.append({
            "modulePartId": part_ids['kommune'],  # ID: 2
            "values": [kommune] if isinstance(kommune, str) else kommune
        })
    
    if branche:
        parts.append({
            "modulePartId": part_ids['branche'],  # ID: 5
            "values": [branche] if isinstance(branche, str) else branche
        })
    
    return requests.post(
        f"{BASE_URL}/steps/main",
        headers={"X-API-Key": API_KEY},
        json={
            "name": name,
            "moduleId": 110,
            "lookbackDays": 30,
            "parts": parts
        }
    ).json()

# Brug
step = create_arbejdstilsyn_monitoring(
    name="Byggevirksomheder i Aarhus",
    kommune="Aarhus",
    branche="412000"
)

# Hent hits senere
hits = get_step_hits(step['id'])
```

### Projekt 2: Hvis du har hardcoded filter-navne

**Før:**
```python
filters = {
    "kontraktvaerdi": 1000000,
    "virksomhed": ["Novo Nordisk"],
    "kommune": ["Aarhus"]
}
```

**Problem:** 
1. Filter-navne matcher ikke modulePartId værdier
2. Virksomhed skal være CVR nummer, ikke navn
3. Amount skal være string, ikke integer

**Efter:**
```python
# Først: Find CVR nummer
search = requests.get(
    f"{BASE_URL}/companies/add/search",
    params={"q": "novo nordisk"},
    headers={"X-API-Key": API_KEY}
).json()
novo_cvr = search['results'][0]['cvr']  # "24256790"

# Så: Brug korrekt format
parts = [
    {
        "modulePartId": 137,  # Kontraktværdi (find ID fra modul først!)
        "values": ["1000000"]  # String, ikke integer!
    },
    {
        "modulePartId": 133,  # Virksomhed
        "values": [novo_cvr]  # CVR nummer, ikke navn!
    },
    {
        "modulePartId": 134,  # Kommune (ID kan variere!)
        "values": ["Aarhus"]
    }
]
```

### Projekt 3: Hvis du cache'r eller gemmer resultater

**Før:**
```python
def get_and_cache_hits(query):
    cache_key = f"hits_{query['module']}_{query['kommune']}"
    
    if cache_key in cache:
        return cache[cache_key]
    
    hits = requests.get(f"{BASE_URL}/hits", params=query).json()
    cache[cache_key] = hits
    return hits
```

**Efter:**
```python
def get_or_create_step(module_id, name, filters):
    """Generer step eller genbruger eksisterende"""
    # Check om step allerede eksisterer
    existing_steps = requests.get(
        f"{BASE_URL}/steps/main",
        headers={"X-API-Key": API_KEY},
        params={"moduleId": module_id}
    ).json()
    
    # Find matching step ved navn
    for step in existing_steps['items']:
        if step['name'] == name:
            return step
    
    # Opret nyt step hvis det ikke findes
    return create_monitoring(module_id, name, filters)

def get_cached_hits(step_id):
    """Cache hits fra et step"""
    cache_key = f"hits_{step_id}"
    
    # Check cache (med TTL)
    if cache_key in cache and not cache_expired(cache_key):
        return cache[cache_key]
    
    # Hent fra API
    hits = get_step_hits(step_id)
    cache[cache_key] = hits
    return hits
```

---

## 📋 Migration Checklist

### For Hvert Projekt:

- [ ] **Identificer search funktioner**
  - Find alle steder hvor du kalder API'et med filtre
  - Notér hvilke moduler de bruger
  - Notér hvilke filtre de prøver at sende

- [ ] **Map filtre til modulePartId**
  - For hvert modul: Hent `GET /api/modules/basic/{id}`
  - Lav en mapping: `{'kommune': 2, 'branche': 5, ...}`
  - Gem denne mapping (den ændrer sig sjældent)

- [ ] **Omskriv til step-baseret**
  - Erstat søge-funktioner med step-oprettelses-funktioner
  - Tilføj funktioner til at hente hits fra steps
  - Håndter step lifecycle (opret, hent, slet)

- [ ] **Test hver ændring**
  - Opret testStep
  - Verificer at det får hits
  - Check at filtre virker som forventet

- [ ] **Opdater error handling**
  - Steps kan oprettes selvom filtre er forkerte
  - Check for tomme resultater
  - Valider modulePartId før oprettelse

- [ ] **Dokumenter nye modulePartId værdier**
  - Lav en reference fil med ID'er for dine moduler
  - Kommenter din kode med hvilke ID'er du bruger

---

## 🔍 Debugging Guide

### "Jeg får ingen hits!"

**Tjek 1: Er dit step overhovedet oprettet?**
```python
steps = requests.get(
    f"{BASE_URL}/steps/main",
    headers={"X-API-Key": API_KEY}
).json()

print("Dine steps:")
for step in steps['items']:
    print(f"- {step['name']} (ID: {step['id']}, Module: {step['moduleId']})")
```

**Tjek 2: Har step'et de rigtige filtre?**
```python
step = requests.get(
    f"{BASE_URL}/steps/main/{step_id}",
    headers={"X-API-Key": API_KEY}
).json()

print("Step parts:")
for part in step['parts']:
    print(f"- Part ID {part['modulePartId']}: {part['values']}")
```

**Tjek 3: Er dine modulePartId værdier korrekte?**
```python
# Hent modul og sammenlign
module = requests.get(
    f"{BASE_URL}/modules/basic/{module_id}",
    headers={"X-API-Key": API_KEY}
).json()

print("Tilgængelige parts:")
for part in module['parts']:
    print(f"- {part['name']} ({part['slug']}): ID {part['id']}")

# Sammenlign med dit step
print("\nDit step bruger:")
for part in step['parts']:
    matching = next((p for p in module['parts'] if p['id'] == part['modulePartId']), None)
    if matching:
        print(f"✅ Part ID {part['modulePartId']}: {matching['name']}")
    else:
        print(f"❌ Part ID {part['modulePartId']}: IKKE FUNDET I MODUL!")
```

### "Jeg ved ikke hvilket modulePartId jeg skal bruge!"

**Løsning: Hent altid modulet først**
```python
def print_module_parts(module_id):
    """Print alle tilgængelige parts for et modul"""
    module = requests.get(
        f"{BASE_URL}/modules/basic/{module_id}",
        headers={"X-API-Key": API_KEY}
    ).json()
    
    print(f"\n📋 Parts for {module['title']} (ID: {module_id}):\n")
    print(f"{'ID':<6} {'Slug':<20} {'Navn':<25} {'Multi?':<8}")
    print("-" * 65)
    
    for part in sorted(module['parts'], key=lambda x: x['order']):
        print(f"{part['id']:<6} {part['slug']:<20} {part['name']:<25} "
              f"{'Ja' if part['canSelectMultiple'] else 'Nej':<8}")

# Brug
print_module_parts(280)  # Udbud
print_module_parts(110)  # Arbejdstilsyn
print_module_parts(510)  # Danske Medier
```

---

## 💡 Tips

### 1. Lav en Part ID Cache

```python
import json
from pathlib import Path

class PartIDCache:
    def __init__(self, cache_dir="./km24_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_part_ids(self, module_id):
        """Hent part IDs (fra cache hvis muligt)"""
        cache_file = self.cache_dir / f"module_{module_id}_parts.json"
        
        # Check cache
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        
        # Hent fra API
        response = requests.get(
            f"{BASE_URL}/modules/basic/{module_id}",
            headers={"X-API-Key": API_KEY}
        )
        module = response.json()
        
        part_ids = {
            part['slug']: {
                'id': part['id'],
                'name': part['name'],
                'canSelectMultiple': part['canSelectMultiple']
            }
            for part in module['parts']
        }
        
        # Gem i cache
        with open(cache_file, 'w') as f:
            json.dump(part_ids, f, indent=2)
        
        return part_ids

# Brug
cache = PartIDCache()
parts = cache.get_part_ids(280)
print(f"Kommune part ID: {parts['kommune']['id']}")
```

### 2. Lav en Step Manager Klasse

```python
class StepManager:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}
        self.cache = PartIDCache()
    
    def create_step(self, module_id, name, filters, lookback_days=30):
        """Opret step med automatic part ID resolution"""
        part_ids = self.cache.get_part_ids(module_id)
        
        parts = []
        for filter_slug, values in filters.items():
            if filter_slug not in part_ids:
                print(f"⚠️ Warning: '{filter_slug}' findes ikke i modul {module_id}")
                continue
            
            # Ensure values is a list
            if not isinstance(values, list):
                values = [values]
            
            parts.append({
                "modulePartId": part_ids[filter_slug]['id'],
                "values": values
            })
        
        step_data = {
            "name": name,
            "moduleId": module_id,
            "lookbackDays": lookback_days,
            "parts": parts
        }
        
        response = requests.post(
            f"{BASE_URL}/steps/main",
            headers=self.headers,
            json=step_data
        )
        response.raise_for_status()
        return response.json()
    
    def get_hits(self, step_id, page=1, page_size=25):
        """Hent hits fra step"""
        response = requests.get(
            f"{BASE_URL}/steps/main/hits/{step_id}",
            headers=self.headers,
            params={"page": page, "pageSize": page_size}
        )
        return response.json()
    
    def list_steps(self, module_id=None):
        """List alle steps"""
        params = {"moduleId": module_id} if module_id else {}
        response = requests.get(
            f"{BASE_URL}/steps/main",
            headers=self.headers,
            params=params
        )
        return response.json()

# Brug
manager = StepManager(API_KEY)

# Opret step med slug-navne (ikke part IDs!)
step = manager.create_step(
    module_id=280,
    name="Udbud i Aarhus",
    filters={
        'kommune': ['Aarhus'],
        'soegeord': ['transport', 'logistik']
    }
)

# Hent hits
hits = manager.get_hits(step['id'])
```

---

## 🎯 Konklusion

**Husk:**
1. KM24 er subscription-based, ikke search-based
2. Filtre sendes som `parts` med `modulePartId`, ikke som query parameters
3. Du skal altid hente modul-data først for at finde de rigtige ID'er
4. Steps valideres IKKE ved oprettelse - tjek altid for hits bagefter

**Næste skridt:**
1. Gennemgå dine tre projekter
2. Identificer alle API kald
3. Brug denne guide til at omskrive dem
4. Test grundigt

Held og lykke med migrationen! 🚀