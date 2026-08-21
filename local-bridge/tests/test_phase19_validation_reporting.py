from __future__ import annotations

import pytest

from app.hardening.readiness import ProductionReadiness
from app.reporting import EngineeringReportGenerator
from app.validation import ValidationManager, ValidationStatus, ValidationStorage
from app.validation.reference_cases import REFERENCE_CASES, reference_case

VALIDATION_TARGETS = [
    ValidationStatus.RUNNING, ValidationStatus.CANCELLED,
    ValidationStatus.COMPLETED, ValidationStatus.FAILED,
]


@pytest.mark.parametrize("target", VALIDATION_TARGETS * 5)
def test_validation_lifecycle_records_only(tmp_path, target):
    storage = ValidationStorage(tmp_path / "validation.db")
    manager = ValidationManager(storage)
    record = manager.create("demo", "repo", "python", "fastapi", [{"type": "BUG_FIX", "description": "fix auth"}])
    assert record.status is ValidationStatus.CREATED
    if target in (ValidationStatus.COMPLETED, ValidationStatus.FAILED):
        manager.transition(record.id, ValidationStatus.RUNNING.value)
    changed = manager.transition(record.id, target.value)
    assert changed.status is target
    assert not hasattr(ValidationManager, "execute")


@pytest.mark.parametrize("case_id", ["bug_fix", "refactoring", "failure_recovery"])
def test_reference_cases_are_defined(case_id):
    case = reference_case(case_id)
    assert case is not None
    assert case["name"]
    assert case["stages"]


def test_reference_flows_are_read_only(tmp_path):
    manager = ValidationManager(ValidationStorage(tmp_path / "validation.db"))
    flows = manager.reference_flows()
    assert flows["readOnly"] is True
    assert len(flows["cases"]) == 3


def test_validation_storage_round_trip(tmp_path):
    storage = ValidationStorage(tmp_path / "validation.db")
    record = ValidationManager(storage).create("demo", "repo", "python", "fastapi", [{"type": "REFACTOR", "description": "extract module"}])
    assert storage.get(record.id) is not None
    assert storage.list("demo")[0].id == record.id
    assert storage.scenarios(record.id)[0].scenario_type.value == "REFACTOR"
    manager = ValidationManager(storage)
    run = manager.record_run(storage.scenarios(record.id)[0].id, workflow_id="wf_1", execution_loop_id="loop_1", agents=["ag_1"], result="COMPLETED", human_rating=88)
    assert storage.runs(storage.scenarios(record.id)[0].id)[0].id == run.id


@pytest.mark.parametrize("scenario_type", ["BUG_FIX", "FEATURE", "REFACTOR", "ARCHITECTURE_CHANGE"])
def test_validation_scenario_types(scenario_type):
    from app.validation import ValidationScenario, ValidationScenarioType
    scenario = ValidationScenario("vsc_1", "val_1", ValidationScenarioType(scenario_type), "desc")
    assert scenario.as_dict()["scenarioType"] == scenario_type
    assert scenario.as_dict()["readOnly"] is True


def test_reporting_generator_sections(tmp_path):
    report = EngineeringReportGenerator().generate(
        "demo",
        insights=[{"id": "i1", "title": "architecture_risk"}],
        decisions=[{"id": "d1", "title": "extract auth"}],
        loops=[{"id": "l1", "status": "COMPLETED"}],
        verifications=[{"id": "v1", "status": "PASS"}],
        failures=[{"id": "f1", "severity": "high"}],
        learning=[{"id": "e1", "title": "lesson"}],
    )
    assert report.as_dict()["readOnly"] is True
    assert report.analysis
    assert report.decisions
    assert report.execution
    assert report.risk
    assert report.learning
    assert "Engineering Report" in report.as_markdown()


def test_reporting_is_deterministic(tmp_path):
    generator = EngineeringReportGenerator()
    first = generator.generate("demo", loops=[{"id": "l1", "status": "COMPLETED"}])
    second = generator.generate("demo", loops=[{"id": "l1", "status": "COMPLETED"}])
    assert first.as_dict() == second.as_dict()


def test_readiness_environment_and_migrations(tmp_path):
    from app.config import get_settings
    settings = get_settings()
    readiness = ProductionReadiness(settings)
    env = readiness.environment()
    assert env["status"] in {"pass", "warn"}
    migrations = readiness.migrations()
    assert migrations["status"] in {"pass", "warn"}
    backup = readiness.backup_restore()
    assert backup["status"] == "pass"
    assert readiness.summary()["readOnly"] is True


@pytest.mark.parametrize("index", range(6))
def test_readiness_backup_restore_is_repeatable(tmp_path, index):
    from app.config import get_settings
    readiness = ProductionReadiness(get_settings())
    assert readiness.backup_restore()["status"] == "pass"


def test_validation_api_requires_approval(bridge):
    pending = bridge.client.post("/validation/create", json={"project": "demo", "repository": "repo", "language": "python", "framework": "fastapi", "scenarios": [{"type": "BUG_FIX", "description": "fix"}]})
    assert pending.status_code == 202
    assert pending.json()["action"] == "validation_create"
    assert bridge.client.get("/validation/list").json()["validations"] == []


def test_validation_reference_api_read_only(bridge):
    response = bridge.client.get("/validation/reference")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_reporting_api_read_only(bridge):
    response = bridge.client.get("/reporting/generate?project=demo")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_production_readiness_api_read_only(bridge):
    response = bridge.client.get("/production/readiness")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
