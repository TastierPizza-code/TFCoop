"""Headless release/update fault tests; no network, application or game starts."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request
import zipfile

from prototype import updater


class Response(io.BytesIO):
    def __init__(self, raw, length=None):
        super().__init__(raw)
        self.headers = {"Content-Length": str(len(raw) if length is None else length)}


def archive(tag="v0.5.3", *, extra=None, manifest_extra=None, flat=False, root="TFCoop"):
    files = {"TF2-Coop.exe": b"MZ-fake-test-launcher", "_internal/test.dll": b"fake-test-library",
             "ANLEITUNG.html": b"<p>test</p>"}
    if manifest_extra:
        files.update(manifest_extra)
    manifest = {"release_tag": tag, "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    data = io.BytesIO()
    prefix = "" if flat else root + "/"
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as output:
        def write(name, content):
            # A release asset is immutable. Keep fixtures byte-identical across
            # calls even when a slow test crosses ZIP's two-second clock tick.
            entry = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(entry, content)
        for name, content in files.items():
            write(prefix + name, content)
        write(prefix + "package_manifest.json", json.dumps(manifest).encode())
        for name, content in extra or []:
            if isinstance(name, zipfile.ZipInfo):
                write(name, content)
            else:
                write(prefix + name, content)
    return data.getvalue()


def release(raw, tag="v0.5.3"):
    return {"tag_name": tag, "draft": False, "prerelease": False, "assets": [{
        "name": updater.ASSET_NAME, "size": len(raw),
        "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "browser_download_url": f"https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{updater.ASSET_NAME}"}]}


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.current = self.root / "current"
        self.current.mkdir()
        (self.current / "package_manifest.json").write_text(json.dumps({"release_tag": "v0.5.2"}), encoding="utf-8")
        self.cache = self.root / "cache"
        active = patch.object(updater, "_runtime_active", return_value=False)
        self.active = active.start()
        self.addCleanup(active.stop)

    def perform(self, raw=None, *, metadata=None, actual=None, cache=None, progress=None, active_check=None):
        raw = archive() if raw is None else raw
        metadata = release(raw) if metadata is None else metadata
        def open_response(url, *, api=False):
            if api:
                self.assertEqual(url, updater.API_URL)
                return Response(json.dumps(metadata).encode())
            self.assertEqual(url, metadata["assets"][0]["browser_download_url"])
            return Response(raw if actual is None else actual, length=metadata["assets"][0]["size"])
        with patch.object(updater, "_open", side_effect=open_response) as opened:
            result = updater.check_for_update(self.current, cache or self.cache,
                                             progress=progress or (lambda message: None),
                                             active_check=active_check or (lambda: False))
        return result, opened

    def test_installs_verified_immutable_bundle_and_atomic_pointer(self):
        messages = []
        result, opened = self.perform(progress=messages.append)
        self.assertEqual(result.version, "v0.5.3")
        self.assertEqual(result.executable.read_bytes(), b"MZ-fake-test-launcher")
        pointer = json.loads((self.cache / "current.json").read_text())
        self.assertEqual(pointer["release_tag"], "v0.5.3")
        self.assertEqual(pointer["directory"], result.executable.parent.name)
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(messages)
        self.assertEqual(list(self.cache.glob("*.part")), [])
        self.assertFalse((self.current / "TF2-Coop.exe").exists())

    def test_flat_zip_supported(self):
        result, _ = self.perform(archive(flat=True))
        self.assertTrue(result.executable.is_file())

    def test_current_release_does_not_download_archive(self):
        raw = archive("v0.5.2")
        result, opened = self.perform(raw, metadata=release(raw, "v0.5.2"))
        self.assertIsNone(result.executable)
        self.assertEqual(result.version, "v0.5.2")
        self.assertEqual(opened.call_count, 1)

    def test_older_remote_release_never_downgrades(self):
        raw = archive("v0.5.1")
        result, opened = self.perform(raw, metadata=release(raw, "v0.5.1"))
        self.assertIsNone(result.executable)
        self.assertEqual(result.version, "v0.5.2")
        self.assertEqual(opened.call_count, 1)

    def test_offline_keeps_original_version_when_no_cache(self):
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(self.current, self.cache)
        self.assertIsNone(result.executable)
        self.assertIn("offline", result.message)
        self.assertFalse((self.cache / "current.json").exists())

    def test_offline_uses_fully_verified_cached_latest(self):
        installed, _ = self.perform()
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(self.current, self.cache)
        self.assertEqual(result.executable, installed.executable)
        self.assertEqual(result.version, "v0.5.3")
        self.assertIn("geprüfte Version", result.message)

    def test_cached_newer_release_survives_remote_rollback(self):
        installed, _ = self.perform()
        raw = archive("v0.5.2")
        result, opened = self.perform(raw, metadata=release(raw, "v0.5.2"))
        self.assertEqual(result.executable, installed.executable)
        self.assertEqual(opened.call_count, 1)

    def test_same_cached_executable_does_not_handoff_to_itself(self):
        installed, _ = self.perform()
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(installed.executable.parent, self.cache)
        self.assertIsNone(result.executable)
        self.assertEqual(result.version, "v0.5.3")

    def test_modified_cached_executable_is_not_run_offline(self):
        installed, _ = self.perform()
        installed.executable.write_bytes(b"changed")
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(self.current, self.cache)
        self.assertIsNone(result.executable)

    def test_modified_cached_manifest_is_not_run_offline(self):
        installed, _ = self.perform()
        manifest = installed.executable.parent / "package_manifest.json"
        manifest.write_text(manifest.read_text() + " ")
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(self.current, self.cache)
        self.assertIsNone(result.executable)

    def test_bad_digest_truncation_and_excess_bytes_leave_no_pointer(self):
        raw = archive()
        cases = [(release(raw), raw[:-1]), (release(raw), raw + b"extra")]
        bad_digest = release(raw)
        bad_digest["assets"][0]["digest"] = "sha256:" + "0" * 64
        cases.append((bad_digest, raw))
        for number, (metadata, actual) in enumerate(cases):
            with self.subTest(number=number):
                cache = self.root / f"cache-{number}"
                result, _ = self.perform(raw, metadata=metadata, actual=actual, cache=cache)
                self.assertIsNone(result.executable)
                self.assertFalse((cache / "current.json").exists())
                self.assertEqual(list(cache.glob("*.part")), [])

    def test_missing_digest_wrong_repo_duplicate_asset_and_prerelease_rejected(self):
        raw = archive()
        for case in ("digest", "repo", "duplicate", "prerelease"):
            with self.subTest(case=case):
                metadata = release(raw)
                if case == "digest":
                    metadata["assets"][0].pop("digest")
                elif case == "repo":
                    metadata["assets"][0]["browser_download_url"] = "https://github.com/other/repo/release.zip"
                elif case == "duplicate":
                    metadata["assets"].append(dict(metadata["assets"][0]))
                else:
                    metadata["prerelease"] = True
                result, opened = self.perform(raw, metadata=metadata, cache=self.root / case)
                self.assertIsNone(result.executable)
                self.assertEqual(opened.call_count, 1)

    def test_unsafe_zip_paths_rejected(self):
        for number, path in enumerate(("../escape.txt", "/absolute.txt", "C:/drive.txt", "dir\\escape.txt",
                                       "file.txt:secret", "CON.txt", "dir /file", "NUL", "bad?.txt",
                                       "_internal/../escape.txt")):
            with self.subTest(path=path):
                raw = archive(extra=[(path, b"bad")])
                cache = self.root / f"bad-{number}"
                result, _ = self.perform(raw, cache=cache)
                self.assertIsNone(result.executable)
                self.assertFalse((cache / "current.json").exists())
        self.assertFalse((self.root / "escape.txt").exists())

    def test_case_aliases_and_symlink_rejected(self):
        linked = zipfile.ZipInfo("TFCoop/link")
        linked.create_system = 3
        linked.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = [archive(extra=[("tf2-coop.exe", b"bad")]),
                 archive(extra=[("_INTERNAL/second.dll", b"bad")]),
                 archive(extra=[(linked, b"../../elsewhere")])]
        for number, raw in enumerate(cases):
            with self.subTest(number=number):
                result, _ = self.perform(raw, cache=self.root / f"alias-{number}")
                self.assertIsNone(result.executable)

    def test_extra_unmanifested_file_rejected(self):
        result, _ = self.perform(archive(extra=[("extra.txt", b"not in manifest")]))
        self.assertIsNone(result.executable)
        self.assertIn("zusätzliche", result.message)

    def test_private_save_secret_and_stock_game_rejected_even_if_manifested(self):
        for number, name in enumerate(("Testspielstand/initial.sav", "initial.sav.lua", "session.key",
                                       "TransportFever2.exe", "alut_real.dll", ".env", "reports/peer.json")):
            with self.subTest(name=name):
                raw = archive(manifest_extra={name: b"private"})
                result, _ = self.perform(raw, cache=self.root / f"private-{number}")
                self.assertIsNone(result.executable)

    def test_size_limits_before_download_and_before_extraction(self):
        raw = archive()
        with patch.object(updater, "MAX_ARCHIVE", 10):
            result, opened = self.perform(raw)
        self.assertIsNone(result.executable)
        self.assertEqual(opened.call_count, 1)
        with patch.object(updater, "MAX_UNPACKED", 10):
            result, _ = self.perform(raw)
        self.assertIsNone(result.executable)
        self.assertFalse((self.cache / "current.json").exists())

    def test_manifest_release_tag_must_match_published_tag(self):
        raw = archive("v9.0.0")
        result, _ = self.perform(raw, metadata=release(raw, "v0.5.3"))
        self.assertIsNone(result.executable)

    def test_interrupted_publication_preserves_old_pointer(self):
        installed, _ = self.perform()
        before = (self.cache / "current.json").read_bytes()
        raw = archive("v0.5.4")
        with patch.object(updater, "_write_pointer", side_effect=OSError("interrupted")):
            result, _ = self.perform(raw, metadata=release(raw, "v0.5.4"))
        self.assertEqual(result.executable, installed.executable)
        self.assertEqual((self.cache / "current.json").read_bytes(), before)

    def test_unreferenced_version_folder_is_replaced_only_after_verified_download(self):
        raw = archive()
        digest = hashlib.sha256(raw).hexdigest()
        name = "v0.5.3-" + digest[:16]
        destination = self.cache / "versions" / name
        destination.parent.mkdir(parents=True)
        fake = archive(manifest_extra={"evil.txt": b"local extra"})
        fake_zip = self.root / "fake.zip"
        fake_zip.write_bytes(fake)
        updater._extract(fake_zip, destination, "v0.5.3")
        result, opened = self.perform(raw)
        self.assertEqual(result.executable, destination / updater.EXECUTABLE)
        self.assertEqual(opened.call_count, 2)
        self.assertFalse((destination / "evil.txt").exists())
        quarantined = list(destination.parent.glob("quarantine-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual((quarantined[0] / "evil.txt").read_bytes(), b"local extra")
        self.assertTrue((self.cache / "current.json").is_file())

    def test_corrupt_cached_release_repairs_online_and_preserves_damaged_bytes(self):
        installed, _ = self.perform()
        installed.executable.write_bytes(b"damaged executable")
        result, opened = self.perform()
        self.assertEqual(result.executable, installed.executable)
        self.assertEqual(result.executable.read_bytes(), b"MZ-fake-test-launcher")
        self.assertEqual(opened.call_count, 2)
        quarantined = list((self.cache / "versions").glob("quarantine-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual((quarantined[0] / updater.EXECUTABLE).read_bytes(), b"damaged executable")
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            offline = updater.check_for_update(self.current, self.cache)
        self.assertEqual(offline.executable, installed.executable)

    def test_cached_release_with_missing_file_repairs_online(self):
        installed, _ = self.perform()
        (installed.executable.parent / "_internal/test.dll").unlink()
        result, _ = self.perform()
        self.assertEqual(result.executable, installed.executable)
        self.assertEqual((result.executable.parent / "_internal/test.dll").read_bytes(), b"fake-test-library")

    def test_existing_non_directory_destination_is_not_moved(self):
        raw = archive()
        destination = self.cache / "versions" / ("v0.5.3-" + hashlib.sha256(raw).hexdigest()[:16])
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"unrelated file")
        result, _ = self.perform(raw)
        self.assertIsNone(result.executable)
        self.assertEqual(destination.read_bytes(), b"unrelated file")
        self.assertEqual(list(destination.parent.glob("quarantine-*")), [])
        self.assertFalse((self.cache / "current.json").exists())

    def test_link_or_reparse_content_in_damaged_cache_is_not_moved(self):
        installed, _ = self.perform()
        installed.executable.write_bytes(b"damaged executable")
        nested = installed.executable.parent / "_internal/test.dll"
        original = updater._ordinary
        def reparse(path, *, directory=False):
            if path == nested:
                raise updater.UpdateError("Verknüpfungen sind im Updateordner nicht erlaubt.")
            return original(path, directory=directory)
        before = (self.cache / "current.json").read_bytes()
        with patch.object(updater, "_ordinary", side_effect=reparse):
            result, _ = self.perform()
        self.assertIsNone(result.executable)
        self.assertEqual(installed.executable.read_bytes(), b"damaged executable")
        self.assertEqual(list((self.cache / "versions").glob("quarantine-*")), [])
        self.assertEqual((self.cache / "current.json").read_bytes(), before)

    def test_busy_game_or_controller_skips_network(self):
        for use_callback in (True, False):
            with self.subTest(use_callback=use_callback):
                self.active.return_value = not use_callback
                with patch.object(updater, "_open") as opened:
                    result = updater.check_for_update(self.current, self.cache, active_check=lambda: use_callback)
                self.assertIsNone(result.executable)
                self.assertIn("verschoben", result.message)
                opened.assert_not_called()

    def test_game_started_during_download_prevents_pointer_publication(self):
        calls = 0
        def active():
            nonlocal calls
            calls += 1
            return calls >= 2
        result, _ = self.perform(active_check=active)
        self.assertIsNone(result.executable)
        self.assertIn("verschoben", result.message)
        self.assertFalse((self.cache / "current.json").exists())

    def test_double_start_mutex_leaves_other_start_in_control(self):
        with updater._update_lock(), patch.object(updater, "_open") as opened:
            result = updater.check_for_update(self.current, self.cache)
        self.assertIsNone(result.executable)
        self.assertIn("anderer Launcher", result.message)
        opened.assert_not_called()

    def test_redirects_only_use_https_github_asset_hosts(self):
        handler = updater._Redirects()
        request = Request("https://github.com/TastierPizza-code/TFCoop/releases/download/v0.5.3/TFCoop-Windows.zip")
        for url in ("http://release-assets.githubusercontent.com/file", "https://attacker.test/file",
                    "https://github.com.attacker.test/file", "https://user:secret@github.com/file",
                    "https://github.com:444/file", "file:///C:/test.exe"):
            with self.subTest(url=url), self.assertRaises(updater.UpdateError):
                handler.redirect_request(request, None, 302, "", {}, url)
        accepted = handler.redirect_request(request, None, 302, "", {},
                                            "https://release-assets.githubusercontent.com/file?sig=temporary")
        self.assertEqual(accepted.host, "release-assets.githubusercontent.com")

    def test_case_ambiguous_manifest_and_duplicate_json_fields_rejected(self):
        with self.assertRaises(updater.UpdateError):
            updater._json(b'{"files": {}, "files": {}}')
        raw = archive(manifest_extra={"tf2-coop.exe": b"alias"})
        result, _ = self.perform(raw)
        self.assertIsNone(result.executable)

    def test_pointer_cannot_escape_cache(self):
        installed, _ = self.perform()
        pointer = json.loads((self.cache / "current.json").read_text())
        pointer["directory"] = "../../current"
        (self.cache / "current.json").write_text(json.dumps(pointer))
        with patch.object(updater, "_open", side_effect=OSError("offline")):
            result = updater.check_for_update(self.current, self.cache)
        self.assertIsNone(result.executable)
        self.assertTrue(installed.executable.is_file())


if __name__ == "__main__":
    unittest.main()
