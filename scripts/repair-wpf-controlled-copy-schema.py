#!/usr/bin/env python3
"""Preserve and remove a server-only controlled-copy table from a WPF SQLite DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIGRATION_ID = "20260720_preserve_server_controlled_copy_grants"
SOURCE_TABLE = "controlled_copy_grants"
ARCHIVE_TABLE = "preserved_server_controlled_copy_grants"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})")]


def row_digest(connection: sqlite3.Connection, table: str) -> str:
    columns = table_columns(connection, table)
    return selected_row_digest(connection, table, columns)


def selected_row_digest(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str],
    *,
    where_sql: str = "",
    parameters: tuple[Any, ...] = (),
) -> str:
    digest = hashlib.sha256()
    if not columns:
        return digest.hexdigest()
    select_columns = ", ".join(quote_identifier(column) for column in columns)
    order_column = "id" if "id" in columns else columns[0]
    for row in connection.execute(
        f"SELECT {select_columns} FROM {quote_identifier(table)} "
        f"{where_sql} ORDER BY {quote_identifier(order_column)}",
        parameters,
    ):
        payload = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), default=str)
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def foreign_key_evidence(connection: sqlite3.Connection) -> tuple[list[list[Any]], str | None]:
    try:
        return [list(row) for row in connection.execute("PRAGMA foreign_key_check")], None
    except sqlite3.Error as error:
        return [], str(error)


def capture_evidence(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        quick_check = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_key_check, foreign_key_check_error = foreign_key_evidence(connection)
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        schemas = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        }
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {quote_identifier(table)}"
            ).fetchone()[0]
            for table in tables
        }
        foreign_keys = {
            table: [
                list(row)
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({quote_identifier(table)})"
                )
            ]
            for table in tables
        }
        protected_digests = {
            table: row_digest(connection, table)
            for table in ("document_versions", "document_access_logs", SOURCE_TABLE, ARCHIVE_TABLE)
            if table in tables
        }
    finally:
        connection.close()

    return {
        "captured_at_utc": utc_now(),
        "database_bytes": database.stat().st_size,
        "database_sha256": sha256_file(database),
        "quick_check": quick_check,
        "foreign_key_check": foreign_key_check,
        "foreign_key_check_error": foreign_key_check_error,
        "table_counts": counts,
        "table_schemas": schemas,
        "table_foreign_keys": foreign_keys,
        "protected_row_digests": protected_digests,
    }


def assert_wpf_database(connection: sqlite3.Connection) -> None:
    document_versions = set(table_columns(connection, "document_versions"))
    documents = set(table_columns(connection, "documents"))
    if not (
        "version_no" in document_versions
        and "file_name" in document_versions
        and "version_id" not in document_versions
        and "folder_id" in documents
    ):
        raise ValueError("대상 DB가 WPF 로컬 document/document_versions schema와 일치하지 않습니다.")


def preserve_and_remove_server_table(database: Path, run_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        assert_wpf_database(connection)
        if not table_exists(connection, SOURCE_TABLE):
            return {"status": "ALREADY_REPAIRED", "source_rows": 0, "archived_rows": 0}

        source_columns = table_columns(connection, SOURCE_TABLE)
        expected_columns = {
            "id", "grant_id", "token_hash", "document_id", "document_version_id",
            "user_id", "session_id", "device_id", "expected_hash_sha256",
            "expected_size_bytes", "status", "expires_at", "consumed_at",
            "failure_reason", "created_at",
        }
        if not expected_columns.issubset(source_columns):
            raise ValueError(f"예상하지 못한 {SOURCE_TABLE} schema입니다: {source_columns}")

        source_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (SOURCE_TABLE,)
        ).fetchone()[0]
        source_rows = connection.execute(f"SELECT COUNT(*) FROM {SOURCE_TABLE}").fetchone()[0]
        source_digest = row_digest(connection, SOURCE_TABLE)
        document_version_rows = connection.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
        document_version_digest = row_digest(connection, "document_versions")
        access_log_rows = (
            connection.execute("SELECT COUNT(*) FROM document_access_logs").fetchone()[0]
            if table_exists(connection, "document_access_logs") else 0
        )
        access_log_digest = (
            row_digest(connection, "document_access_logs")
            if table_exists(connection, "document_access_logs") else hashlib.sha256().hexdigest()
        )
        preserved_at = utc_now()

        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {ARCHIVE_TABLE} AS "
                f"SELECT *, CAST(NULL AS TEXT) AS preserved_at_utc, "
                f"CAST(NULL AS TEXT) AS source_run_id FROM {SOURCE_TABLE} WHERE 0"
            )
            archive_columns = set(table_columns(connection, ARCHIVE_TABLE))
            if not set(source_columns).issubset(archive_columns):
                raise ValueError(f"기존 {ARCHIVE_TABLE} schema가 원천 열을 보존할 수 없습니다.")
            column_sql = ", ".join(quote_identifier(column) for column in source_columns)
            connection.execute(
                f"INSERT INTO {ARCHIVE_TABLE} ({column_sql}, preserved_at_utc, source_run_id) "
                f"SELECT {column_sql}, ?, ? FROM {SOURCE_TABLE}",
                (preserved_at, run_id),
            )
            archived_rows = connection.execute(
                f"SELECT COUNT(*) FROM {ARCHIVE_TABLE} WHERE source_run_id=?", (run_id,)
            ).fetchone()[0]
            if archived_rows != source_rows:
                raise RuntimeError(
                    f"controlled copy 보존 행 수 불일치: source={source_rows}, archive={archived_rows}"
                )
            archived_digest = selected_row_digest(
                connection,
                ARCHIVE_TABLE,
                source_columns,
                where_sql="WHERE source_run_id=?",
                parameters=(run_id,),
            )
            if archived_digest != source_digest:
                raise RuntimeError(
                    "controlled copy 보존 행 hash가 원천과 일치하지 않습니다."
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS local_schema_migration_audit (
                    migration_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    applied_at_utc TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    archive_table TEXT NOT NULL,
                    source_schema_sql TEXT NOT NULL,
                    source_row_count INTEGER NOT NULL,
                    source_row_sha256 TEXT NOT NULL,
                    document_version_row_count INTEGER NOT NULL,
                    document_version_row_sha256 TEXT NOT NULL,
                    document_access_log_row_count INTEGER NOT NULL,
                    document_access_log_row_sha256 TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO local_schema_migration_audit (
                    migration_id, run_id, applied_at_utc, source_table, archive_table,
                    source_schema_sql, source_row_count, source_row_sha256,
                    document_version_row_count, document_version_row_sha256,
                    document_access_log_row_count, document_access_log_row_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    MIGRATION_ID, run_id, preserved_at, SOURCE_TABLE, ARCHIVE_TABLE,
                    source_schema, source_rows, source_digest,
                    document_version_rows, document_version_digest,
                    access_log_rows, access_log_digest,
                ),
            )
            connection.execute(f"DROP TABLE {SOURCE_TABLE}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys=ON")

        if row_digest(connection, "document_versions") != document_version_digest:
            raise RuntimeError("document_versions 원천 hash가 migration 중 변경되었습니다.")
        if table_exists(connection, "document_access_logs") and row_digest(
            connection, "document_access_logs"
        ) != access_log_digest:
            raise RuntimeError("controlled copy 감사 원천 hash가 migration 중 변경되었습니다.")
        return {
            "status": "MIGRATED",
            "source_rows": source_rows,
            "archived_rows": archived_rows,
            "source_row_sha256": source_digest,
            "document_version_rows": document_version_rows,
            "document_version_row_sha256": document_version_digest,
            "document_access_log_rows": access_log_rows,
            "document_access_log_row_sha256": access_log_digest,
        }
    finally:
        connection.close()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WPF 공통 DB controlled copy FK 보존 복구")
    parser.add_argument("--database", type=Path, default=Path("data/local/flownote.local.sqlite"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evidence-root", type=Path, default=Path("data/local/wpf-schema-repair"))
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = args.database.resolve()
    if not database.is_file():
        print(f"ERROR: SQLite DB가 없습니다: {database}", file=sys.stderr)
        return 2
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.run_id):
        print("ERROR: run_id에는 영문, 숫자, '.', '_', '-'만 사용할 수 있습니다.", file=sys.stderr)
        return 2

    run_directory = args.evidence_root.resolve() / args.run_id
    if run_directory.exists() and any(run_directory.iterdir()):
        print(f"ERROR: 보존 증거 경로가 비어 있지 않습니다: {run_directory}", file=sys.stderr)
        return 2
    run_directory.mkdir(parents=True, exist_ok=True)

    before = capture_evidence(database)
    before["run_id"] = args.run_id
    before["phase"] = "before"
    write_json(run_directory / "before-evidence.json", before)

    if args.check_only:
        healthy = (
            before["quick_check"] == ["ok"]
            and not before["foreign_key_check"]
            and before["foreign_key_check_error"] is None
        )
        summary = {"run_id": args.run_id, "status": "PASSED" if healthy else "FAILED", "check_only": True}
        write_json(run_directory / "repair-summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if healthy else 1

    backup = run_directory / "flownote.local.before.sqlite"
    source_connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    backup_connection = sqlite3.connect(backup)
    try:
        source_connection.backup(backup_connection)
    finally:
        backup_connection.close()
        source_connection.close()
    if capture_evidence(backup)["protected_row_digests"] != before["protected_row_digests"]:
        raise RuntimeError("migration 전 SQLite backup의 보호 대상 row hash가 원천과 다릅니다.")

    migration = preserve_and_remove_server_table(database, args.run_id)
    after = capture_evidence(database)
    after["run_id"] = args.run_id
    after["phase"] = "after"
    write_json(run_directory / "after-evidence.json", after)

    healthy = (
        after["quick_check"] == ["ok"]
        and not after["foreign_key_check"]
        and after["foreign_key_check_error"] is None
    )
    protected = (
        before["protected_row_digests"].get("document_versions")
        == after["protected_row_digests"].get("document_versions")
        and before["protected_row_digests"].get("document_access_logs")
        == after["protected_row_digests"].get("document_access_logs")
    )
    summary = {
        "run_id": args.run_id,
        "migration_id": MIGRATION_ID,
        "status": "PASSED" if healthy and protected else "FAILED",
        "check_only": False,
        "database": str(database),
        "backup": str(backup),
        "migration": migration,
        "quick_check": after["quick_check"],
        "foreign_key_violations": len(after["foreign_key_check"]),
        "foreign_key_check_error": after["foreign_key_check_error"],
        "protected_row_hashes_equal": protected,
        "before_database_sha256": before["database_sha256"],
        "after_database_sha256": after["database_sha256"],
    }
    write_json(run_directory / "repair-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
