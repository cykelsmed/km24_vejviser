# 📚 KM24 API Dokumentation (Korrekt Version)

## 🚨 KRITISK ÆNDRING fra Tidligere Version

**KM24 API er SUBSCRIPTION-BASED!** Du laver ikke direkte søgninger med filtre. I stedet:

1. **Opretter du "Steps"** (overvågninger) med filtre
2. **Steps kører automatisk** og finder hits over tid
3. **Du henter hits** fra dine eksisterende steps

Dette er den fundamentale misforståelse der skal rettes i alle projekter!

---

## 🎯 Oversigt

KM24 API er et omfattende system til overvågning af danske offentlige data og medier. API'et giver adgang til 44 forskellige moduler med real-time data fra danske myndigheder, domstole, medier og andre offentlige kilder.

**Base URL**: `https://km24.dk/api`

---

## 🔐 Authentication

### API Key (Anbefalet)

Alle requests skal inkludere din API key som header:

```bash
curl -H "X-API-Key: your_api_key_here" https://km24.dk/api/modules/basic
```

```python
import requests

headers = {
    "X-API-Key": "your_api_key_here"
}

response = requests.get("https://km24.dk/api/modules/basic", headers=headers)
```

### Hent din API Key

Gå til https://km24.dk/tokens og opret din token(s).

---

## 📡 Kernekoncept: Steps (Overvågninger)

### Hvad er et Step?

Et **step** er en overvågning du opretter med specifikke filtre. KM24 systemet kører automatisk dit step og finder hits der matcher dine kriterier.

### Step Workflow

```
1. Opret Step med filtre
   ↓
2. KM24 kører step'et automatisk
   ↓
3. Hent hits fra dit step
```

### Vigtige Step Properties

```json
{
  "name": "Mit overvågningsnavn",
  "moduleId": 280,
  "lookbackDays": 30,
  "onlyActive": false,
  "onlySubscribed": false,
  "parts": [
    {
      "modulePartId": 134,
      "values": ["Aarhus", "København"]
    }
  ]
}
```

**Forklaring:**
- `name`: Dit eget navn på overvågningen
- `moduleId`: Hvilket modul (se næste sektion)
- `lookbackDays`: Hvor mange dage tilbage skal steps kigge? (1-90)
- `onlyActive`: Kun aktive virksomheder? (kun relevant for virksomhedsfiltre)
- `onlySubscribed`: Kun virksomheder du abonnerer på? (kun relevant for virksomhedsfiltre)
- `parts`: **DETTE ER HVOR FILTRENE ER!**

---

## 🔍 Filtrering: Parts og modulePartId

### Sådan Finder du modulePartId

Hvert modul har forskellige filtreringsmuligheder kaldet "parts". Hver part har et unikt `modulePartId`.

**Eksempel: Udbud (moduleId: 280)**

```python
# Hent modul detaljer
response = requests.get(
    "https://km24.dk/api/modules/basic/280",
    headers={"X-API-Key": "your_key"}
)

module = response.json()

# Se alle tilgængelige parts
for part in module['parts']:
    print(f"ID: {part['id']} - {part['name']} ({part['slug']})")
```

**Output:**
```
ID: 137 - Kontraktværdi (kontraktvaerdi)
ID: 133 - Virksomhed (virksomhed)
ID: 136 - Søgeord (soegeord)
ID: 138 - Hitlogik (hitlogik)
```

### Almindelige Part Typer

| Part Type | Beskrivelse | Værdi Format |
|-----------|-------------|--------------|
| `municipality` | Kommune | Liste af kommunenavne: `["Aarhus", "København"]` |
| `company` | Virksomhed | Liste af CVR numre: `["12345678", "87654321"]` |
| `search_string` | Søgeord | Liste af søgestrenge: `["transport", "logistik"]` |
| `industry` | Branche | Liste af branchekoder: `["493100", "561000"]` |
| `amount_selection` | Beløbsgrænse | Enkelt værdi: `["1000000"]` |
| `generic_value` | Diverse kategorier | Afhænger af modul |
| `hit_logic` | Hitlogik | Typisk `["standard"]` eller specifikke værdier |
| `web_source` | Webkilde | Liste af kilde-ID'er |
| `custom_number` | Brugerdefinerede numre | Liste af numre med noter |

