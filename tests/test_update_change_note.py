"""`omh update` tells the user what changed for them, from OMH's own records.

Every case runs against temporary OMH and Hermes homes. "An older generation"
is simulated by rewriting the two records the previous install left behind --
the managed manifest (per-skill checksums) and the update baseline (trigger
phrases and shipped model chains) -- which is exactly what a real earlier
generation would have written.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from _cli_harness import run_cli

from omh.plugin_bundle.omh.hermes_delegation import load_mixture_chain_overrides
from omh.plugin_bundle.omh.runtime_reader import read_omh_status

TITLE = "What changed for you"


class UpdateChangeNoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.omh_home = self.root / ".omh"
        self.base = ["--omh-home", str(self.omh_home), "--hermes-home", str(self.root / ".hermes")]
        # English is the default; the OS locale must never pick the language.
        patcher = mock.patch.dict(os.environ, {"LANG": "ko_KR.UTF-8", "LC_ALL": "ko_KR.UTF-8"})
        patcher.start()
        os.environ.pop("OMH_LANG", None)
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _update(self, *extra: str) -> tuple[str, dict]:
        status, stdout, stderr = run_cli(self.base + ["update", *extra], output_json=False)
        self.assertEqual(status, 0, stderr)
        return stdout, self._note_file()

    def _note_file(self) -> dict:
        path = self.omh_home / "runtime" / "update-change-note.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def _override_quick_chain(self) -> None:
        routing = self.omh_home / "routing"
        routing.mkdir(parents=True, exist_ok=True)
        self._write(
            routing / "model-chains.json",
            {
                "schema_version": "mixture_chain_overrides/v1",
                "categories": {"quick": [{"model": "kimi-k3", "reasoning_effort": "low"}]},
            },
        )
        # The document must be one the reader applies, or the case is vacuous.
        self.assertEqual(load_mixture_chain_overrides(self.omh_home)[1], "applied")

    def _simulate_older_generation(self) -> dict[str, str]:
        """Rewrite the records as an older generation would have left them."""
        manifest_path = self.omh_home / "manifest.json"
        manifest = self._json(manifest_path)
        baseline_path = self.omh_home / "runtime" / "update-baseline.json"
        baseline = self._json(baseline_path)
        rows = manifest["skills"]
        routed = [row["name"] for row in rows if row["name"] in baseline["triggers"]]
        added, changed, rerouted = rows[0]["name"], rows[1]["name"], routed[3]
        rows[1]["sha256"] = "0" * 64
        manifest["skills"] = rows[1:] + [
            {"name": "retired-skill", "path": "retired-skill/SKILL.md", "sha256": "1" * 64, "source": "builtin"}
        ]
        self._write(manifest_path, manifest)
        baseline["version"] = "0.0.1"
        baseline["triggers"][rerouted] = baseline["triggers"][rerouted][1:] + ["legacy phrase"]
        baseline["model_chains"]["quick"] = [["old-model", "low"]]
        baseline["model_chains"]["deep"] = [["old-deep-model", "high"]]
        self._write(baseline_path, baseline)
        return {"added": added, "changed": changed, "rerouted": rerouted}

    def test_first_install_says_there_is_nothing_to_compare(self) -> None:
        stdout, note = self._update()

        self.assertEqual(note["status"], "first_install")
        self.assertIn(TITLE, stdout)
        self.assertIn("First install on this machine: there is no earlier version to compare.", stdout)

    def test_a_no_op_update_prints_no_note_and_keeps_the_last_record(self) -> None:
        self._update()
        before = self._note_file()

        status, stdout, stderr = run_cli(self.base + ["update", "--json"])
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["update_change_note"]["status"], "no_change")
        human, after = self._update()

        self.assertNotIn(TITLE, human)
        self.assertEqual(after, before)

    def test_a_changed_generation_names_skills_routing_and_model_chains(self) -> None:
        self._update()
        names = self._simulate_older_generation()

        stdout, note = self._update("--force")

        self.assertEqual(note["status"], "changed")
        self.assertEqual(note["from_version"], "0.0.1")
        skills = note["skills"]
        self.assertEqual([row["name"] for row in skills["added"]], [names["added"]])
        self.assertEqual([row["name"] for row in skills["removed"]], ["retired-skill"])
        self.assertEqual([row["name"] for row in skills["changed"]], [names["changed"]])
        self.assertEqual([row["name"] for row in note["routing"]], [names["rerouted"]])
        self.assertEqual(note["routing"][0]["removed"], ["legacy phrase"])
        self.assertEqual([row["category"] for row in note["model_chains"]], ["deep", "quick"])
        self.assertIn(TITLE, stdout)
        self.assertIn("New skills: ", stdout)
        self.assertIn("Removed skills: ", stdout)
        self.assertIn("Skills with updated instructions: ", stdout)
        self.assertIn('no longer picks up "legacy phrase"', stdout)
        self.assertIn("    - quick: old-model:low -> ", stdout)
        self.assertIn('Ask Hermes "what changed in OMH?"', stdout)

    def test_user_edits_are_not_reported_as_omh_changes(self) -> None:
        self._update()
        # A hand-edited skill (which --force then overwrites) and a chain
        # override the user wrote: neither is an OMH change.
        manifest = self._json(self.omh_home / "manifest.json")
        skill_file = self.omh_home / "skills" / manifest["skills"][0]["path"]
        skill_file.write_text(skill_file.read_text(encoding="utf-8") + "\nmy note\n", encoding="utf-8")
        self._override_quick_chain()

        status, stdout, stderr = run_cli(self.base + ["update", "--force", "--json"])

        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["update_change_note"]["status"], "no_change")

    def test_a_shipped_change_to_a_chain_the_user_overrides_says_the_override_applies(self) -> None:
        self._update()
        self._simulate_older_generation()
        self._override_quick_chain()

        stdout, note = self._update("--force")

        quick = next(row for row in note["model_chains"] if row["category"] == "quick")
        self.assertTrue(quick["override_applies"])
        self.assertIn("quick: the default changed, but your own chain for it still applies", stdout)
        self.assertNotIn("quick: old-model:low", stdout)

    def test_a_generation_without_a_baseline_compares_skills_only_and_says_so(self) -> None:
        self._update()
        (self.omh_home / "runtime" / "update-baseline.json").unlink()

        stdout, _ = self._update()

        self.assertIn("Routing and model-chain changes are compared from your next update on.", stdout)
        self.assertTrue((self.omh_home / "runtime" / "update-baseline.json").exists())

    def test_localized_output_is_opt_in(self) -> None:
        self._update()
        self._simulate_older_generation()

        stdout, _ = self._update("--force", "--language", "ko")

        self.assertIn("이번 업데이트로 달라진 점", stdout)
        self.assertNotIn(TITLE, stdout)

    def test_omh_status_returns_the_recorded_note(self) -> None:
        self._update()
        self._simulate_older_generation()
        _, note = self._update("--force")

        status = read_omh_status(self.omh_home)

        self.assertEqual(status["last_update_change_note"], note)

    def test_omh_status_without_a_note_returns_an_empty_record(self) -> None:
        self.assertEqual(read_omh_status(self.omh_home)["last_update_change_note"], {})


if __name__ == "__main__":
    unittest.main()
