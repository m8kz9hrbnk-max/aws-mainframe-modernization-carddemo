"""Independent known-answer checks for the executable original posting batch."""
import json
from pathlib import Path

import pytest

from reference.run_posting_reference import build_reference, load_cases, run_case


@pytest.fixture(scope="session")
def executable(tmp_path_factory):
    return build_reference(tmp_path_factory.mktemp("posting-reference-build"))


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["name"])
def test_posting_batch_matches_known_answers(case, executable):
    result = run_case(case, executable)
    expected = case["expected"]
    golden_path = Path(__file__).resolve().parents[1] / "evidence/reference/posting" / f"{case['name']}.json"
    assert result == json.loads(golden_path.read_text())
    assert result["status"] == expected["status"], result
    assert result["return_code"] == expected["return_code"], result
    assert result["counts"] == expected["counts"], result
    assert result["error_kind"] == expected.get("error_kind")
    if expected["status"] == "error":
        assert result["accounts"] is None
        assert result["tran_cat_balances"] is None
        assert result["transactions"] is None
        assert result["rejects"] is None
        account_values = [
            {field: row[field] for field in ("account_id", "current_balance", "cycle_credit", "cycle_debit")}
            for row in result["partial_state"]["accounts"]
        ]
        assert account_values == expected["partial_state"]["accounts"]
        assert result["partial_state"]["tran_cat_balances"] == expected["partial_state"]["tran_cat_balances"]
        return

    assert result["stderr"] == ""
    account_values = [
        {field: row[field] for field in ("account_id", "current_balance", "cycle_credit", "cycle_debit")}
        for row in result["accounts"]
    ]
    assert account_values == expected["accounts"]
    assert result["tran_cat_balances"] == expected["tran_cat_balances"]
    assert [row["transaction_id"] for row in result["transactions"]] == expected["transaction_ids"]
    assert [row["reason_code"] for row in result["rejects"]] == [
        row["reason_code"] for row in expected["rejects"]]
    assert [
        {field: row[field] for field in ("input_seq", "transaction_id", "reason_code", "reason_desc")}
        for row in result["rejects"]
    ] == expected["rejects"]
    for transaction in result["transactions"]:
        assert transaction["processing_timestamp"] == "2026-09-22-12.00.00.000000"
    if case["name"] == "existing_transact":
        survives = "OLD0000000000001" in expected["transaction_ids"]
        assert survives is expected["preexisting_transaction_survives"]


def test_duplicate_transaction_keeps_posting_side_effects(executable):
    case = next(case for case in load_cases() if case["name"] == "duplicate_tran_id")
    result = run_case(case, executable)
    assert "ERROR WRITING TO TRANSACTION FILE" in result["stdout"]
    assert result["error_kind"] == "DUPLICATE_TRANSACTION_ID"
    assert result["partial_state"]["accounts"][0]["current_balance"] == "30.00"
    assert result["partial_state"]["tran_cat_balances"][0]["balance"] == "30.00"