---

## 📡 API Endpoints

### 1. Module Endpoints

#### 1.1 List Alle Moduler
**Endpoint**: `GET /api/modules/basic`

**Response**:
```json
{
  "count": 44,
  "countSubbed": 0,
  "countActive": 44,
  "items": [
    {
      "id": 110,
      "slug": "arbejdstilsyn",
      "title": "Arbejdstilsyn",
      "colorHex": "b8aa40",
      "emoji": "🙁",
      "shortDescription": "Arbejdstilsynets kritik af virksomheder",
      "parts": [
        {
          "id": 204,
          "part": "generic_value",
          "name": "Oprindelsesland",
          "slug": "oprindelsesland",
          "canSelectMultiple": true
        },
        {
          "id": 205,
          "part": "generic_value",
          "name": "Problem",
          "slug": "problem",
          "canSelectMultiple": true
        }
      ]
    }
  ]
}
```

#### 1.2 Hent Specifikt Modul med Parts
**Endpoint**: `GET /api/modules/basic/{module_id}`

**Eksempel**:
```python
response = requests.get(
    "https://km24.dk/api/modules/basic/110",  # Arbejdstilsyn
    headers={"X-API-Key": "your_key"}
)
```

---

### 2. Steps Endpoints (DET VIGTIGSTE!)

#### 2.1 Opret Step (Overvågning)
**Endpoint**: `POST /api/steps/main`

**Request Body**:
```json
{
  "name": "Transportvirksomheder i Trekantområdet med påbud",
  "moduleId": 110,
  "lookbackDays": 30,
  "onlyActive": false,
  "onlySubscribed": false,
  "parts": [
    {
      "modulePartId": 2,
      "values": ["Vejle", "Kolding", "Fredericia"]
    },
    {
      "modulePartId": 5,
      "values": ["493100"]
    },
    {
      "modulePartId": 206,
      "values": ["Påbud"]
    }
  ]
}
```

**Response**:
```json
{
  "id": 12345,
  "name": "Transportvirksomheder i Trekantområdet med påbud",
  "moduleId": 110,
  "created": "2025-10-21T10:00:00Z"
}
```

#### 2.2 List Alle Dine Steps
**Endpoint**: `GET /api/steps/main`

**Query Parameters**:
- `moduleId` (optional): Filtrer steps til specifikt modul
- `page`: Side nummer (default: 1)
- `pageSize`: Antal per side (default: 25, max: 200)

**Response**:
```json
{
  "page": 1,
  "pageSize": 25,
  "numPages": 3,
  "count": 67,
  "items": [
    {
      "id": 12345,
      "name": "Mit step navn",
      "moduleId": 110,
      "moduleName": "Arbejdstilsyn",
      "isActive": true,
      "hitCount": 42,
      "parts": [...]
    }
  ]
}
```

#### 2.3 Hent Hits fra Step
**Endpoint**: `GET /api/steps/main/hits/{stepId}`

**Query Parameters**:
- `page`: Side nummer
- `pageSize`: Antal hits per side
- `ordering`: Sortering (fx `-hitDatetime` for nyeste først)

**Response**:
```json
{
  "page": 1,
  "pageSize": 25,
  "count": 42,
  "items": [
    {
      "id": 789456,
      "title": "Påbud til ABC Transport ApS",
      "hitDatetime": "2025-10-20T14:30:00Z",
      "bodyHtml": "<p>Arbejdstilsynet har givet påbud...</p>",
      "url": "https://...",
      "companies": [
        {
          "cvr": "12345678",
          "name": "ABC Transport ApS"
        }
      ]
    }
  ]
}
```

#### 2.4 Hent Specifikt Hit
**Endpoint**: `GET /api/hits/{hit_id}`

#### 2.5 Slet Step
**Endpoint**: `DELETE /api/steps/main/{stepId}`

#### 2.6 Opdater Step
**Endpoint**: `PUT /api/steps/main/{stepId}`

---

### 3. Companies Endpoints

