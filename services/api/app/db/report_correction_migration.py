from sqlalchemy import text

from app.db.session import Database


def ensure_report_correction_schema(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    additions = {
        "reports": {
            "report_family_id": "VARCHAR(64)",
            "replaces_report_id": "VARCHAR(64)",
            "replaces_report_revision": "INTEGER",
            "correction_reason": "TEXT",
            "superseded_by_report_id": "VARCHAR(64)",
            "superseded_at": "DATETIME",
        },
        "report_mutation_receipts": {
            "report_family_id": "VARCHAR(64)",
            "replaces_report_id": "VARCHAR(64)",
            "replaces_report_revision": "INTEGER",
        },
        "audit_event_envelopes": {
            "related_target_type": "VARCHAR(50)",
            "related_target_id": "VARCHAR(64)",
            "related_target_revision": "INTEGER",
        },
    }
    with database.engine.begin() as connection:
        for table_name, columns in additions.items():
            existing = {
                row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            if not existing:
                continue
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
                    )
        connection.execute(
            text("UPDATE reports SET report_family_id = report_id WHERE report_family_id IS NULL")
        )
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reports_report_family_id ON reports (report_family_id)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_reports_replaces_report_id "
            "ON reports (replaces_report_id) WHERE replaces_report_id IS NOT NULL"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_reports_superseded_by_report_id "
            "ON reports (superseded_by_report_id) WHERE superseded_by_report_id IS NOT NULL"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_report_receipts_family "
            "ON report_mutation_receipts (report_family_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_audit_event_related_target "
            "ON audit_event_envelopes (related_target_id)"
        ))
