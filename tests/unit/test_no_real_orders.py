"""Test ensuring NO real broker order execution functions exist in codebase."""

import re
from pathlib import Path

FORBIDDEN_PATTERNS = [
    r"\bplace_order\b",
    r"\bmodify_order\b",
    r"\bcancel_order\b",
    r"\bbasket_order\b",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_no_real_order_calls_in_codebase():
    """Fail if any broker SDK order placement calls are imported or referenced."""
    source_dirs = [PROJECT_ROOT / "app", PROJECT_ROOT / "config", PROJECT_ROOT / "scripts"]
    violations = []

    for d in source_dirs:
        if not d.exists():
            continue
        for file_path in d.rglob("*.py"):
            content = file_path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_PATTERNS:
                matches = list(re.finditer(pattern, content))
                if matches:
                    violations.append(f"{file_path.relative_to(PROJECT_ROOT)} matches '{pattern}'")

    assert not violations, "Paper Desk safety violation: Real order API calls detected!\n" + "\n".join(violations)
