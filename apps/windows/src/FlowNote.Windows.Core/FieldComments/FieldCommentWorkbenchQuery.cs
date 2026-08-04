using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.FieldComments;

internal sealed class FieldCommentWorkbenchQuery(FlowNoteLocalDatabase database)
{
    internal IReadOnlyList<FieldCommentReviewRecord> ListForReview(FieldCommentReviewFilter? filter = null)
    {
        filter ??= new FieldCommentReviewFilter();
        var clauses = new List<string>();
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();

        var status = CleanFilter(filter.Status);
        if (!string.IsNullOrWhiteSpace(status) &&
            !string.Equals(status, "ALL", StringComparison.OrdinalIgnoreCase))
        {
            FieldCommentWorkflowService.ValidateReviewStatus(status);
            clauses.Add("comment.status = $status");
            command.Parameters.AddWithValue("$status", status);
        }

        var documentText = CleanFilter(filter.DocumentText);
        if (!string.IsNullOrWhiteSpace(documentText))
        {
            clauses.Add("(comment.document_id LIKE $document_text OR document.title LIKE $document_text OR document.file_name LIKE $document_text)");
            command.Parameters.AddWithValue("$document_text", $"%{documentText}%");
        }

        var authorText = CleanFilter(filter.AuthorText);
        if (!string.IsNullOrWhiteSpace(authorText))
        {
            clauses.Add("(comment.author_name LIKE $author_text OR comment.reported_by LIKE $author_text OR comment.operator_name LIKE $author_text)");
            command.Parameters.AddWithValue("$author_text", $"%{authorText}%");
        }

        var tagText = CleanFilter(filter.TagText);
        if (!string.IsNullOrWhiteSpace(tagText))
        {
            clauses.Add(
                """
                EXISTS (
                    SELECT 1
                    FROM document_tags AS filter_document_tag
                    JOIN tag_definitions AS filter_tag ON filter_tag.tag_id = filter_document_tag.tag_id
                    WHERE filter_document_tag.document_id = comment.document_id
                      AND (filter_tag.name LIKE $tag_text OR filter_tag.code LIKE $tag_text)
                )
                """);
            command.Parameters.AddWithValue("$tag_text", $"%{tagText}%");
        }

        var assignedTo = CleanFilter(filter.AssignedTo);
        if (!string.IsNullOrWhiteSpace(assignedTo))
        {
            clauses.Add("comment.assigned_to LIKE $assigned_to");
            command.Parameters.AddWithValue("$assigned_to", $"%{assignedTo}%");
        }

        var assignedRole = CleanFilter(filter.AssignedRole);
        if (!string.IsNullOrWhiteSpace(assignedRole) &&
            !string.Equals(assignedRole, "ALL", StringComparison.OrdinalIgnoreCase))
        {
            clauses.Add("EXISTS (SELECT 1 FROM user_accounts assigned_user WHERE assigned_user.user_id = comment.assigned_to AND assigned_user.role = $assigned_role)");
            command.Parameters.AddWithValue("$assigned_role", assignedRole);
        }

        var signalLevel = CleanFilter(filter.SignalLevel);
        if (!string.IsNullOrWhiteSpace(signalLevel) && !string.Equals(signalLevel, "ALL", StringComparison.OrdinalIgnoreCase))
        {
            clauses.Add("lower(comment.signal_level) = lower($signal_level)");
            command.Parameters.AddWithValue("$signal_level", signalLevel);
        }

        var documentVersionText = CleanFilter(filter.DocumentVersionText);
        if (!string.IsNullOrWhiteSpace(documentVersionText))
        {
            clauses.Add("CAST(comment.document_version_no AS TEXT) LIKE $document_version_text");
            command.Parameters.AddWithValue("$document_version_text", $"%{documentVersionText}%");
        }

        AddTypedTagFilter(clauses, command, "line", filter.LineText);
        AddTypedTagFilter(clauses, command, "equipment", filter.EquipmentText);
        AddTypedTagFilter(clauses, command, "process", filter.ProcessText);
        AddTypedTagFilter(clauses, command, "error_type", filter.ErrorTypeText);

        if (filter.OlderThanDays is > 0)
        {
            clauses.Add("comment.status = 'NEW' AND comment.created_at <= $aging_cutoff");
            command.Parameters.AddWithValue("$aging_cutoff", DateTime.UtcNow.AddDays(-filter.OlderThanDays.Value).ToString("O"));
        }
        if (filter.HasAttachments is not null)
        {
            clauses.Add(filter.HasAttachments.Value
                ? "EXISTS (SELECT 1 FROM field_comment_attachments a WHERE a.comment_id = comment.comment_id)"
                : "NOT EXISTS (SELECT 1 FROM field_comment_attachments a WHERE a.comment_id = comment.comment_id)");
        }
        if (filter.ReportLinked is not null)
        {
            clauses.Add(filter.ReportLinked.Value
                ? "EXISTS (SELECT 1 FROM report_sources r WHERE r.source_type = 'FIELD_COMMENT' AND r.local_source_id = comment.comment_id)"
                : "NOT EXISTS (SELECT 1 FROM report_sources r WHERE r.source_type = 'FIELD_COMMENT' AND r.local_source_id = comment.comment_id)");
        }
        if (filter.Unreviewed is not null)
        {
            clauses.Add(filter.Unreviewed.Value
                ? "comment.status IN ('NEW', 'NEEDS_REVIEW')"
                : "comment.status NOT IN ('NEW', 'NEEDS_REVIEW')");
        }
        if (filter.Overdue is not null)
        {
            var overdueClause = "comment.review_due_at IS NOT NULL AND comment.review_due_at < $review_now AND comment.status NOT IN ('SELECTED', 'EXCLUDED', 'ARCHIVED')";
            clauses.Add(filter.Overdue.Value ? $"({overdueClause})" : $"NOT ({overdueClause})");
            command.Parameters.AddWithValue("$review_now", DateTime.UtcNow.ToString("O"));
        }
        if (filter.Unassigned is not null)
        {
            clauses.Add(filter.Unassigned.Value
                ? "(comment.assigned_to IS NULL OR trim(comment.assigned_to) = '')"
                : "(comment.assigned_to IS NOT NULL AND trim(comment.assigned_to) <> '')");
        }
        if (filter.MissingEvidence is not null)
        {
            var missingClause = "comment.document_version_no IS NULL OR trim(comment.author_name) = '' OR comment.analysis_content IS NULL OR trim(comment.analysis_content) = ''";
            clauses.Add(filter.MissingEvidence.Value ? $"({missingClause})" : $"NOT ({missingClause})");
        }
        if (filter.DuplicateSuspected is not null)
        {
            var duplicateClause = "EXISTS (SELECT 1 FROM field_comments duplicate WHERE duplicate.comment_id <> comment.comment_id AND duplicate.raw_content = comment.raw_content)";
            clauses.Add(filter.DuplicateSuspected.Value ? duplicateClause : $"NOT {duplicateClause}");
        }
        if (filter.Conflict is not null)
        {
            clauses.Add(filter.Conflict.Value ? "comment.conflict_flag = 1" : "comment.conflict_flag = 0");
        }

        if (filter.CreatedFrom is not null)
        {
            clauses.Add("comment.created_at >= $created_from");
            command.Parameters.AddWithValue("$created_from", filter.CreatedFrom.Value.Date.ToString("O"));
        }

        if (filter.CreatedTo is not null)
        {
            clauses.Add("comment.created_at < $created_to");
            command.Parameters.AddWithValue("$created_to", filter.CreatedTo.Value.Date.AddDays(1).ToString("O"));
        }

        if (filter.ReviewDueFrom is not null)
        {
            clauses.Add("comment.review_due_at >= $review_due_from");
            command.Parameters.AddWithValue("$review_due_from", filter.ReviewDueFrom.Value.Date.ToString("O"));
        }

        if (filter.ReviewDueTo is not null)
        {
            clauses.Add("comment.review_due_at < $review_due_to");
            command.Parameters.AddWithValue("$review_due_to", filter.ReviewDueTo.Value.Date.AddDays(1).ToString("O"));
        }

        var where = clauses.Count == 0 ? string.Empty : $"WHERE {string.Join(" AND ", clauses)}";
        command.CommandText = $"""
            SELECT comment.id,
                   comment.comment_id,
                   comment.document_id,
                   COALESCE(document.title, comment.document_id, '문서 연결 없음') AS document_title,
                   COALESCE((
                       SELECT group_concat(tag.name, ', ')
                       FROM document_tags AS document_tag
                       JOIN tag_definitions AS tag ON tag.tag_id = document_tag.tag_id
                       WHERE document_tag.document_id = comment.document_id
                   ), '') AS document_tags,
                   comment.document_version_no,
                   comment.comment_type,
                   comment.input_mode,
                   comment.signal_level,
                   comment.raw_content,
                   comment.normalized_content,
                   comment.analysis_content,
                   comment.author_name,
                   comment.reported_by,
                   comment.operator_name,
                   comment.entry_source,
                   comment.device_id,
                   comment.location_code,
                   comment.assigned_to,
                   comment.review_due_at,
                   comment.status,
                   (
                       SELECT COUNT(*)
                       FROM field_comment_attachments AS attachment
                       WHERE attachment.comment_id = comment.comment_id
                   ) AS attachment_count,
                   comment.created_at,
                   comment.synced_at,
                   comment.review_revision,
                   comment.conflict_flag,
                   comment.conflict_basis
            FROM field_comments AS comment
            LEFT JOIN documents AS document ON document.document_id = comment.document_id
            {where}
            ORDER BY
                CASE WHEN $priority_order = 1 THEN
                    (CASE WHEN comment.conflict_flag = 1 THEN 128 ELSE 0 END)
                    + (CASE WHEN comment.review_due_at IS NOT NULL AND comment.review_due_at < $priority_now AND comment.status NOT IN ('SELECTED', 'EXCLUDED', 'ARCHIVED') THEN 64 ELSE 0 END)
                    + (CASE WHEN comment.assigned_to IS NULL OR trim(comment.assigned_to) = '' THEN 32 ELSE 0 END)
                    + (CASE WHEN comment.document_version_no IS NULL OR trim(comment.author_name) = '' OR comment.analysis_content IS NULL OR trim(comment.analysis_content) = '' THEN 16 ELSE 0 END)
                    + (CASE WHEN EXISTS (SELECT 1 FROM field_comments duplicate WHERE duplicate.comment_id <> comment.comment_id AND duplicate.raw_content = comment.raw_content) THEN 8 ELSE 0 END)
                    + (CASE WHEN comment.status IN ('NEW', 'NEEDS_REVIEW') THEN 4 ELSE 0 END)
                    + (CASE WHEN NOT EXISTS (SELECT 1 FROM report_sources r WHERE r.source_type = 'FIELD_COMMENT' AND r.local_source_id = comment.comment_id) THEN 2 ELSE 0 END)
                  ELSE 0 END DESC,
                CASE comment.status
                    WHEN 'SELECTED' THEN 0
                    WHEN 'REVIEWED' THEN 1
                    WHEN 'ANALYZED' THEN 2
                    WHEN 'NEEDS_REVIEW' THEN 3
                    WHEN 'NEW' THEN 4
                    WHEN 'EXCLUDED' THEN 5
                    WHEN 'ARCHIVED' THEN 6
                    ELSE 7
                END,
                comment.created_at DESC,
                comment.id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", Math.Clamp(filter.Limit, 1, 500));
        command.Parameters.AddWithValue("$priority_order", filter.PriorityOrder ? 1 : 0);
        command.Parameters.AddWithValue("$priority_now", DateTime.UtcNow.ToString("O"));

        using var reader = command.ExecuteReader();
        var records = new List<FieldCommentReviewRecord>();
        while (reader.Read())
        {
            records.Add(ReadFieldCommentReview(reader));
        }

        return records;
    }


    private static FieldCommentReviewRecord ReadFieldCommentReview(SqliteDataReader reader)
    {
        return new FieldCommentReviewRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2),
            reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4),
            reader.IsDBNull(5) ? null : reader.GetInt32(5),
            reader.GetString(6),
            reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.GetString(9),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.IsDBNull(11) ? null : reader.GetString(11),
            reader.GetString(12),
            reader.IsDBNull(13) ? null : reader.GetString(13),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.GetString(15),
            reader.IsDBNull(16) ? null : reader.GetString(16),
            reader.IsDBNull(17) ? null : reader.GetString(17),
            reader.IsDBNull(18) ? null : reader.GetString(18),
            reader.IsDBNull(19) ? null : DateTime.Parse(reader.GetString(19)),
            reader.GetString(20),
            reader.GetInt32(21),
            DateTime.Parse(reader.GetString(22)),
            reader.IsDBNull(23) ? null : DateTime.Parse(reader.GetString(23)),
            reader.GetInt32(24),
            reader.GetInt32(25) != 0,
            reader.IsDBNull(26) ? null : reader.GetString(26));
    }


    private static string? CleanFilter(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static void AddTypedTagFilter(
        List<string> clauses,
        SqliteCommand command,
        string tagType,
        string? value)
    {
        var cleaned = CleanFilter(value);
        if (string.IsNullOrWhiteSpace(cleaned))
        {
            return;
        }
        var parameter = $"$tag_{tagType}";
        clauses.Add($"""
            EXISTS (
                SELECT 1 FROM document_tags typed_document_tag
                JOIN tag_definitions typed_tag ON typed_tag.tag_id = typed_document_tag.tag_id
                WHERE typed_document_tag.document_id = comment.document_id
                  AND typed_tag.tag_type = '{tagType}'
                  AND (typed_tag.name LIKE {parameter} OR typed_tag.code LIKE {parameter})
            )
            """);
        command.Parameters.AddWithValue(parameter, $"%{cleaned}%");
    }


}
