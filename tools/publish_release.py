"""Validate public source/package; --publish pushes source and a verified GitHub release.

Credentials stay in memory. No game files are installed and no application opens.
The default validates locally without using credentials or changing GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prototype.release_version import RELEASE_TAG, DISPLAY_VERSION
from prototype import updater

REPO = updater.REPOSITORY
REMOTE = f"https://github.com/{REPO}.git"
SOURCE_DIRS = ("coop", "mod", "native", "prototype", "tests", "tools")
SOURCE_FILES = ("README.md", "AGENTS.md", ".gitignore", "THIRD_PARTY_NOTICES.md",
                "requirements-build.txt", "requirements-test.txt", "Start-Coop.cmd",
                "probe_launcher.py", "launcher.py", "docs/UPSTREAM.patch",
                "upstream/tpf2-multiplayer/LICENSE", "upstream/tpf2-multiplayer/THIRD_PARTY_NOTICES.md")
EXCLUDED = {".git", "__pycache__", ".deps", ".venv", "out", "staged", "sessions", "results",
            "runtime", "build", "dist", ".publish"}
EXTENSIONS = {".py", ".lua", ".con", ".cpp", ".h", ".asm", ".cmd", ".bat", ".md",
              ".html", ".json", ".txt", ".patch"}
PRIVATE_TEXT = re.compile(
    r"(?:[A-Z]:[/\\]+Users[/\\]+(?!Public(?:[/\\]|$)|<)[^/\\\s<>]+[/\\]+)"
    r"|(?:userdata[/\\]+[1-9]\d*[/\\]+1066780)"
    r"|(?:gh[pousr]_[A-Za-z0-9]{30,})|(?:github_pat_[A-Za-z0-9_]{30,})"
    r"|(?:-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)", re.I)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def source_files(root=ROOT):
    selected = {Path(name) for name in SOURCE_FILES}
    for name in (*SOURCE_DIRS, "upstream/tpf2-multiplayer/bridge/src", "upstream/tpf2-multiplayer/mod"):
        for path in (root / name).rglob("*"):
            relative = path.relative_to(root)
            if any(part in EXCLUDED for part in relative.parts):
                continue
            if path.is_file() and (path.suffix in EXTENSIONS or path.name == ".gitignore"):
                selected.add(relative)
    result = {}
    for relative in sorted(selected):
        updater._public_file(relative.as_posix())
        path = root / relative
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Missing or linked public source: " + relative.as_posix())
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Source file unexpectedly large: " + relative.as_posix())
        if PRIVATE_TEXT.search(data.decode("utf-8", errors="replace")):
            raise ValueError("Private identity/path/credential in public source: " + relative.as_posix())
        result[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    return result


def validate(archive, self_check):
    archive, self_check = Path(archive).resolve(strict=True), Path(self_check).resolve(strict=True)
    if archive.name != updater.ASSET_NAME or archive.stat().st_size > updater.MAX_ARCHIVE:
        raise ValueError("Only the bounded public TFCoop-Windows.zip asset may be published.")
    report = json.loads(self_check.read_text("utf-8"))
    if (report.get("passed") is not True or report.get("frozen") is not True
            or report.get("game_started") is not False or report.get("ui_opened") is not False):
        raise ValueError("A successful frozen, headless package self-check is required.")
    sources = source_files()
    with tempfile.TemporaryDirectory(prefix="tfcoop-publish-") as temporary:
        extracted = Path(temporary) / "package"
        manifest = updater._extract(archive, extracted, RELEASE_TAG)
        if manifest.get("distribution") != "public" or manifest.get("repository") != REPO:
            raise ValueError("This is not a public package for the configured repository.")
        if report.get("package_manifest_sha256") != sha(extracted / "package_manifest.json"):
            raise ValueError("Self-check belongs to another package manifest.")
        built_sources = manifest.get("source_files")
        if not isinstance(built_sources, dict) or "probe_launcher.py" not in built_sources:
            raise ValueError("Package has no build source identities.")
        for name, expected in built_sources.items():
            if sources.get(name) != expected:
                raise ValueError("Public source changed after the package was built: " + name)
        for relative in manifest["files"]:
            if Path(relative).suffix in EXTENSIONS:
                if PRIVATE_TEXT.search((extracted / relative).read_text("utf-8", errors="replace")):
                    raise ValueError("Private text in release document/source: " + relative)
    return {"release_tag": RELEASE_TAG, "archive_sha256": sha(archive), "bytes": archive.stat().st_size,
            "source_files": sources}


def git(arguments, *, cwd=None, allow_failure=False, input=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GCM_GUI_PROMPT="0")
    result = subprocess.run(["git", "-c", "credential.interactive=never", *arguments], cwd=cwd,
                            env=env, input=input, capture_output=True, text=True, encoding="utf-8")
    if result.returncode and not allow_failure:
        # Credential helper output, server response bodies and remote URLs never enter logs.
        raise RuntimeError("Git operation failed: " + arguments[0])
    return result


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Authenticated GitHub API redirects are not allowed.")


class GitHub:
    def __init__(self):
        value = git(["credential", "fill"], input="protocol=https\nhost=github.com\n\n")
        credential = dict(line.split("=", 1) for line in value.stdout.splitlines() if "=" in line)
        self.token = credential.get("password")
        if not self.token:
            raise RuntimeError("Git Credential Manager has no GitHub credential.")

    def call(self, method, path, data=None, *, upload=None, missing_ok=False):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        parsed = urlsplit(url)
        if (parsed.hostname not in {"api.github.com", "uploads.github.com"} or parsed.username
                or parsed.password or parsed.port not in (None, 443) or parsed.scheme != "https"):
            raise ValueError("Unexpected GitHub API destination.")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                   "User-Agent": "TFCoop-release-publisher", "X-GitHub-Api-Version": "2022-11-28"}
        body = None
        if upload:
            body = Path(upload).read_bytes()
            headers["Content-Type"] = "application/zip"
        elif data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with build_opener(_NoRedirects()).open(request, timeout=120 if upload else 30) as response:
                return json.loads(response.read(4 * 1024 * 1024))
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise RuntimeError(f"GitHub API {method} failed (HTTP {exc.code}).") from None


def copy_source(checkout, files):
    checkout = Path(checkout).absolute()
    expected_parent = (ROOT / ".publish").absolute()
    if checkout.parent != expected_parent or checkout.name != "TFCoop":
        raise ValueError("Publication checkout must be the workspace .publish/TFCoop directory.")
    updater._canonical_directory(expected_parent, create=True)
    if not checkout.exists():
        checkout.mkdir()
        git(["init", "-b", "main"], cwd=checkout)
        git(["remote", "add", "origin", REMOTE], cwd=checkout)
    updater._canonical_directory(checkout)
    if git(["remote", "get-url", "origin"], cwd=checkout).stdout.strip() != REMOTE:
        raise ValueError("Publication checkout has an unexpected remote.")
    if git(["status", "--porcelain"], cwd=checkout).stdout.strip():
        raise ValueError("Publication checkout contains uncommitted edits; review it first.")
    remote = git(["ls-remote", "--heads", "origin", "main"], cwd=checkout).stdout.strip()
    if remote:
        git(["fetch", "origin", "main"], cwd=checkout)
        has_head = git(["rev-parse", "--verify", "HEAD"], cwd=checkout, allow_failure=True).returncode == 0
        if has_head:
            git(["merge", "--ff-only", "origin/main"], cwd=checkout)
        else:
            git(["checkout", "-B", "main", "origin/main"], cwd=checkout)
    tracked = set(git(["ls-files", "-z"], cwd=checkout).stdout.split("\0")) - {""}
    if tracked - set(files):
        raise ValueError("Repository contains files outside the current source selection; review removals first.")
    for relative, expected in files.items():
        source, target = ROOT / relative, checkout / relative
        updater._canonical_directory(target.parent, create=True)
        if target.exists():
            updater._ordinary(target)
        if not target.resolve().is_relative_to(checkout.resolve()):
            raise ValueError("Source target escaped publication checkout.")
        shutil.copy2(source, target)
        if sha(target) != expected or sha(source) != expected:
            raise ValueError("Source changed during publication: " + relative)
    # Add only the enumerated source selection; never broad-add the original workspace.
    for offset in range(0, len(files), 50):
        git(["add", "--", *list(files)[offset:offset + 50]], cwd=checkout)
    return checkout


def publish(archive, report):
    api = GitHub()
    user = api.call("GET", "/user")
    repo = api.call("GET", f"/repos/{REPO}")
    if repo.get("full_name") != REPO or not repo.get("permissions", {}).get("push"):
        raise ValueError("Configured GitHub account cannot publish to the requested repository.")
    existing = api.call("GET", f"/repos/{REPO}/releases/tags/{RELEASE_TAG}", missing_ok=True)
    if existing and not existing.get("draft"):
        raise ValueError("This version is already published; choose a new release tag.")
    checkout = copy_source(ROOT / ".publish/TFCoop", report["source_files"])
    git(["config", "user.name", user["login"]], cwd=checkout)
    git(["config", "user.email", f"{user['id']}+{user['login']}@users.noreply.github.com"], cwd=checkout)
    if git(["diff", "--cached", "--quiet"], cwd=checkout, allow_failure=True).returncode:
        git(["commit", "-m", f"Release {RELEASE_TAG}: {DISPLAY_VERSION}"], cwd=checkout)
    commit = git(["rev-parse", "HEAD"], cwd=checkout).stdout.strip()
    tag = git(["rev-parse", "--verify", f"refs/tags/{RELEASE_TAG}"], cwd=checkout, allow_failure=True)
    if tag.returncode == 0 and tag.stdout.strip() != commit:
        raise ValueError("Release tag already points at different source.")
    if tag.returncode:
        git(["tag", RELEASE_TAG, commit], cwd=checkout)
    git(["push", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{RELEASE_TAG}"], cwd=checkout)
    notes = (ROOT / "prototype/RELEASE_NOTES.md").read_text("utf-8")
    release = existing or api.call("POST", f"/repos/{REPO}/releases", {
        "tag_name": RELEASE_TAG, "target_commitish": commit, "name": f"TFCoop {DISPLAY_VERSION}",
        "body": notes, "draft": True, "prerelease": False})
    asset = next((a for a in release.get("assets", []) if a["name"] == updater.ASSET_NAME), None)
    if asset and (asset.get("digest") != "sha256:" + report["archive_sha256"]
                  or asset.get("size") != report["bytes"]):
        raise ValueError("Draft already contains a different asset; inspect it before retrying.")
    if not asset:
        upload = release["upload_url"].split("{", 1)[0] + "?name=" + updater.ASSET_NAME
        asset = api.call("POST", upload, upload=archive)
    if asset.get("digest") != "sha256:" + report["archive_sha256"] or asset.get("size") != report["bytes"]:
        raise ValueError("Uploaded asset hash/size mismatch; release remains a draft.")
    finished = api.call("PATCH", f"/repos/{REPO}/releases/{release['id']}", {
        "draft": False, "prerelease": False, "make_latest": "true", "body": notes})
    return {"release": finished["html_url"], "download": asset["browser_download_url"],
            "commit": commit, "sha256": report["archive_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--self-check", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    checked = validate(arguments.archive, arguments.self_check)
    if arguments.publish:
        result = publish(arguments.archive, checked)
    else:
        result = {key: value for key, value in checked.items() if key != "source_files"}
        result["source_file_count"] = len(checked["source_files"])
        result["published"] = False
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
