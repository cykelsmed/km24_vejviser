# 🚀 KM24 API Quick Reference

## 🔑 Setup

```python
import requests

BASE_URL = "https://km24.dk/api"
API_KEY = "your_api_key_here"
headers = {"X-API-Key": API_KEY}
```

---

## 📋 Module Operations

### List Alle Moduler
```python
modules = requests.get(f"{BASE_URL}/modules/basic", headers=headers).json()

for module in modules['items']:
    print(f"{module['id']}: {module['title']} {module['emoji']}")
```

### Hent Modul med Parts
```python
module_id = 280  # Udbud
module = requests.get(f"{BASE_URL}/modules/basic/{module_id}", headers=headers).json()

# Print parts
for part in module['parts']:
    print(f"ID {part['id']}: {part['name']} ({part['slug']})")
```

### Quick Part ID Lookup
```python
def get_part_ids(module_id):
    module = requests.get(f"{BASE_URL}/modules/basic/{module_id}", headers=headers).json()
    return {p['slug']: p['id'] for p in module['parts']}

# Brug
parts = get_part_ids(280)
print(f"Kommune: {parts['kommune']}")
print(f"Søgeord: {parts['soegeord']}")
```

---

## 📝 Step (Overvågning) Operations

### Opret Step
```python
step_data = {
    "name": "Mit step navn",
    "moduleId": 280,
    "lookbackDays": 30,
    "parts": [
        {
            "modulePartId": 134,  # Kommune
            "values": ["Aarhus", "København"]
        },
        {
            "modulePartId": 136,  # Søgeord
            "values": ["transport"]
        }
    ]
}

step = requests.post(f"{BASE_URL}/steps/main", headers=headers, json=step_data).json()
step_id = step['id']
```

### List Dine Steps
```python
# Alle steps
steps = requests.get(f"{BASE_URL}/steps/main", headers=headers).json()

# Steps for specifikt modul
steps = requests.get(
    f"{BASE_URL}/steps/main",
    headers=headers,
    params={"moduleId": 280}
).json()

for step in steps['items']:
    print(f"{step['id']}: {step['name']} ({step['hitCount']} hits)")
```

### Hent Hits fra Step
```python
hits = requests.get(
    f"{BASE_URL}/steps/main/hits/{step_id}",
    headers=headers,
    params={
        "page": 1,
        "pageSize": 50,
        "ordering": "-hitDatetime"  # Nyeste først
    }
).json()

print(f"Total hits: {hits['count']}")
for hit in hits['items']:
    print(f"- {hit['title']} ({hit['hitDatetime']})")
```

### Slet Step
```python
requests.delete(f"{BASE_URL}/steps/main/{step_id}", headers=headers)
```

---

## 🏢 Virksomhed Operations

### Søg Virksomhed
```python
search = requests.get(
    f"{BASE_URL}/companies/add/search",
    headers=headers,
    params={"q": "novo nordisk"}
).json()

for company in search['results']:
    print(f"{company['name']} - CVR: {company['cvr']}")
```

### Find CVR Nummer
```python
def get_cvr(company_name):
    search = requests.get(
        f"{BASE_URL}/companies/add/search",
        headers=headers,
        params={"q": company_name}
    ).json()
    
    if search['results']:
        return search['results'][0]['cvr']
    return None

# Brug
cvr = get_cvr("novo nordisk")  # Returns: "24256790"
```

### Subscribe til Virksomhed
```python
# Subscribe
requests.post(
    f"{BASE_URL}/companies/main/{module_id}/subscribe",
    headers=headers,
    params={"cvr": 24256790}
)

# Unsubscribe
requests.delete(
    f"{BASE_URL}/companies/main/{module_id}/subscribe",
    headers=headers,
    params={"cvr": 24256790}
)
```

---

## 🔍 Almindelige Moduler & Part IDs

### Udbud (280)
```python
parts = {
    137: "Kontraktværdi",
    133: "Virksomhed",
    134: "Kommune",
    136: "Søgeord",
    138: "Hitlogik"
}
```

**Eksempel:**
```python
step = {
    "name": "Udbud i Aarhus over 10 mio",
    "moduleId": 280,
    "lookbackDays": 30,
    "parts": [
        {"modulePartId": 137, "values": ["10000000"]},
        {"modulePartId": 134, "values": ["Aarhus"]}
    ]
}
```

### Arbejdstilsyn (110)
```python
parts = {
    204: "Oprindelsesland",
    205: "Problem",
    206: "Reaktion",
    5: "Branche",
    3: "Virksomhed",
    2: "Kommune",
    9: "Hitlogik"
}
```

**Eksempel:**
```python
step = {
    "name": "Påbud i byggebranchen",
    "moduleId": 110,
    "lookbackDays": 90,
    "parts": [
        {"modulePartId": 206, "values": ["Påbud"]},
        {"modulePartId": 5, "values": ["412000"]}
    ]
}
```

