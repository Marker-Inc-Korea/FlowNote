from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def query_rows(connection: sqlite3.Connection, sql: str) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(sql)]


def canonical_hash(rows: list[dict[str, object]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_bytes(payload.encode("utf-8"))


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def inspect_database(path: Path, kind: str) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = query_rows(connection, "PRAGMA foreign_key_check")
        result: dict[str, object] = {
            "path": str(path),
            "database_sha256": sha256_bytes(path.read_bytes()),
            "integrity_check": integrity,
            "foreign_key_violations": foreign_keys,
        }
        if kind == "wpf":
            queue_rows = query_rows(connection, "SELECT * FROM server_sync_queue ORDER BY id")
            result["queue_status_counts"] = query_rows(
                connection,
                "SELECT status, COUNT(*) AS count FROM server_sync_queue GROUP BY status ORDER BY status",
            )
            result["queue_canonical_sha256"] = canonical_hash(queue_rows)
            result["queue_idempotency_duplicates"] = query_rows(
                connection,
                "SELECT idempotency_key, COUNT(*) AS count FROM server_sync_queue "
                "GROUP BY idempotency_key HAVING COUNT(*) > 1 ORDER BY idempotency_key",
            )
            file_rows = query_rows(
                connection,
                "SELECT local_path FROM field_comment_attachments UNION SELECT local_path FROM document_versions",
            )
            result["source_file_paths_count"] = len(file_rows)
            result["source_file_path_set_sha256"] = canonical_hash(file_rows)
        else:
            field_comment_sources = query_rows(
                connection,
                "SELECT rs.source_hash_sha256, fc.* FROM report_sources rs JOIN field_comments fc ON "
                "rs.source_type = 'FIELD_COMMENT' AND rs.source_id = fc.comment_id ORDER BY rs.id",
            )
            mismatch_count = 0
            for row in field_comment_sources:
                created_at = row["created_at"]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).isoformat()
                snapshot = {
                    "comment_id": row["comment_id"],
                    "document_id": row["document_id"],
                    "document_version_id": row["document_version_id"],
                    "structure_item_id": row["structure_item_id"],
                    "work_record_id": row["work_record_id"],
                    "comment_type": row["comment_type"],
                    "input_mode": row["input_mode"],
                    "signal_level": row["signal_level"],
                    "template_id": row["template_id"],
                    "raw_content": row["raw_content"],
                    "author_id": row["author_id"],
                    "reported_by": row["reported_by"],
                    "operator_id": row["operator_id"],
                    "entry_source": row["entry_source"],
                    "device_id": row["device_id"],
                    "location_code": row["location_code"],
                    "created_at": created_at,
                }
                canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if sha256_bytes(canonical.encode("utf-8")) != row["source_hash_sha256"]:
                    mismatch_count += 1
            result["field_comment_source_hash_mismatch_count"] = mismatch_count
            result["report_source_orphan_count"] = connection.execute(
                "SELECT COUNT(*) FROM report_sources rs LEFT JOIN reports r ON r.report_id = rs.report_id "
                "WHERE r.report_id IS NULL"
            ).fetchone()[0]
            duplicate_tables = [
                table for table in (
                    "field_comments",
                    "field_comment_attachments",
                    "field_comment_review_mutation_receipts",
                    "reports",
                    "report_mutation_receipts",
                ) if table_exists(connection, table)
            ]
            result["idempotency_duplicate_count"] = sum(
                connection.execute(
                    f"SELECT COUNT(*) FROM (SELECT {column}, COUNT(*) FROM {table} "
                    f"WHERE {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*) > 1)",
                ).fetchone()[0]
                for table, column in (
                    (table, "mutation_key" if "receipt" in table else "idempotency_key")
                    for table in duplicate_tables
                )
            )
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-db", type=Path, required=True)
    parser.add_argument("--wpf-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    preservation = {}
    for kind, source in (("api", args.api_db), ("wpf", args.wpf_db)):
        before = inspect_database(source, kind)
        target = args.output_dir / f"{args.run_id}-{kind}.sqlite"
        shutil.copy2(source, target)
        after = inspect_database(target, kind)
        snapshots[kind] = after
        preservation[kind] = {
            "database_sha256_equal": before["database_sha256"] == after["database_sha256"],
            "integrity_equal": before["integrity_check"] == after["integrity_check"],
        }
        if kind == "api":
            preservation[kind]["field_comment_source_hash_change_count"] = abs(
                int(before["field_comment_source_hash_mismatch_count"])
                - int(after["field_comment_source_hash_mismatch_count"])
            )
            preservation[kind]["report_source_orphan_change_count"] = abs(
                int(before["report_source_orphan_count"]) - int(after["report_source_orphan_count"])
            )
        else:
            preservation[kind]["queue_status_counts_equal"] = (
                before["queue_status_counts"] == after["queue_status_counts"]
            )
            preservation[kind]["queue_canonical_sha256_equal"] = (
                before["queue_canonical_sha256"] == after["queue_canonical_sha256"]
            )
            preservation[kind]["source_file_path_set_sha256_equal"] = (
                before["source_file_path_set_sha256"] == after["source_file_path_set_sha256"]
            )
    evidence = {
        "run_id": args.run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
        "preservation_comparison": preservation,
    }
    output = args.output_dir / f"{args.run_id}-integrity.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
