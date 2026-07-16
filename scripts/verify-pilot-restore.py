#!/usr/bin/env python3
"""Capture and compare read-only SQLite/file evidence for a pilot restore drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def database_evidence(database: Path) -> dict[str, Any]:
    if not database.is_file():
        raise ValueError(f"SQLite 파일이 없습니다: {database}")

    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        quick_check = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_key_check_error = None
        try:
            foreign_key_check = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
        except sqlite3.Error as error:
            foreign_key_check = []
            foreign_key_check_error = str(error)
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {quote_identifier(table)}"
            ).fetchone()[0]
            for table in table_names
        }
    finally:
        connection.close()

    return {
        "path_label": database.name,
        "bytes": database.stat().st_size,
        "sha256": sha256(database),
        "quick_check": quick_check,
        "foreign_key_check": foreign_key_check,
        "foreign_key_check_error": foreign_key_check_error,
        "table_counts": counts,
    }


def file_evidence(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"파일 루트가 없습니다: {root}")

    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"파일 루트 안의 심볼릭 링크는 허용하지 않습니다: {path}")
        if path.is_file():
            files.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    return {
        "root_label": root.name,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def validate_run_id(value: str) -> str:
    if not value.startswith("PILOT-") or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in value):
        raise argparse.ArgumentTypeError("run_id는 PILOT- 접두사와 영문, 숫자, '-', '_'만 사용해야 합니다.")
    return value


def capture(args: argparse.Namespace) -> int:
    evidence = {
        "schema_version": 1,
        "run_id": args.run_id,
        "target": args.target,
        "phase": args.phase,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": database_evidence(args.database),
        "file_set": file_evidence(args.files),
    }
    output = args.evidence_root / args.run_id / "backup-restore" / f"{args.target}-{args.phase}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    integrity_ok = (
        evidence["database"]["quick_check"] == ["ok"]
        and not evidence["database"]["foreign_key_check"]
        and evidence["database"]["foreign_key_check_error"] is None
    )
    print(f"증거 저장: {output}")
    print(f"DB quick_check: {evidence['database']['quick_check']}")
    print(f"foreign key 위반: {len(evidence['database']['foreign_key_check'])}건")
    if evidence["database"]["foreign_key_check_error"]:
        print(f"foreign key 검사 오류: {evidence['database']['foreign_key_check_error']}", file=sys.stderr)
    print(f"파일: {evidence['file_set']['file_count']}건")
    return 0 if integrity_ok else 1


def compare(args: argparse.Namespace) -> int:
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    failures: list[str] = []

    for field in ("run_id", "target"):
        if before.get(field) != after.get(field):
            failures.append(f"{field} 불일치: {before.get(field)!r} != {after.get(field)!r}")
    if before.get("phase") != "before" or after.get("phase") != "after":
        failures.append("비교 입력 phase는 before/after여야 합니다.")

    before_db = before["database"]
    after_db = after["database"]
    if before_db["quick_check"] != ["ok"]:
        failures.append(f"원천 DB quick_check 실패: {before_db['quick_check']!r}")
    if before_db["foreign_key_check"]:
        failures.append(f"원천 DB foreign key 위반 {len(before_db['foreign_key_check'])}건")
    if before_db.get("foreign_key_check_error"):
        failures.append(f"원천 DB foreign key 검사 오류: {before_db['foreign_key_check_error']}")
    if before_db["table_counts"] != after_db["table_counts"]:
        failures.append("SQLite 테이블별 원천 개수가 다릅니다.")
    if after_db["quick_check"] != ["ok"]:
        failures.append(f"복구 DB quick_check 실패: {after_db['quick_check']!r}")
    if after_db["foreign_key_check"]:
        failures.append(f"복구 DB foreign key 위반 {len(after_db['foreign_key_check'])}건")
    if after_db.get("foreign_key_check_error"):
        failures.append(f"복구 DB foreign key 검사 오류: {after_db['foreign_key_check_error']}")

    before_files = before["file_set"]
    after_files = after["file_set"]
    if before_files["files"] != after_files["files"]:
        failures.append("파일 상대경로·크기·SHA-256 목록이 다릅니다.")

    report = {
        "schema_version": 1,
        "run_id": before.get("run_id"),
        "target": before.get("target"),
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "before": str(args.before),
        "after": str(args.after),
        "table_counts_equal": before_db["table_counts"] == after_db["table_counts"],
        "file_manifest_equal": before_files["files"] == after_files["files"],
    }
    output = args.output or args.after.with_name(f"{before.get('target', 'restore')}-comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"비교 결과: {report['result']}")
    print(f"증거 저장: {output}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 0 if not failures else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="FlowNote 파일럿 백업·복구 무결성 증거 도구")
    commands = result.add_subparsers(dest="command", required=True)

    capture_parser = commands.add_parser("capture", help="복구 전/후 DB와 파일 증거를 수집합니다.")
    capture_parser.add_argument("--run-id", required=True, type=validate_run_id)
    capture_parser.add_argument("--target", required=True, choices=("server", "wpf"))
    capture_parser.add_argument("--phase", required=True, choices=("before", "after"))
    capture_parser.add_argument("--database", required=True, type=Path)
    capture_parser.add_argument("--files", required=True, type=Path)
    capture_parser.add_argument("--evidence-root", required=True, type=Path)
    capture_parser.set_defaults(handler=capture)

    compare_parser = commands.add_parser("compare", help="복구 전/후 증거를 비교합니다.")
    compare_parser.add_argument("--before", required=True, type=Path)
    compare_parser.add_argument("--after", required=True, type=Path)
    compare_parser.add_argument("--output", type=Path)
    compare_parser.set_defaults(handler=compare)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
