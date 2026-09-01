from __future__ import annotations

import unittest

from .build_data import build


class BuildDataTest(unittest.TestCase):
    def test_classifies_and_counts_repositories(self) -> None:
        result = build(
            {
                "owner": "sunccchengze",
                "since": "2026-08-01T00:00:00Z",
                "repositories": [
                    {
                        "nameWithOwner": "sunccchengze/zixue2026",
                        "isPrivate": False,
                        "branches": [
                            {
                                "name": "main",
                                "sha": "abc",
                                "recent_commits": [
                                    {
                                        "sha": "c1",
                                        "date": "2026-08-20T10:00:00Z",
                                        "message": "docs: add learning note",
                                        "url": "https://example.test/c1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(result["stats"]["repositories"], 1)
        self.assertEqual(result["stats"]["branches"], 1)
        self.assertEqual(result["stats"]["recentCommits"], 1)
        self.assertEqual(result["repositories"][0]["categories"], ["learning"])
        self.assertEqual(result["repositories"][0]["latestCommit"]["sha"], "c1")
        self.assertEqual(len(result["timeline"]), 31)

    def test_merge_commits_are_not_meaningful(self) -> None:
        result = build(
            {
                "repositories": [
                    {
                        "nameWithOwner": "sunccchengze/123",
                        "branches": [
                            {
                                "name": "main",
                                "recent_commits": [
                                    {"sha": "m", "date": "2026-08-20T10:00:00Z", "message": "Merge pull request #1"},
                                    {"sha": "f", "date": "2026-08-21T10:00:00Z", "message": "feat: make a thing"},
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(result["stats"]["recentCommits"], 2)
        self.assertEqual(result["stats"]["meaningfulCommits"], 1)
        self.assertEqual(result["highlights"][0]["sha"], "f")


if __name__ == "__main__":
    unittest.main()
