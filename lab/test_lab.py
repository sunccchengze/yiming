from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from .council import discover_roster
from .council_protocol import _build_blind_packet, prepare_council, run_council
from .council_records import extract_sections, parse_ballot
from .pipeline import PreparationError, prepare_run
from .routing import route_task


class LabAdapterTests(unittest.TestCase):
    def test_router_keeps_decision_and_evidence_explicit(self) -> None:
        route = route_task("比较两个研究方案，决定下一步做哪个实验")
        self.assertEqual(route["capability"], "deep_research")
        self.assertTrue(route["decision_task"])
        self.assertIn("sun-chengze-perspective", route["selected_skills"])
        self.assertIn("QUALITY_GATES", route["selected_skills"])

    def test_roster_discovers_only_people_and_books(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (
                "skills/community/nuwa-distilled/book-test/SKILL.md",
                "skills/community/nuwa-distilled/feynman-perspective/SKILL.md",
                "skills/community/nuwa-distilled/ordinary-method/SKILL.md",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "---\nname: test\ndescription: test\n---\n\nA bounded lens.\n",
                    encoding="utf-8",
                )
            seats = discover_roster([root], mode="people-books")
            self.assertEqual(len(seats), 2)
            self.assertEqual({seat.kind for seat in seats}, {"book", "person"})
            self.assertEqual(len({seat.seat_id for seat in seats}), 2)

    def test_roster_records_git_provenance_and_lens_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/community/nuwa-distilled/feynman-perspective/SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text("---\nname: feynman\n---\nAsk for evidence.\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            seat = discover_roster([root], mode="people-books")[0]
            self.assertRegex(seat.source_commit, r"^[0-9a-f]{40}$")
            self.assertTrue(seat.source_branch in {"main", "master"} or seat.source_branch)
            self.assertFalse(seat.source_dirty)
            self.assertEqual(seat.lens_policy, "analytical_person_lens_not_person_statement")

    def test_structured_ballot_and_chair_headings_never_impute_missing_fields(self) -> None:
        ballot = parse_ballot(
            "<ballot>{\"stance\":\"conditional\",\"preferred_option\":\"pilot\","
            "\"confidence\":0.75,\"scores\":{\"evidence\":4,\"expected_value\":3,"
            "\"reversibility\":5,\"actionability\":4}}</ballot>"
        )
        self.assertEqual(ballot["parse_status"], "parsed")
        self.assertEqual(ballot["weighted_score"], 0.8)
        missing = parse_ballot("A memo without a machine ballot")
        self.assertIsNone(missing["weighted_score"])
        self.assertIn("stance", missing["missing_fields"])
        sections = extract_sections(
            "1. Consensus and convergence\nA\n"
            "2. Strongest dissent and why it might be right\nB\n"
            "3. Small reversible next experiment\nC\n"
        )
        self.assertEqual(sections["consensus"], "A")
        self.assertEqual(sections["strongest_dissent"], "B")
        self.assertEqual(sections["next_experiment"], "C")

    def test_chair_section_body_starting_with_alias_word_is_not_a_heading(self) -> None:
        # A real chair body may begin with a word that is also a single-word
        # section alias (e.g. "Confidence low for ..."). It must not truncate
        # the preceding section heading.
        sections = extract_sections(
            "## Consensus and convergence\nSeveral seats converged on a small experiment.\n"
            "## Confidence and what would change your mind\n"
            "Confidence low for real-world correctness; higher for protocol integrity.\n"
        )
        self.assertEqual(sections["consensus"], "Several seats converged on a small experiment.")
        self.assertIn(
            "protocol integrity",
            sections["chair_confidence"],
            "chair_confidence body must not be truncated by an alias-word body line",
        )
        # Terse single-word headings must still match exactly.
        sections = extract_sections("Confidence\nHigh.\n")
        self.assertEqual(sections.get("chair_confidence"), "High.")

    def test_blind_packet_redacts_lens_identity_but_keeps_private_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/community/nuwa-distilled/book-test/SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text("---\nname: book-test\n---\nBounded lens.\n", encoding="utf-8")
            output = root / "council"
            prepare_council(output, skill_roots=[root], max_seats=0, reviewer_count=0)
            seat = discover_roster([root], mode="people-books")[0]
            stdout = output / "seats" / seat.seat_id / "stdout.log"
            stdout.write_text(f"I am the {seat.display_name} lens; recommend a pilot.", encoding="utf-8")
            blind, private_map = _build_blind_packet(
                output,
                [seat],
                [{"seat_id": seat.seat_id, "status": "completed", "stdout_path": str(stdout)}],
            )
            self.assertNotIn(seat.display_name, blind["proposals"][0]["response"])
            self.assertEqual(private_map["mapping"][0]["display_name"], seat.display_name)

    def test_prepare_records_isolation_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/community/nuwa-distilled/book-test/SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text("---\nname: test\n---\nBounded lens.\n", encoding="utf-8")
            output = root / "council"
            manifest = prepare_council(
                output,
                skill_roots=[root],
                max_seats=0,
                reviewer_count=2,
                max_attempts=2,
                max_calls=8,
            )
            audit = json.loads((output / "isolation-audit.json").read_text(encoding="utf-8"))
            self.assertFalse(audit["peer_outputs_available_at_prompt_creation"])
            self.assertFalse(audit["seat_inputs"][0]["peer_output_injected"])
            self.assertEqual(manifest["execution"]["worst_case_calls"], 8)
            with self.assertRaises(ValueError):
                prepare_council(
                    root / "too-small",
                    skill_roots=[root],
                    max_seats=0,
                    reviewer_count=2,
                    max_attempts=2,
                    max_calls=7,
                )

    def test_prepare_is_private_and_scans_opted_in_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "inventory.json"
            inventory.write_text(
                json.dumps(
                    {
                        "owner": "example",
                        "generated_at": "2026-09-01T00:00:00Z",
                        "since": "2026-08-01T00:00:00Z",
                        "repositories": [
                            {
                                "nameWithOwner": "example/project",
                                "description": "test project",
                                "isPrivate": True,
                                "defaultBranchRef": {"name": "main"},
                                "branches": [
                                    {
                                        "name": "main",
                                        "sha": "a" * 40,
                                        "commit_url": "https://github.com/example/project/commit/" + "a" * 40,
                                        "recent_commits": [
                                            {
                                                "sha": "a" * 40,
                                                "date": "2026-09-01",
                                                "message": "test commit",
                                                "url": "https://github.com/example/project/commit/" + "a" * 40,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            corpus = root / "corpus.jsonl"
            corpus.write_text(
                json.dumps({"kind": "repository_file", "repo": "example/project", "text": "safe evidence"})
                + "\n"
                + json.dumps({"kind": "repository_file", "repo": "example/project", "text": "api_key='this-looks-like-a-secret-value'"})
                + "\n",
                encoding="utf-8",
            )
            skill_root = root / "skills"
            for spec in (
                ("tools/openwiki/SKILL.md", "openwiki"),
                ("skills/community/DeepTutor/SKILL.md", "DeepTutor"),
                ("bundles/research-workflow-kit/WORKFLOW.md", "research"),
                ("governance/QUALITY_GATES.md", "gates"),
                ("SKILL.md", "router"),
            ):
                path = skill_root / spec[0]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"---\nname: {spec[1]}\n---\n\ncontract\n", encoding="utf-8")
            perspective_root = root / "perspective"
            perspective = perspective_root / "skills/community/nuwa-distilled/sun-chengze-perspective/SKILL.md"
            perspective.parent.mkdir(parents=True, exist_ok=True)
            perspective.write_text("---\nname: sun\n---\n\nmirror\n", encoding="utf-8")

            output = root / "run-output"
            manifest = prepare_run(
                inventory,
                output,
                corpus_path=corpus,
                include_corpus=True,
                local_repositories=[("example", root)],
                skill_root=skill_root,
                perspective_root=perspective_root,
                task="是否选择这个研究方案？",
            )
            self.assertEqual(manifest["inventory_stats"]["repositories"], 1)
            self.assertEqual(manifest["corpus"]["records_written"], 1)
            self.assertEqual(manifest["corpus"]["records_skipped_secret"], 1)
            self.assertTrue((output / "run.json").is_file())
            self.assertTrue((output / "RUN_PLAN.md").is_file())
            corpus_text = "\n".join(path.read_text(encoding="utf-8") for path in (output / "source-pack" / "corpus").glob("*.md"))
            self.assertIn("safe evidence", corpus_text)
            self.assertNotIn("this-looks-like-a-secret-value", corpus_text)

    def test_council_prepare_is_model_free_and_dry_run_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/community/nuwa-distilled/book-test/SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text("---\nname: book-test\n---\n\nUse experiments.\n", encoding="utf-8")
            output = root / "council"
            manifest = prepare_council(
                output,
                skill_roots=[root],
                roster_mode="people-books",
                max_seats=0,
                task="选择一个可逆实验",
            )
            self.assertEqual(manifest["roster"]["count"], 1)
            self.assertTrue((output / "seats").is_dir())
            result = run_council(output)
            self.assertEqual(result["status"], "dry-run")
            self.assertEqual(result["seat_count"], 1)

    def test_execute_path_isolates_homes_and_chair_reads_blind_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("book-alpha", "book-beta"):
                skill = root / f"skills/community/nuwa-distilled/{name}/SKILL.md"
                skill.parent.mkdir(parents=True, exist_ok=True)
                skill.write_text(f"---\nname: {name}\n---\n\nLens {name}.\n", encoding="utf-8")
            output = root / "council"
            prepare_council(
                output,
                skill_roots=[root],
                roster_mode="people-books",
                max_seats=0,
                task="选择一个可逆实验",
            )
            fake = root / "fake-deeptutor"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "print(json.dumps({'home': os.environ.get('DEEPTUTOR_HOME'), 'argc': len(sys.argv)}))\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            result = run_council(
                output,
                execute=True,
                workers=2,
                timeout_seconds=10,
                deeptutor_bin=str(fake),
            )
            self.assertEqual(result["status"], "completed")
            homes = {
                json.loads(Path(item["stdout_path"]).read_text(encoding="utf-8"))["home"]
                for item in result["seat_results"]
            }
            self.assertEqual(len(homes), 2)
            self.assertTrue(all("runtime/seats" in home for home in homes))
            self.assertEqual(len(result["reviewer_results"]), 3)
            self.assertTrue(all(item["cwd"].endswith(item["reviewer_id"]) for item in result["reviewer_results"]))
            blind = json.loads((output / "blind-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(len(blind["proposals"]), 2)
            self.assertNotIn("display_name", blind["proposals"][0])
            self.assertNotIn("seat_id", blind["proposals"][0])
            self.assertTrue((output / "blind-map.json").is_file())
            self.assertTrue((output / "ballots.json").is_file())
            self.assertTrue((output / "reviewer-ballots.json").is_file())
            self.assertTrue((output / "decision-record.json").is_file())
            self.assertTrue((output / "quality-gates.json").is_file())
            self.assertTrue((output / "isolation-audit.json").is_file())
            self.assertTrue((output / "DISSENT_LEDGER.md").is_file())
            self.assertTrue((output / "chair" / "final.md").is_file())
            resumed = run_council(
                output,
                execute=True,
                workers=2,
                timeout_seconds=10,
                deeptutor_bin=str(fake),
                resume=True,
            )
            self.assertTrue(all(item.get("resumed") for item in resumed["seat_results"]))

    def test_private_output_inside_checkout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "inventory.json"
            inventory.write_text('{"repositories": []}', encoding="utf-8")
            # The test executes from the checkout, so use the real checkout as
            # the forbidden parent and a child that does not need to be written.
            with self.assertRaises(PreparationError):
                prepare_run(inventory, Path.cwd() / ".lab-test-private-output")


if __name__ == "__main__":
    unittest.main()
