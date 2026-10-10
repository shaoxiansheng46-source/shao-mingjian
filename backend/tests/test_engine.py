import json
from pathlib import Path

from backend.app.core.engine import load_database, reference_enumeration, validate_input, InputValidationError

ROOT = Path(__file__).resolve().parents[2]


def read_input(name):
    return json.loads((ROOT / "SST_V1_4_Demo_Data" / name).read_text(encoding="utf-8"))


def test_reference_regression():
    result = reference_enumeration(read_input("sample_input_feasible.json"))
    assert (result["candidate_count"], result["feasible_count"], result["pareto_count"]) == (14400, 34, 2)


def test_guards():
    db = load_database()
    for name, error in [("sample_input_engineering_blocked.json", "SYNTHETIC_DATA_BLOCKED_IN_ENGINEERING"), ("sample_input_unsupported.json", "UNSUPPORTED_WAVEFORM")]:
        try:
            validate_input(read_input(name), db)
        except InputValidationError as exc:
            assert str(exc) == error
        else:
            raise AssertionError("guard did not reject input")