### Danske Medier (510)
```python
parts = {
    54: "Medie",
    52: "Virksomhed",
    53: "Søgeord",
    198: "Hitlogik"
}
```

**Eksempel:**
```python
step = {
    "name": "Novo Nordisk i medierne",
    "moduleId": 510,
    "lookbackDays": 7,
    "parts": [
        {"modulePartId": 52, "values": ["24256790"]},  # CVR!
        {"modulePartId": 53, "values": ["diabetes", "ozempic"]}
    ]
}
```

### Domme (250)
```python
parts = {
    197: "Ret",
    283: "Gerningskode",
    66: "Branche",
    67: "Virksomhed",
    70: "Søgeord",
    71: "Hitlogik"
}
```

### Boligsiden (1400)
```python
parts = {
    31: "Adressetype",
    30: "Beløb",
    245: "BFE",
    24: "Branche",
    25: "Virksomhed",
    26: "Kommune",
    27: "Søgeord",
    29: "Hitlogik"
}
```

**Eksempel:**
```python
step = {
    "name": "Boliger over 5 mio i Aarhus",
    "moduleId": 1400,
    "lookbackDays": 14,
    "parts": [
        {"modulePartId": 30, "values": ["5000000"]},
        {"modulePartId": 26, "values": ["Aarhus"]}
    ]
}
```

---

## 🎯 Komplette Use Cases

### Use Case 1: Overvåg Transportvirksomheder med Påbud

```python
# Step 1: Find branchekode for transport
# 493100 = Godstransport på vej

# Step 2: Opret step
step = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json={
        "name": "Transport påbud - Trekantområdet",
        "moduleId": 110,  # Arbejdstilsyn
        "lookbackDays": 60,
        "parts": [
            {"modulePartId": 5, "values": ["493100"]},  # Branche
            {"modulePartId": 206, "values": ["Påbud"]},  # Reaktion
            {"modulePartId": 2, "values": ["Vejle", "Kolding", "Fredericia"]}  # Kommune
        ]
    }
).json()

# Step 3: Hent hits
hits = requests.get(
    f"{BASE_URL}/steps/main/hits/{step['id']}",
    headers=headers,
    params={"pageSize": 100}
).json()

# Step 4: Analyser
for hit in hits['items']:
    print(f"\n{hit['title']}")
    print(f"Dato: {hit['hitDatetime']}")
    if hit.get('companies'):
        for company in hit['companies']:
            print(f"Virksomhed: {company['name']} (CVR: {company['cvr']})")
```

### Use Case 2: Find Konkursryttere

```python
# Kombiner Arbejdstilsyn + Konkurs for at finde konkursryttere

# Step 1: Opret arbejdstilsyn overvågning
at_step = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json={
        "name": "Arbejdstilsyn - Byggebranchen",
        "moduleId": 110,
        "lookbackDays": 180,
        "parts": [
            {"modulePartId": 5, "values": ["412000", "421100", "429000"]},  # Byggerelaterede brancher
            {"modulePartId": 206, "values": ["Påbud", "Forbud"]}
        ]
    }
).json()

# Step 2: Opret konkurs overvågning (Statstidende)
konkurs_step = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json={
        "name": "Konkurser - Byggebranchen",
        "moduleId": 170,  # Statstidende (antaget ID)
        "lookbackDays": 180,
        "parts": [
            {"modulePartId": 5, "values": ["412000", "421100", "429000"]}
        ]
    }
).json()

# Step 3: Hent hits fra begge
at_hits = requests.get(f"{BASE_URL}/steps/main/hits/{at_step['id']}", headers=headers).json()
konkurs_hits = requests.get(f"{BASE_URL}/steps/main/hits/{konkurs_step['id']}", headers=headers).json()

# Step 4: Find overlap (virksomheder i begge)
at_cvrs = {c['cvr'] for hit in at_hits['items'] for c in hit.get('companies', [])}
konkurs_cvrs = {c['cvr'] for hit in konkurs_hits['items'] for c in hit.get('companies', [])}

konkursryttere = at_cvrs & konkurs_cvrs
print(f"Fandt {len(konkursryttere)} mulige konkursryttere")
```

### Use Case 3: Medieovervågning af Portefølje

```python
# Step 1: Define portfolio
portfolio = {
    "Novo Nordisk": "24256790",
    "Vestas": "10403782",
    "Mærsk": "22756214"
}

# Step 2: Opret step for hver virksomhed
steps = {}
for name, cvr in portfolio.items():
    step = requests.post(
        f"{BASE_URL}/steps/main",
        headers=headers,
        json={
            "name": f"Medieomtale - {name}",
            "moduleId": 510,  # Danske Medier
            "lookbackDays": 7,
            "parts": [
                {"modulePartId": 52, "values": [cvr]}
            ]
        }
    ).json()
    steps[name] = step['id']

# Step 3: Hent hits for hver
for name, step_id in steps.items():
    hits = requests.get(
        f"{BASE_URL}/steps/main/hits/{step_id}",
        headers=headers
    ).json()
    
    print(f"\n{name}: {hits['count']} artikler")
    for hit in hits['items'][:5]:  # Vis kun de 5 nyeste
        print(f"  - {hit['title']}")
```

