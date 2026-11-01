"""pytest plugin: measure static/app.js coverage from Chromium, without changing any test.

Usage: PYTHONPATH=scripts pytest tests -m e2e -p hw2_jscov  (writes JSCOV_OUT, default jscoverage.txt)
Any test that uses Playwright's `page` fixture is measured through the Chrome DevTools Protocol.
"""
import os
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent.parent / "static" / "app.js"
_covered = bytearray(len(SOURCE.read_text()))


def _merge(result):
    for script in result["result"]:
        if not script["url"].endswith("/app.js"):
            continue
        hits = [0] * len(_covered)
        # Ranges are outer-first, so inner counts overwrite outer ones.
        for fn in script["functions"]:
            for r in fn["ranges"]:
                hits[r["startOffset"]:r["endOffset"]] = [r["count"]] * (r["endOffset"] - r["startOffset"])
        for i, count in enumerate(hits):
            if count:
                _covered[i] = 1


@pytest.fixture(autouse=True)
def _js_coverage(request):
    if "page" not in request.fixturenames:
        yield
        return
    page = request.getfixturevalue("page")
    cdp = page.context.new_cdp_session(page)
    cdp.send("Profiler.enable")
    cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
    yield
    _merge(cdp.send("Profiler.takePreciseCoverage"))


def pytest_sessionfinish(session):
    text = SOURCE.read_text()
    code = [i for i, c in enumerate(text) if not c.isspace()]
    pct = 100 * sum(_covered[i] for i in code) / len(code)
    lines, offset, missed = text.split("\n"), 0, []
    for number, line in enumerate(lines, 1):
        idx = [offset + i for i, c in enumerate(line) if not c.isspace()]
        if idx and not line.strip().startswith("//") and sum(_covered[i] for i in idx) < len(idx):
            missed.append(f"{number}: {line.strip()[:110]}")
        offset += len(line) + 1
    report = [f"static/app.js covered characters: {pct:.1f}%", f"lines not fully covered: {len(missed)}", *missed]
    Path(os.environ.get("JSCOV_OUT", "jscoverage.txt")).write_text("\n".join(report) + "\n")
