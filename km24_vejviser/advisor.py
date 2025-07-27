from typing import Optional, List, Dict

# Simple mapping for power tips pr. modul og operator
POWER_TIPS = {
    "Tinglysning": {
        "title": "+1-tricket",
        "explanation": "Opret brugere som navn+1@domæne.dk for at køre flere overvågninger parallelt."
    },
    "Status": {
        "title": ";-tricket",
        "explanation": "Brug semikolon (;) til at overvåge navnevariationer, fx 'fragt;fragtfirma'."
    },
    "Domme": {
        "title": "Hitlogik",
        "explanation": "Kombinér OG/ELLER for at styre præcist, hvilke domme der matches."
    },
    ";-operator": {
        "title": "Power-tip",
        "explanation": "Brug `term1;term2` for at sikre, at du fanger begge begreber i ét modul – fx både 'solcellepark' og 'solcelleanlæg'."
    }
}

# Mapping for supplerende moduler baseret på nøgleord
SUPPLEMENTARY_MODULES = [
    {"keywords": ["retslister", "domstol"], "module": "Domme", "reason": "Hvis retssager fører til afsagte domme."},
    {"keywords": ["eu", "energi", "solcelle"], "module": "EU", "reason": "Hvis nogle solcelleprojekter er støttet via EU’s energifonde."},
    {"keywords": ["miljø", "kommune", "annoncering"], "module": "Miljø-annonceringer", "reason": "Hvis kommuner annoncerer planer via miljøportaler."},
    {"keywords": ["byggeri", "transport"], "module": "Klagenævn", "reason": "Indeholder branchespecifikke sager fra fx Transportklagenævnet."},
    {"keywords": ["landbrug", "pant"], "module": "Personbogen", "reason": "Pant i løsøre og årets høst er relevant for landbrugssager."}
]

def get_supplementary_modules(prompt_text: str) -> List[Dict[str, str]]:
    """Foreslå supplerende moduler baseret på prompt/plan."""
    suggestions = []
    text = str(prompt_text).lower()
    for entry in SUPPLEMENTARY_MODULES:
        if any(word in text for word in entry["keywords"]):
            suggestions.append({"module": entry["module"], "reason": entry["reason"]})
    return suggestions

def determine_notification_type(module_name: str) -> str:
    """Bestem anbefalet notifikations-kadence for et modul."""
    løbende_moduler = ["Tinglysning", "Registrering", "Kapitalændring", "Retslister", "Status"]
    if module_name in løbende_moduler:
        return "løbende"
    return "interval"

def get_warning(module_name: str) -> Optional[str]:
    """Returnér advarsel hvis modulet kræver kildevalg."""
    moduler_med_kildekrav = [
        "Kommuner", "Danske medier", "Lokalpolitik", "Retslister", "Webstedsovervågning",
        "Centraladministrationen", "Udenlandske medier", "EU", "Forskning", "Sundhed", "Klima"
    ]
    if module_name in moduler_med_kildekrav:
        return "Du skal vælge en eller flere relevante kilder (fx kommuner eller retskredse) – ellers får du ingen hits."
    return None

def get_power_tip(module_name: str = None, search_string: str = None) -> Optional[Dict[str, str]]:
    """Returnér power-tip for et givet modul eller søgestreng."""
    if search_string and ";" in search_string:
        return POWER_TIPS.get(";-operator")
    if module_name and module_name in POWER_TIPS:
        return POWER_TIPS[module_name]
    return None

def get_geo_advice(step_title: str) -> Optional[str]:
    """Returnér geografisk vejledning hvis step handler om kommuner/regioner/geo."""
    geo_keywords = ["kommune", "region", "geografi", "lokal", "miljø", "solcelle", "energi"]
    if any(word in step_title.lower() for word in geo_keywords):
        return "Overvej at bruge eksterne kilder som PlanEnergi, Energistyrelsen eller kommunale energiplaner som udgangspunkt for at finde kommuner med aktive solcelleparker."
    return None 