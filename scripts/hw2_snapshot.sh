#!/usr/bin/env bash
# Freeze one HW2 test round: scripts/hw2_snapshot.sh <round> [--mutation]
# Writes docs/hw2/snapshots/<round>/ and refuses to overwrite an existing snapshot.
set -u

ROUND="${1:?usage: hw2_snapshot.sh <round> [--mutation]}"
MUTATION="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/hw2/snapshots/$ROUND"
PY="$ROOT/.venv/bin/python"

if [ -e "$OUT" ]; then
  echo "refusing to overwrite $OUT; use a new round name" >&2
  exit 1
fi
cd "$ROOT" || exit 1
mkdir -p "$OUT"
cp -R tests "$OUT/tests"
find "$OUT/tests" -name __pycache__ -type d -prune -exec rm -rf {} +

# Isolation: no key, throwaway data, and no sockets except localhost.
export GEMINI_API_KEY="" GOOGLE_API_KEY=""
export DATA_DIR="$(mktemp -d)"

# Full run in file order, with line + branch coverage. Exit code is recorded, not fatal.
"$PY" -m pytest tests -p no:randomly --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost \
  --cov=app --cov-branch --cov-report=term-missing --cov-report=json:"$OUT/coverage.json" \
  --junitxml="$OUT/junit.xml" -q >"$OUT/pytest.txt" 2>&1
STATUS=$?
sed -n '/coverage:/,/^TOTAL/p' "$OUT/pytest.txt" >"$OUT/coverage.txt"

# Flakiness: 5 runs in random order, one line per run.
: >"$OUT/flaky.txt"
for SEED in 1 2 3 4 5; do
  LINE="$("$PY" -m pytest tests -q --randomly-seed="$SEED" \
    --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost 2>&1 | grep -E "[0-9]+ (passed|failed|error)" | tail -1)"
  echo "seed $SEED: $LINE" >>"$OUT/flaky.txt"
done

# Frontend coverage from Chromium; needs no test changes.
JSCOV_OUT="$OUT/jscoverage.txt" PYTHONPATH="$ROOT/scripts" "$PY" -m pytest tests -m e2e -p hw2_jscov -q -p no:randomly \
  --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost >/dev/null 2>&1

if [ "$MUTATION" = "--mutation" ]; then
  "$ROOT/scripts/hw2_mutation.sh" >"$OUT/mutation.txt" 2>&1
fi

"$PY" - "$OUT" "$ROUND" "$STATUS" <<'PY'
import json, platform, subprocess, sys, xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

out, round_name, status = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
suite = ET.parse(out / "junit.xml").getroot()
suite = suite.find("testsuite") if suite.tag == "testsuites" else suite
cov = json.loads((out / "coverage.json").read_text())["totals"]
meta = {
    "round": round_name,
    "date": date.today().isoformat(),
    "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
    "python": platform.python_version(),
    "pytest_exit": status,
    "tests": int(suite.get("tests")),
    "failures": int(suite.get("failures")),
    "errors": int(suite.get("errors")),
    "skipped": int(suite.get("skipped")),
    "line_pct": round(100 * cov["covered_lines"] / cov["num_statements"], 1),
    "branch_pct": round(100 * cov["covered_branches"] / cov["num_branches"], 1) if cov["num_branches"] else None,
    "combined_pct": round(cov["percent_covered"], 1),
}
(out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

rows = ["| Round | Tests | Failed | Errors | Skipped/xfail | Line % | Branch % | Combined % |", "|---|---|---|---|---|---|---|---|"]
for path in sorted(out.parent.glob("*/meta.json")):
    m = json.loads(path.read_text())
    rows.append(f"| {m['round']} | {m['tests']} | {m['failures']} | {m['errors']} | {m['skipped']} | {m['line_pct']} | {m['branch_pct']} | {m['combined_pct']} |")
(out.parent / "summary.md").write_text("\n".join(rows) + "\n")
print(json.dumps(meta))
PY
