# Step 0 – Analysis of CBTRN02C (POSTTRAN – daily transaction posting)

Repo: `martinwolff84-arch/aws-mainframe-modernization-carddemo`, branch `demo-baseline`
@ `88a86f152d2962058525c2a3383397795a7ecfe2`. Source: `app/cbl/CBTRN02C.cbl` (731 lines), JCL `app/jcl/POSTTRAN.jcl`.
Analysis only: no code changed, no PR. Line numbers refer to `CBTRN02C.cbl`.

## 1. Purpose
Reads the daily transaction file in order, validates every record against card cross-reference and
account master. Valid records are posted (category balance, account balance, transaction master);
invalid records go to a reject file with a reason code.

## 2. Inputs / outputs

| DD | File | Org / access | Mode | Key | LRECL | Copybook |
|---|---|---|---|---|---|---|
| DALYTRAN | Daily transactions | Sequential | INPUT | – | 350 | CVTRA06Y |
| XREFFILE | Card → account xref | KSDS random | INPUT | card num X(16) | 50 | CVACT03Y |
| ACCTFILE | Account master | KSDS random | I-O (REWRITE) | acct id 9(11) | 300 | CVACT01Y |
| TCATBALF | Transaction category balance | KSDS random | I-O (WRITE/REWRITE) | acct 9(11)+type X(2)+cat 9(4) | 50 | CVTRA01Y |
| TRANFILE | Transaction master | KSDS random | **OUTPUT** | tran id X(16) | 350 | CVTRA05Y |
| DALYREJS | Rejects (GDG +1) | Sequential | OUTPUT | – | 430 | 350 input record + 80 trailer |

All numeric fields are **zoned decimal (DISPLAY) with overpunch sign** (e.g. `0000005047G` = +50.47,
`}` = negative last digit) – no COMP/COMP-3 in this program's records.

Key fields:
- DALYTRAN / TRAN: `ID X(16)`, `TYPE-CD X(2)`, `CAT-CD 9(4)`, `SOURCE X(10)`, `DESC X(100)`, `AMT S9(9)V99`,
  `MERCHANT-ID 9(9)`, `MERCHANT-NAME/CITY X(50)`, `ZIP X(10)`, `CARD-NUM X(16)`, `ORIG-TS X(26)`, `PROC-TS X(26)`.
- ACCOUNT: `CURR-BAL`, `CREDIT-LIMIT`, `CASH-CREDIT-LIMIT`, `CURR-CYC-CREDIT`, `CURR-CYC-DEBIT` all `S9(10)V99`;
  `EXPIRAION-DATE X(10)` (sic), `ACTIVE-STATUS X(1)`.
- TCATBAL: `TRAN-CAT-BAL S9(9)V99`.
- Reject trailer: `REASON 9(4)` + `DESC X(76)`.

## 3. Business rules

| # | Rule | Lines |
|---|---|---|
| R1 | Records processed strictly in input order; counters for processed and rejected. | 193-233 |
| R2 | Card number not in XREF → reject **100** "INVALID CARD NUMBER FOUND"; no further checks. | 380-392 |
| R3 | Account (from XREF) not found → reject **101** "ACCOUNT RECORD NOT FOUND". | 393-400 |
| R4 | Overlimit: `TEMP = CYC-CREDIT − CYC-DEBIT + AMT`; if `CREDIT-LIMIT < TEMP` → **102** "OVERLIMIT TRANSACTION". | 403-412 |
| R5 | Expiry: if `EXPIRAION-DATE < ORIG-TS(1:10)` (string compare `YYYY-MM-DD`) → **103** "TRANSACTION RECEIVED AFTER ACCT EXPIRATION". | 414-420 |
| R6 | Reject record = original 350-byte input + 4-digit code + 76-char description. | 446-466 |
| R7 | Posting order per valid record: TCATBAL → ACCOUNT → TRANSACT. | 424-445 |
| R8 | TCATBAL key = (xref acct id, type cd, cat cd). Missing → create with balance = AMT; existing → balance += AMT. | 467-544 |
| R9 | ACCOUNT: `CURR-BAL += AMT`; if `AMT >= 0` → `CYC-CREDIT += AMT`, else `CYC-DEBIT += AMT` (debit becomes more negative). | 545-560 |
| R10 | TRANSACT = copy of input fields, `PROC-TS` = current timestamp `YYYY-MM-DD-HH.MM.SS.hh0000` (input PROC-TS ignored). | 424-445, 692-706 |
| R11 | RC = 4 if at least one reject, else 0. | 229-231 |
| R12 | Any unexpected file status → display + abend 999 (CEE3ABD). | 707-713 |

## 4. Legacy quirks / possible defects (list only – preserve in migration)

