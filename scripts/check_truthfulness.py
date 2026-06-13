#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
failures = []
required = [
    "README.md",
    "docs/truthful-build-doctrine.md",
    "docs/claim_matrix.md",
    "docs/release_truthfulness_checklist.md",
]
for rel in required:
    if not (ROOT / rel).exists():
        failures.append(f"missing {rel}")

readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace") if (ROOT / "README.md").exists() else ""
claim_matrix = (ROOT / "docs/claim_matrix.md").read_text(encoding="utf-8", errors="replace") if (ROOT / "docs/claim_matrix.md").exists() else ""

banned = [r"ultimate", r"state[- ]of[- ]the[- ]art", r"all[- ]in[- ]one", r"production[- ]ready", r"enterprise[- ]ready", r"guaranteed", r"seamless"]
for pattern in banned:
    if re.search(pattern, readme, re.I):
        failures.append(f"README contains inflated phrase matching /{pattern}/i")

if not re.search(r"limitations|boundaries|not implemented|optional|requires|credential|manual|planned|experimental|caveat", readme, re.I):
    failures.append("README lacks explicit limitations/boundaries language")

if "Untested" in claim_matrix:
    failures.append("claim matrix contains Untested rows; label as manual/optional/failing/passing instead")

if "unsupported claims are defects" not in (ROOT / "docs/truthful-build-doctrine.md").read_text(encoding="utf-8", errors="replace").lower():
    failures.append("truthful build doctrine missing core invariant wording")

if failures:
    print("Truthfulness documentation check failed:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    sys.exit(1)

print("Truthfulness documentation check passed.")
