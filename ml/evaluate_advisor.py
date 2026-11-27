"""Evaluate the Phase 9 advisor on hand-written user situations.

There is no dataset of "correct advice", so, as with the realistic-text
stress tests of Phases 3 and 5, the advisor is checked against situations
written by hand with the advice a careful planner would give first
(backend/tests/advisor_scenarios.py). Three measures:

1. Expected advice: right action first, required actions present,
   forbidden ones absent, right setup steps.
2. Degradation: every usable module knocked out in turn, for every
   scenario. Advice must still build, be marked partial and never cite the
   missing module.
3. Traceability: every ₹ figure shown in an action must be recorded in the
   action's own data or its source modules.

The same checks run in the test suite (backend/tests/test_advisor_eval.py);
this script writes them as a report.

Run:
    cd ml && python3 evaluate_advisor.py
Writes ml/models/advisor_eval/metrics.json.
"""

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR.parent / "backend"))

from app.core.advisor_config import ADVISOR_VERSION, PRIORITY
from app.services.advisor.rules import build_actions
from tests.advisor_scenarios import (
    _RUPEES,
    SCENARIOS,
    degradation_failures,
    expectation_failures,
    untraced_amounts,
)

OUTPUT = ML_DIR / "models" / "advisor_eval" / "metrics.json"


def main() -> None:
    rows, rule_hits = [], Counter()
    trials = degradation_problems = amounts_checked = untraced = 0
    for s in SCENARIOS:
        modules = s.results()
        result = build_actions(modules)
        ids = [a["id"] for a in result["actions"]]
        rule_hits.update(ids)
        failures = expectation_failures(s)
        degraded = degradation_failures(s)
        trials += sum(m["status"] in ("ok", "stale") for m in modules)
        degradation_problems += len(degraded)
        shown = sum(len(_RUPEES.findall(a["title"] + " " + a["detail"])) for a in result["actions"])
        missing = untraced_amounts(result, modules)
        amounts_checked += shown
        untraced += len(missing)
        rows.append({
            "scenario": s.name, "story": s.story, "expected_first": s.first, "actions": ids,
            "setup": [x["title"] for x in result["setup"]], "passed": not failures,
            "failures": failures, "degradation_failures": degraded, "untraced_amounts": missing,
        })

    passed = sum(r["passed"] for r in rows)
    report = {
        "advisor_version": ADVISOR_VERSION,
        "scenarios": {"total": len(rows), "passed": passed, "pass_rate": round(passed / len(rows), 4)},
        "degradation": {"module_knockouts": trials, "problems": degradation_problems},
        "traceability": {"amounts_shown": amounts_checked, "untraced": untraced},
        "rule_coverage": {r: rule_hits.get(r, 0) for r in PRIORITY},
        "llm_wording": ("Not measured: no LLM key configured in this run. The number guard is tested "
                        "in backend/tests/test_advisor_api.py with changed, reordered and failed replies."),
        "limits": [
            "Scenarios are hand-written by the developers, not reviewed by a certified financial planner.",
            "They test the rules' decisions on realistic inputs, not whether users find the advice useful; "
            "that needs a user study.",
            "18 scenarios cover every rule, but not every combination of situations.",
        ],
        "results": rows,
        "computed_at": datetime.now(UTC).isoformat(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"Advisor {ADVISOR_VERSION}: {passed}/{len(rows)} scenarios give the expected advice")
    for r in rows:
        mark = "OK  " if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['scenario']:28} -> {', '.join(r['actions']) or '(setup only)'}")
        for f in r["failures"]:
            print(f"         {f}")
    print(f"Degradation: {trials} module knock-outs, {degradation_problems} problems")
    print(f"Traceability: {amounts_checked} ₹ figures shown, {untraced} untraced")
    print(f"Rules exercised: {sum(1 for v in report['rule_coverage'].values() if v)}/{len(PRIORITY)}")
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
