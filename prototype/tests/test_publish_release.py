"""Public release validation and mocked draft lifecycle; no Git/GitHub writes."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

from tools import publish_release as publisher


class PublishValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = {"probe_launcher.py": "d" * 64, "README.md": "f" * 64}
        source_patch = patch.object(publisher, "source_files", return_value=self.sources)
        source_patch.start()
        self.addCleanup(source_patch.stop)

    def package(self, *, distribution="public", repository=None, files=None, built_sources=None):
        payload = {"TF2-Coop.exe": b"MZ-never-executed-test-fixture", "README.md": b"Public test instructions"}
        payload.update(files or {})
        manifest = {"release_tag": publisher.RELEASE_TAG, "distribution": distribution,
                    "repository": repository or publisher.REPO,
                    "source_files": self.sources if built_sources is None else built_sources,
                    "files": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}}
        manifest_bytes = json.dumps(manifest).encode()
        path = self.root / publisher.updater.ASSET_NAME
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in payload.items():
                archive.writestr("TFCoop/" + name, data)
            archive.writestr("TFCoop/package_manifest.json", manifest_bytes)
        report = {"passed": True, "frozen": True, "game_started": False,
                  "game_installed": False, "ui_opened": False,
                  "package_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
        report_path = self.root / "self-check.json"
        report_path.write_text(json.dumps(report))
        return path, report_path

    def test_validate_binds_real_extracted_archive_to_frozen_report(self):
        archive, report = self.package()
        with patch.object(publisher, "source_files", return_value=self.sources), \
                patch.object(publisher, "GitHub", side_effect=AssertionError("No credentials in validation")), \
                patch.object(publisher, "git", side_effect=AssertionError("No Git in validation")):
            result = publisher.validate(archive, report)
        self.assertEqual(result["archive_sha256"], publisher.sha(archive))
        self.assertEqual(result["bytes"], archive.stat().st_size)
        self.assertEqual(result["source_files"], self.sources)

    def test_wrong_selfcheck_manifest_rejected(self):
        archive, report = self.package()
        document = json.loads(report.read_text())
        document["package_manifest_sha256"] = "0" * 64
        report.write_text(json.dumps(document))
        with patch.object(publisher, "source_files") as sources:
            with self.assertRaisesRegex(ValueError, "another package manifest"):
                publisher.validate(archive, report)
        sources.assert_called_once_with()

    def test_nonfrozen_failed_or_ui_game_selfcheck_cannot_publish(self):
        for key, value in (("passed", False), ("frozen", False), ("game_started", True), ("ui_opened", True)):
            with self.subTest(key=key):
                archive, report = self.package()
                document = json.loads(report.read_text())
                document[key] = value
                report.write_text(json.dumps(document))
                with patch.object(publisher, "source_files") as sources, self.assertRaisesRegex(ValueError, "self-check"):
                    publisher.validate(archive, report)
                sources.assert_not_called()

    def test_private_distribution_and_wrong_repository_rejected(self):
        for options in ({"distribution": "private"}, {"repository": "example/other"}):
            with self.subTest(options=options):
                archive, report = self.package(**options)
                with patch.object(publisher, "source_files"), self.assertRaisesRegex(ValueError, "public package"):
                    publisher.validate(archive, report)

    def test_private_save_and_secret_names_rejected_inside_valid_manifest(self):
        for name in ("Testspielstand/initial.sav", "initial.sav.lua", "session.key", "alut_real.dll"):
            with self.subTest(name=name):
                archive, report = self.package(files={name: b"private fixture"})
                with patch.object(publisher, "source_files"), self.assertRaises(publisher.updater.UpdateError):
                    publisher.validate(archive, report)

    def test_private_text_in_public_document_rejected(self):
        private_path = "\\".join(("C:", "Users", "FixturePerson", "Documents", "notes.txt"))
        archive, report = self.package(files={"PRIVATE.md": private_path.encode()})
        with patch.object(publisher, "source_files", return_value=self.sources), self.assertRaisesRegex(ValueError, "Private text"):
            publisher.validate(archive, report)

    def test_source_change_after_package_build_cannot_be_published(self):
        archive, report = self.package()
        changed = dict(self.sources, **{"probe_launcher.py": "0" * 64})
        with patch.object(publisher, "source_files", return_value=changed):
            with self.assertRaisesRegex(ValueError, "source changed after"):
                publisher.validate(archive, report)

    def test_missing_build_source_identity_rejected(self):
        archive, report = self.package(built_sources={})
        with self.assertRaisesRegex(ValueError, "no build source identities"):
            publisher.validate(archive, report)

    def test_asset_name_and_size_limit_enforced(self):
        archive, report = self.package()
        wrong = archive.with_name("private.zip")
        archive.rename(wrong)
        with self.assertRaisesRegex(ValueError, "Only the bounded public"):
            publisher.validate(wrong, report)
        wrong.rename(archive)
        with patch.object(publisher.updater, "MAX_ARCHIVE", 1), self.assertRaisesRegex(ValueError, "bounded public"):
            publisher.validate(archive, report)


class SourceCurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text("Public source\n")
        (self.root / "prototype").mkdir()
        for patcher in (patch.object(publisher, "SOURCE_FILES", ("README.md",)),
                        patch.object(publisher, "SOURCE_DIRS", ("prototype",))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def put(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_curates_sources_and_ignores_runtime_and_original_binaries(self):
        self.put("prototype/mod.lua", "return {}")
        self.put("prototype/results/report.json", "private report")
        self.put("prototype/staged/initial.sav.lua", "private metadata")
        self.put("prototype/native/out/original.dll", "private binary")
        self.put("unselected/secret.txt", "private outside source roots")
        selected = publisher.source_files(self.root)
        self.assertEqual(set(selected), {"README.md", "prototype/mod.lua"})

    def test_metadata_save_cannot_hide_under_lua_extension(self):
        self.put("prototype/initial.sav.lua", "return {private = true}")
        with self.assertRaises(publisher.updater.UpdateError):
            publisher.source_files(self.root)

    def test_plain_and_json_escaped_user_paths_and_steam_ids_are_rejected(self):
        user_path = "\\".join(("C:", "Users", "FixturePerson", "Documents", "state.json"))
        steam_path = "\\".join(("userdata", "123456789", "1066780", "local"))
        for content in (user_path, json.dumps({"path": user_path}), steam_path, json.dumps({"path": steam_path})):
            with self.subTest(content=content):
                self.put("prototype/config.json", content)
                with self.assertRaisesRegex(ValueError, "Private identity/path/credential"):
                    publisher.source_files(self.root)

    def test_zero_account_placeholder_remains_allowed(self):
        self.put("prototype/example.txt", "\\".join(("userdata", "0", "1066780", "local")))
        self.assertIn("prototype/example.txt", publisher.source_files(self.root))

    def test_credential_patterns_rejected_without_printing_contents(self):
        fake_token = "gh" + "p_" + "x" * 40
        self.put("prototype/config.json", json.dumps({"credential": fake_token}))
        with self.assertRaises(ValueError) as caught:
            publisher.source_files(self.root)
        self.assertNotIn(fake_token, str(caught.exception))


class PublisherAPITests(unittest.TestCase):
    def test_git_failure_does_not_expose_helper_output(self):
        secret = "synthetic-private-helper-output"
        result = subprocess.CompletedProcess([], 1, stdout=secret, stderr=secret)
        with patch.object(publisher.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                publisher.git(["credential", "fill"], input="fixture")
        self.assertEqual(str(caught.exception), "Git operation failed: credential")
        self.assertNotIn(secret, str(caught.exception))

    def test_authenticated_redirects_are_rejected_before_sending_credentials(self):
        handler = publisher._NoRedirects()
        request = Request("https://api.github.com/user", headers={"Authorization": "Bearer fixture-only"})
        for url in ("https://attacker.invalid/collect", "https://uploads.github.com/another"):
            with self.subTest(url=url), self.assertRaisesRegex(RuntimeError, "redirects are not allowed"):
                handler.redirect_request(request, None, 302, "", {}, url)

    def test_api_rejects_foreign_initial_host_and_sanitizes_http_errors(self):
        api = publisher.GitHub.__new__(publisher.GitHub)
        api.token = "fixture-only"
        with patch.object(publisher, "build_opener") as opener:
            with self.assertRaises(ValueError):
                api.call("POST", "https://attacker.invalid/collect", {"fixture": True})
        opener.assert_not_called()
        error = HTTPError("https://api.github.com/user", 403, "do not expose this", {}, io.BytesIO(b"private body"))
        opener = Mock()
        opener.open.side_effect = error
        with patch.object(publisher, "build_opener", return_value=opener):
            with self.assertRaises(RuntimeError) as caught:
                api.call("GET", "/user")
        self.assertEqual(str(caught.exception), "GitHub API GET failed (HTTP 403).")


class DraftLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "prototype").mkdir()
        (self.root / "prototype/RELEASE_NOTES.md").write_text("Synthetic release notes")
        self.report = {"archive_sha256": "a" * 64, "bytes": 123, "source_files": {"README.md": "b" * 64}}
        self.archive = self.root / publisher.updater.ASSET_NAME
        self.events = []
        self.existing = None
        self.wrong_upload = False
        self.asset = {"name": publisher.updater.ASSET_NAME, "digest": "sha256:" + "a" * 64, "size": 123,
                      "browser_download_url": "https://github.com/fixture/download"}

    def api(self, method, path, data=None, **options):
        self.events.append((method, path, data))
        if path == "/user":
            return {"login": "fixture", "id": 1}
        if path == f"/repos/{publisher.REPO}":
            return {"full_name": publisher.REPO, "permissions": {"push": True}}
        if method == "GET":
            return self.existing
        if method == "POST" and "upload" in options:
            return dict(self.asset, digest="sha256:" + "0" * 64) if self.wrong_upload else self.asset
        if method == "POST":
            self.assertIs(data["draft"], True)
            return {"id": 42, "upload_url": "https://uploads.github.com/fixture{?name,label}", "assets": []}
        if method == "PATCH":
            self.assertIs(data["draft"], False)
            self.assertIs(data["prerelease"], False)
            self.assertEqual(data["make_latest"], "true")
            return {"html_url": "https://github.com/fixture/release"}
        raise AssertionError("Unexpected mocked API call")

    def git(self, arguments, **options):
        self.events.append(("git", list(arguments), None))
        if arguments == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="c" * 40 + "\n")
        if arguments[:2] == ["rev-parse", "--verify"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    def run_publish(self):
        api = Mock()
        api.call.side_effect = self.api
        with patch.object(publisher, "ROOT", self.root), \
                patch.object(publisher, "GitHub", return_value=api), \
                patch.object(publisher, "git", side_effect=self.git), \
                patch.object(publisher, "copy_source", return_value=self.root / ".publish/TFCoop") as copy:
            result = publisher.publish(self.archive, self.report)
        copy.assert_called_once_with(self.root / ".publish/TFCoop", self.report["source_files"])
        return result

    def test_first_release_pushes_atomic_tag_and_only_publishes_after_verified_upload(self):
        self.asset["browser_download_url"] = "https://github.com/fixture/releases/download/untagged-fixture/TFCoop-Windows.zip"
        result = self.run_publish()
        self.assertEqual(result["sha256"], "a" * 64)
        self.assertEqual(result["download"], f"https://github.com/{publisher.REPO}/releases/download/{publisher.RELEASE_TAG}/TFCoop-Windows.zip")
        push = next(event for event in self.events if event[0] == "git" and event[1][0] == "push")
        self.assertIn("--atomic", push[1])
        methods = [event[0] for event in self.events if event[0] != "git"]
        self.assertEqual(methods, ["GET", "GET", "GET", "POST", "POST", "PATCH"])

    def test_wrong_uploaded_digest_keeps_release_draft(self):
        self.wrong_upload = True
        with self.assertRaisesRegex(ValueError, "remains a draft"):
            self.run_publish()
        self.assertFalse(any(event[0] == "PATCH" for event in self.events))

    def test_retry_matching_draft_asset_does_not_upload_again(self):
        self.existing = {"id": 42, "draft": True, "assets": [self.asset]}
        self.run_publish()
        self.assertFalse(any(event[0] == "POST" for event in self.events))
        self.assertEqual(sum(event[0] == "PATCH" for event in self.events), 1)

    def test_retry_mismatched_draft_asset_does_not_publish(self):
        self.existing = {"id": 42, "draft": True, "assets": [dict(self.asset, size=99)]}
        with self.assertRaisesRegex(ValueError, "different asset"):
            self.run_publish()
        self.assertFalse(any(event[0] == "PATCH" for event in self.events))

    def test_published_version_refused_before_source_mutation(self):
        api = Mock()
        self.existing = {"id": 42, "draft": False}
        api.call.side_effect = self.api
        with patch.object(publisher, "GitHub", return_value=api), \
                patch.object(publisher, "copy_source") as copy, \
                patch.object(publisher, "git") as git:
            with self.assertRaisesRegex(ValueError, "already published"):
                publisher.publish(self.archive, self.report)
        copy.assert_not_called()
        git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
