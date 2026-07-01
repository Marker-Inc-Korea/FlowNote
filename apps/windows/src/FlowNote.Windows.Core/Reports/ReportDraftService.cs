using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Reports;

public sealed class ReportDraftService(FlowNoteLocalDatabase database, DocumentService documents)
{
    public IReadOnlyList<ReportSourceCandidateRecord> ListFieldCommentSources(int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT comment.comment_id,
                   COALESCE(document.title, comment.document_id, 'No document') AS title,
                   comment.raw_content,
                   comment.created_at
            FROM field_comments AS comment
            LEFT JOIN documents AS document ON document.document_id = comment.document_id
            ORDER BY comment.created_at DESC, comment.id DESC
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
                DateTime.Parse(reader.GetString(3))));
        }

        return records;
    }

    public IReadOnlyList<ReportSourceCandidateRecord> ListDocumentSources(int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document_id, title, file_name, updated_at
            FROM documents
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
                DateTime.Parse(reader.GetString(3))));
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
                DateTime.Parse(reader.GetString(3))));
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
        string actorName)
    {
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
        return documents.UpdateDocumentStatus(document.DocumentId, "IN_REVIEW", actorName);
    }

    public async Task<ReportServerSaveResult> SaveDraftToServerAsync(
        FlowNoteServerDocumentClient serverClient,
        long folderId,
        string title,
        string summary,
        string content,
        IEnumerable<ReportSourceCandidateRecord> selectedSources,
        string actorName,
        CancellationToken cancellationToken = default)
    {
        var sourceMap = MapServerReportSources(selectedSources);
        if (sourceMap.Sources.Count == 0)
        {
            throw new InvalidOperationException("No selected report source is linked to a server id.");
        }

        var draft = await serverClient.CreateReportDraftAsync(
            new ServerReportDraftCreateRequest
            {
                ReportType = "field_review",
                Title = Clean(title, "Field report draft"),
                Summary = Clean(summary, string.Empty),
                AnalysisContent = Clean(content, string.Empty),
                Sources = sourceMap.Sources
            },
            cancellationToken);

        var saved = await serverClient.SaveReportAsync(
            new ServerReportSaveRequest
            {
                DraftReportId = draft.ReportId,
                AnalysisContent = Clean(content, string.Empty),
                SaveAsDocument = true,
                DocumentTitle = Clean(title, "Field report draft"),
                DocumentStatus = "IN_REVIEW"
            },
            cancellationToken);

        DocumentRecord? localDocument = null;
        if (!string.IsNullOrWhiteSpace(saved.GeneratedDocumentId))
        {
            localDocument = SaveDraftAsDocument(folderId, title, content, actorName);
            LinkLocalDocumentToServerReport(localDocument.DocumentId, saved, actorName);
            localDocument = documents.UpdateDocumentStatus(localDocument.DocumentId, "IN_REVIEW", actorName);
        }

        return new ReportServerSaveResult(draft, saved, localDocument, sourceMap.SkippedSources);
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

    private void LinkLocalDocumentToServerReport(string localDocumentId, ServerReportResponse savedReport, string actorName)
    {
        var generatedDocument = savedReport.GeneratedDocument;
        var serverDocumentId = savedReport.GeneratedDocumentId;
        var serverVersionId = generatedDocument?.LatestVersionId ?? generatedDocument?.PublishedVersionId;
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE documents
            SET server_report_id = $server_report_id,
                server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id;

            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND is_latest = 1;
            """;
        command.Parameters.AddWithValue("$server_report_id", Clean(savedReport.ReportId, string.Empty));
        command.Parameters.AddWithValue(
            "$server_document_id",
            string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        command.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        command.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        command.Parameters.AddWithValue("$document_id", localDocumentId);
        command.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "report.server_saved",
            actorName,
            "document",
            localDocumentId,
            savedReport.Title,
            $"Server report saved: {savedReport.ReportId} / {serverDocumentId}",
            now);
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
