"""Pydantic models for researcher-based responses.

Definerer response struktur for den nye researcher-tilgang,
hvor LLM forklarer dybt hvorfor moduler og filtre vælges.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class MonitoringExplanation(BaseModel):
    """Deep explanation of monitoring coverage."""

    what_it_catches: List[str] = Field(
        description="Hvad fanger denne overvågning? (konkrete eksempler)"
    )
    what_it_misses: List[str] = Field(
        description="Hvad fanger den IKKE? (vigtige begrænsninger)"
    )
    expected_volume: str = Field(
        description="Estimeret antal hits med disclaimer om usikkerhed"
    )
    false_positive_risk: str = Field(
        description="Risiko for irrelevante hits (Lav/Medium/Høj + forklaring)"
    )


class JournalisticContext(BaseModel):
    """Journalistisk kontekst og arbejdsmetoder."""

    story_angles: List[str] = Field(
        description="Konkrete historievinkler"
    )
    investigative_tactics: str = Field(
        description="Hvordan arbejder man journalistisk med hits"
    )
    red_flags: List[str] = Field(
        description="Hvad skal man kigge efter i hits?"
    )


class ModuleRef(BaseModel):
    """Reference til KM24 modul."""

    name: str = Field(description="Modul navn (fx 'Arbejdstilsyn')")
    id: str = Field(description="Modul ID (fx '110')")


class ResearcherStep(BaseModel):
    """Enkelt overvågnings-setup med dyb forklaring."""

    step_number: int
    title: str
    module: ModuleRef
    filters: Dict[str, Any]

    # Researcher forklaringer
    module_rationale: str = Field(
        description="Dyb forklaring af hvorfor dette modul passer til målet"
    )
    filter_explanations: Dict[str, str] = Field(
        description="Forklaring af hvert filter (key = filter navn)"
    )
    monitoring_explanation: MonitoringExplanation
    journalistic_context: JournalisticContext

    # Backward compatibility med eksisterende system
    rationale: str = Field(
        description="Kort version af module_rationale"
    )
    explanation: str = Field(
        description="Kort generel forklaring"
    )

    # Tilføjes af backend efter LLM response
    km24_step_json: Optional[Dict[str, Any]] = None
    km24_curl_command: Optional[str] = None
    part_id_mapping: Optional[Dict[str, int]] = None
    km24_warnings: Optional[List[str]] = None


class ResearcherResponse(BaseModel):
    """Complete researcher response med forståelse og anbefalinger."""

    understanding: str = Field(
        description="Researcher's forståelse af brugerens journalistiske mål"
    )
    monitoring_setups: List[ResearcherStep] = Field(
        description="1-3 anbefalede overvågninger (typisk 1-2)"
    )
    overall_strategy: Optional[str] = Field(
        None,
        description="Overordnet strategi hvis multiple setups"
    )
    important_context: Optional[str] = Field(
        None,
        description="Relevant dansk data-kontekst og baggrundsviden"
    )