#### 3.1 Søg Virksomheder
**Endpoint**: `GET /api/companies/add/search`

**Query Parameters**:
- `q`: Søgeord (virksomhedsnavn eller CVR)

**Response**:
```json
{
  "results": [
    {
      "cvr": "24256790",
      "name": "Novo Nordisk A/S",
      "address": "Novo Allé 1",
      "zipCode": "2880",
      "city": "Bagsværd"
    }
  ]
}
```

#### 3.2 Hent Virksomheder i Modul
**Endpoint**: `GET /api/companies/main/{moduleId}`

**Query Parameters**:
- `isSubbed`: Filter på subscribed virksomheder (true/false)
- `search`: Søgeord
- `page`: Side nummer
- `pageSize`: Antal per side

#### 3.3 Subscribe til Virksomhed i Modul
**Endpoint**: `POST /api/companies/main/{moduleId}/subscribe`

**Query Parameters**:
- `cvr`: CVR nummer (integer)

**Response**:
```json
{
  "detail": "Du abonnerer nu på virksomheden"
}
```

#### 3.4 Unsubscribe fra Virksomhed
**Endpoint**: `DELETE /api/companies/main/{moduleId}/subscribe`

**Query Parameters**:
- `cvr`: CVR nummer (optional - hvis udeladt, unsubscribes fra alle)

---

### 4. Hits Overview Endpoints

#### 4.1 Hent Alle Dine Hits
**Endpoint**: `GET /api/hits`

**VIGTIGT**: Dette henter hits fra ALLE dine steps, ikke fra specifikke søgninger!

**Query Parameters**:
- `module`: Filter til specifikt modul ID (optional)
- `page`: Side nummer
- `pageSize`: Antal hits per side

---

## 🎓 Eksempler

### Eksempel 1: Opret Overvågning af Udbud over 10 mio i Aarhus

```python
import requests

BASE_URL = "https://km24.dk/api"
API_KEY = "your_api_key"

headers = {"X-API-Key": API_KEY}

# Step 1: Find de rigtige modulePartId værdier
module_response = requests.get(
    f"{BASE_URL}/modules/basic/280",  # Udbud modul
    headers=headers
)
module = module_response.json()

# Print parts for at se ID'er
for part in module['parts']:
    print(f"{part['name']}: ID {part['id']}")

# Output:
# Kontraktværdi: ID 137
# Virksomhed: ID 133
# Søgeord: ID 136
# Hitlogik: ID 138

# Step 2: Opret step med korrekte ID'er
step_data = {
    "name": "Udbud over 10 mio i Aarhus",
    "moduleId": 280,
    "lookbackDays": 30,
    "parts": [
        {
            "modulePartId": 137,  # Kontraktværdi
            "values": ["10000000"]
        },
        {
            "modulePartId": 134,  # Kommune (ID kan variere, check først!)
            "values": ["Aarhus"]
        }
    ]
}

create_response = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json=step_data
)

step = create_response.json()
step_id = step['id']

print(f"Step oprettet med ID: {step_id}")

# Step 3: Hent hits fra dit step
hits_response = requests.get(
    f"{BASE_URL}/steps/main/hits/{step_id}",
    headers=headers,
    params={"pageSize": 20}
)

hits = hits_response.json()
print(f"Fandt {hits['count']} hits")

for hit in hits['items']:
    print(f"- {hit['title']} ({hit['hitDatetime']})")
```

### Eksempel 2: Medie Overvågning af Novo Nordisk

```python
# Step 1: Find CVR for Novo Nordisk
search_response = requests.get(
    f"{BASE_URL}/companies/add/search",
    headers=headers,
    params={"q": "novo nordisk"}
)

companies = search_response.json()['results']
novo_cvr = companies[0]['cvr']  # "24256790"

# Step 2: Opret medie step
step_data = {
    "name": "Novo Nordisk i medierne",
    "moduleId": 510,  # Danske Medier
    "lookbackDays": 7,
    "parts": [
        {
            "modulePartId": 52,  # Virksomhed
            "values": [novo_cvr]
        },
        {
            "modulePartId": 54,  # Medie (optional)
            "values": ["1234", "5678"]  # Specifikke medie ID'er
        }
    ]
}

create_response = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json=step_data
)
```

