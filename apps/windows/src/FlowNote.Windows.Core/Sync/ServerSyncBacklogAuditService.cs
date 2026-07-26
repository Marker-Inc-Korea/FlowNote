using Microsoft.Data.Sqlite;
using SQLitePCL;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed class ServerSyncBacklogAuditService(string databasePath)
{
    private static bool sqliteInitialized;

    public ServerSyncBacklogAudit Create(string runId)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("run_id가 필요합니다.", nameof(runId));
        }

        var fullPath = Path.GetFullPath(databasePath);
        var fileHashBefore = HashFile(fullPath);
        using var connection = OpenReadOnly(fullPath);
        var integrity = ScalarText(connection, "PRAGMA integrity_check;");
        var foreignKeyViolations = ScalarLong(
            connection,
            "SELECT COUNT(*) FROM pragma_foreign_key_check;");
        var items = LoadItems(connection);
        var stateCounts = items
            .GroupBy(item => item.OperationalState)
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
        var statusCounts = items
            .GroupBy(item => item.Status)
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
        var queueHash = ComputeSha256(JsonSerializer.Serialize(
            items.Select(item => new
            {
                item.QueueId,
                item.SyncId,
                item.EntityType,
                item.EntityId,
                item.Action,
                item.IdempotencyKey,
                item.Status,
                item.AttemptCount,
                item.LastError,
                item.LocalHashSha256,
                item.ServerHashSha256,
                item.ResolutionAction,
                item.ResolutionReason,
                item.ResolvedBy,
                item.ResolvedAt
            })));
        var fileHashAfter = HashFile(fullPath);

        return new ServerSyncBacklogAudit(
            runId.Trim(),
            DateTimeOffset.UtcNow,
            fullPath,
            fileHashBefore,
            fileHashAfter,
            string.Equals(fileHashBefore, fileHashAfter, StringComparison.Ordinal),
            integrity,
            foreignKeyViolations,
            items.Count,
            items.Count(item => string.IsNullOrWhiteSpace(item.OperationalState)),
            items.Count(item => string.IsNullOrWhiteSpace(item.NextAction)),
            CountDuplicates(connection, "server_sync_queue", "idempotency_key"),
            CountMappingDuplicates(connection),
            CountOrphanMappings(connection),
            CountOrphanReportSources(connection),
            CountPreservedLegacyOrphanReportSources(connection),
            queueHash,
            statusCounts,
            stateCounts,
            items);
    }

    private static IReadOnlyList<ServerSyncBacklogAuditItem> LoadItems(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        var serverHashColumn = ColumnExists(
            connection,
            "server_sync_queue",
            "server_conflict_hash_sha256")
            ? "server_conflict_hash_sha256"
            : "NULL AS server_conflict_hash_sha256";
        command.CommandText = $$"""
            SELECT id, sync_id, entity_type, entity_id, action, idempotency_key,
                   status, attempt_count, last_error, local_file_hash_sha256,
                   {{serverHashColumn}},
                   conflict_details, resolution_action, resolution_reason,
                   resolved_by, resolved_at
            FROM server_sync_queue
            WHERE status NOT IN ('SYNCED', 'DISCARDED')
            ORDER BY id;
            """;
        using var reader = command.ExecuteReader();
        var items = new List<ServerSyncBacklogAuditItem>();
        while (reader.Read())
        {
            var status = reader.GetString(6);
            var entityType = reader.GetString(2);
            var action = reader.GetString(4);
            var error = reader.IsDBNull(8) ? null : reader.GetString(8);
            var diagnosis = ServerSyncQueueDiagnostics.Classify(
                status,
                entityType,
                action,
                error);
            var conflictDetails = reader.IsDBNull(11) ? null : reader.GetString(11);
            items.Add(new ServerSyncBacklogAuditItem(
                reader.GetInt64(0),
                reader.GetString(1),
                entityType,
                reader.GetString(3),
                action,
                reader.GetString(5),
                status,
                reader.GetInt32(7),
                error,
                diagnosis.OperationalState,
                diagnosis.Category,
                diagnosis.OperatorAction,
                diagnosis.ResponsibleRole,
                diagnosis.HandlingDeadline,
                diagnosis.AutoRetryLimit,
                diagnosis.ManualClosureCriteria,
                reader.IsDBNull(9) ? null : reader.GetString(9),
                reader.IsDBNull(10)
                    ? ExtractServerHash(conflictDetails)
                    : reader.GetString(10),
                reader.IsDBNull(12) ? null : reader.GetString(12),
                reader.IsDBNull(13) ? null : reader.GetString(13),
                reader.IsDBNull(14) ? null : reader.GetString(14),
                reader.IsDBNull(15) ? null : reader.GetString(15)));
        }
        return items;
    }

    private static bool ColumnExists(
        SqliteConnection connection,
        string table,
        string column)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"PRAGMA table_info({table});";
        using var reader = command.ExecuteReader();
        while (reader.Read())
        {
            if (string.Equals(reader.GetString(1), column, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static string? ExtractServerHash(string? conflictDetails)
    {
        if (string.IsNullOrWhiteSpace(conflictDetails))
        {
            return null;
        }
        try
        {
            using var document = JsonDocument.Parse(conflictDetails);
            var detail = document.RootElement.TryGetProperty("detail", out var nested)
                ? nested
                : document.RootElement;
            foreach (var name in new[] { "actualFileHash", "existingFileHash", "serverHash" })
            {
                if (detail.TryGetProperty(name, out var value) &&
                    value.ValueKind == JsonValueKind.String)
                {
                    return value.GetString();
                }
            }
        }
        catch (JsonException)
        {
            // The original response remains in conflict_details even if it predates JSON errors.
        }
        return null;
    }

    private static int CountDuplicates(SqliteConnection connection, string table, string column) =>
        Convert.ToInt32(ScalarLong(
            connection,
            $"SELECT COUNT(*) FROM (SELECT {column} FROM {table} GROUP BY {column} HAVING COUNT(*) > 1);"));

    private static int CountMappingDuplicates(SqliteConnection connection) =>
        Convert.ToInt32(ScalarLong(
            connection,
            """
            SELECT COUNT(*) FROM (
                SELECT entity_type, local_id, local_version_no
                FROM server_id_mappings
                GROUP BY entity_type, local_id, local_version_no
                HAVING COUNT(*) > 1
            );
            """));

    private static int CountOrphanMappings(SqliteConnection connection) =>
        Convert.ToInt32(ScalarLong(
            connection,
            """
            SELECT COUNT(*)
            FROM server_id_mappings AS mapping
            WHERE
                (mapping.entity_type IN (
                    'document', 'document_version', 'document_publish',
                    'document_status', 'document_tags'
                ) AND NOT EXISTS (
                    SELECT 1 FROM documents WHERE document_id = mapping.local_id
                ))
                OR (mapping.entity_type IN ('field_comment', 'field_comment_review') AND NOT EXISTS (
                    SELECT 1 FROM field_comments WHERE comment_id = mapping.local_id
                ))
                OR (mapping.entity_type = 'field_comment_attachment' AND NOT EXISTS (
                    SELECT 1 FROM field_comment_attachments
                    WHERE attachment_id = mapping.local_id
                ))
                OR (mapping.entity_type LIKE 'document_access_log%' AND NOT EXISTS (
                    SELECT 1 FROM document_view_logs
                    WHERE CAST(id AS TEXT) = mapping.local_id
                ))
                OR (mapping.entity_type = 'report' AND NOT EXISTS (
                    SELECT 1 FROM documents WHERE document_id = mapping.local_id
                ));
            """));

    private static int CountOrphanReportSources(SqliteConnection connection) =>
        Convert.ToInt32(ScalarLong(
            connection,
            """
            SELECT COUNT(*)
            FROM report_sources AS source
            WHERE source.trace_id NOT LIKE 'legacy-report-source-%'
              AND (NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE document_id = source.local_report_document_id
                )
               OR (source.source_type = 'DOCUMENT' AND NOT EXISTS (
                    SELECT 1 FROM documents WHERE document_id = source.local_source_id
                ))
               OR (source.source_type = 'FIELD_COMMENT' AND NOT EXISTS (
                    SELECT 1 FROM field_comments WHERE comment_id = source.local_source_id
                )));
            """));

    private static int CountPreservedLegacyOrphanReportSources(SqliteConnection connection) =>
        Convert.ToInt32(ScalarLong(
            connection,
            """
            SELECT COUNT(*)
            FROM report_sources AS source
            WHERE source.trace_id LIKE 'legacy-report-source-%'
              AND ((source.source_type = 'DOCUMENT' AND NOT EXISTS (
                    SELECT 1 FROM documents WHERE document_id = source.local_source_id
                ))
                OR (source.source_type = 'FIELD_COMMENT' AND NOT EXISTS (
                    SELECT 1 FROM field_comments WHERE comment_id = source.local_source_id
                )));
            """));

    private static SqliteConnection OpenReadOnly(string path)
    {
        if (!sqliteInitialized)
        {
            Batteries_V2.Init();
            sqliteInitialized = true;
        }
        var connection = new SqliteConnection(
            new SqliteConnectionStringBuilder
            {
                DataSource = path,
                Mode = SqliteOpenMode.ReadOnly
            }.ToString());
        connection.Open();
        return connection;
    }

    private static long ScalarLong(SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private static string ScalarText(SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(command.ExecuteScalar()) ?? string.Empty;
    }

    private static string HashFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static string ComputeSha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}

public sealed record ServerSyncBacklogAudit(
    string RunId,
    DateTimeOffset CreatedAt,
    string DatabasePath,
    string DatabaseSha256Before,
    string DatabaseSha256After,
    bool DatabaseUnchanged,
    string IntegrityCheck,
    long ForeignKeyViolationCount,
    int NonCompletedCount,
    int MissingOperationalStateCount,
    int MissingNextActionCount,
    int IdempotencyDuplicateCount,
    int MappingDuplicateCount,
    int OrphanMappingCount,
    int OrphanReportSourceCount,
    int PreservedLegacyOrphanReportSourceCount,
    string QueueCanonicalSha256,
    IReadOnlyDictionary<string, int> StatusCounts,
    IReadOnlyDictionary<string, int> OperationalStateCounts,
    IReadOnlyList<ServerSyncBacklogAuditItem> Items);

public sealed record ServerSyncBacklogAuditItem(
    long QueueId,
    string SyncId,
    string EntityType,
    string EntityId,
    string Action,
    string IdempotencyKey,
    string Status,
    int AttemptCount,
    string? LastError,
    string OperationalState,
    string Category,
    string NextAction,
    string ResponsibleRole,
    string HandlingDeadline,
    int AutoRetryLimit,
    string ManualClosureCriteria,
    string? LocalHashSha256,
    string? ServerHashSha256,
    string? ResolutionAction,
    string? ResolutionReason,
    string? ResolvedBy,
    string? ResolvedAt);
