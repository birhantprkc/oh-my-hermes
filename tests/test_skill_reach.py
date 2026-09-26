from __future__ import annotations

import unittest

from _cli_harness import run_cli
from omh.quality.skill_reach import (
    NO_NEGATIVE_CONTROL_BASELINE,
    REASON_ADDRESSED_BY_DESIGN,
    REASON_CORPUS_GAP,
    UNREACHED_POSITIVE_BASELINE,
    SkillReachMeasurement,
    build_skill_reach_projection,
    measure_skill_reach,
    natural_trigger_probe,
    skill_reach_errors,
)


# The shrink-only ledgers. Each is the baseline as measured when the gate
# landed; the baselines in `omh.quality.skill_reach` may only be subsets of
# these. A skill added to the catalog later is not here, so it cannot be
# excused by listing it -- it has to be reached. Remove a name here in the same
# commit that removes it from the baseline, so it cannot quietly re-join.
UNREACHED_POSITIVE_LEDGER = frozenset(
    {
        "achievements", "agent-debug", "ai-slop-cleaner", "ask", "buzz", "cancel",
        "capability-toggle", "codebase-onboarding", "codegraph-refresh", "connector-operator",
        "cto-loop", "data-analysis", "decision-recall", "deploy-and-monitor",
        "design-orchestration", "failure-signal-audit", "gateway-intent-card",
        "harness-session-inventory", "instinct-ledger", "jev-action-check", "jev-ask",
        "jev-done-check", "jev-failure-triage", "jev-review-gate", "jev-route",
        "live-info-operator", "meeting-brief", "meta-router", "operating-rhythm",
        "physical-device-readiness", "production-audit", "prompt-import-readiness",
        "provider-profile-posture", "report-package", "run-efficiency", "skill", "skill-health",
        "skill-scout", "ultraqa", "voice-operator", "wiki", "workspace-file-operator",
    }
)
NO_NEGATIVE_CONTROL_LEDGER = frozenset(
    {
        "adversarial-consensus", "cancel", "context", "doctor", "failure-signal-audit",
        "harness-session-inventory", "jev-action-check", "jev-done-check", "jev-failure-triage",
        "jev-review-gate", "jev-route", "jit-learn", "media-input-operator", "ops-review",
        "physical-device-readiness", "run-efficiency", "skill-health",
    }
)