| # | Observation | Impact for migration |
|---|---|---|
| Q1 | 103 overwrites 102 when both apply (last check wins). Only one code per reject. | Must keep precedence: 100 > 101 > 103 > 102. |
| Q2 | Overlimit uses cycle fields, not `CURR-BAL`. Because debits are stored negative, `CREDIT − DEBIT` = gross activity; **payments/credits (negative AMT) increase the value seen by later overlimit checks**. | Looks like a defect; preserve and flag for business decision. |
| Q3 | Order dependency: each posting changes CYC-CREDIT/DEBIT used by the next record on the same account. | No set-based join; needs ordered per-account fold (see §5). |
| Q4 | `WS-TEMP-BAL` is `S9(9)V99` but account fields are `S9(10)V99` → high-order digit silently truncated (no ON SIZE ERROR). | Reproduce truncation to stay field-exact. |
| Q5 | `ADD` to `TRAN-CAT-BAL S9(9)V99` / account fields without ON SIZE ERROR → silent overflow truncation. | Same. |
| Q6 | `ACCT-ACTIVE-STATUS` is not checked; inactive accounts get postings. | Do not add the check. |
| Q7 | Reason 109 on account REWRITE INVALID KEY is set but ignored: record is still written to TRANSACT and not counted as reject (effectively dead code). | Keep, document. |
| Q8 | No rollback: if TRANSACT write fails (e.g. duplicate tran id → status 22) the program abends **after** TCATBAL and ACCOUNT were already updated. | Define abend behaviour for Delta (all-or-nothing vs partial) – question B4. |
| Q9 | TRANFILE opened `OUTPUT` → transaction master is rebuilt/emptied each run (platform-dependent for KSDS). | Verify in Step 1 reference; question B3. |
| Q10 | Expiry check is a lexical string compare; malformed dates are not validated. | Compare strings, not parsed dates. |
| Q11 | Diagnostics bug: DALYREJS close error displays `XREFFILE-STATUS` (line 649). | Cosmetic, log only. |
| Q12 | `PROC-TS` comes from the system clock per record → non-deterministic. | Inject a fixed clock for parity tests. |

## 5. Proposed Delta model and Spark mapping

Tables (Unity Catalog, one schema per environment, e.g. `carddemo_dev`):
- `daily_transactions` (input, with `input_seq BIGINT` to preserve file order)
- `card_xref`, `accounts`, `tran_cat_balances`, `transactions`, `daily_rejects`, `job_runs` (counts + RC)
- Amounts stored as `DECIMAL(11,2)` / `DECIMAL(12,2)`, computed internally as **integer cents** with explicit PIC-width truncation helpers.

Processing:
1. Read input with `input_seq`; left-join xref and accounts (no inner joins → 100/101 must not be lost).
2. Rows without valid account → rejects immediately (order-independent).
3. Remaining rows: `groupBy(acct_id)` + `applyInPandas` (or `mapInPandas` after `repartition(acct_id)` + sort by `input_seq`) doing the
   sequential fold per account: running CYC-CREDIT/DEBIT, rules R4/R5 with Q1/Q2/Q4, posting or reject.
   Accounts are independent → parallel across accounts, sequential within one account = same result as COBOL.
4. TCATBAL: aggregate posted amounts per key with PIC truncation, then one `MERGE` (insert-or-update).
5. ACCOUNT: one `MERGE` with new balances; TRANSACT: overwrite/append per B3; REJECTS: append with `run_id`.
6. Atomicity: write all targets per `run_id` and commit via staging + `MERGE`/`replaceWhere`; RC 4/0 as job output.

## 6. Open business-rule questions

- **B1** Keep Q2 (payments consume limit in later checks) for parity, or fix later as separate change? *(Proposal: keep, flag.)*
- **B2** Keep 103-over-102 precedence and single reason code? *(Proposal: keep.)*
- **B3** TRANSACT: rebuild per run (as OUTPUT suggests) or append to history in Delta? *(Proposal: parity mode = replace; history via Delta time travel.)*
- **B4** On abend: all-or-nothing in Delta (cleaner) or replicate partial updates? *(Proposal: all-or-nothing, documented deviation.)*
- **B5** RC 4 in Databricks Workflow: job "succeeded with warnings" (task value) instead of failure? *(Proposal: success + task value `rc=4`.)*
- **B6** Scope: only CBTRN02C, or also the downstream chain INTCALC (CBACT04C, already migrated) in Step 3? *(Proposal: as planned in Step 3.)*

## Next step (Step 1, after approval)
Executable GnuCOBOL reference + synthetic fixtures for CBTRN02C (incl. Q1-Q5 edge cases), frozen golden outputs, PR into `demo-baseline`.
