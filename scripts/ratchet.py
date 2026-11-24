"""Run the code-health checks and compare each count with its ceiling.

    python scripts/ratchet.py                  ruff, pyright, imports, duplication
    python scripts/ratchet.py ruff coverage    only these
    python scripts/ratchet.py staticcheck      Go; needs the `go` tool

Ceilings are in ratchets.json. A check fails when its count is ABOVE the
ceiling (coverage: BELOW the floor). When the count is better, the script
says so and what to write in ratchets.json: do that in the same PR, so the
gain cannot be lost later. Never raise a ceiling.

`coverage` reads coverage.json, which the test run writes:
    pytest tests --cov=app --cov-report=json
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CEILINGS = json.loads((ROOT / "ratchets.json").read_text("utf-8"))
PY_PATHS = ["app", "scripts", "tests", "testdata", "run_local.py"]
STATICCHECK = "honnef.co/go/tools/cmd/staticcheck@2026.2.2"
DUPLICATION = {"python": "app", "javascript": "app/static", "go": "companion"}


def run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)


def ruff() -> int:
    done = run([sys.executable, "-m", "ruff", "check", *PY_PATHS, "--output-format", "json", "--no-cache"])
    return len(json.loads(done.stdout))  # exit 1 only means "found something"


def pyright() -> int:
    done = run([sys.executable, "-m", "pyright", "--pythonpath", sys.executable, "--outputjson"])
    return json.loads(done.stdout)["summary"]["errorCount"]


def imports() -> int:
    # what the `lint-imports` command runs (the module has no __main__)
    done = run([sys.executable, "-c", "from importlinter.cli import lint_imports_command; lint_imports_command()"])
    if "Contracts:" not in done.stdout:  # it did not run at all: never read that as "kept"
        sys.exit(f"import-linter did not run:\n{done.stdout}{done.stderr}")
    print(done.stdout.strip().splitlines()[-1])
    if done.returncode:
        print(done.stdout)
    return 0 if done.returncode == 0 else 1


def duplication() -> dict[str, float]:
    npx = shutil.which("npx") or "npx"
    found = {}
    for fmt, path in DUPLICATION.items():
        with tempfile.TemporaryDirectory() as out:
            run([npx, "--yes", "jscpd@4", "--min-tokens", "50", "--max-lines", "100000", "--max-size", "5mb",
                 "--format", fmt, "--ignore", "**/*_test.go", "--reporters", "json", "--output", out,
                 "--silent", path])
            report = json.loads((Path(out) / "jscpd-report.json").read_text("utf-8"))
        found[fmt] = report["statistics"]["total"]["percentage"]
    return found


def coverage() -> int:
    data = json.loads((ROOT / "coverage.json").read_text("utf-8"))
    return math.floor(data["totals"]["percent_covered"])


def staticcheck() -> int:
    go = shutil.which("go") or "go"
    done = run([go, "run", STATICCHECK, "./..."], cwd=ROOT / "companion")
    if done.returncode > 1:
        sys.exit(f"staticcheck did not run:\n{done.stderr}")
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    print("\n".join(lines))
    return len(lines)


def judge(name: str, count: float, ceiling: float, floor: bool = False) -> bool:
    ok = count >= ceiling if floor else count <= ceiling
    better = count > ceiling if floor else count < ceiling
    print(f"{name}: {count} (ceiling {ceiling}) {'ok' if ok else 'FAIL, worse than the ceiling'}")
    if ok and better:
        print(f"  -> {'raise the floor' if floor else 'lower the ceiling'} to {count} in ratchets.json")
    return ok


def judge_duplication() -> bool:
    return all([judge(f"duplication {fmt} %", pct, CEILINGS["duplication_percent"][fmt])
                for fmt, pct in duplication().items()])


CHECKS = {
    "ruff": lambda: judge("ruff findings", ruff(), CEILINGS["ruff"]),
    "pyright": lambda: judge("pyright errors", pyright(), CEILINGS["pyright"]),
    "imports": lambda: judge("import-linter broken contracts", imports(), CEILINGS["import_contracts_broken"]),
    "duplication": judge_duplication,
    "coverage": lambda: judge("coverage %", coverage(), CEILINGS["coverage_percent_floor"], floor=True),
    "staticcheck": lambda: judge("staticcheck findings", staticcheck(), CEILINGS["staticcheck"]),
}
DEFAULT = ["ruff", "pyright", "imports", "duplication"]


def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"unknown check {unknown}; choose from {list(CHECKS)}")
        return 2
    results = [CHECKS[name]() for name in names or DEFAULT]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