### Eksempel 3: Arbejdstilsyn med Problem-filter

```python
# Step 1: Hent modul 110 (Arbejdstilsyn) for at se parts
module = requests.get(
    f"{BASE_URL}/modules/basic/110",
    headers=headers
).json()

# Find "Problem" part
problem_part = next(p for p in module['parts'] if p['slug'] == 'problem')
print(f"Problem part ID: {problem_part['id']}")  # 205

# Step 2: Opret step med problem-filter
step_data = {
    "name": "Asbest problemer i byggebranchen",
    "moduleId": 110,
    "lookbackDays": 90,
    "parts": [
        {
            "modulePartId": 205,  # Problem
            "values": ["Asbest"]  # Eller hvilket problem der findes
        },
        {
            "modulePartId": 5,  # Branche
            "values": ["412000", "429000"]  # Byggerelaterede brancher
        }
    ]
}

requests.post(f"{BASE_URL}/steps/main", headers=headers, json=step_data)
```

### Eksempel 4: Find Alle Hits på Tværs af Moduler

```python
# Hent alle hits fra alle dine steps
all_hits = requests.get(
    f"{BASE_URL}/hits",
    headers=headers,
    params={
        "pageSize": 50,
        "ordering": "-hitDatetime"  # Nyeste først
    }
).json()

print(f"Total hits: {all_hits['count']}")

for hit in all_hits['items']:
    print(f"[{hit['moduleName']}] {hit['title']}")
```

---

## 🔧 Almindelige Part IDs på Tværs af Moduler

Disse part typer går ofte igen, men **ID'et varierer fra modul til modul**. Du skal altid checke det specifikke modul først!

### Kommune Part IDs (Eksempler)
- Arbejdstilsyn (110): `2`
- Udbud (280): `134`
- Boligsiden (1400): `26`
- Domme (250): Findes ikke i alle moduler

### Virksomhed Part IDs (Eksempler)
- Arbejdstilsyn (110): `3`
- Udbud (280): `133`
- Børsmeddelelser (220): `33`
- Boligsiden (1400): `25`

### Søgeord Part IDs (Eksempler)
- Arbejdstilsyn (110): Ingen søgeord part!
- Udbud (280): `136`
- Danske Medier (510): `53`
- Domme (250): `70`

### Hitlogik Part IDs (Eksempler)
- Arbejdstilsyn (110): `9`
- Udbud (280): `138`
- Børsmeddelelser (220): `38`

**TIP**: Lav altid et opslag først for at få de præcise ID'er!

---

## ⚠️ Almindelige Fejl og Løsninger

### Fejl 1: "Det virker ikke - får ingen hits!"

**Årsag**: Du prøver at søge direkte i stedet for at oprette steps.

**Løsning**:
```python
# ❌ FORKERT - dette virker ikke!
response = requests.get(
    f"{BASE_URL}/hits",
    params={"kommune": "Aarhus", "moduleId": 280}
)

# ✅ KORREKT - opret først et step
step = requests.post(
    f"{BASE_URL}/steps/main",
    headers=headers,
    json={
        "name": "Aarhus overvågning",
        "moduleId": 280,
        "parts": [{"modulePartId": 134, "values": ["Aarhus"]}]
    }
).json()

# Hent derefter hits fra step'et
hits = requests.get(
    f"{BASE_URL}/steps/main/hits/{step['id']}",
    headers=headers
).json()
```

### Fejl 2: "Forkert modulePartId!"

**Årsag**: Du bruger modulePartId fra et andet modul eller gætter.

**Løsning**: Hent altid modulet først!
```python
# Hent modul og find rigtige ID'er
module = requests.get(
    f"{BASE_URL}/modules/basic/{module_id}",
    headers=headers
).json()

# Print alle parts
for part in module['parts']:
    print(f"{part['slug']}: {part['id']}")
```

### Fejl 3: "Virksomhedsfilter virker ikke!"

**Årsag**: Du bruger virksomhedsnavn i stedet for CVR nummer.

