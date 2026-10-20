"""Compile and run unchanged AWS CBTRN02C against synthetic indexed files."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
import os
from decimal import Decimal
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
FIXED_CLOCK = "2026/09/22 12:00:00.00+00:00"


def load_cases():
    return json.loads((ROOT / "fixtures/posting_cases.json").read_text())["cases"]


def _defaults():
    return json.loads((ROOT / "fixtures/posting_cases.json").read_text())["defaults"]


def build_reference(build_dir=None):
    compiler = os.environ.get("COBC") or shutil.which("cobc")
    if not compiler:
        raise RuntimeError("Install GnuCOBOL with indexed-file support (cobc).")
    build_dir = Path(build_dir or ROOT / ".build").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    executable = build_dir / "carddemo-posting-reference"
    sources = [ROOT / "reference/posting_driver.cbl",
               ROOT / "upstream/app/cbl/CBTRN02C.cbl",
               ROOT / "reference/abend.cbl"]
    command = [compiler, "-x", "-std=ibm", "-Wno-others", "-I",
               str(ROOT / "upstream/app/cpy"), "-o", str(executable)]
    result = subprocess.run(command + [str(path) for path in sources],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Reference compile failed:\n{result.stdout}\n{result.stderr}")
    return executable


def _money(value):
    amount = Decimal(str(value))
    return "0.00" if amount == 0 else format(amount, ".2f")


def _write_lines(path, rows):
    for row in rows:
        if any(any(ch in str(value) for ch in "|\r\n") for value in row):
            raise ValueError("Fixture contains an invalid adapter delimiter")
    path.write_text("".join("|".join(map(str, row)) + "\n" for row in rows))


def _account_rows(case, defaults):
    account_defaults = defaults["account"]
    fields = ("account_id", "group", "current_balance", "cycle_credit", "cycle_debit",
              "active", "credit_limit", "cash_credit_limit", "open_date",
              "expiration_date", "reissue_date", "zip")
    rows = []
    for account in case["accounts"]:
        values = {**account_defaults, **account}
        rows.append([values[field] for field in fields])
    return rows


def _transaction(case_transaction, defaults, sequence):
    values = {**defaults["transaction"], **case_transaction}
    values.setdefault("transaction_id", f"POST{sequence:012d}")
    return {
        "transaction_id": values["transaction_id"],
        "type": values["type"],
        "category": values["category"],
        "source": values["source"],
        "description": values["description"],
        "amount": _money(values["amount"]),
        "merchant_id": values["merchant_id"],
        "merchant_name": values["merchant_name"],
        "merchant_city": values["merchant_city"],
        "merchant_zip": values["merchant_zip"],
        "card_number": values["card_number"],
        "original_timestamp": values["original_timestamp"],
        "processing_timestamp": values["processing_timestamp"],
    }


def _transaction_rows(transactions):
    fields = ("transaction_id", "type", "category", "source", "description", "amount",
              "merchant_id", "merchant_name", "merchant_city", "merchant_zip",
              "card_number", "original_timestamp", "processing_timestamp")
    return [[transaction[field] for field in fields] for transaction in transactions]


def _read_table(path, count, name):
    rows = []
    for line in path.read_text().splitlines():
        values = [value.strip() for value in line.split("|")]
        if len(values) != count:
            raise ValueError(f"Malformed {name} export: {line!r}")
        rows.append(values)
    return rows


def _accounts(path):
    result = []
    for values in _read_table(path, 12, "account"):
        result.append(dict(account_id=values[0], group=values[1],
                           current_balance=_money(values[2]), cycle_credit=_money(values[3]),
                           cycle_debit=_money(values[4]), active=values[5],
                           credit_limit=_money(values[6]), cash_credit_limit=_money(values[7]),
                           open_date=values[8], expiration_date=values[9],
                           reissue_date=values[10], zip=values[11]))
    return result


def _categories(path):
    rows = _read_table(path, 4, "transaction category balance")
    return [dict(account_id=row[0], type=row[1], category=row[2], balance=_money(row[3]))
            for row in rows]


def _transactions(path):
    result = []
    for values in _read_table(path, 13, "transaction"):
        result.append(dict(transaction_id=values[0], type=values[1], category=values[2],
                           source=values[3], description=values[4], amount=_money(values[5]),
                           card_number=values[6], original_timestamp=values[7],
                           processing_timestamp=values[8], merchant_id=values[9],
                           merchant_name=values[10], merchant_city=values[11],
                           merchant_zip=values[12]))
    return result


def _rejects(path, source_transactions):
    queues = defaultdict(deque)
    for input_seq, transaction in enumerate(source_transactions, 1):
        signature = (transaction["transaction_id"], transaction["card_number"],
                     transaction["amount"], transaction["original_timestamp"])
        queues[signature].append(input_seq)
    result = []
    for values in _read_table(path, 6, "reject"):
        transaction_id, card_number, amount, original_timestamp, code, description = values
        signature = (transaction_id, card_number, _money(amount), original_timestamp)
        if not queues[signature]:
            raise ValueError(f"Reject does not match a daily input record: {signature!r}")
        result.append(dict(input_seq=queues[signature].popleft(),
                           transaction_id=transaction_id, card_number=card_number,
                           amount=_money(amount), original_timestamp=original_timestamp,
                           reason_code=code, reason_desc=description.strip()))
    return result


def _export(executable, work, env, source_transactions):
    completed = subprocess.run([str(executable), "export"], cwd=work, env=env,
                               capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise RuntimeError(f"Reference export failed: {completed.stdout}\n{completed.stderr}")
    accounts = _accounts(work / "accounts.out")
    categories = _categories(work / "categories.out")
    transactions = _transactions(work / "transactions.out")
    rejects = _rejects(work / "rejects.out", source_transactions)
    return accounts, categories, transactions, rejects


def run_case(case, executable=None, work_dir=None):
    executable = Path(executable or build_reference()).resolve()
    if work_dir is None:
        with tempfile.TemporaryDirectory(prefix="carddemo-posting-reference-") as temporary:
            return run_case(case, executable, temporary)
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    defaults = _defaults()
    transactions = [_transaction(row, defaults, number)
                    for number, row in enumerate(case["transactions"], 1)]
    preseeded = [_transaction(row, defaults, number)
                 for number, row in enumerate(case.get("preseed_transactions", []), 1)]
    env = os.environ.copy()
    env["COB_CURRENT_DATE"] = FIXED_CLOCK
    env.update({
        "DD_DALYTRAN": str(work / "DALYTRAN"),
        "DD_XREFFILE": str(work / "XREFFILE"),
        "DD_ACCTFILE": str(work / "ACCTFILE"),
        "DD_TCATBALF": str(work / "TCATBALF"),
        "DD_TRANFILE": str(work / "TRANFILE"),
        "DD_DALYREJS": str(work / "DALYREJS"),
    })
    inputs = {
        "ACCOUNTS": _account_rows(case, defaults),
        "XREFS": [[xref["card_number"], xref["account_id"],
                   xref.get("customer_id", "000000001")] for xref in case["xrefs"]],
        "CATEGORIES": [[row["account_id"], row["type"], row["category"], row["balance"]]
                       for row in case["categories"]],
        "TRANSACTIONS": _transaction_rows(transactions),
        "PRESEEDED_TRANSACTIONS": _transaction_rows(preseeded),
    }
    for name, rows in inputs.items():
        path = work / f"{name.lower()}.txt"
        _write_lines(path, rows)
        env[f"REF_{name}_INPUT"] = str(path)
    output_paths = {
        "REF_ACCOUNTS_OUTPUT": work / "accounts.out",
        "REF_CATEGORIES_OUTPUT": work / "categories.out",
        "REF_TRANSACTIONS_OUTPUT": work / "transactions.out",
        "REF_REJECTS_OUTPUT": work / "rejects.out",
    }
    env.update({key: str(value) for key, value in output_paths.items()})
    seeded = subprocess.run([str(executable), "seed"], cwd=work, env=env,
                            capture_output=True, text=True, timeout=60)
    if seeded.returncode:
        raise RuntimeError(f"Reference seed failed: {seeded.stdout}\n{seeded.stderr}")
    executed = subprocess.run([str(executable), "run"], cwd=work, env=env,
                              capture_output=True, text=True, timeout=60)
    counts = {}
    for key, label in (("processed", "PROCESSED"), ("rejected", "REJECTED")):
        match = re.search(rf"TRANSACTIONS {label}\s*:\s*(\d+)", executed.stdout)
        counts[key] = int(match.group(1)) if match else None
    successful = executed.returncode in (0, 4)
    errors = {
        "ERROR WRITING TO TRANSACTION FILE": "DUPLICATE_TRANSACTION_ID",
    }
    error_kind = None if successful else next(
        (kind for message, kind in errors.items() if message in executed.stdout),
        "UNCLASSIFIED_REFERENCE_ERROR")
    result = dict(case=case["name"], upstream_commit=UPSTREAM_COMMIT,
                  status="success" if successful else "error",
                  error_kind=error_kind, return_code=executed.returncode,
                  stdout=executed.stdout, stderr=executed.stderr, counts=counts,
                  accounts=None, tran_cat_balances=None, transactions=None, rejects=None)
    exported = _export(executable, work, env, transactions)
    accounts, categories, posted, rejected = exported
    if successful:
        result.update(accounts=accounts, tran_cat_balances=categories,
                      transactions=posted, rejects=rejected)
    else:
        result["partial_state"] = dict(accounts=accounts, tran_cat_balances=categories)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="baseline", help="Name from posting_cases.json")
    parser.add_argument("--all", action="store_true", help="Run every supplied case")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence/reference/posting")
    args = parser.parse_args()
    cases = [case for case in load_cases() if args.all or case["name"] == args.case]
    if not cases:
        parser.error(f"Unknown case: {args.case}")
    executable = build_reference()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        result = run_case(case, executable)
        destination = args.output_dir / f"{case['name']}.json"
        destination.write_text(json.dumps(result, indent=2) + "\n")
        print(f"{case['name']}: {result['status']} (exit {result['return_code']}) -> {destination}")


if __name__ == "__main__":
    main()
