"""
Pydantic models for deterministic KM24 Vejviser output.

Defines the complete contract for recipe responses with validation
and sensible defaults to ensure consistent output structure.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger(__name__)

# Type aliases for better readability
Notif = Literal["instant", "daily", "weekly"]
MonType = Literal["cvr", "keywords", "mixed"]


class ModuleRef(BaseModel):
    """Reference to a KM24 module with validation."""

    id: str = Field(..., description="Unique module identifier")
    name: str = Field(..., description="Human-readable module name")
    is_web_source: bool = Field(
        default=False, description="Whether module requires source selection"
    )


class ApiBlock(BaseModel):
    """API configuration block for a step."""

    endpoint: str = Field(..., description="API endpoint URL")
    method: str = Field(default="POST", description="HTTP method")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    body: Dict[str, Any] = Field(default_factory=dict, description="Request body")
    example_curl: Optional[str] = Field(None, description="Example cURL command")


class Guardrails(BaseModel):
    """Safety and validation rules for a step."""

    max_hits: Optional[int] = Field(None, description="Maximum allowed hits")
    min_amount: Optional[float] = Field(None, description="Minimum amount filter")
    max_amount: Optional[float] = Field(None, description="Maximum amount filter")
    required_filters: List[str] = Field(
        default_factory=list, description="Required filters"
    )
    warnings: List[str] = Field(default_factory=list, description="Safety warnings")


class HitDefinition(BaseModel):
    """What counts as a hit for this step."""

    hit_types: List[str] = Field(
        default_factory=list, description="Types of hits to watch for"
    )
    indicators: List[str] = Field(
        default_factory=list, description="Specific indicators/patterns"
    )


class ContextBlock(BaseModel):
    """Investigative context and expectations."""

    background: str = Field(..., description="Domain background and why this matters")
    what_to_expect: str = Field(..., description="What kind of hits to expect")
    caveats: List[str] = Field(
        default_factory=list, description="Limitations and caveats"
    )
    coverage: str = Field(default="", description="Geographic/temporal coverage")


class AIAssessment(BaseModel):
    """LLM's strategic assessment of the monitoring plan."""

    search_plan_summary: str = Field(..., description="High-level search strategy")
    likely_signals: List[str] = Field(
        default_factory=list, description="Expected signals/patterns"
    )
    quality_checks: List[str] = Field(
        default_factory=list, description="Pre-activation quality checks"
    )


class StepEducational(BaseModel):
    """Educational content enrichment for a single step."""

    principle: Optional[str] = Field(
        None, description="Relevant KM24 principle for this step"
    )
    filter_explanations: Dict[str, str] = Field(
        default_factory=dict, description="Inline explanations for each filter"
    )
    quality_checklist: List[str] = Field(
        default_factory=list, description="Pre-activation quality checklist items"
    )
    common_mistakes: List[str] = Field(
        default_factory=list, description="Common mistakes to avoid for this module"
    )
    red_flags: List[str] = Field(
        default_factory=list, description="What to watch for in hits"
    )
    action_plan: Optional[str] = Field(None, description="What to do when hits arrive")
    example_hit: Optional[str] = Field(
        None, description="Example of what a hit might look like"
    )
    what_counts_as_hit: Optional[str] = Field(
        None, description="What patterns/indicators count as hits"
    )
    why_this_step: Optional[str] = Field(
        None, description="Strategic rationale for this step"
    )


class Step(BaseModel):
    """Individual investigation step with complete configuration."""

    step_number: int = Field(..., description="Sequential step number")
    title: str = Field(..., description="Step title")
    type: str = Field(..., description="Step type (search, monitoring, etc.)")
    module: ModuleRef = Field(..., description="KM24 module reference")
    rationale: str = Field(..., description="Why this step is needed")
    search_string: str = Field(default="", description="Search query string")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Module filters")
    notification: Notif = Field(default="daily", description="Notification frequency")
    delivery: str = Field(default="email", description="Delivery method")
    api: Optional[ApiBlock] = Field(None, description="API configuration")
    guardrails: Guardrails = Field(
        default_factory=Guardrails, description="Safety rules"
    )
    source_selection: List[str] = Field(
        default_factory=list, description="Selected sources for web modules"
    )
    strategic_note: Optional[str] = Field(None, description="Strategic guidance")
    explanation: str = Field(default="", description="Detailed explanation")
    creative_insights: Optional[str] = Field(None, description="Creative observations")
    advanced_tactics: Optional[str] = Field(None, description="Advanced tactics")
    educational: Optional[StepEducational] = Field(
        None, description="Educational content for this step"
    )

    @field_validator("source_selection", mode="before")
    @classmethod
    def require_sources_for_webkilder(cls, v, info):
        """Validate that web source modules have source selection."""
        if info.data and "module" in info.data:
            module = info.data["module"]
            if module and getattr(module, "is_web_source", False) and not v:
                raise ValueError("webkilde-modul kræver source_selection")
        return v


class CrossRef(BaseModel):
    """Cross-reference between modules."""

    from_step: int = Field(..., description="Source step number")
    to_step: int = Field(..., description="Target step number")
    relationship: str = Field(..., description="Type of relationship")
    rationale: str = Field(..., description="Why this cross-reference is useful")


class SyntaxGuide(BaseModel):
    """Search syntax and query guidance."""

    basic_syntax: List[str] = Field(
        default_factory=list, description="Basic search syntax examples"
    )
    advanced_syntax: List[str] = Field(
        default_factory=list, description="Advanced search patterns"
    )
    tips: List[str] = Field(default_factory=list, description="Search tips and tricks")


class Quality(BaseModel):
    """Quality assurance checks."""

    checks: List[str] = Field(
        default_factory=list, description="Quality checks performed"
    )
    warnings: List[str] = Field(default_factory=list, description="Quality warnings")
    recommendations: List[str] = Field(
        default_factory=list, description="Quality recommendations"
    )