class SkillReachGateTests(unittest.TestCase):
    measurements: list[SkillReachMeasurement]

    @classmethod
    def setUpClass(cls) -> None:
        cls.measurements = measure_skill_reach(source="discord")

    def _errors(
        self,
        *,
        positive: dict[str, str] | None = None,
        negative: dict[str, str] | None = None,
    ) -> list[str]:
        return skill_reach_errors(
            self.measurements,
            positive_baseline=dict(UNREACHED_POSITIVE_BASELINE) if positive is None else positive,
            negative_baseline=dict(NO_NEGATIVE_CONTROL_BASELINE) if negative is None else negative,
        )

    def _row(self, skill: str) -> SkillReachMeasurement:
        return next(row for row in self.measurements if row["skill"] == skill)

    def test_every_installable_skill_is_reached_or_baselined_with_a_verified_reason(self) -> None:
        errors = self._errors()
        self.assertEqual([], errors, "\n".join(errors))

    def test_baselines_only_shrink(self) -> None:
        self.assertLessEqual(
            set(UNREACHED_POSITIVE_BASELINE),
            UNREACHED_POSITIVE_LEDGER,
            "a skill cannot join UNREACHED_POSITIVE_BASELINE; add an intervention case that reaches it",
        )
        self.assertLessEqual(
            set(NO_NEGATIVE_CONTROL_BASELINE),
            NO_NEGATIVE_CONTROL_LEDGER,
            "a skill cannot join NO_NEGATIVE_CONTROL_BASELINE; add a negative control for it",
        )

    def test_projection_measures_every_installable_skill_once(self) -> None:
        payload = build_skill_reach_projection(source="discord")
        skills = [row["skill"] for row in payload["skills"]]
        self.assertEqual(len(skills), len(set(skills)))
        self.assertEqual([row["skill"] for row in self.measurements], skills)
        summary = payload["summary"]
        self.assertEqual(summary["skill_count"], len(skills))
        self.assertEqual(summary["unreached_count"], len(UNREACHED_POSITIVE_BASELINE))
        self.assertEqual(summary["no_negative_control_count"], len(NO_NEGATIVE_CONTROL_BASELINE))
        self.assertEqual(summary["error_count"], 0)
        self.assertEqual(payload["errors"], [])

    def test_an_unreached_skill_missing_from_the_baseline_fails_by_name(self) -> None:
        positive = dict(UNREACHED_POSITIVE_BASELINE)
        del positive["wiki"]
        errors = self._errors(positive=positive)
        self.assertEqual(1, len(errors), errors)
        self.assertTrue(errors[0].startswith("wiki: no intervention case dispatches to it"), errors)

    def test_a_skill_without_a_negative_control_fails_by_name(self) -> None:
        negative = dict(NO_NEGATIVE_CONTROL_BASELINE)
        del negative["doctor"]
        errors = self._errors(negative=negative)
        self.assertEqual(1, len(errors), errors)
        self.assertTrue(errors[0].startswith("doctor: no negative control"), errors)

    def test_a_reached_skill_still_listed_fails(self) -> None:
        reached = next(row["skill"] for row in self.measurements if row["natural_dispatch_cases"])
        covered = next(row["skill"] for row in self.measurements if row["negative_control_cases"])
        errors = self._errors(
            positive={**UNREACHED_POSITIVE_BASELINE, reached: REASON_CORPUS_GAP},
            negative={**NO_NEGATIVE_CONTROL_BASELINE, covered: REASON_CORPUS_GAP},
        )
        self.assertEqual(2, len(errors), errors)
        self.assertIn("still listed in UNREACHED_POSITIVE_BASELINE", errors[0] + errors[1])
        self.assertIn("still listed in NO_NEGATIVE_CONTROL_BASELINE", errors[0] + errors[1])

    def test_a_baseline_entry_for_a_skill_not_in_the_catalog_fails(self) -> None:
        errors = self._errors(positive={**UNREACHED_POSITIVE_BASELINE, "no-such-skill": REASON_CORPUS_GAP})
        self.assertEqual(
            ["no-such-skill: listed in UNREACHED_POSITIVE_BASELINE but is not an installable skill; remove the entry"],
            errors,
        )

    def test_a_wrong_positive_reason_fails(self) -> None:
        # `jev-ask` is reached only when addressed, so "corpus_gap" (a non-name
        # trigger reaches it) is false; `wiki` is reached by its own trigger,
        # so "addressed_by_design" is false.
        self.assertEqual(REASON_ADDRESSED_BY_DESIGN, UNREACHED_POSITIVE_BASELINE["jev-ask"])
        self.assertEqual(REASON_CORPUS_GAP, UNREACHED_POSITIVE_BASELINE["wiki"])
        errors = self._errors(
            positive={**UNREACHED_POSITIVE_BASELINE, "jev-ask": REASON_CORPUS_GAP, "wiki": REASON_ADDRESSED_BY_DESIGN}
        )
        self.assertEqual(2, len(errors), errors)
        self.assertTrue(any(error.startswith("jev-ask: baseline reason corpus_gap is wrong") for error in errors), errors)
        self.assertTrue(
            any(error.startswith("wiki: baseline reason addressed_by_design is wrong") for error in errors), errors
        )

    def test_an_explicit_invocation_does_not_count_as_natural_reach(self) -> None:
        # Every `jev-ask` intervention case names Jev; the router records each
        # as explicit, so they count as addressed and never as natural reach.
        row = self._row("jev-ask")
        self.assertEqual(0, row["natural_dispatch_cases"])
        self.assertGreater(row["addressed_dispatch_cases"], 0)

    def test_a_shortlist_first_case_is_shown_but_not_counted_as_reach(self) -> None:
        # Its intervention cases ask with `deploy-and-monitor` as the first
        # candidate instead of dispatching: the router did not pick it.
        row = self._row("deploy-and-monitor")
        self.assertEqual(0, row["natural_dispatch_cases"])
        self.assertGreater(row["shortlist_first_cases"], 0)

    def test_the_trigger_probe_skips_a_trigger_that_only_spells_the_name(self) -> None:
        # A bare `skill-health` dispatches without the router marking it
        # explicit, so only the name-spelling skip keeps it from passing as
        # natural reach.
        self.assertEqual(
            "", natural_trigger_probe("skill-health", ("skill-health", "skill health"), source="discord")
        )
        self.assertEqual(
            "skill portfolio health",
            natural_trigger_probe("skill-health", ("skill-health", "skill portfolio health"), source="discord"),
        )

    def test_demo_skill_reach_summary_reports_the_measured_counts(self) -> None:
        status, stdout, stderr = run_cli(["demo", "skill-reach", "--summary"], output_json=False)

        self.assertEqual(status, 0, stderr)
        self.assertEqual(stderr, "")
        total = len(self.measurements)
        reached = sum(1 for row in self.measurements if row["natural_dispatch_cases"])
        covered = sum(1 for row in self.measurements if row["negative_control_cases"])
        self.assertIn("OMH skill reach (operators and agents)", stdout)
        self.assertIn(f"Natural positive reach: {reached}/{total} skills; unreached: {total - reached}", stdout)
        self.assertIn(f"Negative controls: {covered}/{total} skills; uncovered: {total - covered}", stdout)
        self.assertIn("- jev-ask: no non-name trigger dispatches; addressed cases", stdout)
        self.assertNotIn("Errors:", stdout)


if __name__ == "__main__":
    unittest.main()
