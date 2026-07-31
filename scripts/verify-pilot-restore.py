#!/usr/bin/env python3
"""Capture and compare read-only SQLite/file evidence for a pilot restore drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RESPONSIBILITY_TABLES = (
    "server_identity",
    "documents",
    "document_versions",
    "file_objects",
    "reports",
    "report_sources",
    "document_mutation_receipts",
    "report_mutation_receipts",
    "server_notification_cursors",
    "server_notification_messages",
    "server_sync_queue",
    "server_id_mappings",
)


def local_host_identity() -> dict[str, str]:
    system = platform.system()
    source: str
    raw_identity: str
    if system == "Windows":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            raw_identity = str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
        source = "windows-machine-guid"
    elif system == "Darwin":
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            check=True,
            capture_output=True,
            text=True,
        )
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
        if match is None:
            raise ValueError("macOS 장비 식별값을 확인할 수 없습니다.")
        raw_identity = match.group(1).strip()
        source = "macos-io-platform-uuid"
    else:
        machine_id_path = next(
            (
                path
                for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))
                if path.is_file()
            ),
            None,
        )
        if machine_id_path is None:
            raise ValueError("이 운영체제의 장비 식별값을 확인할 수 없습니다.")
        raw_identity = machine_id_path.read_text(encoding="utf-8").strip()
        source = "linux-machine-id"
    if not raw_identity:
        raise ValueError("운영체제 장비 식별값이 비어 있습니다.")
    return {
        "source": source,
        "sha256": hashlib.sha256(raw_identity.encode("utf-8")).hexdigest(),
    }


def path_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "modified_ns": None}
    stat = path.stat()
    return {
        "exists": True,
        "bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({quote_identifier(table)})"
        )
    }


def canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    return value


def table_fingerprint(connection: sqlite3.Connection, table: str) -> str:
    rows = [
        json.dumps(
            [canonical_value(value) for value in row],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in connection.execute(f"SELECT * FROM {quote_identifier(table)}")
    ]
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def responsibility_checks(
    connection: sqlite3.Connection, table_names: list[str]
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_sql_check(name: str, required: dict[str, set[str]], sql: str) -> None:
        applicable = all(
            table in table_names
            and columns.issubset(table_columns(connection, table))
            for table, columns in required.items()
        )
        rows = [list(row) for row in connection.execute(sql)] if applicable else []
        checks.append(
            {
                "name": name,
                "applicable": applicable,
                "violation_count": len(rows),
                "examples": rows[:20],
            }
        )

    add_sql_check(
        "latest_version_pointer",
        {
            "documents": {"document_id", "latest_version_id"},
            "document_versions": {"document_id", "version_id"},
        },
        """
        SELECT document.document_id, document.latest_version_id
        FROM documents AS document
        LEFT JOIN document_versions AS version
          ON version.version_id = document.latest_version_id
         AND version.document_id = document.document_id
        WHERE document.latest_version_id IS NOT NULL AND version.version_id IS NULL
        """,
    )
    add_sql_check(
        "published_version_pointer",
        {
            "documents": {"document_id", "published_version_id"},
            "document_versions": {"document_id", "version_id"},
        },
        """
        SELECT document.document_id, document.published_version_id
        FROM documents AS document
        LEFT JOIN document_versions AS version
          ON version.version_id = document.published_version_id
         AND version.document_id = document.document_id
        WHERE document.published_version_id IS NOT NULL AND version.version_id IS NULL
        """,
    )
    add_sql_check(
        "report_source_hash",
        {"report_sources": {"report_id", "trace_id", "source_hash_sha256"}},
        """
        SELECT report_id, trace_id, source_hash_sha256
        FROM report_sources
        WHERE source_hash_sha256 IS NULL
           OR length(source_hash_sha256) <> 64
           OR lower(source_hash_sha256) GLOB '*[^0-9a-f]*'
        """,
    )
    add_sql_check(
        "report_source_parent",
        {
            "reports": {"report_id"},
            "report_sources": {"report_id", "trace_id"},
        },
        """
        SELECT source.report_id, source.trace_id
        FROM report_sources AS source
        LEFT JOIN reports AS report ON report.report_id = source.report_id
        WHERE report.report_id IS NULL
        """,
    )
    for table, key in (
        ("document_mutation_receipts", "mutation_key"),
        ("report_mutation_receipts", "mutation_key"),
        ("server_sync_queue", "idempotency_key"),
    ):
        add_sql_check(
            f"{table}_{key}_unique",
            {table: {key}},
            f"""
            SELECT {quote_identifier(key)}, COUNT(*)
            FROM {quote_identifier(table)}
            WHERE {quote_identifier(key)} IS NOT NULL
            GROUP BY {quote_identifier(key)}
            HAVING COUNT(*) > 1
            """,
        )
    add_sql_check(
        "processed_message_cursor",
        {
            "server_notification_cursors": {
                "id",
                "server_scope",
                "user_id",
                "last_success_cursor",
            },
            "server_notification_messages": {
                "server_scope",
                "user_id",
                "message_id",
                "cursor",
            },
        },
        """
        SELECT message.server_scope, message.user_id, message.message_id, message.cursor
        FROM server_notification_messages AS message
        LEFT JOIN server_notification_cursors AS cursor
          ON cursor.server_scope = message.server_scope
         AND cursor.user_id = message.user_id
        WHERE cursor.id IS NULL OR message.cursor > cursor.last_success_cursor
        """,
    )
    return {
        "checks": checks,
        "applicable_count": sum(check["applicable"] for check in checks),
        "violation_count": sum(check["violation_count"] for check in checks),
    }


def database_evidence(database: Path) -> dict[str, Any]:
    if not database.is_file():
        raise ValueError(f"SQLite 파일이 없습니다: {database}")

    database_before = path_state(database)
    wal_path = Path(f"{database}-wal")
    shm_path = Path(f"{database}-shm")
    wal_before = path_state(wal_path)
    shm_before = path_state(shm_path)
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro", uri=True
    )
    try:
        connection.execute("PRAGMA query_only = ON")
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        quick_check = [row[0] for row in connection.execute("PRAGMA quick_check")]
        integrity_check = [
            row[0] for row in connection.execute("PRAGMA integrity_check")
        ]
        foreign_key_check_error = None
        try:
            foreign_key_check = [
                list(row) for row in connection.execute("PRAGMA foreign_key_check")
            ]
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
        fingerprints = {
            table: table_fingerprint(connection, table)
            for table in RESPONSIBILITY_TABLES
            if table in table_names
        }
        responsibility = responsibility_checks(connection, table_names)
    finally:
        connection.close()

    database_hash = sha256(database)
    database_after = path_state(database)
    wal_after = path_state(wal_path)
    shm_after = path_state(shm_path)
    capture_stable = (
        database_before == database_after
        and wal_before == wal_after
        and shm_before == shm_after
    )
    checkpoint_clean = not wal_after["exists"] or wal_after["bytes"] == 0
    return {
        "path_label": database.name,
        "bytes": database.stat().st_size,
        "sha256": database_hash,
        "journal_mode": journal_mode,
        "quick_check": quick_check,
        "integrity_check": integrity_check,
        "foreign_key_check": foreign_key_check,
        "foreign_key_check_error": foreign_key_check_error,
        "table_counts": counts,
        "responsibility_table_fingerprints": fingerprints,
        "responsibility_checks": responsibility,
        "quiescence": {
            "capture_stable": capture_stable,
            "checkpoint_clean": checkpoint_clean,
            "database_before": database_before,
            "database_after": database_after,
            "wal_before": wal_before,
            "wal_after": wal_after,
            "shm_before": shm_before,
            "shm_after": shm_after,
        },
    }


def file_evidence(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"파일 루트가 없습니다: {root}")

    before_paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda item: item.as_posix(),
    )
    before_states = {
        path.relative_to(root).as_posix(): path_state(path) for path in before_paths
    }
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

    after_paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda item: item.as_posix(),
    )
    after_states = {
        path.relative_to(root).as_posix(): path_state(path) for path in after_paths
    }
    return {
        "root_label": root.name,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
        "capture_stable": before_states == after_states,
    }


def referenced_file_checks(
    database: Path,
    file_set: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    files = {item["relative_path"]: item for item in file_set["files"]}
    references: list[dict[str, Any]] = []
    connection = sqlite3.connect(
        f"file:{database.resolve().as_posix()}?mode=ro", uri=True
    )
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if target == "server" and "file_objects" in tables:
            columns = table_columns(connection, "file_objects")
            if {"storage_key", "size_bytes", "hash_sha256"}.issubset(columns):
                references = [
                    {
                        "source": f"file_objects:{row[0]}",
                        "relative_path": str(row[0]).replace("\\", "/").lstrip("/"),
                        "expected_bytes": row[1],
                        "expected_sha256": row[2],
                    }
                    for row in connection.execute(
                        "SELECT storage_key, size_bytes, hash_sha256 FROM file_objects"
                    )
                ]
        elif target == "wpf":
            local_path_tables = (
                ("documents", "document_id", "local_path", None, None),
                ("document_versions", "id", "local_path", None, None),
                (
                    "field_comment_attachments",
                    "attachment_id",
                    "local_path",
                    "size_bytes",
                    "hash_sha256",
                ),
            )
            for table, id_column, path_column, size_column, hash_column in local_path_tables:
                if table not in tables:
                    continue
                columns = table_columns(connection, table)
                required = {id_column, path_column}
                if not required.issubset(columns):
                    continue
                selected = [id_column, path_column]
                selected.extend(
                    column
                    for column in (size_column, hash_column)
                    if column is not None
                )
                query = ", ".join(quote_identifier(column) for column in selected)
                for row in connection.execute(
                    f"SELECT {query} FROM {quote_identifier(table)} "
                    f"WHERE {quote_identifier(path_column)} IS NOT NULL "
                    f"AND trim({quote_identifier(path_column)}) <> ''"
                ):
                    raw_path = str(row[1]).replace("\\", "/")
                    marker = "/Files/"
                    relative_path = (
                        raw_path.split(marker, 1)[1]
                        if marker in raw_path
                        else (
                            raw_path[len("Files/") :]
                            if raw_path.startswith("Files/")
                            else raw_path.lstrip("./")
                        )
                    )
                    references.append(
                        {
                            "source": f"{table}:{row[0]}",
                            "relative_path": relative_path,
                            "expected_bytes": row[2] if size_column else None,
                            "expected_sha256": row[3] if hash_column else None,
                        }
                    )
    finally:
        connection.close()

    missing: list[str] = []
    size: list[str] = []
    digest: list[str] = []
    for reference in references:
        actual = files.get(reference["relative_path"])
        if actual is None:
            missing.append(reference["source"])
            continue
        if (
            reference["expected_bytes"] is not None
            and reference["expected_bytes"] != actual["bytes"]
        ):
            size.append(reference["source"])
        if (
            reference["expected_sha256"]
            and str(reference["expected_sha256"]).lower() != actual["sha256"].lower()
        ):
            digest.append(reference["source"])
    return {
        "applicable": bool(references),
        "reference_count": len(references),
        "missing_count": len(missing),
        "size_mismatch_count": len(size),
        "sha256_mismatch_count": len(digest),
        "mismatches": {"missing": missing, "size": size, "sha256": digest},
    }


def validate_run_id(value: str) -> str:
    if not value.startswith("PILOT-") or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in value
    ):
        raise argparse.ArgumentTypeError(
            "run_id는 PILOT- 접두사와 영문, 숫자, '-', '_'만 사용해야 합니다."
        )
    return value


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"기존 증거를 덮어쓸 수 없습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def capture(args: argparse.Namespace) -> int:
    database = database_evidence(args.database)
    file_set = file_evidence(args.files)
    host_identity = getattr(args, "host_identity", None) or local_host_identity()
    evidence = {
        "schema_version": 4,
        "run_id": args.run_id,
        "target": args.target,
        "phase": args.phase,
        "machine_id": args.machine_id,
        "host_identity": host_identity,
        "backup_set_id": args.backup_set_id,
        "restore_approval_id": args.restore_approval_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "file_set": file_set,
        "referenced_file_checks": referenced_file_checks(
            args.database, file_set, args.target
        ),
    }
    output = (
        args.evidence_root
        / args.run_id
        / "backup-restore"
        / f"{args.target}-{args.phase}.json"
    )
    write_evidence(output, evidence)

    integrity_ok = (
        evidence["database"]["quick_check"] == ["ok"]
        and evidence["database"]["integrity_check"] == ["ok"]
        and not evidence["database"]["foreign_key_check"]
        and evidence["database"]["foreign_key_check_error"] is None
        and evidence["database"]["quiescence"]["capture_stable"]
        and evidence["database"]["quiescence"]["checkpoint_clean"]
        and evidence["file_set"]["capture_stable"]
        and evidence["database"]["responsibility_checks"]["violation_count"] == 0
        and evidence["referenced_file_checks"]["missing_count"] == 0
        and evidence["referenced_file_checks"]["size_mismatch_count"] == 0
        and evidence["referenced_file_checks"]["sha256_mismatch_count"] == 0
    )
    print(f"증거 저장: {output}")
    print(f"DB quick_check: {evidence['database']['quick_check']}")
    print(f"DB integrity_check: {evidence['database']['integrity_check']}")
    print(f"foreign key 위반: {len(evidence['database']['foreign_key_check'])}건")
    if evidence["database"]["foreign_key_check_error"]:
        print(
            f"foreign key 검사 오류: {evidence['database']['foreign_key_check_error']}",
            file=sys.stderr,
        )
    print(f"파일: {evidence['file_set']['file_count']}건")
    print(
        "데이터 책임 교차 검사 위반: "
        f"{evidence['database']['responsibility_checks']['violation_count']}건"
    )
    print(
        "DB 참조 파일 불일치: "
        f"{sum(evidence['referenced_file_checks'][field] for field in ('missing_count', 'size_mismatch_count', 'sha256_mismatch_count'))}건"
    )
    print(
        "쓰기 정지 관찰: "
        f"{'정상' if evidence['database']['quiescence']['capture_stable'] and evidence['file_set']['capture_stable'] else '변경 감지'}"
    )
    print(
        "SQLite checkpoint 잔여: "
        f"{'없음' if evidence['database']['quiescence']['checkpoint_clean'] else 'WAL 잔여 있음'}"
    )
    return 0 if integrity_ok else 1


def compare(args: argparse.Namespace) -> int:
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    failures: list[str] = []

    for field in ("run_id", "target"):
        if before.get(field) != after.get(field):
            failures.append(
                f"{field} 불일치: {before.get(field)!r} != {after.get(field)!r}"
            )
    if before.get("phase") != "before" or after.get("phase") != "after":
        failures.append("비교 입력 phase는 before/after여야 합니다.")
    if not before.get("machine_id") or not after.get("machine_id"):
        failures.append("복구 전후 익명 machine_id가 모두 필요합니다.")
    elif (
        before["machine_id"].strip().casefold()
        == after["machine_id"].strip().casefold()
    ):
        failures.append("복구 대상은 원본과 다른 별도 PC여야 합니다.")
    before_host_identity = before.get("host_identity", {})
    after_host_identity = after.get("host_identity", {})
    before_host_sha256 = before_host_identity.get("sha256")
    after_host_sha256 = after_host_identity.get("sha256")
    if (
        not before_host_identity.get("source")
        or not after_host_identity.get("source")
        or not before_host_sha256
        or not after_host_sha256
    ):
        failures.append("복구 전후 OS 장비 식별값의 익명 hash가 모두 필요합니다.")
    elif before_host_sha256 == after_host_sha256:
        failures.append(
            "복구 전후 OS 장비 식별 hash가 같습니다. machine_id 문자열만 바꾼 로컬 복사는 별도 PC 증거가 아닙니다."
        )
    for field, label in (
        ("backup_set_id", "백업 세트"),
        ("restore_approval_id", "복구 승인"),
    ):
        if not before.get(field) or before.get(field) != after.get(field):
            failures.append(f"복구 전후 {label} ID가 없거나 다릅니다.")

    before_db = before["database"]
    after_db = after["database"]
    database_file_equal = (
        before_db["bytes"] == after_db["bytes"]
        and before_db["sha256"] == after_db["sha256"]
    )
    if before_db["quick_check"] != ["ok"]:
        failures.append(f"원천 DB quick_check 실패: {before_db['quick_check']!r}")
    if before_db.get("integrity_check") != ["ok"]:
        failures.append(
            f"원천 DB integrity_check 실패: {before_db.get('integrity_check')!r}"
        )
    if before_db["foreign_key_check"]:
        failures.append(
            f"원천 DB foreign key 위반 {len(before_db['foreign_key_check'])}건"
        )
    if before_db.get("foreign_key_check_error"):
        failures.append(
            f"원천 DB foreign key 검사 오류: {before_db['foreign_key_check_error']}"
        )
    if before_db["table_counts"] != after_db["table_counts"]:
        failures.append("SQLite 테이블별 원천 개수가 다릅니다.")
    before_fingerprints = before_db.get("responsibility_table_fingerprints", {})
    after_fingerprints = after_db.get("responsibility_table_fingerprints", {})
    fingerprint_tables = sorted(set(before_fingerprints) | set(after_fingerprints))
    fingerprint_mismatches = [
        table
        for table in fingerprint_tables
        if before_fingerprints.get(table) != after_fingerprints.get(table)
    ]
    if fingerprint_mismatches:
        failures.append(
            "공개 version 포인터·보고서 source hash·cursor·receipt 책임 원천이 다릅니다."
        )
    if after_db["quick_check"] != ["ok"]:
        failures.append(f"복구 DB quick_check 실패: {after_db['quick_check']!r}")
    if after_db.get("integrity_check") != ["ok"]:
        failures.append(
            f"복구 DB integrity_check 실패: {after_db.get('integrity_check')!r}"
        )
    if after_db["foreign_key_check"]:
        failures.append(
            f"복구 DB foreign key 위반 {len(after_db['foreign_key_check'])}건"
        )
    if after_db.get("foreign_key_check_error"):
        failures.append(
            f"복구 DB foreign key 검사 오류: {after_db['foreign_key_check_error']}"
        )
    for phase, database in (("원천", before_db), ("복구", after_db)):
        violation_count = database.get("responsibility_checks", {}).get(
            "violation_count"
        )
        if violation_count != 0:
            failures.append(f"{phase} 데이터 책임 교차 검사 위반 {violation_count!r}건")
    for phase, database, file_set in (
        ("원천", before_db, before["file_set"]),
        ("복구", after_db, after["file_set"]),
    ):
        quiescence = database.get("quiescence", {})
        if quiescence.get("capture_stable") is not True:
            failures.append(f"{phase} DB 증거 수집 중 쓰기 변경이 감지되었습니다.")
        if quiescence.get("checkpoint_clean") is not True:
            failures.append(f"{phase} DB에 checkpoint되지 않은 WAL이 남아 있습니다.")
        if file_set.get("capture_stable") is not True:
            failures.append(f"{phase} 파일 증거 수집 중 쓰기 변경이 감지되었습니다.")

    before_files = before["file_set"]
    after_files = after["file_set"]
    before_by_path = {item["relative_path"]: item for item in before_files["files"]}
    after_by_path = {item["relative_path"]: item for item in after_files["files"]}
    missing_paths = sorted(set(before_by_path) - set(after_by_path))
    extra_paths = sorted(set(after_by_path) - set(before_by_path))
    common_paths = sorted(set(before_by_path) & set(after_by_path))
    size_mismatches = [
        path
        for path in common_paths
        if before_by_path[path]["bytes"] != after_by_path[path]["bytes"]
    ]
    hash_mismatches = [
        path
        for path in common_paths
        if before_by_path[path]["sha256"] != after_by_path[path]["sha256"]
    ]
    before_counts = before_db["table_counts"]
    after_counts = after_db["table_counts"]
    table_names = sorted(set(before_counts) | set(after_counts))
    table_count_mismatches = [
        {
            "table": table,
            "before": before_counts.get(table),
            "after": after_counts.get(table),
        }
        for table in table_names
        if before_counts.get(table) != after_counts.get(table)
    ]
    if missing_paths or extra_paths or size_mismatches or hash_mismatches:
        failures.append("파일 상대경로·크기·SHA-256 목록이 다릅니다.")
    reference_check_failures: dict[str, dict[str, int]] = {}
    for phase, evidence in (("before", before), ("after", after)):
        checks = evidence.get("referenced_file_checks", {})
        counts = {
            field: checks.get(field, 0)
            for field in (
                "missing_count",
                "size_mismatch_count",
                "sha256_mismatch_count",
            )
        }
        reference_check_failures[phase] = counts
        if any(count != 0 for count in counts.values()):
            failures.append(f"{phase} DB 참조 파일 교차 검사가 실패했습니다.")

    report = {
        "schema_version": 4,
        "run_id": before.get("run_id"),
        "target": before.get("target"),
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "before_manifest": f"backup-restore/{args.before.name}",
        "after_manifest": f"backup-restore/{args.after.name}",
        "before_manifest_sha256": sha256(args.before),
        "after_manifest_sha256": sha256(args.after),
        "source_machine_id": before.get("machine_id"),
        "restore_machine_id": after.get("machine_id"),
        "source_host_identity": before_host_identity,
        "restore_host_identity": after_host_identity,
        "backup_set_id": before.get("backup_set_id"),
        "restore_approval_id": before.get("restore_approval_id"),
        "database_checks": {
            "database_file_equal": database_file_equal,
            "before_bytes": before_db["bytes"],
            "after_bytes": after_db["bytes"],
            "before_sha256": before_db["sha256"],
            "after_sha256": after_db["sha256"],
            "before_quick_check_ok": before_db["quick_check"] == ["ok"],
            "before_integrity_check_ok": before_db.get("integrity_check") == ["ok"],
            "before_foreign_key_violation_count": len(before_db["foreign_key_check"]),
            "after_quick_check_ok": after_db["quick_check"] == ["ok"],
            "after_integrity_check_ok": after_db.get("integrity_check") == ["ok"],
            "after_foreign_key_violation_count": len(after_db["foreign_key_check"]),
            "before_capture_stable": before_db.get("quiescence", {}).get(
                "capture_stable"
            )
            is True,
            "before_checkpoint_clean": before_db.get("quiescence", {}).get(
                "checkpoint_clean"
            )
            is True,
            "after_capture_stable": after_db.get("quiescence", {}).get(
                "capture_stable"
            )
            is True,
            "after_checkpoint_clean": after_db.get("quiescence", {}).get(
                "checkpoint_clean"
            )
            is True,
        },
        "file_capture_checks": {
            "before_capture_stable": before_files.get("capture_stable") is True,
            "after_capture_stable": after_files.get("capture_stable") is True,
        },
        "table_counts_equal": not table_count_mismatches,
        "table_count_mismatch_count": len(table_count_mismatches),
        "table_count_mismatches": table_count_mismatches,
        "responsibility_table_fingerprints_equal": not fingerprint_mismatches,
        "responsibility_table_fingerprint_mismatch_count": len(
            fingerprint_mismatches
        ),
        "responsibility_table_fingerprint_mismatches": fingerprint_mismatches,
        "responsibility_check_violation_counts": {
            "before": before_db.get("responsibility_checks", {}).get(
                "violation_count"
            ),
            "after": after_db.get("responsibility_checks", {}).get(
                "violation_count"
            ),
        },
        "referenced_file_check_mismatch_counts": reference_check_failures,
        "file_manifest_equal": not (
            missing_paths or extra_paths or size_mismatches or hash_mismatches
        ),
        "file_mismatch_counts": {
            "missing": len(missing_paths),
            "extra": len(extra_paths),
            "size": len(size_mismatches),
            "sha256": len(hash_mismatches),
        },
        "file_mismatches": {
            "missing": missing_paths,
            "extra": extra_paths,
            "size": size_mismatches,
            "sha256": hash_mismatches,
        },
    }
    output = args.output or args.after.with_name(
        f"{before.get('target', 'restore')}-comparison.json"
    )
    write_evidence(output, report)
    print(f"비교 결과: {report['result']}")
    print(f"증거 저장: {output}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 0 if not failures else 1


def compare_set(args: argparse.Namespace) -> int:
    server = json.loads(args.server.read_text(encoding="utf-8"))
    wpf = json.loads(args.wpf.read_text(encoding="utf-8"))
    failures: list[str] = []
    for report, target in ((server, "server"), (wpf, "wpf")):
        if report.get("target") != target:
            failures.append(f"{target} 비교 파일의 target이 올바르지 않습니다.")
        if report.get("result") != "PASS":
            failures.append(f"{target} 복구 비교가 PASS가 아닙니다.")
        database_checks = report.get("database_checks", {})
        file_capture_checks = report.get("file_capture_checks", {})
        if (
            report.get("table_counts_equal") is not True
            or report.get("table_count_mismatch_count") != 0
            or report.get("responsibility_table_fingerprints_equal") is not True
            or report.get("responsibility_table_fingerprint_mismatch_count") != 0
            or report.get("responsibility_check_violation_counts")
            != {"before": 0, "after": 0}
            or report.get("referenced_file_check_mismatch_counts")
            != {
                "before": {
                    "missing_count": 0,
                    "size_mismatch_count": 0,
                    "sha256_mismatch_count": 0,
                },
                "after": {
                    "missing_count": 0,
                    "size_mismatch_count": 0,
                    "sha256_mismatch_count": 0,
                },
            }
            or report.get("file_manifest_equal") is not True
            or report.get("file_mismatch_counts")
            != {"missing": 0, "extra": 0, "size": 0, "sha256": 0}
            or not report.get("source_host_identity", {}).get("sha256")
            or not report.get("restore_host_identity", {}).get("sha256")
            or report.get("source_host_identity", {}).get("sha256")
            == report.get("restore_host_identity", {}).get("sha256")
            or any(
                database_checks.get(field) is not True
                for field in (
                    "before_quick_check_ok",
                    "before_integrity_check_ok",
                    "after_quick_check_ok",
                    "after_integrity_check_ok",
                    "before_capture_stable",
                    "before_checkpoint_clean",
                    "after_capture_stable",
                    "after_checkpoint_clean",
                )
            )
            or database_checks.get("before_foreign_key_violation_count") != 0
            or database_checks.get("after_foreign_key_violation_count") != 0
            or file_capture_checks.get("before_capture_stable") is not True
            or file_capture_checks.get("after_capture_stable") is not True
        ):
            failures.append(f"{target} 비교의 DB·파일 0건 조건이 완전하지 않습니다.")
    for field, label in (
        ("run_id", "run ID"),
        ("backup_set_id", "백업 세트 ID"),
        ("restore_approval_id", "복구 승인 ID"),
    ):
        if not server.get(field) or server.get(field) != wpf.get(field):
            failures.append(f"server와 wpf의 {label}가 없거나 다릅니다.")

    report = {
        "schema_version": 1,
        "run_id": server.get("run_id"),
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "backup_set_id": server.get("backup_set_id"),
        "restore_approval_id": server.get("restore_approval_id"),
        "server_comparison": args.server.name,
        "server_comparison_sha256": sha256(args.server),
        "wpf_comparison": args.wpf.name,
        "wpf_comparison_sha256": sha256(args.wpf),
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = args.output or args.server.with_name("restore-set-comparison.json")
    write_evidence(output, report)
    print(f"통합 비교 결과: {report['result']}")
    print(f"증거 저장: {output}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 0 if not failures else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="FlowNote 파일럿 백업·복구 무결성 증거 도구"
    )
    commands = result.add_subparsers(dest="command", required=True)

    capture_parser = commands.add_parser(
        "capture", help="복구 전/후 DB와 파일 증거를 수집합니다."
    )
    capture_parser.add_argument("--run-id", required=True, type=validate_run_id)
    capture_parser.add_argument("--target", required=True, choices=("server", "wpf"))
    capture_parser.add_argument("--phase", required=True, choices=("before", "after"))
    capture_parser.add_argument("--database", required=True, type=Path)
    capture_parser.add_argument("--files", required=True, type=Path)
    capture_parser.add_argument("--machine-id", required=True)
    capture_parser.add_argument("--backup-set-id", required=True)
    capture_parser.add_argument("--restore-approval-id", required=True)
    capture_parser.add_argument("--evidence-root", required=True, type=Path)
    capture_parser.set_defaults(handler=capture)

    compare_parser = commands.add_parser(
        "compare", help="복구 전/후 증거를 비교합니다."
    )
    compare_parser.add_argument("--before", required=True, type=Path)
    compare_parser.add_argument("--after", required=True, type=Path)
    compare_parser.add_argument("--output", type=Path)
    compare_parser.set_defaults(handler=compare)

    set_parser = commands.add_parser(
        "compare-set",
        help="server와 wpf 비교가 같은 백업 세트·복구 승인에 속하는지 검증합니다.",
    )
    set_parser.add_argument("--server", required=True, type=Path)
    set_parser.add_argument("--wpf", required=True, type=Path)
    set_parser.add_argument("--output", type=Path)
    set_parser.set_defaults(handler=compare_set)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        sqlite3.Error,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
