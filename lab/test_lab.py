from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from .council import discover_roster
from .council_protocol import prepare_council, run_council
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
            blind = json.loads((output / "blind-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(len(blind["proposals"]), 2)
            self.assertNotIn("display_name", blind["proposals"][0])
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
