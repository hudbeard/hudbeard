"""Verify attribution and privacy boundaries for the public activity totals."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import update_profile as profile


def commit(sha, login="hudbeard", name="hudbeard", parents=1):
    return {"sha": sha, "author": None if login is None else {"login": login},
            "commit": {"author": {"name": name}}, "parents": [{}] * parents}


class PublicActivityTests(unittest.TestCase):
    def test_attribution_deduplication_private_filter_and_immutable_cache(self):
        calls = []

        def github(path, payload=None):
            calls.append(path)
            if path == "graphql":
                return {"data": {"user": {"contributionsCollection": {"commitContributionsByRepository": [
                    {"repository": {"nameWithOwner": "other/public", "isPrivate": False}},
                    {"repository": {"nameWithOwner": "other/private", "isPrivate": True}},
                ]}}}}
            if path.startswith("repos/hudbeard/project/commits?"):
                return [commit("shared"), commit("unlinked", login=None), commit("merge", parents=2),
                        commit("someone-else", login="other"), commit("wrong-name", login=None, name="other")]
            if path.startswith("repos/other/public/commits?"):
                return [commit("shared"), commit("unlinked-foreign", login=None)]
            if path.startswith("repos/hudbeard/empty/commits?"):
                raise HTTPError(path, 409, "Git Repository is empty", {}, None)
            if path.endswith("/commits/unlinked"):
                return {"stats": {"additions": 11, "deletions": 3}}
            raise AssertionError(f"Unexpected API request: {path}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            cache_path = root / "assets/activity-cache.json"
            cache_path.write_text(json.dumps({"shared": {"added": 9, "deleted": 1}}))
            with patch.object(profile, "ROOT", root), patch.object(profile, "github", github):
                result = profile.collect_activity({"created_at": "2026-01-01T00:00:00Z"}, [
                    {"full_name": "hudbeard/project", "private": False},
                    {"full_name": "hudbeard/empty", "private": False},
                    {"full_name": "hudbeard/private", "private": True},
                ])
            self.assertEqual(result, {"commits": 2, "contributed": 2, "added": 20, "deleted": 4, "net": 16})
            self.assertFalse(any("private" in path for path in calls))
            self.assertFalse(any(path.endswith("/commits/shared") for path in calls))
            self.assertEqual(set(json.loads(cache_path.read_text())), {"shared", "unlinked"})

    def test_refuses_incomplete_contribution_history(self):
        with patch.object(profile, "github", return_value={"errors": [{"message": "Unavailable"}]}):
            with self.assertRaisesRegex(RuntimeError, "full contribution history"):
                profile.collect_activity({"created_at": "2026-01-01T00:00:00Z"}, [])


if __name__ == "__main__":
    unittest.main()
