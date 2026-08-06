using FlowNote.Windows.Core.Auth;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Storage;

public sealed partial class FlowNoteLocalDatabase
{
    public void Initialize()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(DatabasePath)!);
        Directory.CreateDirectory(Path.Combine(DefaultDataDirectory, LocalFilesDirectoryName));

        using var connection = OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS user_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                login_id TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                group_id TEXT NULL,
                supervisor_user_id TEXT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL UNIQUE,
                group_code TEXT NOT NULL UNIQUE,
                group_name TEXT NOT NULL,
                group_type TEXT NOT NULL,
                leader_user_id TEXT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id TEXT NOT NULL UNIQUE,
                parent_id INTEGER NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL UNIQUE,
                folder_id INTEGER NOT NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL,
                document_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                local_path TEXT NULL,
                version_no INTEGER NOT NULL DEFAULT 1,
                published_version_no INTEGER NULL,
                latest_comment TEXT NULL,
                server_report_id TEXT NULL,
                server_report_revision INTEGER NULL,
                server_report_content_hash_sha256 TEXT NULL,
                server_report_source_set_hash_sha256 TEXT NULL,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_revision INTEGER NULL,
                server_published_version_id TEXT NULL,
                server_tags_json TEXT NULL,
                synced_at TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS document_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                version_no INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                local_path TEXT NULL,
                comment TEXT NULL,
                version_status TEXT NOT NULL DEFAULT 'WORKING',
                is_latest INTEGER NOT NULL DEFAULT 0,
                is_published INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS field_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id TEXT NOT NULL UNIQUE,
                document_id TEXT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                document_version_no INTEGER NULL,
                comment_type TEXT NOT NULL,
                input_mode TEXT NOT NULL,
                signal_level TEXT NULL,
                raw_content TEXT NOT NULL,
                normalized_content TEXT NULL,
                analysis_content TEXT NULL,
                author_name TEXT NOT NULL,
                reported_by TEXT NULL,
                operator_name TEXT NULL,
                entry_source TEXT NOT NULL,
                device_id TEXT NULL,
                location_code TEXT NULL,
                assigned_to TEXT NULL,
                review_due_at TEXT NULL,
                last_transition_reason TEXT NULL,
                conflict_flag INTEGER NOT NULL DEFAULT 0,
                conflict_basis TEXT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                synced_at TEXT NULL,
                review_revision INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS ix_field_comments_document_created
                ON field_comments (document_id, created_at);

            CREATE TABLE IF NOT EXISTS field_comment_saved_views (
                name TEXT PRIMARY KEY,
                filter_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS field_comment_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attachment_id TEXT NOT NULL UNIQUE,
                comment_id TEXT NOT NULL REFERENCES field_comments(comment_id) ON DELETE CASCADE,
                local_path TEXT NOT NULL,
                original_file_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                content_type TEXT NULL,
                size_bytes INTEGER NOT NULL,
                hash_sha256 TEXT NOT NULL,
                attachment_type TEXT NOT NULL,
                caption TEXT NULL,
                captured_at TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                server_attachment_id TEXT NULL,
                synced_at TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_field_comment_attachments_comment
                ON field_comment_attachments (comment_id, created_at);

            CREATE TABLE IF NOT EXISTS document_view_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                version_no INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                view_started_at TEXT NOT NULL,
                closed_at TEXT NULL,
                close_reason TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_document_view_logs_document_started
                ON document_view_logs (document_id, view_started_at);

            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NULL,
                target_title TEXT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_activity_history_created
                ON activity_history (created_at, id);

            CREATE INDEX IF NOT EXISTS ix_activity_history_target
                ON activity_history (target_type, target_id);

            CREATE TABLE IF NOT EXISTS file_watch_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL UNIQUE,
                source_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                last_write_time_utc TEXT NOT NULL,
                status TEXT NOT NULL,
                document_id TEXT NULL REFERENCES documents(document_id) ON DELETE SET NULL,
                detected_by TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                version_label TEXT NULL,
                change_reason TEXT NULL,
                resolved_by TEXT NULL,
                resolved_at TEXT NULL,
                UNIQUE(source_path, status)
            );

            CREATE INDEX IF NOT EXISTS ix_file_watch_candidates_status
                ON file_watch_candidates (status, detected_at);

            CREATE INDEX IF NOT EXISTS ix_file_watch_candidates_document
                ON file_watch_candidates (document_id, status);

            CREATE TABLE IF NOT EXISTS tag_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_id TEXT NOT NULL UNIQUE,
                tag_type TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_tag_id TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(tag_type, code)
            );

            CREATE TABLE IF NOT EXISTS document_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES tag_definitions(tag_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, tag_id)
            );

            CREATE INDEX IF NOT EXISTS ix_document_tags_document
                ON document_tags (document_id);

            CREATE INDEX IF NOT EXISTS ix_document_tags_tag
                ON document_tags (tag_id);

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT NOT NULL UNIQUE,
                notification_type TEXT NOT NULL DEFAULT 'document',
                recipient_name TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_title TEXT NOT NULL,
                target_type TEXT NULL,
                target_id TEXT NULL,
                target_title TEXT NULL,
                source_candidate_id TEXT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS server_notification_cursors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_scope TEXT NOT NULL,
                user_id TEXT NOT NULL,
                last_success_cursor INTEGER NOT NULL DEFAULT 0,
                observed_server_cursor INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                initial_sync_completed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                reset_confirmed_by TEXT NULL,
                reset_confirmed_at TEXT NULL,
                UNIQUE(server_scope, user_id),
                CHECK(last_success_cursor >= 0),
                CHECK(observed_server_cursor >= 0),
                CHECK(status IN ('ACTIVE', 'RESET_REQUIRED'))
            );

            CREATE TABLE IF NOT EXISTS server_notification_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_scope TEXT NOT NULL,
                user_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                cursor INTEGER NOT NULL,
                processed_at TEXT NOT NULL,
                UNIQUE(server_scope, user_id, message_id),
                CHECK(cursor >= 0)
            );

            CREATE INDEX IF NOT EXISTS ix_server_notification_messages_scope_cursor
                ON server_notification_messages (server_scope, user_id, cursor);

            CREATE TABLE IF NOT EXISTS server_bindings (
                server_scope TEXT PRIMARY KEY,
                server_instance_id TEXT NOT NULL,
                server_epoch INTEGER NOT NULL,
                schema_contract INTEGER NOT NULL,
                api_contract_min INTEGER NOT NULL,
                api_contract_max INTEGER NOT NULL,
                status TEXT NOT NULL,
                observed_server_instance_id TEXT NULL,
                observed_server_epoch INTEGER NULL,
                block_reason TEXT NULL,
                updated_at TEXT NOT NULL,
                approved_by TEXT NULL,
                approved_at TEXT NULL,
                restore_pilot_run_id TEXT NULL,
                restore_backup_set_id TEXT NULL,
                restore_approval_id TEXT NULL,
                restore_responsible_owner TEXT NULL,
                restore_fault_code TEXT NULL,
                convergence_status TEXT NOT NULL DEFAULT 'NORMAL_OPERATION',
                CHECK(server_epoch >= 1),
                CHECK(status IN ('ACTIVE', 'RECONCILIATION_REQUIRED'))
            );

            CREATE TABLE IF NOT EXISTS reconciliation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                server_scope TEXT NOT NULL,
                previous_server_instance_id TEXT NULL,
                previous_server_epoch INTEGER NULL,
                server_instance_id TEXT NOT NULL,
                server_epoch INTEGER NOT NULL,
                trigger_reason TEXT NOT NULL,
                status TEXT NOT NULL,
                client_cursor INTEGER NOT NULL,
                server_cursor INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                approval_reason TEXT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT NULL,
                CHECK(status IN ('REVIEW_REQUIRED', 'APPLIED', 'FAILED'))
            );

            CREATE TABLE IF NOT EXISTS reconciliation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL REFERENCES reconciliation_runs(run_id),
                client_item_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                local_id TEXT NOT NULL,
                local_version_no INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT NOT NULL,
                local_hash_sha256 TEXT NULL,
                verdict TEXT NOT NULL,
                proposed_action TEXT NOT NULL,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_revision INTEGER NULL,
                server_hash_sha256 TEXT NULL,
                details TEXT NULL,
                resolution_action TEXT NULL,
                resolution_status TEXT NULL,
                resolution_reason TEXT NULL,
                resolved_by TEXT NULL,
                resolved_at TEXT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, client_item_id),
                CHECK(verdict IN ('CONFIRMED', 'ABSENT', 'DIVERGED')),
                CHECK(proposed_action IN ('REBOUND', 'REQUEUE', 'CONFLICT'))
            );

            CREATE INDEX IF NOT EXISTS ix_reconciliation_items_run
                ON reconciliation_items (run_id, id);

            CREATE TABLE IF NOT EXISTS work_sequence_boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NULL,
                line_code TEXT NULL,
                board_date TEXT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_boards_updated
                ON work_sequence_boards (updated_at, id);

            CREATE TABLE IF NOT EXISTS work_sequence_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NULL,
                work_order_no TEXT NULL,
                document_id TEXT NULL,
                status TEXT NOT NULL,
                hold_reason TEXT NULL,
                sort_order INTEGER NOT NULL,
                assigned_to TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(board_id, sort_order)
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_items_board_order
                ON work_sequence_items (board_id, sort_order);

            CREATE TABLE IF NOT EXISTS work_sequence_change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                item_id TEXT NULL REFERENCES work_sequence_items(item_id) ON DELETE SET NULL,
                change_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                before_value TEXT NULL,
                after_value TEXT NULL,
                change_reason TEXT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_history_board_created
                ON work_sequence_change_history (board_id, created_at);

            CREATE TABLE IF NOT EXISTS work_sequence_notification_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                item_id TEXT NULL REFERENCES work_sequence_items(item_id) ON DELETE SET NULL,
                event_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                recipient_name TEXT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                notification_id TEXT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_notify_board_created
                ON work_sequence_notification_candidates (board_id, created_at);

            CREATE TABLE IF NOT EXISTS server_sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_id TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                local_document_id TEXT NULL,
                local_version_no INTEGER NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NULL,
                created_at TEXT NOT NULL,
                last_attempt_at TEXT NULL,
                synced_at TEXT NULL,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_report_id TEXT NULL,
                server_comment_id TEXT NULL,
                server_attachment_id TEXT NULL,
                server_log_id TEXT NULL
                ,base_server_revision INTEGER NULL
                ,expected_server_version_id TEXT NULL
                ,expected_published_version_id TEXT NULL
                ,local_file_hash_sha256 TEXT NULL
                ,conflict_code TEXT NULL
                ,conflict_details TEXT NULL
                ,resolution_action TEXT NULL
                ,resolution_reason TEXT NULL
                ,resolved_by TEXT NULL
                ,resolved_at TEXT NULL
                ,base_domain_revision INTEGER NULL
                ,intent_hash TEXT NULL
                ,source_set_hash TEXT NULL
                ,payload_json TEXT NULL
                ,server_conflict_hash_sha256 TEXT NULL
                ,base_snapshot_hash_sha256 TEXT NULL
                ,server_read_back_json TEXT NULL
                ,allowed_actions_json TEXT NULL
                ,source_preserved_path TEXT NULL
                ,retry_not_before TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_server_sync_queue_status
                ON server_sync_queue (status, id);

            CREATE TABLE IF NOT EXISTS server_id_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                local_id TEXT NOT NULL,
                local_version_no INTEGER NOT NULL DEFAULT 0,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_report_id TEXT NULL,
                server_comment_id TEXT NULL,
                server_attachment_id TEXT NULL,
                server_log_id TEXT NULL,
                server_revision INTEGER NULL,
                server_file_hash_sha256 TEXT NULL,
                server_published_version_id TEXT NULL,
                synced_at TEXT NOT NULL,
                UNIQUE(entity_type, local_id, local_version_no)
            );

            CREATE TABLE IF NOT EXISTS report_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_report_document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                source_type TEXT NOT NULL,
                local_source_id TEXT NOT NULL,
                source_version_id TEXT NULL,
                trace_id TEXT NULL,
                source_hash_sha256 TEXT NULL,
                source_revision INTEGER NULL,
                snapshot_verified INTEGER NOT NULL DEFAULT 0,
                relation_type TEXT NULL,
                title TEXT NULL,
                detail TEXT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_report_sources_local_report
                ON report_sources (local_report_document_id, id);

            CREATE UNIQUE INDEX IF NOT EXISTS ux_report_sources_local_source
                ON report_sources (local_report_document_id, source_type, local_source_id, COALESCE(source_version_id, ''));
            """;
        command.ExecuteNonQuery();
        EnsureColumn(connection, "user_accounts", "group_id", "TEXT NULL");
        EnsureColumn(connection, "user_accounts", "supervisor_user_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "updated_at", "TEXT NULL");
        EnsureColumn(connection, "documents", "local_path", "TEXT NULL");
        EnsureColumn(connection, "documents", "version_no", "INTEGER NOT NULL DEFAULT 1");
        EnsureColumn(connection, "documents", "published_version_no", "INTEGER NULL");
        EnsureColumn(connection, "documents", "latest_comment", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_report_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_report_revision", "INTEGER NULL");
        EnsureColumn(connection, "documents", "server_report_content_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_report_source_set_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_document_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_version_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_revision", "INTEGER NULL");
        EnsureColumn(connection, "documents", "server_published_version_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_tags_json", "TEXT NULL");
        EnsureColumn(connection, "documents", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "version_status", "TEXT NOT NULL DEFAULT 'WORKING'");
        EnsureColumn(connection, "document_versions", "is_latest", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "document_versions", "is_published", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "document_versions", "published_at", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "version_label", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "server_version_id", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "server_comment_id", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "assigned_to", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "review_due_at", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "last_transition_reason", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "conflict_flag", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "field_comments", "conflict_basis", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "field_comments", "review_revision", "INTEGER NOT NULL DEFAULT 1");
        EnsureColumn(connection, "field_comment_attachments", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "field_comment_attachments", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_comment_id", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_report_id", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "base_server_revision", "INTEGER NULL");
        EnsureColumn(connection, "server_sync_queue", "expected_server_version_id", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "expected_published_version_id", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "local_file_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "conflict_code", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "conflict_details", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "resolution_action", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "resolution_reason", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "resolved_by", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "resolved_at", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "base_domain_revision", "INTEGER NULL");
        EnsureColumn(connection, "server_sync_queue", "intent_hash", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "source_set_hash", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "payload_json", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_conflict_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "base_snapshot_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_read_back_json", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "allowed_actions_json", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "source_preserved_path", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "retry_not_before", "TEXT NULL");
        EnsureColumn(connection, "reconciliation_items", "resolution_status", "TEXT NULL");
        EnsureColumn(connection, "server_bindings", "restore_pilot_run_id", "TEXT NULL");
        EnsureColumn(connection, "server_bindings", "restore_backup_set_id", "TEXT NULL");
        EnsureColumn(connection, "server_bindings", "restore_approval_id", "TEXT NULL");
        EnsureColumn(connection, "server_bindings", "restore_responsible_owner", "TEXT NULL");
        EnsureColumn(connection, "server_bindings", "restore_fault_code", "TEXT NULL");
        EnsureColumn(
            connection,
            "server_bindings",
            "convergence_status",
            "TEXT NOT NULL DEFAULT 'NORMAL_OPERATION'");
        EnsureColumn(connection, "server_id_mappings", "server_comment_id", "TEXT NULL");
        EnsureColumn(connection, "server_id_mappings", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "server_id_mappings", "server_report_id", "TEXT NULL");
        EnsureColumn(connection, "server_id_mappings", "server_revision", "INTEGER NULL");
        EnsureColumn(connection, "server_id_mappings", "server_file_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "server_id_mappings", "server_published_version_id", "TEXT NULL");
        EnsureColumn(connection, "report_sources", "trace_id", "TEXT NULL");
        EnsureColumn(connection, "report_sources", "source_hash_sha256", "TEXT NULL");
        EnsureColumn(connection, "report_sources", "source_revision", "INTEGER NULL");
        EnsureColumn(connection, "report_sources", "snapshot_verified", "INTEGER NOT NULL DEFAULT 0");
        using (var reportSourceBackfill = connection.CreateCommand())
        {
            reportSourceBackfill.CommandText = """
                UPDATE report_sources
                SET trace_id = 'legacy-report-source-' || id
                WHERE trace_id IS NULL OR trim(trace_id) = '';

                UPDATE report_sources
                SET source_hash_sha256 = lower(hex(randomblob(32)))
                WHERE source_hash_sha256 IS NULL OR trim(source_hash_sha256) = '';

                UPDATE report_sources
                SET source_version_id = CASE source_type
                    WHEN 'FIELD_COMMENT' THEN (
                        SELECT CAST(comment.document_version_no AS TEXT)
                        FROM field_comments AS comment
                        WHERE comment.comment_id = report_sources.local_source_id
                    )
                    WHEN 'DOCUMENT' THEN (
                        SELECT COALESCE(
                            document.server_version_id,
                            CAST(document.published_version_no AS TEXT),
                            CAST(document.version_no AS TEXT))
                        FROM documents AS document
                        WHERE document.document_id = report_sources.local_source_id
                    )
                    WHEN 'WORK_SEQUENCE_HISTORY' THEN local_source_id
                    WHEN 'WORK_SEQUENCE_ITEM' THEN COALESCE((
                        SELECT history.change_id
                        FROM work_sequence_change_history AS history
                        WHERE history.item_id = report_sources.local_source_id
                        ORDER BY history.created_at DESC, history.id DESC
                        LIMIT 1
                    ), local_source_id)
                    ELSE source_version_id
                END
                WHERE source_version_id IS NULL OR trim(source_version_id) = '';
                """;
            reportSourceBackfill.ExecuteNonQuery();
        }
        EnsureColumn(connection, "document_view_logs", "server_start_log_id", "INTEGER NULL");
        EnsureColumn(connection, "document_view_logs", "server_close_log_id", "INTEGER NULL");
        EnsureColumn(connection, "document_view_logs", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "notifications", "notification_type", "TEXT NOT NULL DEFAULT 'document'");
        EnsureColumn(connection, "notifications", "target_type", "TEXT NULL");
        EnsureColumn(connection, "notifications", "target_id", "TEXT NULL");
        EnsureColumn(connection, "notifications", "target_title", "TEXT NULL");
        EnsureColumn(connection, "notifications", "source_candidate_id", "TEXT NULL");
        EnsureColumn(connection, "work_sequence_items", "hold_reason", "TEXT NULL");
        EnsureColumn(connection, "work_sequence_notification_candidates", "recipient_name", "TEXT NULL");
        EnsureColumn(connection, "work_sequence_notification_candidates", "notification_id", "TEXT NULL");
        EnsureDocumentUpdatedAt(connection);
        EnsureDocumentVersionState(connection);
        BackfillFieldCommentsFromVersionComments(connection);

        SeedDefaultGroups(connection);
        SeedDefaultUsers(connection);
        var rootFolderId = SeedRootFolder(connection);
        SeedDefaultSystemFolders(connection, rootFolderId);
        var documentsFolderId = EnsureDefaultSystemFolder(connection, rootFolderId, DocumentsFolderName);
        SeedDocumentCategoryFolders(connection, documentsFolderId);
        MigrateDirectDocumentsToCategoryFolders(connection, documentsFolderId);
    }
}
