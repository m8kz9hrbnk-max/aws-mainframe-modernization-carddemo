# CBTRN02C executable reference

This package compiles the unchanged upstream `CBTRN02C` daily posting batch at
`59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`. Its synthetic cases and manually
derived expected values are in `fixtures/posting_cases.json`; frozen outputs from
the GnuCOBOL run are in `evidence/reference/posting/`.

## Run

From `migration/`, with GnuCOBOL and the Python test requirements installed:

```sh
python reference/run_posting_reference.py --all --output-dir evidence/reference/posting
python -m pytest tests/test_posting_reference.py -q
```

The runner compiles with `cobc -x -std=ibm`, creates a new temporary directory
for each case, fixes `COB_CURRENT_DATE` to `2026/09/22 12:00:00.00+00:00`, and
exports the account, category-balance, transaction, and reject records as JSON.
Reject runs with return code 4 are successful batch executions. The duplicate
transaction case abends with return code 99 and exports account/category
`partial_state`; those partial values document observed side effects and are not
a parity target.

## Adapter boundaries

- `posting_driver.cbl` seeds fixed 350-byte `DALYTRAN` records by moving fixture
  values into the unchanged `CVTRA06Y` layout, so signed amounts use GnuCOBOL's
  zoned-decimal overpunch representation. It creates the indexed `XREFFILE`,
  `ACCTFILE`, and `TCATBALF`, optionally seeds indexed `TRANFILE`, calls
  `CBTRN02C`, and exports its files. `DALYREJS` is read as fixed 430-byte
  sequential records.
- The adapter maps GnuCOBOL `DD_*` environment variables to local files.
  Indexed-file behavior comes from the installed GnuCOBOL backend; it is not a
  VSAM emulator and does not certify IBM runtime behavior.
- `reference/abend.cbl` is the existing CEE3ABD stub and is reused unchanged.
  The posting runner classifies a duplicate transaction write error as
  `DUPLICATE_TRANSACTION_ID`; other abnormal returns are unclassified.
- Account records contain the same 12 exported business fields as the existing
  CBACT04C adapter; transactions contain the same 13 fields. Monetary values
  are decimal strings and negative zero is normalized to `0.00`. Category
  balances are sorted by account, type, and category. Rejects preserve file
  order and expose input sequence, transaction/card identifiers, amount,
  original timestamp, reason code, and trimmed description.
- An abend leaves no canonical account/category/transaction/reject payload.
  The separately exported partial account/category state makes the source's
  no-rollback behavior visible without treating it as transaction-level parity.

## Observed source behavior

The fixtures cover normal posting; reject codes 100–103; equal-limit and
expiration boundaries; reason 103 taking precedence over 102; input-order and
payment-dependent limit checks; the `S9(9)V99` temporary and category-balance
truncations; inactive-account posting; empty input; duplicate transaction IDs;
and a pre-seeded transaction file. The expected values are derived from the
unchanged source rules in `docs/CBTRN02C-ANALYSIS.md`, not copied from the
reference output. The duplicate-ID partial state is descriptive only.

The `existing_transact` result records whether the pre-existing transaction
did not survive `OPEN OUTPUT` under the tested GnuCOBOL 3.1.2/BDB indexed-file
backend; only the new posting was exported. This is an observation under
GnuCOBOL/BDB, not IBM-certified behavior. The fixed clock produced processing
timestamps in `YYYY-MM-DD-HH.MM.SS.000000` format (`2026-09-22-12.00.00.000000`
for this run).

The setup used Python 3.10.12, pytest 8.3.5, and OpenJDK 17.0.20.1 on Ubuntu.