class Artifacts(BaseModel):
    """Output artifacts and exports."""

    exports: List[Literal["csv", "json", "xlsx"]] = Field(
        default_factory=list, description="Export formats"
    )
    reports: List[str] = Field(default_factory=list, description="Generated reports")
    visualizations: List[str] = Field(
        default_factory=list, description="Data visualizations"
    )


class Overview(BaseModel):
    """High-level overview of the investigation."""

    title: str = Field(..., description="Investigation title")
    strategy_summary: str = Field(..., description="Overall strategy summary")
    creative_approach: str = Field(..., description="Creative investigation approach")
    module_flow: List[str] = Field(
        default_factory=list, description="Module execution flow"
    )
    estimated_duration: str = Field(
        default="1-2 weeks", description="Estimated investigation duration"
    )


class Scope(BaseModel):
    """Investigation scope and boundaries."""

    primary_focus: str = Field(..., description="Primary investigation focus")
    secondary_areas: List[str] = Field(
        default_factory=list, description="Secondary investigation areas"
    )
    exclusions: List[str] = Field(default_factory=list, description="Excluded areas")
    limitations: List[str] = Field(
        default_factory=list, description="Known limitations"
    )


class Monitoring(BaseModel):
    """Monitoring configuration."""

    type: MonType = Field(default="keywords", description="Monitoring type")
    frequency: str = Field(default="daily", description="Monitoring frequency")
    alerts: List[str] = Field(default_factory=list, description="Alert conditions")
    escalation: Optional[str] = Field(None, description="Escalation procedure")


class HitBudget(BaseModel):
    """Hit budget and resource allocation."""

    expected_hits: str = Field(default="moderate", description="Expected hit volume")
    budget_allocation: Dict[str, int] = Field(
        default_factory=dict, description="Budget per step"
    )
    resource_requirements: List[str] = Field(
        default_factory=list, description="Resource needs"
    )


class Notifications(BaseModel):
    """Notification configuration."""

    primary: Notif = Field(
        default="daily", description="Primary notification frequency"
    )
    secondary: Optional[Notif] = Field(
        None, description="Secondary notification frequency"
    )
    escalation: Optional[str] = Field(None, description="Escalation conditions")
    channels: List[str] = Field(
        default_factory=lambda: ["email"], description="Notification channels"
    )


class ParallelProfile(BaseModel):
    """Parallel execution profile."""

    max_concurrent: int = Field(default=3, description="Maximum concurrent steps")
    dependencies: Dict[int, List[int]] = Field(
        default_factory=dict, description="Step dependencies"
    )
    critical_path: List[int] = Field(
        default_factory=list, description="Critical path steps"
    )


class EducationalContent(BaseModel):
    """Universal educational content for the entire recipe."""

    syntax_guide: str = Field(default="", description="Search string syntax guide")
    common_pitfalls: str = Field(default="", description="Common mistakes to avoid")
    troubleshooting: str = Field(default="", description="Troubleshooting guide")
    km24_principles: Dict[str, str] = Field(
        default_factory=dict, description="Core KM24 principles"
    )


class UseCaseResponse(BaseModel):
    """Complete deterministic response model for KM24 Vejviser."""

    overview: Overview = Field(..., description="Investigation overview")
    scope: Scope = Field(..., description="Investigation scope")
    monitoring: Monitoring = Field(..., description="Monitoring configuration")
    hit_budget: HitBudget = Field(..., description="Hit budget allocation")
    notifications: Notifications = Field(..., description="Notification settings")
    parallel_profile: ParallelProfile = Field(
        ..., description="Parallel execution profile"
    )
    steps: List[Step] = Field(..., description="Investigation steps")
    cross_refs: List[CrossRef] = Field(
        default_factory=list, description="Cross-references"
    )
    syntax_guide: SyntaxGuide = Field(..., description="Search syntax guidance")
    quality: Quality = Field(..., description="Quality assurance")
    artifacts: Artifacts = Field(..., description="Output artifacts")
    next_level_questions: List[str] = Field(
        default_factory=list, description="Follow-up questions"
    )
    potential_story_angles: List[str] = Field(
        default_factory=list, description="Potential story angles"
    )
    creative_cross_references: List[str] = Field(
        default_factory=list, description="Creative cross-references"
    )
    educational_content: Optional[EducationalContent] = Field(
        None, description="Universal educational content"
    )
    context: Optional[ContextBlock] = Field(
        None, description="Investigative context and expectations"
    )
    ai_assessment: Optional[AIAssessment] = Field(
        None, description="LLM's strategic assessment"
    )

    @model_validator(mode="after")
    def validate_structure(self):
        """Validate step numbers and cross-references."""
        # Validate step numbers are sequential and unique
        steps = self.steps
        step_numbers = [step.step_number for step in steps]

        if len(step_numbers) != len(set(step_numbers)):
            raise ValueError("Step numbers must be unique")

        # Check if step numbers start from 1 and are sequential
        if step_numbers and (
            min(step_numbers) != 1
            or step_numbers != list(range(1, len(step_numbers) + 1))
        ):
            raise ValueError("Step numbers must be sequential starting from 1")

        # Validate cross-reference step numbers exist
        cross_refs = self.cross_refs
        valid_step_numbers = {step.step_number for step in steps}

        for cross_ref in cross_refs:
            if cross_ref.from_step not in valid_step_numbers:
                raise ValueError(
                    f"Cross-reference from_step {cross_ref.from_step} does not exist"
                )
            if cross_ref.to_step not in valid_step_numbers:
                raise ValueError(
                    f"Cross-reference to_step {cross_ref.to_step} does not exist"
                )

        return self
