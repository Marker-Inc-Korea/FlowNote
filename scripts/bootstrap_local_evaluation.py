#!/usr/bin/env python3
"""Create a Git-ignored FlowNote environment file for local API evaluation."""

from __future__ import annotations

import argparse
import secrets
import stat
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = REPOSITORY_ROOT / "services" / "api" / ".env.example"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "services" / "api" / ".env"
REQUIRED_REPLACEMENTS = {
    "FLOWNOTE_ENV": "local",
    "FLOWNOTE_INITIAL_ADMIN_PASSWORD": None,
    "FLOWNOTE_ACCESS_TOKEN_SECRET": None,
}


def _replace_setting(contents: str, name: str, value: str) -> str:
    prefix = f"{name}="
    lines = contents.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"{name} must appear exactly once in the environment template.")
    lines[matches[0]] = f"{prefix}{value}"
    return "\n".join(lines) + "\n"


def render_environment(template: str, admin_password: str, token_secret: str) -> str:
    values = {
        **REQUIRED_REPLACEMENTS,
        "FLOWNOTE_INITIAL_ADMIN_PASSWORD": admin_password,
        "FLOWNOTE_ACCESS_TOKEN_SECRET": token_secret,
    }
    rendered = template
    for name, value in values.items():
        if value is None:
            raise ValueError(f"No value was generated for {name}.")
        rendered = _replace_setting(rendered, name, value)
    return rendered


def write_environment(output: Path, contents: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
    except FileExistsError as exception:
        raise FileExistsError(
            f"Environment file already exists and was not changed: {output}"
        ) from exception

    try:
        output.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Some Windows filesystems do not expose POSIX permission bits.
        pass


def validate_output_path(output: Path) -> None:
    name = output.name
    is_ignored_environment_name = (
        name == ".env"
        or name.endswith(".env.local")
        or (name.startswith(".env.") and name.endswith(".local"))
    )
    if not is_ignored_environment_name:
        raise ValueError(
            "Output must use a Git-ignored environment filename such as .env or *.env.local."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate local-only FlowNote API secrets and create a Git-ignored .env file. "
            "This command is not an operational deployment tool."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Environment file to create (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-show-password",
        action="store_true",
        help="Do not print the generated initial administrator password.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = args.output.resolve()
        validate_output_path(output)
        template = DEFAULT_TEMPLATE.read_text(encoding="utf-8")
        admin_password = secrets.token_urlsafe(18)
        token_secret = secrets.token_urlsafe(48)
        rendered = render_environment(template, admin_password, token_secret)
        write_environment(output, rendered)
    except (FileExistsError, OSError, ValueError) as exception:
        print(f"[ERROR] {exception}", file=sys.stderr)
        return 2

    print(f"[OK] Local evaluation environment created: {output}")
    print("[LOGIN] Initial administrator username: admin")
    if args.no_show_password:
        print("[LOGIN] Password output suppressed; read the Git-ignored environment file.")
    else:
        print(f"[LOGIN] Initial administrator password: {admin_password}")
    print("[NEXT] Install the API dependencies, start uvicorn from services/api, then change the password.")
    print("[NOTICE] This local environment is not evidence of an approved operational deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
