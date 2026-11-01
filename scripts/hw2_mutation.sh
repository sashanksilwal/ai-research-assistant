#!/usr/bin/env bash
# Mutation testing, one scratch copy per module, in parallel. mutmut 2 edits source files in place,
# so it must never run inside the repo. Usage: hw2_mutation.sh [jobs]  (tests marked e2e are excluded)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOBS="${1:-6}"
PY="$ROOT/.venv/bin/python"
BASE="$(mktemp -d)"

one() {
  module="$1"; WORK="$BASE/$module"; mkdir -p "$WORK"
  cp -R "$ROOT/app" "$ROOT/tests" "$ROOT/static" "$WORK/"
  cd "$WORK" || exit 1
  export GEMINI_API_KEY="" GOOGLE_API_KEY="" DATA_DIR="$WORK/data" PYTHONPATH="$WORK"
  "$ROOT/.venv/bin/mutmut" run --paths-to-mutate "app/$module.py" --tests-dir tests \
    --runner "$PY -m pytest tests -x -q -m 'not e2e' -p no:randomly -p no:cacheprovider --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost" \
    --no-progress --simple-output >run.log 2>&1
  "$PY" - "$module" <<'PY'
import sqlite3, subprocess, sys
rows = sqlite3.connect(".mutmut-cache").execute("select id, status from Mutant").fetchall()
for mutant_id, status in rows:
    if status == "bad_survived":
        diff = subprocess.run([sys.executable.replace("python", "mutmut"), "show", str(mutant_id)], capture_output=True, text=True).stdout
        open("survivors.txt", "a").write(diff + "\n")
PY
}
export -f one
export ROOT PY BASE
ls "$ROOT"/app/*.py | xargs -n1 basename | sed 's/\.py$//' | grep -v __init__ \
  | xargs -P "$JOBS" -I{} bash -c 'one {}'

"$PY" - "$BASE" <<'PY'
import collections, pathlib, sqlite3, sys
base = pathlib.Path(sys.argv[1])
total = collections.Counter()
print("module      killed survived timeout other  score")
for cache in sorted(base.glob("*/.mutmut-cache")):
    rows = collections.Counter(dict(sqlite3.connect(cache).execute("select status, count(*) from Mutant group by status").fetchall()))
    k, s, t = rows["ok_killed"], rows["bad_survived"], rows["bad_timeout"]
    other = sum(rows.values()) - k - s - t
    total.update(rows)
    print(f"{cache.parent.name:<11} {k:>6} {s:>8} {t:>7} {other:>5} {100 * (k + t) / max(1, k + s + t):>5.1f}%")
k, s, t = total["ok_killed"], total["bad_survived"], total["bad_timeout"]
print(f"MUTATION SCORE: {k + t}/{k + s + t} = {100 * (k + t) / (k + s + t):.1f}% (survived {s}, other {sum(total.values()) - k - s - t})")
for f in sorted(base.glob("*/survivors.txt")):
    print(f"\n===== survivors: {f.parent.name}\n{f.read_text()}")
PY
