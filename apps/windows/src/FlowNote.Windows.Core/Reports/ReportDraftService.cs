using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Storage;

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
}
