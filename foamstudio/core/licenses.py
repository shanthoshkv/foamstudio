"""GPL-3.0-only compatibility check for third-party licence strings.

`pip-licenses` emits free-form text, not reliable SPDX. The rules are:

- `AND` means every clause must be compatible.
- `OR`, and a short `;`-separated classifier list, means one alternative is enough.
- GPL-2.0-only cannot join a GPL-3.0-only program. GPL-2.0-or-later can.
- LGPL is not GPL-2.0-only.
- An unknown or missing licence fails closed.
- A proprietary classifier fails unless another alternative in the same OR-list
  is a compatible open-source grant (Qt publishes LGPL and a commercial licence).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import cast

APP_LICENSE_ID = "GPL-3.0-only"

_ALLOW = re.compile(
    r"(?:"
    r"\bmit\b"
    r"|bsd"
    r"|apache software license"
    r"|apache[- ](?:license[- ])?2"
    r"|\bisc\b"
    r"|lgpl"
    r"|lesser general public"
    r"|gnu library or lesser"
    r"|mpl[- ]2"
    r"|mozilla public license 2"
    r"|python software foundation"
    r"|\bpsf\b"
    r"|unlicense"
    r"|cc0"
    r"|public domain"
    r"|0bsd"
    r"|historical permission notice"
    r"|\bhpnd\b"
    r"|\bzlib\b"
    r"|gnu general public license v3"
    r"|gnu general public license version 3"
    r"|gpl-?v?3"
    r"|gnu affero general public license"
    r"|agpl-?v?3"
    r")",
    re.IGNORECASE,
)
_PROPRIETARY = re.compile(r"proprietary|commercial|all rights reserved", re.IGNORECASE)
_APACHE_OLD = re.compile(r"apache[- ](?:license[- ])?1(?:\b|\.)", re.IGNORECASE)
_GPL2 = re.compile(
    r"(?<![a-z])gpl-?v?2|general public license v(?:ersion )?2",
    re.IGNORECASE,
)
_LATER = re.compile(r"or[- ]later|\+|plus", re.IGNORECASE)
_ONLY = re.compile(r"\bonly\b", re.IGNORECASE)
_LGPL = re.compile(r"lgpl|lesser", re.IGNORECASE)
_UNKNOWN = {"", "UNKNOWN", "NONE", "NOASSERTION"}


@dataclass(frozen=True)
class LicenseVerdict:
    expression: str
    compatible: bool
    reason: str


def _split_top(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    token = f" {operator} "
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "(":
            depth += 1
            buf.append(char)
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            buf.append(char)
            index += 1
            continue
        # SPDX operators are uppercase. "Library or Lesser" is English, not an operator.
        if depth == 0 and expression[index : index + len(token)] == token:
            parts.append("".join(buf).strip())
            buf = []
            index += len(token)
            continue
        buf.append(char)
        index += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _strip_parens(text: str) -> str:
    value = text.strip()
    while value.startswith("(") and value.endswith(")") and _balanced(value[1:-1]):
        value = value[1:-1].strip()
    return value


def _classifier_parts(expression: str) -> list[str] | None:
    if ";" not in expression:
        return None
    parts = [part.strip() for part in expression.split(";") if part.strip()]
    if len(parts) < 2:
        return None
    if all(len(part) <= 80 for part in parts):
        return parts
    return None


def _one_alternative(text: str) -> LicenseVerdict:
    raw = _strip_parens(text)
    if raw.upper() in _UNKNOWN:
        return LicenseVerdict(text, False, "missing or unknown licence")
    if _APACHE_OLD.search(raw):
        return LicenseVerdict(text, False, "Apache-1.x is incompatible with GPL-3.0")
    if _GPL2.search(raw) and not _LGPL.search(raw):
        if _LATER.search(raw) and not _ONLY.search(raw):
            return LicenseVerdict(text, True, "GPL-2.0-or-later can be used under GPL-3.0")
        return LicenseVerdict(text, False, "GPL-2.0-only is incompatible with GPL-3.0")
    if _PROPRIETARY.search(raw):
        return LicenseVerdict(text, False, "proprietary licence")
    if _ALLOW.search(raw):
        return LicenseVerdict(text, True, "compatible with GPL-3.0-only")
    return LicenseVerdict(text, False, "unrecognised licence")


def _or_clause(text: str) -> LicenseVerdict:
    alternatives = _split_top(text, "OR")
    if len(alternatives) == 1:
        classified = _classifier_parts(text)
        if classified is not None:
            alternatives = classified
        elif " / " in text:
            alternatives = [part.strip() for part in text.split(" / ") if part.strip()]
    verdicts = [_one_alternative(part) for part in alternatives]
    good = [item for item in verdicts if item.compatible]
    if good:
        if len(verdicts) == 1:
            return verdicts[0]
        chosen = _strip_parens(good[0].expression)
        return LicenseVerdict(text, True, f"using {chosen}: {good[0].reason}")
    reasons = "; ".join(f"{item.expression}: {item.reason}" for item in verdicts)
    return LicenseVerdict(text, False, reasons)


def license_compatible(expression: str) -> LicenseVerdict:
    text = " ".join(expression.split())
    clauses = _split_top(text, "AND") if text else [text]
    verdicts = [_or_clause(clause) for clause in clauses]
    if verdicts and all(item.compatible for item in verdicts):
        if len(verdicts) == 1:
            return verdicts[0]
        return LicenseVerdict(text, True, "every AND clause is compatible with GPL-3.0-only")
    reasons = "; ".join(item.reason for item in verdicts if not item.compatible)
    return LicenseVerdict(text, False, reasons or "missing or unknown licence")


def normalise_entries(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise ValueError("Licence report must be a JSON list of packages.")
    entries: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Licence entry {index} is not an object.")
        mapping = cast(dict[object, object], item)
        name = mapping.get("Name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Licence entry {index} is missing Name.")
        version = mapping.get("Version", "")
        license_name = mapping.get("License", "")
        entries.append(
            {
                "Name": name.strip(),
                "Version": version if isinstance(version, str) else str(version),
                "License": license_name if isinstance(license_name, str) else str(license_name),
            }
        )
    return entries


def format_report(entries: list[dict[str, str]]) -> tuple[str, list[str]]:
    lines = [
        "Third-party licences",
        f"App licence: {APP_LICENSE_ID}",
        "Generated by scripts/license_audit.py",
        "A package passes when its licence can be combined with GPL-3.0-only.",
        "",
    ]
    bad: list[str] = []
    ordered = sorted(entries, key=lambda item: item["Name"].casefold())
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for entry in ordered:
        key = (entry["Name"], entry["Version"], entry["License"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    ordered = unique
    for entry in ordered:
        verdict = license_compatible(entry["License"])
        status = "OK" if verdict.compatible else "INCOMPATIBLE"
        lines.append(f"{entry['Name']} {entry['Version']}")
        lines.append(f"  License: {entry['License']}")
        lines.append(f"  Status: {status} ({verdict.reason})")
        lines.append("")
        if not verdict.compatible:
            bad.append(f"{entry['Name']} {entry['Version']}: {entry['License']} — {verdict.reason}")
    lines.append(f"Packages: {len(entries)}")
    lines.append(f"Incompatible: {len(bad)}")
    if bad:
        lines.append("")
        lines.append("Incompatible packages:")
        lines.extend(f"- {item}" for item in bad)
    return "\n".join(lines) + "\n", bad


def read_pip_licenses_json() -> str:
    command = [
        sys.executable,
        "-m",
        "piplicenses",
        "--format=json",
        "--from=mixed",
        "--with-system",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    detail = (completed.stderr or completed.stdout).strip()
    shown = " ".join(command)
    if completed.returncode != 0:
        raise RuntimeError(
            'pip-licenses failed. Install the dev extra: pip install -e ".[dev]".\n'
            f"Command: {shown}\n{detail}"
        )
    if not completed.stdout.strip():
        raise RuntimeError(f"pip-licenses produced no JSON.\nCommand: {shown}\n{detail}")
    return completed.stdout


def loads_report(text: str) -> object:
    return cast(object, json.loads(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit installed licences against GPL-3.0-only.")
    parser.add_argument("--input", help="JSON file from pip-licenses. Default: run pip-licenses.")
    parser.add_argument("--write", help="Write the report to this path.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any package is incompatible with GPL-3.0-only.",
    )
    args = parser.parse_args(argv)
    try:
        if args.input:
            with open(args.input, encoding="utf-8") as handle:
                text = handle.read()
        else:
            text = read_pip_licenses_json()
        report, bad = format_report(normalise_entries(loads_report(text)))
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Licence audit failed: {exc}", file=sys.stderr)
        return 2
    if args.write:
        with open(args.write, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
    else:
        print(report, end="")
    kind = "check" if args.check else "report"
    print(f"{kind}: Incompatible: {len(bad)}")
    if bad:
        for item in bad:
            print(item, file=sys.stderr)
        return 1
    return 0
