"""
Unit tests for deterministic KM24 Vejviser output.

Tests the Pydantic models and validation rules to ensure
consistent and reliable output structure.
"""

import pytest
from pydantic import ValidationError
from km24_vejviser.models.usecase_response import (
    UseCaseResponse,
    Step,
    ModuleRef,
    Overview,
    Scope,
    Monitoring,
    HitBudget,
    Notifications,
    ParallelProfile,
    CrossRef,
    SyntaxGuide,
    Quality,
    Artifacts,
)


class TestModuleRef:
    """Test ModuleRef model validation."""

    def test_valid_module_ref(self):
        """Test valid module reference."""
        module = ModuleRef(id="tinglysning", name="Tinglysning", is_web_source=False)
        assert module.id == "tinglysning"
        assert module.name == "Tinglysning"
        assert module.is_web_source is False

    def test_web_source_module(self):
        """Test web source module."""
        module = ModuleRef(id="lokalpolitik", name="Lokalpolitik", is_web_source=True)
        assert module.is_web_source is True


class TestStepValidation:
    """Test Step model validation rules."""

    def test_valid_step(self):
        """Test valid step without web source."""
        step = Step(
            step_number=1,
            title="Test Step",
            type="search",
            module=ModuleRef(id="test", name="Test Module", is_web_source=False),
            rationale="Test rationale",
            source_selection=[],
        )
        assert step.step_number == 1
        assert step.notification == "daily"  # Default
        assert step.delivery == "email"  # Default

    def test_web_source_with_selection(self):
        """Test web source module with source selection."""
        step = Step(
            step_number=1,
            title="Web Source Step",
            type="search",
            module=ModuleRef(
                id="lokalpolitik", name="Lokalpolitik", is_web_source=True
            ),
            rationale="Test rationale",
            source_selection=["Aarhus", "København"],
        )
        assert len(step.source_selection) == 2

    def test_web_source_without_selection_raises_error(self):
        """Test that web source module without selection raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Step(
                step_number=1,
                title="Web Source Step",
                type="search",
                module=ModuleRef(
                    id="lokalpolitik", name="Lokalpolitik", is_web_source=True
                ),
                rationale="Test rationale",
                source_selection=[],  # Empty - should raise error
            )

        error_msg = str(exc_info.value)
        assert "webkilde-modul kræver source_selection" in error_msg

    def test_step_defaults(self):
        """Test step default values."""
        step = Step(
            step_number=1,
            title="Test Step",
            type="search",
            module=ModuleRef(id="test", name="Test Module", is_web_source=False),
            rationale="Test rationale",
        )
        assert step.notification == "daily"
        assert step.delivery == "email"
        assert step.filters == {}
        assert step.source_selection == []


class TestUseCaseResponseValidation:
    """Test complete UseCaseResponse model validation."""

    def test_minimal_valid_response(self):
        """Test minimal valid response structure."""
        response = UseCaseResponse(
            overview=Overview(
                title="Test Investigation",
                strategy_summary="Test strategy",
                creative_approach="Test approach",
            ),
            scope=Scope(primary_focus="Test focus"),
            monitoring=Monitoring(),
            hit_budget=HitBudget(),
            notifications=Notifications(),
            parallel_profile=ParallelProfile(),
            steps=[
                Step(
                    step_number=1,
                    title="Step 1",
                    type="search",
                    module=ModuleRef(
                        id="test", name="Test Module", is_web_source=False
                    ),
                    rationale="Test rationale",
                )
            ],
            syntax_guide=SyntaxGuide(),
            quality=Quality(),
            artifacts=Artifacts(),
        )
        assert response.overview.title == "Test Investigation"
        assert len(response.steps) == 1

    def test_sequential_step_numbers(self):
        """Test that step numbers must be sequential."""
        with pytest.raises(ValidationError) as exc_info:
            UseCaseResponse(
                overview=Overview(
                    title="Test Investigation",
                    strategy_summary="Test strategy",
                    creative_approach="Test approach",
                ),
                scope=Scope(primary_focus="Test focus"),
                monitoring=Monitoring(),
                hit_budget=HitBudget(),
                notifications=Notifications(),
                parallel_profile=ParallelProfile(),
                steps=[
                    Step(
                        step_number=2,  # Non-sequential
                        title="Step 2",
                        type="search",
                        module=ModuleRef(
                            id="test", name="Test Module", is_web_source=False
                        ),
                        rationale="Test rationale",
                    )
                ],
                syntax_guide=SyntaxGuide(),
                quality=Quality(),
                artifacts=Artifacts(),
            )

        error_msg = str(exc_info.value)
        assert "Step numbers must be sequential" in error_msg

    def test_unique_step_numbers(self):
        """Test that step numbers must be unique."""
        with pytest.raises(ValidationError) as exc_info:
            UseCaseResponse(
                overview=Overview(
                    title="Test Investigation",
                    strategy_summary="Test strategy",
                    creative_approach="Test approach",
                ),
                scope=Scope(primary_focus="Test focus"),
                monitoring=Monitoring(),
                hit_budget=HitBudget(),
                notifications=Notifications(),
                parallel_profile=ParallelProfile(),
                steps=[
                    Step(
                        step_number=1,
                        title="Step 1",
                        type="search",
                        module=ModuleRef(
                            id="test1", name="Test Module 1", is_web_source=False
                        ),
                        rationale="Test rationale 1",
                    ),
                    Step(
                        step_number=1,  # Duplicate
                        title="Step 1 Duplicate",
                        type="search",
                        module=ModuleRef(
                            id="test2", name="Test Module 2", is_web_source=False
                        ),
                        rationale="Test rationale 2",
                    ),
                ],
                syntax_guide=SyntaxGuide(),
                quality=Quality(),
                artifacts=Artifacts(),
            )

        error_msg = str(exc_info.value)
        assert "Step numbers must be unique" in error_msg

    def test_cross_reference_validation(self):
        """Test cross-reference validation."""
        with pytest.raises(ValidationError) as exc_info:
            UseCaseResponse(
                overview=Overview(
                    title="Test Investigation",
                    strategy_summary="Test strategy",
                    creative_approach="Test approach",
                ),
                scope=Scope(primary_focus="Test focus"),
                monitoring=Monitoring(),
                hit_budget=HitBudget(),
                notifications=Notifications(),
                parallel_profile=ParallelProfile(),
                steps=[
                    Step(
                        step_number=1,
                        title="Step 1",
                        type="search",
                        module=ModuleRef(
                            id="test", name="Test Module", is_web_source=False
                        ),
                        rationale="Test rationale",
                    )
                ],
                cross_refs=[
                    CrossRef(
                        from_step=1,
                        to_step=2,  # Non-existent step
                        relationship="follows",
                        rationale="Test cross-ref",
                    )
                ],
                syntax_guide=SyntaxGuide(),
                quality=Quality(),
                artifacts=Artifacts(),
            )

        error_msg = str(exc_info.value)
        assert "Cross-reference to_step 2 does not exist" in error_msg


class TestNotificationDefaults:
    """Test notification default behavior."""

    def test_step_notification_default(self):
        """Test that step without notification gets 'daily' default."""
        step = Step(
            step_number=1,
            title="Test Step",
            type="search",
            module=ModuleRef(id="test", name="Test Module", is_web_source=False),
            rationale="Test rationale",
        )
        assert step.notification == "daily"

    def test_notification_validation(self):
        """Test notification value validation."""
        step = Step(
            step_number=1,
            title="Test Step",
            type="search",
            module=ModuleRef(id="test", name="Test Module", is_web_source=False),
            rationale="Test rationale",
            notification="instant",
        )
        assert step.notification == "instant"


class TestQualityChecks:
    """Test quality checks and defaults."""

    def test_quality_defaults(self):
        """Test quality model defaults."""
        quality = Quality()
        assert quality.checks == []
        assert quality.warnings == []
        assert quality.recommendations == []

    def test_quality_with_checks(self):
        """Test quality model with checks."""
        quality = Quality(
            checks=["webkilder har valgte kilder", "beløbsgrænser sat hvor muligt"],
            warnings=["Test warning"],
            recommendations=["Test recommendation"],
        )
        assert len(quality.checks) == 2
        assert len(quality.warnings) == 1
        assert len(quality.recommendations) == 1


class TestArtifactsValidation:
    """Test artifacts model validation."""

    def test_artifacts_defaults(self):
        """Test artifacts model defaults."""
        artifacts = Artifacts()
        assert artifacts.exports == []
        assert artifacts.reports == []
        assert artifacts.visualizations == []

    def test_artifacts_with_exports(self):
        """Test artifacts with export formats."""
        artifacts = Artifacts(
            exports=["csv", "json"],
            reports=["Summary Report"],
            visualizations=["Chart 1"],
        )
        assert artifacts.exports == ["csv", "json"]
        assert artifacts.reports == ["Summary Report"]
        assert artifacts.visualizations == ["Chart 1"]

    def test_invalid_export_format(self):
        """Test invalid export format raises error."""
        with pytest.raises(ValidationError):
            Artifacts(exports=["invalid_format"])


if __name__ == "__main__":
    pytest.main([__file__])
