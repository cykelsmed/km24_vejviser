# KM24 Vejviser - Forbedringer og Roadmap

**Dato:** 16. august 2025  
**Status:** Under udvikling  
**Version:** 1.0

## 🎯 Overordnet Mål

Transformere KM24 Vejviser fra en struktureret planlægger til en **proaktiv, kreativ datajournalistisk sparringspartner**, der:
- Genererer "ud af boksen"-forslag og uventede vinkler
- Formulerer dybere, "næste niveau"-spørgsmål
- Leverer beriget og kontekstuel viden om KM24-moduler
- Foreslår konkrete, potentielle historievinkler og hypoteser

---

## 📋 Opgaver

### 🔧 AI Prompt Optimering

#### 1. Styrket Rollebeskrivelse
- [x] Udvid systempromptens "1. ROLLE OG MÅL" sektion
- [x] Tilføj instruktion om at tænke som "erfaren og nysgerrig datajournalist"
- [x] Fokuser på skjulte sammenhænge og potentielle misbrug
- [x] Test promptændringer med forskellige mål

#### 2. Forbedring af "Næste Niveau" Spørgsmål
- [x] Redefiner `next_level_questions` til dybdegående og bredere tænkende
- [x] Introducer ny sektion: `"potential_story_angles": [...]`
- [x] Fokuser på "worst-case scenarios" og "systemiske fejl"
- [x] Test kvaliteten af de nye spørgsmål

#### 3. Kreativ Modulanvendelse
- [x] Tilføj ny sektion "7. KREATIV MODULANVENDELSE"
- [x] Instruer Claude i at overveje urelaterede moduler
- [x] Fokuser på krydsreferering af data fra forskellige kilder
- [x] Implementer kreative måder at kombinere filtre på

#### 4. Strategic Notes og Power Tips
- [x] Forbedre `strategic_note` generering
- [x] Tilføj avancerede taktikker og advarsler
- [x] Implementer kreative måder at kombinere filtre/moduler
- [x] Test kvaliteten af de nye noter

### 🔌 Backend Kontekstberigelse

#### 5. Dynamisk Indlæsning af Moduldata
- [x] Udvid `km24_client` med nye endpoints
- [x] Implementer hentning af branchekode-lister med beskrivelser
- [x] Tilføj filtreringsmuligheder (Problem, Reaktion, Oprindelsesland)
- [x] Implementer lister over mediekilder (Landsdækkende, Lokale)

#### 6. Berigelse af Module Suggestions
- [x] Forbedre `get_module_suggestions_for_goal`
- [x] Tilføj AI-genereret begrundelse for relevans
- [x] Implementer kreativ kontekst for modulvalg
- [x] Test kvaliteten af forslagene

#### 7. Dynamiske Søge-eksempler
- [x] Berige `search_string` med søgetips
- [x] Implementer eksempel-søgestrenge per modul
- [x] Tilføj branche-specifikke søgetips
- [x] Test relevansen af søgetips

#### 8. Complete Recipe Forbedringer
- [x] Tilpas `complete_recipe` til at kalde nye endpoints
- [x] Injicer dynamiske data i `details` sektioner
- [x] Implementer "Live data fra KM24" sektioner
- [x] Test integrationen af dynamiske data

### 🎨 Frontend Præsentation

#### 9. Visuel Fremhævelse
- [x] Gør "Næste Niveau" sektion mere prominent
- [x] Tilføj visuelle elementer (ikoner, farver)
- [x] Implementer dedikerede bokse for inspiration
- [x] Test brugeroplevelsen

#### 10. Interaktivitet
- [x] Implementer fold-ud-funktionalitet for lister
- [x] Tilføj "Kopiér" knapper til søgestrenge
- [x] Forbedre formatering af dynamiske lister
- [x] Test interaktivitet og brugervenlighed
- [x] Tilføj input validering (minimum 10 tegn)
- [x] Forbedre fejlhåndtering og brugerfeedback

#### 11. Responsivt Design
- [ ] Sikre mobil-venlig visning
- [ ] Test på forskellige skærmstørrelser
- [ ] Optimere loading-tider
- [ ] Implementer progressive enhancement

### 🧪 Test og Evaluering

#### 12. Funktional Test
- [ ] Test alle nye endpoints
- [ ] Valider JSON output struktur
- [ ] Test error handling
- [ ] Verificer API integration

#### 13. Brugertest
- [ ] Gennemfør omfattende brugertest
- [ ] Mål brugerengagement med nye sektioner
- [ ] Indsamle feedback på kreativitet
- [ ] Evaluere relevans af forslag

#### 14. Performance Test
- [ ] Mål loading-tider
- [ ] Test med store datamængder
- [ ] Optimere cache-strategier
- [ ] Monitor API response times

### 📊 Succeskriterier

#### 15. Metrikker og Måling
- [ ] Implementer tracking af brugerengagement
- [ ] Mål stigning i "Næste Niveau" klik
- [ ] Spor brugen af "Potentielle Historier"
- [ ] Indsamle kvalitativ feedback

#### 16. Kvalitetskontrol
- [ ] Reducere antal "tomme" strategic_note felter
- [ ] Øge kompleksitet af modul-kombinationer
- [ ] Forbedre relevans af forslag
- [ ] Sikre konsistent output kvalitet

---

## 🚀 Næste Skridt

### Prioritet 1 (Høj)
1. [x] Implementer AI prompt optimering
2. [x] Udvikl km24_client endpoints
3. [x] Test grundlæggende funktionalitet

### Prioritet 2 (Medium)
1. [x] Tilpas complete_recipe
2. [x] Implementer frontend forbedringer
3. [ ] Gennemfør brugertest

### Prioritet 3 (Lav)
1. [ ] Optimering og finjustering
2. [ ] Dokumentation og træning
3. [ ] Deployment og monitoring

---

## 📝 Noter

### Tekniske Detaljer
- Alle ændringer skal være bagudkompatible
- API endpoints skal følge REST konventioner
- Frontend skal være responsivt og tilgængeligt

### Kvalitetskrav
- Alle nye features skal have unit tests
- Performance må ikke påvirkes negativt
- Brugervenlighed skal forbedres

### Dokumentation
- [ ] Opdater API dokumentation
- [ ] Skriv brugerguide for nye features
- [ ] Dokumenter tekniske ændringer

---

## 📊 Fremskridt Oversigt

### ✅ Fuldførte Opgaver: 38/69 (55%)
- **Prioritet 1:** 3/3 (100%) ✅
- **Prioritet 2:** 3/3 (100%) ✅
- **AI Prompt Optimering:** 4/4 (100%) ✅
- **Backend Kontekstberigelse:** 4/4 (100%) ✅
- **Frontend Præsentation:** 2/3 (67%) 🔄

### 🎯 Næste Skridt
1. **Afslut frontend forbedringer** (Interaktivitet og Responsivt Design)
2. **Gennemfør omfattende test** (Funktional, Brugertest, Performance)
3. **Implementer succeskriterier** (Metrikker og Kvalitetskontrol)

---

**Sidst opdateret:** 16. august 2025  
**Næste review:** 23. august 2025
