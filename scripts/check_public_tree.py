#!/usr/bin/env python3
"""Check tracked files for common public-repository leaks and broken Markdown links."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_SUFFIXES = {
    ".aab",
    ".apk",
    ".cer",
    ".crt",
    ".db",
    ".jks",
    ".key",
    ".keystore",
    ".log",
    ".msi",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
FORBIDDEN_PATH_PARTS = {".gradle", ".venv", "bin", "obj", "build", "TestResults"}
ALLOWED_DATA_FILES = {
    "services/api/data/.gitkeep",
    "services/api/storage/.gitkeep",
}
RUNTIME_DATA_PREFIXES = (
    "data/",
    "Data/",
    "storage/",
    "services/api/data/",
    "services/api/storage/",
    "apps/windows/src/FlowNote.Windows.App/Data/",
)
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTTP_HOST_PATTERN = re.compile(r"https?://([A-Za-z0-9.-]+)", re.IGNORECASE)
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
UNIX_HOME_PATTERN = re.compile(r"/(?:Users|home)/([^/\s]+)/")
WINDOWS_HOME_PATTERN = re.compile(r"(?i)\b[A-Z]:\\Users\\([^\\\s]+)\\")
EMAIL_PATTERN = re.compile(
    r"(?i)(?<![A-Z0-9._%+-])([A-Z0-9._%+-]+@(?:[A-Z0-9-]+\.)+[A-Z]{2,})(?![A-Z0-9._%+-])"
)
ALLOWED_EXAMPLE_USERS = {"example", "example-user"}
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "users.noreply.github.com",
}


def candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [Path(value.decode("utf-8")) for value in result.stdout.split(b"\0") if value]


def check_tracked_path(path: Path) -> list[str]:
    relative = path.as_posix()
    errors: list[str] = []
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        errors.append(f"tracked sensitive/generated file: {relative}")
    if any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
        errors.append(f"tracked build or dependency output: {relative}")
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        errors.append(f"tracked environment file: {relative}")
    if relative.startswith(RUNTIME_DATA_PREFIXES) and relative not in ALLOWED_DATA_FILES:
        errors.append(f"tracked runtime/test data: {relative}")
    return errors


def check_text(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    relative = path.as_posix()
    if PRIVATE_KEY_PATTERN.search(text):
        errors.append(f"private key marker in tracked text: {relative}")
    if "file:" + "//" in text:
        errors.append(f"machine-local file URI in tracked text: {relative}")

    local_user_names = {
        *UNIX_HOME_PATTERN.findall(text),
        *WINDOWS_HOME_PATTERN.findall(text),
    }
    for user_name in sorted(local_user_names):
        if user_name.lower() not in ALLOWED_EXAMPLE_USERS:
            errors.append(
                f"machine-local user path in tracked text: {relative}: {user_name}"
            )

    for email_address in sorted(set(EMAIL_PATTERN.findall(text))):
        domain = email_address.rsplit("@", 1)[1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS and not domain.endswith(
            (".example", ".invalid")
        ):
            errors.append(f"non-example email address in tracked text: {relative}")

    for host in HTTP_HOST_PATTERN.findall(text):
        normalized = host.rstrip(".").lower()
        if normalized.startswith("flownote.") and not normalized.endswith((".example", ".invalid")):
            errors.append(f"non-reserved FlowNote host in tracked text: {relative}: {host}")
    return errors


def check_markdown_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
        target = raw_target.strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        file_target = unquote(target.split("#", 1)[0])
        if not file_target:
            continue
        resolved = (REPOSITORY_ROOT / path.parent / file_target).resolve()
        try:
            resolved.relative_to(REPOSITORY_ROOT)
        except ValueError:
            errors.append(f"Markdown link escapes the repository: {path.as_posix()}: {target}")
            continue
        if not resolved.exists():
            errors.append(f"broken Markdown link: {path.as_posix()}: {target}")
    return errors


def main() -> int:
    errors: list[str] = []
    files = candidate_files()
    for path in files:
        errors.extend(check_tracked_path(path))
        absolute = REPOSITORY_ROOT / path
        try:
            text = absolute.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        errors.extend(check_text(path, text))
        if path.suffix.lower() == ".md":
            errors.extend(check_markdown_links(path, text))

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print(f"Public tree check failed with {len(errors)} issue(s).")
        return 1

    markdown_count = sum(path.suffix.lower() == ".md" for path in files)
    print(
        f"[PASS] Checked {len(files)} tracked or unignored files and {markdown_count} "
        "Markdown files; "
        "no forbidden artifacts, private-key markers, machine-local user paths, "
        "non-example email addresses, non-reserved FlowNote hosts, or broken relative "
        "links were found."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
