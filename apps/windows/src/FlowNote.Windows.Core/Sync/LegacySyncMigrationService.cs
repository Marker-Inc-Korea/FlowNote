using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Sync;

public sealed class LegacySyncMigrationService(string databasePath)
{
    private const string Failed = "FAILED";
    private static bool sqliteInitialized;

    public LegacySyncMigrationPlan CreateDryRunPlan()
    {
        using var connection = Open(readOnly: true);
        var rows = LoadFailedRows(connection);
        var items = rows.Select(row => Classify(connection, row)).OrderBy(item => item.SourceRowId).ToArray();
        var categoryCounts = items.GroupBy(item => item.Category)
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
        var stateCounts = items.GroupBy(item => item.MigrationState)
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
        var planHash = CreatePlanHash(items);

        return new LegacySyncMigrationPlan(
            Path.GetFullPath(databasePath),
            rows.Count,
            items.Length,
            planHash,
            categoryCounts,
            stateCounts,
            items);
    }

    public LegacySyncMigrationExecutionResult ExecuteApproved(
        IEnumerable<long> approvedSourceRowIds,
        string approvedBy,
        string expectedPlanHash)
    {
        if (string.IsNullOrWhiteSpace(approvedBy))
        {
            throw new ArgumentException("승인 실행에는 승인자 이름이 필요합니다.", nameof(approvedBy));
        }

        var approvedIds = approvedSourceRowIds.Distinct().Order().ToArray();
        var plan = CreateDryRunPlan();
        if (!string.Equals(plan.PlanHash, expectedPlanHash, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("dry-run 이후 원본 큐가 변경되었습니다. 새 dry-run의 planHash로 다시 승인하세요.");
        }

        var selected = plan.Items
            .Where(item => approvedIds.Contains(item.SourceRowId))
            .OrderBy(item => item.SourceEntityType == "field_note" ? 0 : 1)
            .ThenBy(item => item.SourceRowId)
            .ToArray();
        var messages = new List<string>();
        var rejected = approvedIds.Length - selected.Length;
        foreach (var missingId in approvedIds.Except(selected.Select(item => item.SourceRowId)))
        {
            messages.Add($"원천 큐 #{missingId}: 현재 FAILED 행이 아니거나 존재하지 않아 승인 대상에서 제외했습니다.");
        }

        using var connection = Open(readOnly: false);
        using var transaction = connection.BeginTransaction();
        EnsureAuditSchema(connection, transaction);

        var createdSources = 0;
        var createdQueues = 0;
        var createdAudits = 0;
        var alreadyMigrated = 0;
        var approved = 0;

        foreach (var item in selected)
        {
            if (item.MigrationState is not (
                LegacySyncMigrationStates.AutomaticallyConvertible or
                LegacySyncMigrationStates.AdministratorReviewRequired))
            {
                rejected++;
                messages.Add($"원천 큐 #{item.SourceRowId}: {item.MigrationState} 상태이므로 신규 큐를 만들지 않았습니다. {item.OperatorAction}");
                continue;
            }

            if (AuditExists(connection, transaction, item.SourceRowId))
            {
                alreadyMigrated++;
                approved++;
                messages.Add($"원천 큐 #{item.SourceRowId}: 이미 전환 감사 기록이 있어 중복 생성하지 않았습니다.");
                continue;
            }

            if (item.SourceEntityType == "field_note_attachment" &&
                !CanMigrateLegacyAttachmentParent(connection, transaction, plan, selected, item))
            {
                rejected++;
                messages.Add($"원천 큐 #{item.SourceRowId}: 구 FieldNote 본문을 함께 승인하거나 먼저 전환해야 첨부를 전환할 수 있습니다.");
                continue;
            }

            var sourceSnapshot = LoadSourceSnapshot(connection, transaction, item);
            if (item.SourceEntityType == "field_note")
            {
                createdSources += InsertLegacyFieldComment(connection, transaction, item);
            }
            else if (item.SourceEntityType == "field_note_attachment")
            {
                createdSources += InsertLegacyFieldCommentAttachment(connection, transaction, item);
            }

            var requestedTargetSyncId = CreateTargetSyncId(item.SourceSyncId);
            createdQueues += InsertTargetQueue(connection, transaction, item, requestedTargetSyncId);
            var targetSyncId = GetTargetSyncId(connection, transaction, item.ExpectedIdempotencyKey!)
                ?? throw new InvalidOperationException($"원천 큐 #{item.SourceRowId}: 신규 큐 또는 동일 idempotency key 큐를 확인할 수 없습니다.");
            createdAudits += InsertAudit(
                connection,
                transaction,
                item,
                targetSyncId,
                approvedBy.Trim(),
                plan.PlanHash,
                sourceSnapshot);
            approved++;
        }

        transaction.Commit();
        return new LegacySyncMigrationExecutionResult(
            approvedIds.Length,
            approved,
            createdSources,
            createdQueues,
            createdAudits,
            alreadyMigrated,
            rejected,
            messages);
    }

    private LegacySyncMigrationPlanItem Classify(SqliteConnection connection, FailedRow row)
    {
        var category = GetCategory(row);
        var source = InspectSource(connection, row);
        var target = GetTarget(connection, row, source);
        var state = GetMigrationState(row, category, source, target);
        var (reason, action) = GetKoreanGuidance(row, category, state, source, target);

        return new LegacySyncMigrationPlanItem(
            row.Id,
            row.SyncId,
            row.EntityType,
            row.EntityId,
            row.Action,
            row.IdempotencyKey,
            row.AttemptCount,
            category,
            state,
            reason,
            action,
            source.Exists,
            source.FileExists,
            source.FilePath,
            target.EntityType,
            target.EntityId,
            target.Action,
            target.IdempotencyKey,
            target.ParentSourceSyncId);
    }

    private static string GetCategory(FailedRow row)
    {
        if (row.EntityType is "field_note" or "field_note_attachment" ||
            row.Action.Contains("field_note", StringComparison.OrdinalIgnoreCase))
        {
            return LegacySyncMigrationCategories.LegacyFieldNote;
        }

        if (string.Equals(row.Action, "create", StringComparison.OrdinalIgnoreCase))
        {
            return LegacySyncMigrationCategories.LegacyCreate;
        }

        if (row.LastError.Contains("로컬 파일을 찾을 수 없어", StringComparison.Ordinal) ||
            row.LastError.Contains("Local document file not found", StringComparison.OrdinalIgnoreCase))
        {
            return LegacySyncMigrationCategories.MissingLocalFile;
        }

        if (row.LastError.Contains("선행 ", StringComparison.Ordinal) ||
            row.LastError.Contains("서버 매핑", StringComparison.Ordinal) ||
            row.LastError.Contains("보고서 근거", StringComparison.Ordinal))
        {
            return LegacySyncMigrationCategories.MissingPredecessorServerId;
        }

        return LegacySyncMigrationCategories.ServerOrAuthenticationError;
    }

    private static string GetMigrationState(FailedRow row, string category, SourceInspection source, Target target)
    {
        if (!source.Exists || source.FileExists == false)
        {
            return LegacySyncMigrationStates.SourceMissingUnconvertible;
        }

        if (category == LegacySyncMigrationCategories.LegacyFieldNote ||
            row.EntityType == "document_view_log")
        {
            return target.Action is null
                ? LegacySyncMigrationStates.SourceMissingUnconvertible
                : LegacySyncMigrationStates.AdministratorReviewRequired;
        }

        if (category == LegacySyncMigrationCategories.LegacyCreate)
        {
            return target.Action is null
                ? LegacySyncMigrationStates.AdministratorReviewRequired
                : LegacySyncMigrationStates.AutomaticallyConvertible;
        }

        return LegacySyncMigrationStates.KeepPreserved;
    }

    private static (string Reason, string OperatorAction) GetKoreanGuidance(
        FailedRow row,
        string category,
        string state,
        SourceInspection source,
        Target target)
    {
        if (!source.Exists)
        {
            return (
                $"원천 {source.SourceLabel} 행을 찾을 수 없어 무손실 전환에 필요한 내용을 복원할 수 없습니다.",
                $"원천 테이블에서 {row.EntityId} 기록을 백업 또는 과거 DB로 복구한 뒤 다시 진단하세요. 기존 큐 행은 계속 보존합니다.");
        }

        if (source.FileExists == false)
        {
            return (
                $"원천 행은 있으나 로컬 파일이 없습니다: {source.FilePath}",
                "원본 파일을 동일 경로로 복구하거나 관리자 확인으로 대체 원본을 연결한 뒤 다시 dry-run 하세요. 기존 큐 행은 계속 보존합니다.");
        }

        if (state == LegacySyncMigrationStates.AutomaticallyConvertible)
        {
            return (
                $"원천을 확인했으며 현재 action {target.Action}의 별도 신규 큐로 전환할 수 있습니다.",
                "dry-run의 원천 row, 대상 action, 예상 idempotency key를 검토한 뒤 해당 row만 승인하세요.");
        }

        if (category == LegacySyncMigrationCategories.LegacyFieldNote)
        {
            return (
                "구 명칭 원천이 남아 있어 FieldComment 원천과 신규 큐로 복제할 수 있으나 의미와 첨부 연결은 관리자 승인이 필요합니다.",
                row.EntityType == "field_note_attachment"
                    ? "작성자·시각·원천 ID·구 명칭 이력을 확인하고 연결된 구 FieldNote 본문과 함께 승인하세요."
                    : "작성자·시각·본문·첨부·원천 ID를 확인한 뒤 FieldComment 전환을 승인하거나 계속 보존하세요.");
        }

        if (row.EntityType == "document_view_log")
        {
            return (
                $"구 열람 로그 create는 현재 이벤트 action {target.Action}로 해석되며 관리자 확인이 필요합니다.",
                "열람 시작 시각과 종료 사유를 확인한 뒤 승인하거나 원본 큐를 계속 보존하세요.");
        }

        if (category == LegacySyncMigrationCategories.MissingPredecessorServerId)
        {
            return (row.LastError, "선행 문서·버전·FieldComment 서버 ID를 먼저 복구 또는 동기화한 뒤 기존 큐를 재시도하세요. 새 마이그레이션 큐는 만들지 않습니다.");
        }

        return (row.LastError, "서버 실행 상태, URL, 네트워크와 로그인을 조치한 뒤 기존 큐를 재시도하세요. 새 마이그레이션 큐는 만들지 않습니다.");
    }

    private Target GetTarget(SqliteConnection connection, FailedRow row, SourceInspection source)
    {
        return (row.EntityType, row.Action) switch
        {
            ("document", "create") => new("document", row.EntityId, "register_document", $"wpf:document:{row.EntityId}:v{row.LocalVersionNo ?? 1}", null),
            ("document_version", "create") => new("document_version", row.EntityId, "register_document_version", $"wpf:document-version:{row.EntityId}:v{row.LocalVersionNo ?? 1}", null),
            ("field_comment", "create") => new("field_comment", row.EntityId, "register_field_comment", $"wpf:field-comment:{row.EntityId}", null),
            ("field_comment_attachment", "create") => new("field_comment_attachment", row.EntityId, "register_field_comment_attachment", $"wpf:field-comment-attachment:{row.EntityId}", null),
            ("document_view_log", "create") => GetLegacyViewLogTarget(connection, row),
            ("field_note", _) => GetLegacyFieldNoteTarget(row),
            ("field_note_attachment", _) => GetLegacyFieldNoteAttachmentTarget(connection, row),
            _ => new(null, null, null, null, null)
        };
    }

    private static Target GetLegacyViewLogTarget(SqliteConnection connection, FailedRow row)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT closed_at, close_reason FROM document_view_logs WHERE id = $id LIMIT 1;";
        command.Parameters.AddWithValue("$id", row.EntityId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return new(null, null, null, null, null);
        }

        var closeReason = reader.IsDBNull(1) ? null : reader.GetString(1);
        var action = reader.IsDBNull(0)
            ? "register_access_log_started"
            : closeReason switch
            {
                "auto_closed" => "register_access_log_auto_closed",
                "download_blocked" => "register_access_log_download_blocked",
                _ => "register_access_log_closed"
            };
        return new("document_access_log", row.EntityId, action, $"wpf:access-log:{row.EntityId}:{action}", null);
    }

