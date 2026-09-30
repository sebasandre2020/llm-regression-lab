"""Validate local links, generated contracts, examples, and blueprint YAML."""

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".venv", ".git", "node_modules", ".terraform", ".ruff_cache", ".pytest_cache", "artifacts"}


def files(pattern):
    return [p for p in ROOT.rglob(pattern) if not IGNORED.intersection(p.relative_to(ROOT).parts)]


def main():
    errors = []
    docs = files("*.md")
    links = 0
    for doc in docs:
        content = doc.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            target = target.strip("<>")
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            path, _, anchor = target.partition("#")
            destination = (doc.parent / unquote(path)).resolve() if path else doc
            links += 1
            if not destination.exists():
                errors.append(f"{doc.relative_to(ROOT)}: missing {target}")
            elif anchor and destination.suffix == ".md":
                headings = re.findall(r"^#+\s+(.+)$", destination.read_text(encoding="utf-8"), re.M)
                anchors = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-") for h in headings]
                if unquote(anchor) not in anchors:
                    errors.append(f"{doc.relative_to(ROOT)}: unknown anchor {target}")
    with TemporaryDirectory(prefix="lab-contract-check-") as temporary:
        generated = Path(temporary)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_contract.py"), "--output-dir", str(generated)], check=True
        )
        for path in generated.rglob("*.json"):
            relative = path.relative_to(generated)
            saved = ROOT / relative
            if not saved.exists() or saved.read_bytes() != path.read_bytes():
                errors.append(f"generated content missing or drifted: {relative}")
    schemas = json.loads((ROOT / "contracts/schemas.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schemas)
    mapping = {
        "dataset": "Dataset",
        "config": "EvaluationConfig",
        "job": "JobRequest",
        "job-status": "Job",
        "report": "Report",
        "gate": "Gate",
    }
    for name, definition in mapping.items():
        schema = {**schemas, "$ref": f"#/$defs/{definition}"}
        instance = json.loads((ROOT / f"examples/{name}.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)
    spec = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
    validate(spec)
    index = (ROOT / "Index.md").read_text(encoding="utf-8")
    for path, methods in spec["paths"].items():
        for method in methods:
            if f"{method.upper()} `{path}`" not in index:
                errors.append(f"API endpoint absent from Index.md: {method} {path}")
    yamls = files("*.yaml") + files("*.yml") + files("*.yml.example")
    for path in yamls:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    report = json.loads((ROOT / "examples/report.json").read_text(encoding="utf-8"))
    if report["coverage"]["valid"] > report["coverage"]["expected"]:
        errors.append("report coverage exceeds expected observations")
    if report["gate"]["job_id"] != report["job_id"]:
        errors.append("report and gate job mismatch")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"PASS: {len(docs)} Markdown files, {links} local links, {len(mapping)} schema fixtures, {len(spec['paths'])} API paths, {len(yamls)} YAML files; generated contracts match."
    )


if __name__ == "__main__":
    main()
