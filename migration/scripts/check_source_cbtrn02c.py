"""Verify CBTRN02C source, fixtures, and frozen reference evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "evidence/acceptance-manifest-cbtrn02c.json").read_text())
for name, expected in manifest["sha256"].items():
    actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"CBTRN02C acceptance mismatch: {name}")
cases = json.loads((ROOT / "fixtures/posting_cases.json").read_text())["cases"]
identities = [case["name"] for case in cases]
if identities != manifest["cases"]:
    raise SystemExit("CBTRN02C case identities differ from the acceptance manifest")
print(f"Verified {len(manifest['sha256'])} CBTRN02C frozen files and {len(identities)} case identities")