    private static Target GetLegacyFieldNoteTarget(FailedRow row)
    {
        var targetId = CreateMigratedId("fc-legacy", "field_note", row.EntityId);
        return new("field_comment", targetId, "register_field_comment", $"wpf:field-comment:{targetId}", null);
    }

    private static Target GetLegacyFieldNoteAttachmentTarget(SqliteConnection connection, FailedRow row)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT note_id FROM field_note_attachments WHERE attachment_id = $id LIMIT 1;";
        command.Parameters.AddWithValue("$id", row.EntityId);
        var noteId = command.ExecuteScalar() as string;
        if (string.IsNullOrWhiteSpace(noteId))
        {
            return new(null, null, null, null, null);
        }

        var targetId = CreateMigratedId("att-legacy", "field_note_attachment", row.EntityId);
        using var parent = connection.CreateCommand();
        parent.CommandText = "SELECT sync_id FROM server_sync_queue WHERE entity_type = 'field_note' AND entity_id = $note_id ORDER BY id LIMIT 1;";
        parent.Parameters.AddWithValue("$note_id", noteId);
        var parentSyncId = parent.ExecuteScalar() as string;
        return new("field_comment_attachment", targetId, "register_field_comment_attachment", $"wpf:field-comment-attachment:{targetId}", parentSyncId);
    }

    private SourceInspection InspectSource(SqliteConnection connection, FailedRow row)
    {
        var (table, idColumn, sourceLabel, fileColumn) = row.EntityType switch
        {
            "document" => ("documents", "document_id", "documents", "local_path"),
            "document_version" => ("document_versions", "document_id", "document_versions", "local_path"),
            "document_view_log" or "document_access_log" => ("document_view_logs", "id", "document_view_logs", (string?)null),
            "field_comment" => ("field_comments", "comment_id", "field_comments", (string?)null),
            "field_comment_attachment" => ("field_comment_attachments", "attachment_id", "field_comment_attachments", "local_path"),
            "field_note" => ("field_notes", "note_id", "구 field_notes", (string?)null),
            "field_note_attachment" => ("field_note_attachments", "attachment_id", "구 field_note_attachments", "local_path"),
            "document_publish" or "document_status" => ("documents", "document_id", "documents", (string?)null),
            _ => ("", "", row.EntityType, (string?)null)
        };

        if (string.IsNullOrWhiteSpace(table) || !TableExists(connection, table))
        {
            return new(false, null, null, sourceLabel);
        }

        using var command = connection.CreateCommand();
        var versionClause = table == "document_versions" && row.LocalVersionNo is not null
            ? " AND version_no = $version_no"
            : string.Empty;
        command.CommandText = fileColumn is null
            ? $"SELECT 1 FROM {table} WHERE {idColumn} = $id{versionClause} LIMIT 1;"
            : $"SELECT {fileColumn} FROM {table} WHERE {idColumn} = $id{versionClause} LIMIT 1;";
        command.Parameters.AddWithValue("$id", row.EntityType is "document_view_log" or "document_access_log" && long.TryParse(row.EntityId, out var numericId)
            ? numericId
            : row.EntityId);
        if (versionClause.Length > 0)
        {
            command.Parameters.AddWithValue("$version_no", row.LocalVersionNo!.Value);
        }

        var value = command.ExecuteScalar();
        if (value is null || value is DBNull)
        {
            return new(false, null, null, sourceLabel);
        }

        if (fileColumn is null)
        {
            return new(true, null, null, sourceLabel);
        }

        var storedPath = Convert.ToString(value);
        var resolvedPath = ResolveFilePath(storedPath);
        return new(true, File.Exists(resolvedPath), resolvedPath, sourceLabel);
    }

    private string ResolveFilePath(string? storedPath)
    {
        if (string.IsNullOrWhiteSpace(storedPath))
        {
            return "(경로 없음)";
        }

        var normalized = storedPath.Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar);
        if (Path.IsPathRooted(normalized))
        {
            return Path.GetFullPath(normalized);
        }

        var databaseDirectory = Path.GetDirectoryName(Path.GetFullPath(databasePath))!;
        return Path.GetFullPath(Path.Combine(databaseDirectory, normalized));
    }

    private static IReadOnlyList<FailedRow> LoadFailedRows(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, sync_id, entity_type, entity_id, action, local_document_id,
                   local_version_no, idempotency_key, attempt_count, COALESCE(last_error, '')
            FROM server_sync_queue
            WHERE status = 'FAILED'
            ORDER BY id;
            """;
        using var reader = command.ExecuteReader();
        var rows = new List<FailedRow>();
        while (reader.Read())
        {
            rows.Add(new FailedRow(
                reader.GetInt64(0), reader.GetString(1), reader.GetString(2), reader.GetString(3), reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5), reader.IsDBNull(6) ? null : reader.GetInt32(6),
                reader.GetString(7), reader.GetInt32(8), reader.GetString(9)));
        }

        return rows;
    }

    private static string CreatePlanHash(IEnumerable<LegacySyncMigrationPlanItem> items)
    {
        var canonical = string.Join('\n', items.Select(item => string.Join('|',
            item.SourceRowId,
            item.SourceSyncId,
            item.SourceEntityType,
            item.SourceEntityId,
            item.SourceAction,
            item.SourceIdempotencyKey,
            item.AttemptCount,
            item.Category,
            item.MigrationState,
            item.SourceExists,
            item.LocalFileExists?.ToString() ?? "",
            item.TargetEntityType ?? "",
            item.TargetEntityId ?? "",
            item.TargetAction ?? "",
            item.ExpectedIdempotencyKey ?? "")));
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
    }

    private static string CreateMigratedId(string prefix, string sourceType, string sourceId)
    {
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{sourceType}:{sourceId}"))).ToLowerInvariant();
        return $"{prefix}-{hash[..24]}";
    }

    private static string CreateTargetSyncId(string sourceSyncId) => CreateMigratedId("sync-migration", "sync", sourceSyncId);

    private static bool TableExists(SqliteConnection connection, string table)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = $name LIMIT 1;";
        command.Parameters.AddWithValue("$name", table);
        return command.ExecuteScalar() is not null;
    }

    private static SqliteConnection Open(bool readOnly, string databasePath)
    {
        if (!sqliteInitialized)
        {
            SQLitePCL.Batteries_V2.Init();
            sqliteInitialized = true;
        }

        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = Path.GetFullPath(databasePath),
            Mode = readOnly ? SqliteOpenMode.ReadOnly : SqliteOpenMode.ReadWrite,
            ForeignKeys = true,
            DefaultTimeout = 5
        };
        var connection = new SqliteConnection(builder.ToString());
        connection.Open();
        return connection;
    }

    private SqliteConnection Open(bool readOnly) => Open(readOnly, databasePath);

    private static void EnsureAuditSchema(SqliteConnection connection, SqliteTransaction transaction)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            CREATE TABLE IF NOT EXISTS server_sync_migration_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id TEXT NOT NULL UNIQUE,
                source_queue_id INTEGER NOT NULL UNIQUE REFERENCES server_sync_queue(id) ON DELETE RESTRICT,
                source_sync_id TEXT NOT NULL,
                source_entity_type TEXT NOT NULL,
                source_entity_id TEXT NOT NULL,
                source_action TEXT NOT NULL,
                source_idempotency_key TEXT NOT NULL,
                classification TEXT NOT NULL,
                migration_state TEXT NOT NULL,
                decision TEXT NOT NULL,
                approved_by TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                plan_hash TEXT NOT NULL,
                target_entity_type TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                target_action TEXT NOT NULL,
                target_idempotency_key TEXT NOT NULL UNIQUE,
                target_sync_id TEXT NOT NULL UNIQUE,
                source_snapshot_json TEXT NOT NULL,
                legacy_domain_name TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_server_sync_migration_audit_source
                ON server_sync_migration_audit (source_entity_type, source_entity_id);
            """;
        command.ExecuteNonQuery();
    }

    private static bool AuditExists(SqliteConnection connection, SqliteTransaction transaction, long sourceRowId)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT 1 FROM server_sync_migration_audit WHERE source_queue_id = $id LIMIT 1;";
        command.Parameters.AddWithValue("$id", sourceRowId);
        return command.ExecuteScalar() is not null;
    }

    private static bool CanMigrateLegacyAttachmentParent(
        SqliteConnection connection,
        SqliteTransaction transaction,
        LegacySyncMigrationPlan plan,
        IReadOnlyCollection<LegacySyncMigrationPlanItem> selected,
        LegacySyncMigrationPlanItem attachment)
    {
        var parent = plan.Items.FirstOrDefault(item => item.SourceSyncId == attachment.ParentSourceSyncId);
        if (parent is null)
        {
            return false;
        }

        if (selected.Any(item => item.SourceRowId == parent.SourceRowId))
        {
            return true;
        }

        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT 1 FROM server_sync_migration_audit WHERE source_queue_id = $id LIMIT 1;";
        command.Parameters.AddWithValue("$id", parent.SourceRowId);
        return command.ExecuteScalar() is not null;
    }

    private static int InsertLegacyFieldComment(SqliteConnection connection, SqliteTransaction transaction, LegacySyncMigrationPlanItem item)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT OR IGNORE INTO field_comments (
                comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                raw_content, normalized_content, analysis_content, author_name, reported_by, operator_name,
                entry_source, device_id, location_code, status, created_at, synced_at, server_comment_id
            )
            SELECT $target_id, document_id, document_version_no, note_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by, operator_name,
                   entry_source, device_id, location_code, status, created_at, NULL, NULL
            FROM field_notes
            WHERE note_id = $source_id;
            """;
        command.Parameters.AddWithValue("$target_id", item.TargetEntityId!);
        command.Parameters.AddWithValue("$source_id", item.SourceEntityId);
        return command.ExecuteNonQuery();
    }

    private static int InsertLegacyFieldCommentAttachment(SqliteConnection connection, SqliteTransaction transaction, LegacySyncMigrationPlanItem item)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT OR IGNORE INTO field_comment_attachments (
                attachment_id, comment_id, local_path, original_file_name, extension, content_type,
                size_bytes, hash_sha256, attachment_type, caption, captured_at, created_by, created_at,
                server_attachment_id, synced_at
            )
            SELECT $target_id,
                   'fc-legacy-' || lower(substr(hex(sha256_placeholder), 1, 24)),
                   local_path, original_file_name, extension, content_type, size_bytes, hash_sha256,
                   attachment_type, caption, captured_at, created_by, created_at, NULL, NULL
            FROM field_note_attachments
            WHERE attachment_id = $source_id;
            """;
        // SQLite에는 SHA-256 함수가 없으므로 부모 ID를 C#에서 결정해 SQL 식을 교체한다.
        using var parentLookup = connection.CreateCommand();
        parentLookup.Transaction = transaction;
        parentLookup.CommandText = "SELECT note_id FROM field_note_attachments WHERE attachment_id = $id LIMIT 1;";
        parentLookup.Parameters.AddWithValue("$id", item.SourceEntityId);
        var parentSourceId = parentLookup.ExecuteScalar() as string
            ?? throw new InvalidOperationException("구 FieldNote 첨부의 부모 원천을 찾을 수 없습니다.");
        command.CommandText = command.CommandText.Replace(
            "'fc-legacy-' || lower(substr(hex(sha256_placeholder), 1, 24))",
            "$target_comment_id",
            StringComparison.Ordinal);
        command.Parameters.AddWithValue("$target_id", item.TargetEntityId!);
        command.Parameters.AddWithValue("$target_comment_id", CreateMigratedId("fc-legacy", "field_note", parentSourceId));
        command.Parameters.AddWithValue("$source_id", item.SourceEntityId);
        return command.ExecuteNonQuery();
    }

    private static int InsertTargetQueue(SqliteConnection connection, SqliteTransaction transaction, LegacySyncMigrationPlanItem item, string targetSyncId)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT OR IGNORE INTO server_sync_queue (
                sync_id, entity_type, entity_id, action, local_document_id, local_version_no,
                idempotency_key, status, attempt_count, last_error, created_at
            )
            SELECT $sync_id, $entity_type, $entity_id, $action,
                   CASE WHEN $source_type = 'field_note' THEN field_notes.document_id
                        WHEN $source_type = 'field_note_attachment' THEN (
                            SELECT field_notes.document_id
                            FROM field_note_attachments
                            JOIN field_notes ON field_notes.note_id = field_note_attachments.note_id
                            WHERE field_note_attachments.attachment_id = $source_entity_id
                        )
                        ELSE local_document_id END,
                   CASE WHEN $source_type = 'field_note' THEN field_notes.document_version_no
                        WHEN $source_type = 'field_note_attachment' THEN (
                            SELECT field_notes.document_version_no
                            FROM field_note_attachments
                            JOIN field_notes ON field_notes.note_id = field_note_attachments.note_id
                            WHERE field_note_attachments.attachment_id = $source_entity_id
                        )
                        ELSE local_version_no END,
                   $idempotency_key, 'PENDING', 0, NULL, $created_at
            FROM server_sync_queue
            LEFT JOIN field_notes
              ON $source_type = 'field_note' AND field_notes.note_id = $source_entity_id
            WHERE server_sync_queue.id = $source_queue_id;
            """;
        command.Parameters.AddWithValue("$sync_id", targetSyncId);
        command.Parameters.AddWithValue("$entity_type", item.TargetEntityType!);
        command.Parameters.AddWithValue("$entity_id", item.TargetEntityId!);
        command.Parameters.AddWithValue("$action", item.TargetAction!);
        command.Parameters.AddWithValue("$source_type", item.SourceEntityType);
        command.Parameters.AddWithValue("$source_entity_id", item.SourceEntityId);
        command.Parameters.AddWithValue("$idempotency_key", item.ExpectedIdempotencyKey!);
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$source_queue_id", item.SourceRowId);
        return command.ExecuteNonQuery();
    }

    private static string? GetTargetSyncId(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string idempotencyKey)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT sync_id FROM server_sync_queue WHERE idempotency_key = $key LIMIT 1;";
        command.Parameters.AddWithValue("$key", idempotencyKey);
        return command.ExecuteScalar() as string;
    }

    private static int InsertAudit(
        SqliteConnection connection,
        SqliteTransaction transaction,
        LegacySyncMigrationPlanItem item,
        string targetSyncId,
        string approvedBy,
        string planHash,
        string sourceSnapshot)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT OR IGNORE INTO server_sync_migration_audit (
                migration_id, source_queue_id, source_sync_id, source_entity_type, source_entity_id,
                source_action, source_idempotency_key, classification, migration_state, decision,
                approved_by, approved_at, plan_hash, target_entity_type, target_entity_id, target_action,
                target_idempotency_key, target_sync_id, source_snapshot_json, legacy_domain_name
            )
            VALUES (
                $migration_id, $source_queue_id, $source_sync_id, $source_entity_type, $source_entity_id,
                $source_action, $source_idempotency_key, $classification, $migration_state, 'APPROVED',
                $approved_by, $approved_at, $plan_hash, $target_entity_type, $target_entity_id, $target_action,
                $target_idempotency_key, $target_sync_id, $source_snapshot_json, $legacy_domain_name
            );
            """;
        command.Parameters.AddWithValue("$migration_id", CreateMigratedId("migration", "queue", item.SourceSyncId));
        command.Parameters.AddWithValue("$source_queue_id", item.SourceRowId);
        command.Parameters.AddWithValue("$source_sync_id", item.SourceSyncId);
        command.Parameters.AddWithValue("$source_entity_type", item.SourceEntityType);
        command.Parameters.AddWithValue("$source_entity_id", item.SourceEntityId);
        command.Parameters.AddWithValue("$source_action", item.SourceAction);
        command.Parameters.AddWithValue("$source_idempotency_key", item.SourceIdempotencyKey);
        command.Parameters.AddWithValue("$classification", item.Category);
        command.Parameters.AddWithValue("$migration_state", item.MigrationState);
        command.Parameters.AddWithValue("$approved_by", approvedBy);
        command.Parameters.AddWithValue("$approved_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$plan_hash", planHash);
        command.Parameters.AddWithValue("$target_entity_type", item.TargetEntityType!);
        command.Parameters.AddWithValue("$target_entity_id", item.TargetEntityId!);
        command.Parameters.AddWithValue("$target_action", item.TargetAction!);
        command.Parameters.AddWithValue("$target_idempotency_key", item.ExpectedIdempotencyKey!);
        command.Parameters.AddWithValue("$target_sync_id", targetSyncId);
        command.Parameters.AddWithValue("$source_snapshot_json", sourceSnapshot);
        command.Parameters.AddWithValue("$legacy_domain_name", item.SourceEntityType.StartsWith("field_note", StringComparison.Ordinal) ? "FieldNote" : DBNull.Value);
        return command.ExecuteNonQuery();
    }

    private static string LoadSourceSnapshot(SqliteConnection connection, SqliteTransaction transaction, LegacySyncMigrationPlanItem item)
    {
        var table = item.SourceEntityType switch
        {
            "field_note" => "field_notes",
            "field_note_attachment" => "field_note_attachments",
            "field_comment" => "field_comments",
            "field_comment_attachment" => "field_comment_attachments",
            "document" => "documents",
            "document_version" => "document_versions",
            "document_view_log" => "document_view_logs",
            _ => null
        };
        if (table is null)
        {
            return JsonSerializer.Serialize(new { item.SourceEntityType, item.SourceEntityId });
        }

        var idColumn = item.SourceEntityType switch
        {
            "field_note" => "note_id",
            "field_note_attachment" or "field_comment_attachment" => "attachment_id",
            "field_comment" => "comment_id",
            "document" or "document_version" => "document_id",
            "document_view_log" => "id",
            _ => "id"
        };
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = $"SELECT * FROM {table} WHERE {idColumn} = $id" +
            (item.SourceEntityType == "document_version" && item.TargetAction == "register_document_version" ? " AND version_no = $version_no" : string.Empty) +
            " LIMIT 1;";
        command.Parameters.AddWithValue("$id", item.SourceEntityType == "document_view_log" && long.TryParse(item.SourceEntityId, out var id) ? id : item.SourceEntityId);
        if (item.SourceEntityType == "document_version" && item.TargetAction == "register_document_version")
        {
            using var versionLookup = connection.CreateCommand();
            versionLookup.Transaction = transaction;
            versionLookup.CommandText = "SELECT local_version_no FROM server_sync_queue WHERE id = $id;";
            versionLookup.Parameters.AddWithValue("$id", item.SourceRowId);
            command.Parameters.AddWithValue("$version_no", versionLookup.ExecuteScalar() ?? 1);
        }

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return "{}";
        }

        var snapshot = new SortedDictionary<string, object?>(StringComparer.Ordinal);
        for (var index = 0; index < reader.FieldCount; index++)
        {
            snapshot[reader.GetName(index)] = reader.IsDBNull(index) ? null : reader.GetValue(index);
        }
        return JsonSerializer.Serialize(snapshot);
    }

    private sealed record FailedRow(
        long Id, string SyncId, string EntityType, string EntityId, string Action,
        string? LocalDocumentId, int? LocalVersionNo, string IdempotencyKey, int AttemptCount, string LastError);

    private sealed record SourceInspection(bool Exists, bool? FileExists, string? FilePath, string SourceLabel);

    private sealed record Target(string? EntityType, string? EntityId, string? Action, string? IdempotencyKey, string? ParentSourceSyncId);
}