**Løsning**:
```python
# ❌ FORKERT
"values": ["Novo Nordisk"]

# ✅ KORREKT - brug CVR nummer
"values": ["24256790"]

# Find CVR først hvis nødvendigt
search = requests.get(
    f"{BASE_URL}/companies/add/search",
    headers=headers,
    params={"q": "novo nordisk"}
).json()
cvr = search['results'][0]['cvr']
```

### Fejl 4: "Ingen validation når jeg opretter step!"

**Dette er korrekt adfærd!** KM24 validerer ikke filtre når du opretter et step. Step'et oprettes altid, men:
- Hvis dine filtre er forkerte, får du ingen hits
- Hvis modulePartId er forkert, får du ingen hits
- Du opdager først problemet når du tjekker for hits

**Løsning**: Test altid dine steps efter oprettelse:
```python
# Opret step
step = create_step(...)

# Vent lidt (eller tjek senere)
import time
time.sleep(60)

# Tjek om der er hits
hits = requests.get(
    f"{BASE_URL}/steps/main/hits/{step['id']}",
    headers=headers
).json()

if hits['count'] == 0:
    print("⚠️ Ingen hits - check dine filtre!")
```

---

## 📊 Modul Reference

### Oversigt over Almindelige Moduler

| Module ID | Navn | Emoji | Beskrivelse |
|-----------|------|-------|-------------|
| 110 | Arbejdstilsyn | 🙁 | Arbejdstilsynets kritik af virksomheder |
| 220 | Børsmeddelelser | 💰 | Nye børsmeddelelser fra Nasdaq |
| 250 | Domme | 🏛️ | Nye domme fra domsdatabasen |
| 280 | Udbud | 🏗️ | Alle nye danske offentlige udbud |
| 510 | Danske medier | 📰 | Nyt indhold på danske mediesites |
| 1100 | Dødsfald | 💀 | Nye dødsfald fra Datafordeleren |
| 1200 | Kystdirektoratet | 💦 | Afgørelser fra Kystdirektoratet |
| 1240 | Andelsboligbogen | 🏠 | Pant og udlæg i Andelsboligforeninger |
| 1260 | Bilbogen | 🚗 | Pant i køretøjer |
| 1340 | Kommuner | 🏛️ | Nyt fra kommunale websites |
| 1360 | Centraladministrationen | 📂 | Nyt fra ministerier og styrelser |
| 1380 | EU | 🇪🇺 | Nyt fra EU-organer |
| 1400 | Boligsiden | 🏠 | Nye boliger til salg |

---

## 🚀 Best Practices

### 1. Cache Modul Data

Modul data ændrer sig sjældent. Cache parts data lokalt:

```python
import json
from pathlib import Path

def get_module_parts(module_id, cache_dir="./cache"):
    cache_file = Path(cache_dir) / f"module_{module_id}.json"
    
    # Check cache først
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    
    # Hent fra API
    response = requests.get(
        f"{BASE_URL}/modules/basic/{module_id}",
        headers=headers
    )
    data = response.json()
    
    # Gem i cache
    cache_file.parent.mkdir(exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(data, f)
    
    return data
```

### 2. Brug Descriptive Step Names

```python
# ❌ Dårligt
"name": "Step 1"

# ✅ Godt
"name": "Udbud over 10 mio i Trekantområdet - Transport"
```

### 3. Start Bredt, Indsnævr Senere

Når du tester nye overvågninger:
1. Start med få filtre
2. Se hvad du får
3. Tilføj flere filtre for at indsnævre

```python
# Første iteration - bredt
step_v1 = {
    "name": "Transport arbejdstilsyn",
    "moduleId": 110,
    "parts": [
        {"modulePartId": 5, "values": ["493100"]}  # Kun branche
    ]
}

# Anden iteration - mere specifikt efter at have set resultaterne
step_v2 = {
    "name": "Transport arbejdstilsyn - Trekantområdet - Påbud",
    "moduleId": 110,
    "parts": [
        {"modulePartId": 5, "values": ["493100"]},
        {"modulePartId": 2, "values": ["Vejle", "Kolding"]},
        {"modulePartId": 206, "values": ["Påbud"]}
    ]
}
```