---

## 🛠️ Utility Functions

### Helper: Smart Step Creator
```python
def create_step_smart(module_id, name, **filters):
    """
    Opret step med automatisk part ID lookup
    
    Eksempel:
    create_step_smart(
        280,
        "Mit step",
        kommune=["Aarhus"],
        soegeord=["transport"]
    )
    """
    # Hent part IDs
    module = requests.get(f"{BASE_URL}/modules/basic/{module_id}", headers=headers).json()
    part_map = {p['slug']: p['id'] for p in module['parts']}
    
    # Byg parts
    parts = []
    for filter_name, values in filters.items():
        if filter_name not in part_map:
            print(f"⚠️ Warning: '{filter_name}' ikke fundet")
            continue
        
        if not isinstance(values, list):
            values = [values]
        
        parts.append({
            "modulePartId": part_map[filter_name],
            "values": values
        })
    
    # Opret step
    return requests.post(
        f"{BASE_URL}/steps/main",
        headers=headers,
        json={
            "name": name,
            "moduleId": module_id,
            "lookbackDays": 30,
            "parts": parts
        }
    ).json()

# Brug
step = create_step_smart(
    280,
    "Udbud i Aarhus",
    kommune=["Aarhus"],
    soegeord=["transport", "logistik"]
)
```

### Helper: Get All Hits (Paginated)
```python
def get_all_hits(step_id, max_hits=1000):
    """Hent alle hits fra et step (med pagination)"""
    all_hits = []
    page = 1
    page_size = 100
    
    while len(all_hits) < max_hits:
        response = requests.get(
            f"{BASE_URL}/steps/main/hits/{step_id}",
            headers=headers,
            params={"page": page, "pageSize": page_size}
        ).json()
        
        all_hits.extend(response['items'])
        
        # Check om der er flere sider
        if len(response['items']) < page_size:
            break
        
        page += 1
    
    return all_hits[:max_hits]

# Brug
hits = get_all_hits(step_id, max_hits=500)
```

### Helper: Find Virksomheder i Hits
```python
def extract_companies(hits):
    """Ekstraher alle unikke virksomheder fra hits"""
    companies = {}
    
    for hit in hits:
        for company in hit.get('companies', []):
            cvr = company['cvr']
            if cvr not in companies:
                companies[cvr] = {
                    'cvr': cvr,
                    'name': company['name'],
                    'hit_count': 0
                }
            companies[cvr]['hit_count'] += 1
    
    # Sortér efter antal hits
    return sorted(companies.values(), key=lambda x: x['hit_count'], reverse=True)

# Brug
hits = get_all_hits(step_id)
companies = extract_companies(hits)

print("Top 10 virksomheder:")
for company in companies[:10]:
    print(f"{company['name']}: {company['hit_count']} hits")
```

---

## 🚨 Common Pitfalls

### ❌ FORKERT: Query params på /hits
```python
# Dette virker IKKE!
requests.get(
    f"{BASE_URL}/hits",
    params={"module": 280, "kommune": "Aarhus"}
)
```

### ✅ KORREKT: Opret step først
```python
step = requests.post(f"{BASE_URL}/steps/main", headers=headers, json={...})
hits = requests.get(f"{BASE_URL}/steps/main/hits/{step['id']}", headers=headers)
```

### ❌ FORKERT: Virksomhedsnavn som værdi
```python
{"modulePartId": 133, "values": ["Novo Nordisk"]}  # FORKERT!
```

### ✅ KORREKT: CVR nummer som værdi
```python
{"modulePartId": 133, "values": ["24256790"]}  # KORREKT!
```

### ❌ FORKERT: Hardcoded part IDs på tværs af moduler
```python
# Part ID 2 er IKKE "kommune" i alle moduler!
parts = [{"modulePartId": 2, "values": ["Aarhus"]}]
```

### ✅ KORREKT: Lookup part ID for hvert modul
```python
module = requests.get(f"{BASE_URL}/modules/basic/{module_id}", headers=headers).json()
kommune_id = next(p['id'] for p in module['parts'] if p['slug'] == 'kommune')
parts = [{"modulePartId": kommune_id, "values": ["Aarhus"]}]
```

---

## 📚 Nyttige Links

- **API Docs**: https://km24.dk/api/docs/
- **Token Management**: https://km24.dk/tokens
- **Moduler**: https://km24.dk/modules/
- **Schema**: https://km24.dk/api/schema.json

---

## 💡 Pro Tips

1. **Cache modul data** - parts ændrer sig sjældent
2. **Brug descriptive step names** - det hjælper senere
3. **Start bredt, indsnævr gradvist** - tilføj filtre løbende
4. **Check for tomme resultater** - validering sker ikke ved oprettelse
5. **Brug lookbackDays klogt** - større periode = mere data men langsommere

---

**Print denne side og hold den ved hånden når du koder!** 📄