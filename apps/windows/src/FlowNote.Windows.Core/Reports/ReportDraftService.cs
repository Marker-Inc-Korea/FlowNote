using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using Microsoft.Data.Sqlite;
using System.Security.Cryptography;
using System.Text;

namespace FlowNote.Windows.Core.Reports;

public sealed class ReportDraftService(
    FlowNoteLocalDatabase database,
    DocumentService documents,
    ServerSyncService serverSync)
{
    public IReadOnlyList<ReportSourceCandidateRecord> ListFieldCommentSources(int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT comment.comment_id,
                   COALESCE(document.title, comment.document_id, 'No document') AS title,
                   COALESCE(NULLIF(comment.normalized_content, ''), comment.raw_content) ||
                       CASE
                           WHEN comment.analysis_content IS NOT NULL AND trim(comment.analysis_content) <> ''
                           THEN char(10) || '분석: ' || comment.analysis_content
                           ELSE ''
                       END AS detail,
                   comment.created_at,
                   comment.document_version_no
            FROM field_comments AS comment
            LEFT JOIN documents AS document ON document.document_id = comment.document_id
            WHERE comment.status = 'SELECTED'
            ORDER BY comment.created_at DESC,
                comment.id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", Math.Clamp(limit, 1, 500));

        using var reader = command.ExecuteReader();
        var records = new List<ReportSourceCandidateRecord>();
        while (reader.Read())
        {
            records.Add(new ReportSourceCandidateRecord(
                "FIELD_COMMENT",
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                DateTime.Parse(reader.GetString(3)),
                reader.IsDBNull(4) ? null : reader.GetInt32(4).ToString()));
        }

        return records;
    }

    public IReadOnlyList<ReportSourceCandidateRecord> ListDocumentSources(int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document_id, title, file_name, updated_at,
                   COALESCE(server_version_id, CAST(published_version_no AS TEXT), CAST(version_no AS TEXT))
            FROM documents
            WHERE status = 'PUBLISHED'
              AND published_version_no IS NOT NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", Math.Clamp(limit, 1, 500));

        using var reader = command.ExecuteReader();
        var records = new List<ReportSourceCandidateRecord>();
        while (reader.Read())
        {
            records.Add(new ReportSourceCandidateRecord(
                "DOCUMENT",
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                DateTime.Parse(reader.GetString(3)),
                reader.IsDBNull(4) ? null : reader.GetString(4)));
        }

        return records;
    }

    public IReadOnlyList<ReportSourceCandidateRecord> ListWorkSequenceSources(int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT history.change_id,
                   COALESCE(item.title, board.title, history.board_id) AS title,
                   history.change_type || ': ' ||
                       COALESCE(history.before_value, '') || ' -> ' ||
                       COALESCE(history.after_value, '') AS detail,
                   history.created_at
            FROM work_sequence_change_history AS history
            LEFT JOIN work_sequence_items AS item ON item.item_id = history.item_id
            LEFT JOIN work_sequence_boards AS board ON board.board_id = history.board_id
            ORDER BY history.created_at DESC, history.id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", Math.Clamp(limit, 1, 500));

        using var reader = command.ExecuteReader();
        var records = new List<ReportSourceCandidateRecord>();
        while (reader.Read())
        {
            records.Add(new ReportSourceCandidateRecord(
                "WORK_SEQUENCE_HISTORY",
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                DateTime.Parse(reader.GetString(3)),
                reader.GetString(0)));
        }

        return records;
    }

    public string BuildDraftContent(
        string title,
        string summary,
        IEnumerable<ReportSourceCandidateRecord> sources,
        string actorName)
    {
        var selected = sources.ToList();
        ValidateSourceSet(selected);
        var lines = new List<string>
        {
            $"# {Clean(title, "Field report draft")}",
            "",
            $"CreatedBy: {actorName}",
            $"CreatedAt: {DateTime.UtcNow:O}",
            "",
            "## Summary",
            Clean(summary, "Manager review summary is not written yet."),
            "",
            "## Sources"
        };

        if (selected.Count == 0)
        {
            lines.Add("- No source selected.");
        }
        else
        {
            foreach (var source in selected)
            {
                lines.Add($"- {source.SourceType} {source.SourceId}: {source.Title}");
                lines.Add($"  {source.Detail}");
            }
        }

        lines.Add("");
        lines.Add("## Analysis");
        lines.Add("Write manager analysis here.");
        lines.Add("");
        lines.Add("## Conclusion");
        lines.Add("Write conclusion here.");
        lines.Add("");
        lines.Add("## Action Plan");
        lines.Add("Write follow-up action here.");
        return string.Join(Environment.NewLine, lines);
    }

    public DocumentRecord SaveDraftAsDocument(
        long folderId,
        string title,
        string content,
        string actorName,
        IEnumerable<ReportSourceCandidateRecord>? selectedSources = null,
        string? summary = null)
    {
        var sources = (selectedSources ?? []).ToList();
        ValidateSourceSet(sources);
        var now = DateTime.UtcNow;
        var dataDirectory = Path.GetDirectoryName(database.DatabasePath)!;
        var reportRoot = Path.Combine(dataDirectory, "Files", "Reports", now.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(reportRoot);
        var safeTitle = string.Join("_", Clean(title, "field-report").Split(Path.GetInvalidFileNameChars()));
        var fileName = $"{safeTitle}-{now:HHmmss}.txt";
        var targetPath = GetUniqueTargetPath(reportRoot, fileName);
        File.WriteAllText(targetPath, content);
        var relativePath = Path.GetRelativePath(dataDirectory, targetPath);
        var document = documents.RegisterDocument(
            folderId,
            Clean(title, "Field report draft"),
            Path.GetFileName(targetPath),
            "Report",
            actorName,
            relativePath,
            new[] { "Report", "FieldComment" });
        var updatedDocument = documents.UpdateDocumentStatus(document.DocumentId, "IN_REVIEW", actorName);
        SaveLocalReportSources(updatedDocument.DocumentId, sources);
        SaveReportSummary(updatedDocument.DocumentId, summary);
        return updatedDocument;
    }

    public async Task<ReportServerSaveResult> SaveDraftToServerAsync(
        FlowNoteServerDocumentClient? serverClient,
        long folderId,
        string title,
        string summary,
        string content,
        IEnumerable<ReportSourceCandidateRecord> selectedSources,
        string actorName,
        CancellationToken cancellationToken = default)
    {
        var selected = selectedSources.ToList();
        var localDocument = SaveDraftAsDocument(folderId, title, content, actorName, selected, summary);
        var sourceMap = MapServerReportSources(selected);
        ServerReportResponse? saved = null;
        var syncResult = await serverSync.QueueAndTrySyncReportAsync(
            localDocument,
            serverClient,
            cancellationToken: cancellationToken);
        if (serverClient is not null)
        {
            var serverReportId = TryGetLocalServerReportId(localDocument.DocumentId);
            if (!string.IsNullOrWhiteSpace(serverReportId))
            {
                saved = await serverClient.GetReportAsync(serverReportId, cancellationToken);
            }
        }

        return new ReportServerSaveResult(saved, localDocument, sourceMap.SkippedSources, syncResult);
    }

    public (
        IReadOnlyList<ServerReportSourceRequest> Sources,
        IReadOnlyList<ReportSourceCandidateRecord> SkippedSources) MapServerReportSources(
        IEnumerable<ReportSourceCandidateRecord> selectedSources)
    {
        using var connection = database.OpenConnection();
        var mapped = new List<ServerReportSourceRequest>();
        var skipped = new List<ReportSourceCandidateRecord>();

        foreach (var source in selectedSources)
        {
            if (TryMapServerReportSource(connection, source) is { } request)
            {
                mapped.Add(request);
            }
            else
            {
                skipped.Add(source);
            }
        }

        return (mapped, skipped);
    }

    private static string Clean(string? value, string fallback)
    {
        var cleaned = value?.Trim();
        return string.IsNullOrWhiteSpace(cleaned) ? fallback : cleaned;
    }

    private static void ValidateSourceSet(IReadOnlyCollection<ReportSourceCandidateRecord> sources)
    {
        if (sources.Select(source => Clean(source.SourceType, string.Empty).ToUpperInvariant()).Distinct().Count() < 2)
        {
            throw new InvalidOperationException("보고서는 서로 다른 근거 유형을 최소 2종 선택해야 합니다.");
        }
        if (sources.Any(source => string.IsNullOrWhiteSpace(source.SourceVersionId)))
        {
            throw new InvalidOperationException("모든 보고서 근거는 고정된 원천 버전이 필요합니다.");
        }
        var hasDuplicate = sources
            .GroupBy(source => new
            {
                Type = Clean(source.SourceType, string.Empty).ToUpperInvariant(),
                Id = Clean(source.SourceId, string.Empty),
                Version = Clean(source.SourceVersionId, string.Empty)
            })
            .Any(group => group.Count() > 1);
        if (hasDuplicate)
        {
            throw new InvalidOperationException("같은 보고서 근거와 버전을 중복 선택할 수 없습니다.");
        }
    }

    private static string GetUniqueTargetPath(string directory, string fileName)
    {
        var candidate = Path.Combine(directory, fileName);
        if (!File.Exists(candidate))
        {
            return candidate;
        }

        var name = Path.GetFileNameWithoutExtension(fileName);
        var extension = Path.GetExtension(fileName);
        var index = 1;
        do
        {
            candidate = Path.Combine(directory, $"{name}-{index:00}{extension}");
            index++;
        }
        while (File.Exists(candidate));

        return candidate;
    }

    private void SaveLocalReportSources(
        string localReportDocumentId,
        IEnumerable<ReportSourceCandidateRecord> selectedSources)
    {
        using var connection = database.OpenConnection();
        using var delete = connection.CreateCommand();
        delete.CommandText = """
            DELETE FROM report_sources
            WHERE local_report_document_id = $document_id;
            """;
        delete.Parameters.AddWithValue("$document_id", localReportDocumentId);
        delete.ExecuteNonQuery();

        foreach (var source in selectedSources)
        {
            using var insert = connection.CreateCommand();
            insert.CommandText = """
                INSERT INTO report_sources (
                    local_report_document_id,
                    source_type,
                    local_source_id,
                    source_version_id,
                    trace_id,
                    source_hash_sha256,
                    relation_type,
                    title,
                    detail,
                    created_at
                )
                VALUES (
                    $document_id,
                    $source_type,
                    $local_source_id,
                    $source_version_id,
                    $trace_id,
                    $source_hash_sha256,
                    $relation_type,
                    $title,
                    $detail,
                    $created_at
                );
                """;
            insert.Parameters.AddWithValue("$document_id", localReportDocumentId);
            insert.Parameters.AddWithValue("$source_type", Clean(source.SourceType, string.Empty).ToUpperInvariant());
            insert.Parameters.AddWithValue("$local_source_id", Clean(source.SourceId, string.Empty));
            insert.Parameters.AddWithValue("$source_version_id", string.IsNullOrWhiteSpace(source.SourceVersionId) ? DBNull.Value : source.SourceVersionId);
            insert.Parameters.AddWithValue("$trace_id", $"trace_{Guid.NewGuid():N}");
            insert.Parameters.AddWithValue(
                "$source_hash_sha256",
                Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source.Detail))).ToLowerInvariant());
            insert.Parameters.AddWithValue("$relation_type", string.IsNullOrWhiteSpace(source.RelationType) ? DBNull.Value : source.RelationType);
            insert.Parameters.AddWithValue("$title", string.IsNullOrWhiteSpace(source.Title) ? DBNull.Value : source.Title);
            insert.Parameters.AddWithValue("$detail", string.IsNullOrWhiteSpace(source.Detail) ? DBNull.Value : source.Detail);
            insert.Parameters.AddWithValue("$created_at", source.CreatedAt.ToString("O"));
            insert.ExecuteNonQuery();
        }
    }

    private void SaveReportSummary(string localReportDocumentId, string? summary)
    {
        if (string.IsNullOrWhiteSpace(summary))
        {
            return;
        }

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE documents
            SET latest_comment = $summary
            WHERE document_id = $document_id;
            """;
        command.Parameters.AddWithValue("$summary", summary.Trim());
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        command.ExecuteNonQuery();
    }

    private string? TryGetLocalServerReportId(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_report_id
            FROM documents
            WHERE document_id = $document_id
              AND server_report_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToString(value);
    }

    private static ServerReportSourceRequest? TryMapServerReportSource(SqliteConnection connection, ReportSourceCandidateRecord source)
    {
        var sourceType = Clean(source.SourceType, string.Empty).ToUpperInvariant();
        var sourceId = Clean(source.SourceId, string.Empty);
        if (sourceType.Length == 0 || sourceId.Length == 0)
        {
            return null;
        }

        return sourceType switch
        {
            "FIELD_COMMENT" => TryMapFieldCommentSource(connection, source, sourceId),
            "DOCUMENT" => TryMapDocumentSource(connection, source, sourceId),
            "WORK_SEQUENCE_ITEM" => TryMapLocalOnlySource(connection, "work_sequence_items", "item_id", source, sourceId),
            "WORK_SEQUENCE_HISTORY" => TryMapLocalOnlySource(connection, "work_sequence_change_history", "change_id", source, sourceId),
            "WORK_RECORD" or "WORK_RECORD_VERSION" => CreateServerReportSource(source, sourceId),
            _ => null
        };
    }

    private static ServerReportSourceRequest? TryMapFieldCommentSource(
        SqliteConnection connection,
        ReportSourceCandidateRecord source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_comment_id
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", sourceId);
        var value = command.ExecuteScalar();
        if (value is null)
        {
            return CreateServerReportSource(source, sourceId);
        }

        var serverCommentId = value is DBNull ? null : Convert.ToString(value);
        return string.IsNullOrWhiteSpace(serverCommentId)
            ? null
            : CreateServerReportSource(source, serverCommentId);
    }

    private static ServerReportSourceRequest? TryMapDocumentSource(
        SqliteConnection connection,
        ReportSourceCandidateRecord source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", sourceId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return CreateServerReportSource(source, sourceId);
        }

        var serverDocumentId = reader.IsDBNull(0) ? null : reader.GetString(0);
        if (string.IsNullOrWhiteSpace(serverDocumentId))
        {
            return null;
        }

        var serverVersionId = reader.IsDBNull(1) ? source.SourceVersionId : reader.GetString(1);
        return CreateServerReportSource(source, serverDocumentId, serverVersionId);
    }

    private static ServerReportSourceRequest? TryMapLocalOnlySource(
        SqliteConnection connection,
        string tableName,
        string idColumn,
        ReportSourceCandidateRecord source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"SELECT 1 FROM {tableName} WHERE {idColumn} = $source_id LIMIT 1;";
        command.Parameters.AddWithValue("$source_id", sourceId);
        var value = command.ExecuteScalar();
        return value is null ? CreateServerReportSource(source, sourceId) : null;
    }

    private static ServerReportSourceRequest CreateServerReportSource(
        ReportSourceCandidateRecord source,
        string sourceId,
        string? sourceVersionId = null)
    {
        var sourceType = Clean(source.SourceType, string.Empty).ToUpperInvariant();
        return new ServerReportSourceRequest
        {
            SourceType = sourceType,
            SourceId = sourceId,
            SourceVersionId = Clean(sourceVersionId, string.Empty).Length > 0
                ? sourceVersionId
                : Clean(source.SourceVersionId, string.Empty).Length > 0
                    ? source.SourceVersionId
                    : null,
            RelationType = Clean(source.RelationType, DefaultRelationType(sourceType))
        };
    }

    private static string DefaultRelationType(string sourceType)
    {
        return sourceType switch
        {
            "FIELD_COMMENT" => "primary",
            "DOCUMENT" => "related_document",
            "WORK_SEQUENCE_ITEM" => "work_sequence",
            "WORK_SEQUENCE_HISTORY" => "work_sequence_history",
            "WORK_RECORD" => "work_record",
            "WORK_RECORD_VERSION" => "work_record_version",
            _ => "related"
        };
    }
}