### 4. Monitorer Step Performance

```python
def check_step_health(step_id):
    """Check om et step faktisk får hits"""
    hits = requests.get(
        f"{BASE_URL}/steps/main/hits/{step_id}",
        headers=headers,
        params={"pageSize": 1}
    ).json()
    
    if hits['count'] == 0:
        print(f"⚠️ Step {step_id} har ingen hits!")
        return False
    
    latest_hit = hits['items'][0]
    hit_age_days = (datetime.now() - datetime.fromisoformat(
        latest_hit['hitDatetime'].replace('Z', '+00:00')
    )).days
    
    if hit_age_days > 30:
        print(f"⚠️ Step {step_id} sidst hit for {hit_age_days} dage siden")
        return False
    
    print(f"✅ Step {step_id} har {hits['count']} hits")
    return True
```

---

## 📝 Migration Guide fra Gammel Forståelse

### Hvis Din Kode Ser Sådan Ud:

```python
# ❌ GAMMEL FORKERT TILGANG
def search_udbud(filters):
    return requests.get(
        "https://km24.dk/api/hits",
        params={
            "module": 280,
            "kommune": filters.get('kommune'),
            "kontraktvaerdi": filters.get('amount'),
            "virksomhed": filters.get('company')
        }
    )
```

### Skal Den Ændres Til:

```python
# ✅ NY KORREKT TILGANG
def create_udbud_monitoring(name, kommune=None, min_amount=None, companies=None):
    # Step 1: Find de rigtige modulePartId værdier
    module = requests.get(
        "https://km24.dk/api/modules/basic/280",
        headers={"X-API-Key": API_KEY}
    ).json()
    
    # Map part slugs to IDs
    part_ids = {p['slug']: p['id'] for p in module['parts']}
    
    # Step 2: Byg parts array
    parts = []
    
    if kommune:
        parts.append({
            "modulePartId": part_ids['kommune'],
            "values": kommune if isinstance(kommune, list) else [kommune]
        })
    
    if min_amount:
        parts.append({
            "modulePartId": part_ids['kontraktvaerdi'],
            "values": [str(min_amount)]
        })
    
    if companies:
        parts.append({
            "modulePartId": part_ids['virksomhed'],
            "values": companies if isinstance(companies, list) else [companies]
        })
    
    # Step 3: Opret step
    step_data = {
        "name": name,
        "moduleId": 280,
        "lookbackDays": 30,
        "parts": parts
    }
    
    response = requests.post(
        "https://km24.dk/api/steps/main",
        headers={"X-API-Key": API_KEY},
        json=step_data
    )
    
    return response.json()

# Brug:
step = create_udbud_monitoring(
    name="Udbud i Aarhus over 10 mio",
    kommune=["Aarhus"],
    min_amount=10000000
)

# Hent hits fra step
hits = requests.get(
    f"https://km24.dk/api/steps/main/hits/{step['id']}",
    headers={"X-API-Key": API_KEY}
).json()
```

---

## 🔗 Nyttige Links

- **API Dokumentation**: https://km24.dk/api/docs/
- **API Schema**: https://km24.dk/api/schema.json
- **KM24 Hovedside**: https://km24.dk/
- **Moduler Side**: https://km24.dk/modules/
- **Token Management**: https://km24.dk/tokens

---

## ✅ Tjekliste for Migration af Eksisterende Projekter

- [ ] Identificer alle steder hvor du prøver at lave direkte søgninger
- [ ] For hver søgning: Find hvilket modul det skal være
- [ ] For hver søgning: Hent modul data og find rigtige modulePartId værdier
- [ ] Omskriv til at oprette steps i stedet for direkte søgninger
- [ ] Test at steps faktisk får hits
- [ ] Implementer caching af modul data
- [ ] Tilføj step health monitoring
- [ ] Dokumenter hvilke modulePartId værdier du bruger

---

**Vigtigt**: KM24 API er subscription-based. Du opretter overvågninger (steps) med filtre, og systemet finder automatisk hits over tid. Der er ingen måde at lave direkte søgninger med ad-hoc filtre - alt går gennem steps!