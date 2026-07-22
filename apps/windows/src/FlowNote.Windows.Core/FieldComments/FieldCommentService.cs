using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;
using FlowNote.Windows.Core.History;
using System.Security.Cryptography;
using System.Text.Json;

namespace FlowNote.Windows.Core.FieldComments;

public sealed class FieldCommentService(FlowNoteLocalDatabase database)
{
    public static readonly IReadOnlyList<string> ReviewStatuses =
    [
        "NEW",
        "ASSIGNED",
        "NEEDS_REVIEW",
        "ANALYZED",
        "REVIEWED",
        "SELECTED",
        "EXCLUDED",
        "ARCHIVED"
    ];

    public FieldCommentRecord AddDocumentComment(
        string documentId,
        string rawContent,
        string authorName,
        string commentType = "issue",
        string inputMode = "free_text",
        string entrySource = "field_user",
        string? signalLevel = null,
        string? reportedBy = null,
        string? operatorName = null,
        string? deviceId = null,
        string? locationCode = null)
    {
        if (string.IsNullOrWhiteSpace(documentId))
        {
            throw new ArgumentException("Document id is required.", nameof(documentId));
        }

        var content = rawContent.Trim();
        if (string.IsNullOrWhiteSpace(content))
        {
            throw new ArgumentException("Field comment content is required.", nameof(rawContent));
        }

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT version_no, title
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$document_id", documentId);
        using var documentReader = lookup.ExecuteReader();
        if (!documentReader.Read())
        {
            throw new InvalidOperationException($"Document not found: {documentId}");
        }

        var documentVersionNo = documentReader.GetInt32(0);
        var documentTitle = documentReader.GetString(1);
        documentReader.Close();
        var commentId = $"comment-{Guid.NewGuid():N}";

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO field_comments (
                comment_id,
                document_id,
                document_version_no,
                comment_type,
                input_mode,
                signal_level,
                raw_content,
                author_name,
                reported_by,
                operator_name,
                entry_source,
                device_id,
                location_code,
                status,
                created_at
            )
            VALUES (
                $comment_id,
                $document_id,
                $document_version_no,
                $comment_type,
                $input_mode,
                $signal_level,
                $raw_content,
                $author_name,
                $reported_by,
                $operator_name,
                $entry_source,
                $device_id,
                $location_code,
                'NEW',
                $created_at
            );
            SELECT last_insert_rowid();
            """;
        insert.Parameters.AddWithValue("$comment_id", commentId);
        insert.Parameters.AddWithValue("$document_id", documentId);
        insert.Parameters.AddWithValue("$document_version_no", documentVersionNo);
        insert.Parameters.AddWithValue("$comment_type", commentType);
        insert.Parameters.AddWithValue("$input_mode", inputMode);
        insert.Parameters.AddWithValue("$signal_level", string.IsNullOrWhiteSpace(signalLevel) ? DBNull.Value : signalLevel);
        insert.Parameters.AddWithValue("$raw_content", content);
        insert.Parameters.AddWithValue("$author_name", authorName);
        insert.Parameters.AddWithValue("$reported_by", string.IsNullOrWhiteSpace(reportedBy) ? DBNull.Value : reportedBy);
        insert.Parameters.AddWithValue("$operator_name", string.IsNullOrWhiteSpace(operatorName) ? DBNull.Value : operatorName);
        insert.Parameters.AddWithValue("$entry_source", entrySource);
        insert.Parameters.AddWithValue("$device_id", string.IsNullOrWhiteSpace(deviceId) ? DBNull.Value : deviceId);
        insert.Parameters.AddWithValue("$location_code", string.IsNullOrWhiteSpace(locationCode) ? DBNull.Value : locationCode);
        insert.Parameters.AddWithValue("$created_at", now.ToString("O"));
        var id = Convert.ToInt64(insert.ExecuteScalar());

        using var updateDocument = connection.CreateCommand();
        updateDocument.CommandText = """
            UPDATE documents
            SET latest_comment = $latest_comment,
                updated_at = $updated_at
            WHERE document_id = $document_id;
            """;
        updateDocument.Parameters.AddWithValue("$latest_comment", content);
        updateDocument.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        updateDocument.Parameters.AddWithValue("$document_id", documentId);
        updateDocument.ExecuteNonQuery();

        AddFieldCommentNotification(connection, documentId, authorName, content, now);
        HistoryService.Record(
            connection,
            "field_comment.created",
            authorName,
            "document",
            documentId,
            documentTitle,
            $"현장 코멘트 등록: {documentTitle}",
            now);

        return new FieldCommentRecord(
            id,
            commentId,
            documentId,
            documentVersionNo,
            commentType,
            inputMode,
            signalLevel,
            content,
            null,
            null,
            authorName,
            reportedBy,
            operatorName,
            entrySource,
            deviceId,
            locationCode,
            "NEW",
            now,
            null,
            null,
            null,
            null);
    }

    public IReadOnlyList<FieldCommentRecord> ListDocumentComments(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at,
                   assigned_to, review_due_at, last_transition_reason, review_revision,
                   conflict_flag, conflict_basis
            FROM field_comments
            WHERE document_id = $document_id
            ORDER BY created_at DESC, id DESC;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);

        using var reader = command.ExecuteReader();
        var records = new List<FieldCommentRecord>();
        while (reader.Read())
        {
            records.Add(ReadFieldComment(reader));
        }

        return records;
    }

    public IReadOnlyList<FieldCommentReviewRecord> ListForReview(FieldCommentReviewFilter? filter = null)
    {
        filter ??= new FieldCommentReviewFilter();
        var clauses = new List<string>();
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();

        var status = CleanFilter(filter.Status);
        if (!string.IsNullOrWhiteSpace(status) &&
            !string.Equals(status, "ALL", StringComparison.OrdinalIgnoreCase))
        {
            ValidateReviewStatus(status);
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

    public string? GetServerCommentId(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT server_comment_id FROM field_comments WHERE comment_id = $comment_id LIMIT 1;";
        command.Parameters.AddWithValue("$comment_id", commentId);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToString(value);
    }

    public IReadOnlyList<FieldCommentSavedView> ListSavedViews()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT name, filter_json, updated_at FROM field_comment_saved_views ORDER BY name;";
        using var reader = command.ExecuteReader();
        var result = new List<FieldCommentSavedView>();
        while (reader.Read())
        {
            var filter = JsonSerializer.Deserialize<FieldCommentReviewFilter>(reader.GetString(1));
            if (filter is not null)
            {
                result.Add(new FieldCommentSavedView(reader.GetString(0), filter, DateTime.Parse(reader.GetString(2))));
            }
        }
        return result;
    }

    public void SaveView(string name, FieldCommentReviewFilter filter)
    {
        var cleaned = name.Trim();
        if (cleaned.Length < 2)
        {
            throw new ArgumentException("저장 보기 이름을 2자 이상 입력하세요.", nameof(name));
        }
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO field_comment_saved_views (name, filter_json, updated_at)
            VALUES ($name, $filter_json, $updated_at)
            ON CONFLICT(name) DO UPDATE SET filter_json = excluded.filter_json, updated_at = excluded.updated_at;
            """;
        command.Parameters.AddWithValue("$name", cleaned);
        command.Parameters.AddWithValue("$filter_json", JsonSerializer.Serialize(filter));
        command.Parameters.AddWithValue("$updated_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }

    public FieldCommentRecord UpdateReview(
        string commentId,
        string? normalizedContent,
        string? analysisContent,
        string status,
        string actorName,
        string transitionReason,
        string? assignedTo = null,
        DateTime? reviewDueAt = null,
        bool conflictFlag = false,
        string? conflictBasis = null)
    {
        if (string.IsNullOrWhiteSpace(commentId))
        {
            throw new ArgumentException("Field comment id is required.", nameof(commentId));
        }

        ValidateReviewStatus(status);
        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        var existing = LoadCommentTarget(connection, commentId)
            ?? throw new InvalidOperationException($"Field comment not found: {commentId}");
        var existingComment = LoadComment(connection, commentId)
            ?? throw new InvalidOperationException($"Field comment not found: {commentId}");
        var normalized = CleanNullable(normalizedContent);
        var analysis = CleanNullable(analysisContent);
        var reason = CleanNullable(transitionReason);
        if (existingComment.Status == "SELECTED" && status is not ("REVIEWED" or "EXCLUDED") &&
            (!string.Equals(normalized, existingComment.NormalizedContent, StringComparison.Ordinal) ||
             !string.Equals(analysis, existingComment.AnalysisContent, StringComparison.Ordinal) ||
             conflictFlag != existingComment.ConflictFlag ||
             !string.Equals(CleanNullable(conflictBasis), existingComment.ConflictBasis, StringComparison.Ordinal)))
        {
            throw new InvalidOperationException("선정된 FieldComment 해석을 바꾸려면 검토완료로 되돌린 뒤 재검토하세요.");
        }
        ValidateTransition(existingComment.Status, status, normalized, analysis, reason);
        if (status == "SELECTED" &&
            (existingComment.DocumentVersionNo is null || string.IsNullOrWhiteSpace(existingComment.AuthorName)))
        {
            throw new InvalidOperationException("보고서선정에는 관찰 문서 버전과 원천 작성자가 필요합니다.");
        }

        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE field_comments
            SET normalized_content = $normalized_content,
                analysis_content = $analysis_content,
                assigned_to = $assigned_to,
                review_due_at = $review_due_at,
                last_transition_reason = $transition_reason,
                conflict_flag = $conflict_flag,
                conflict_basis = $conflict_basis,
                status = $status
            WHERE comment_id = $comment_id;
            """;
        update.Parameters.AddWithValue("$normalized_content", normalized ?? (object)DBNull.Value);
        update.Parameters.AddWithValue("$analysis_content", analysis ?? (object)DBNull.Value);
        update.Parameters.AddWithValue("$assigned_to", CleanNullable(assignedTo) ?? (object)DBNull.Value);
        update.Parameters.AddWithValue("$review_due_at", reviewDueAt is null ? DBNull.Value : reviewDueAt.Value.ToString("O"));
        update.Parameters.AddWithValue("$transition_reason", reason ?? (object)DBNull.Value);
        update.Parameters.AddWithValue("$conflict_flag", conflictFlag ? 1 : 0);
        update.Parameters.AddWithValue("$conflict_basis", CleanNullable(conflictBasis) ?? (object)DBNull.Value);
        update.Parameters.AddWithValue("$status", status);
        update.Parameters.AddWithValue("$comment_id", commentId);
        update.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "field_comment.review_updated",
            actorName,
            "field_comment",
            commentId,
            existing.DocumentTitle,
            $"FieldComment 검토 상태 변경: {existingComment.Status} → {status} · 사유: {reason}",
            now);

        return LoadComment(connection, commentId)
            ?? throw new InvalidOperationException($"Field comment not found after update: {commentId}");
    }

    public void ApplyServerReviewResult(
        string commentId,
        string? normalizedContent,
        string? analysisContent,
        string status,
        string? assignedTo,
        DateTime? reviewDueAt,
        string? transitionReason,
        int reviewRevision,
        bool conflictFlag,
        string? conflictBasis,
        string actorName)
    {
        ValidateReviewStatus(status);
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE field_comments
            SET normalized_content = $normalized_content,
                analysis_content = $analysis_content,
                status = $status,
                assigned_to = $assigned_to,
                review_due_at = $review_due_at,
                last_transition_reason = $transition_reason,
                review_revision = $review_revision,
                conflict_flag = $conflict_flag,
                conflict_basis = $conflict_basis,
                synced_at = $synced_at
            WHERE comment_id = $comment_id;
            """;
        command.Parameters.AddWithValue("$normalized_content", CleanNullable(normalizedContent) ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$analysis_content", CleanNullable(analysisContent) ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$status", status);
        command.Parameters.AddWithValue("$assigned_to", CleanNullable(assignedTo) ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$review_due_at", reviewDueAt is null ? DBNull.Value : reviewDueAt.Value.ToString("O"));
        command.Parameters.AddWithValue("$transition_reason", CleanNullable(transitionReason) ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$review_revision", reviewRevision);
        command.Parameters.AddWithValue("$conflict_flag", conflictFlag ? 1 : 0);
        command.Parameters.AddWithValue("$conflict_basis", CleanNullable(conflictBasis) ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$synced_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$comment_id", commentId);
        if (command.ExecuteNonQuery() != 1)
        {
            throw new InvalidOperationException($"Field comment not found: {commentId}");
        }
        HistoryService.Record(
            connection,
            "field_comment.bulk_review_applied",
            actorName,
            "field_comment",
            commentId,
            commentId,
            $"서버 일괄 검토 결과 반영: {status} · revision {reviewRevision}",
            DateTime.UtcNow);
    }

    public FieldCommentAttachmentRecord AddAttachment(
        string commentId,
        string sourcePath,
        string createdBy,
        string? caption = null,
        DateTime? capturedAt = null,
        string? attachmentType = null)
    {
        if (string.IsNullOrWhiteSpace(commentId))
        {
            throw new ArgumentException("Field comment id is required.", nameof(commentId));
        }

        if (string.IsNullOrWhiteSpace(sourcePath) || !File.Exists(sourcePath))
        {
            throw new FileNotFoundException("Attachment source file was not found.", sourcePath);
        }

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        var note = LoadCommentTarget(connection, commentId)
            ?? throw new InvalidOperationException($"Field comment not found: {commentId}");

        var sourceFile = new FileInfo(sourcePath);
        var dataDirectory = Path.GetDirectoryName(database.DatabasePath)!;
        var attachmentRoot = Path.Combine(
            dataDirectory,
            "Files",
            "FieldCommentAttachments",
            now.ToString("yyyy-MM-dd"),
            commentId);
        Directory.CreateDirectory(attachmentRoot);

        var targetPath = GetUniqueTargetPath(attachmentRoot, sourceFile.Name);
        File.Copy(sourceFile.FullName, targetPath);
        var storedRelativePath = Path.GetRelativePath(dataDirectory, targetPath);
        var storedFile = new FileInfo(targetPath);
        var hash = ComputeSha256(targetPath);
        var extension = sourceFile.Extension.ToLowerInvariant();
        var normalizedAttachmentType = NormalizeAttachmentType(attachmentType, extension);
        var contentType = ContentTypeFromExtension(extension);
        var attachmentId = $"att-{Guid.NewGuid():N}";

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO field_comment_attachments (
                attachment_id,
                comment_id,
                local_path,
                original_file_name,
                extension,
                content_type,
                size_bytes,
                hash_sha256,
                attachment_type,
                caption,
                captured_at,
                created_by,
                created_at
            )
            VALUES (
                $attachment_id,
                $comment_id,
                $local_path,
                $original_file_name,
                $extension,
                $content_type,
                $size_bytes,
                $hash_sha256,
                $attachment_type,
                $caption,
                $captured_at,
                $created_by,
                $created_at
            );
            SELECT last_insert_rowid();
            """;
        insert.Parameters.AddWithValue("$attachment_id", attachmentId);
        insert.Parameters.AddWithValue("$comment_id", commentId);
        insert.Parameters.AddWithValue("$local_path", storedRelativePath);
        insert.Parameters.AddWithValue("$original_file_name", sourceFile.Name);
        insert.Parameters.AddWithValue("$extension", extension);
        insert.Parameters.AddWithValue("$content_type", string.IsNullOrWhiteSpace(contentType) ? DBNull.Value : contentType);
        insert.Parameters.AddWithValue("$size_bytes", storedFile.Length);
        insert.Parameters.AddWithValue("$hash_sha256", hash);
        insert.Parameters.AddWithValue("$attachment_type", normalizedAttachmentType);
        insert.Parameters.AddWithValue("$caption", string.IsNullOrWhiteSpace(caption) ? DBNull.Value : caption.Trim());
        insert.Parameters.AddWithValue("$captured_at", capturedAt is null ? DBNull.Value : capturedAt.Value.ToString("O"));
        insert.Parameters.AddWithValue("$created_by", createdBy);
        insert.Parameters.AddWithValue("$created_at", now.ToString("O"));
        var id = Convert.ToInt64(insert.ExecuteScalar());

        HistoryService.Record(
            connection,
            "field_comment.attachment_added",
            createdBy,
            "field_comment",
            commentId,
            note.DocumentTitle,
            $"Field comment attachment added: {sourceFile.Name}",
            now);

        return new FieldCommentAttachmentRecord(
            id,
            attachmentId,
            commentId,
            storedRelativePath,
            sourceFile.Name,
            extension,
            contentType,
            storedFile.Length,
            hash,
            normalizedAttachmentType,
            string.IsNullOrWhiteSpace(caption) ? null : caption.Trim(),
            capturedAt,
            createdBy,
            now,
            null,
            null);
    }

    public IReadOnlyList<FieldCommentAttachmentRecord> ListAttachments(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, attachment_id, comment_id, local_path, original_file_name, extension,
                   content_type, size_bytes, hash_sha256, attachment_type, caption,
                   captured_at, created_by, created_at, server_attachment_id, synced_at
            FROM field_comment_attachments
            WHERE comment_id = $comment_id
            ORDER BY created_at DESC, id DESC;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);

        using var reader = command.ExecuteReader();
        var records = new List<FieldCommentAttachmentRecord>();
        while (reader.Read())
        {
            records.Add(ReadAttachment(reader));
        }

        return records;
    }

    private static FieldCommentRecord ReadFieldComment(SqliteDataReader reader)
    {
        return new FieldCommentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetInt32(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.IsDBNull(9) ? null : reader.GetString(9),
            reader.GetString(10),
            reader.IsDBNull(11) ? null : reader.GetString(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            reader.GetString(13),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : reader.GetString(15),
            reader.GetString(16),
            DateTime.Parse(reader.GetString(17)),
            reader.IsDBNull(18) ? null : DateTime.Parse(reader.GetString(18)),
            reader.IsDBNull(19) ? null : reader.GetString(19),
            reader.IsDBNull(20) ? null : DateTime.Parse(reader.GetString(20)),
            reader.IsDBNull(21) ? null : reader.GetString(21),
            reader.GetInt32(22),
            reader.GetInt32(23) != 0,
            reader.IsDBNull(24) ? null : reader.GetString(24));
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

    private static FieldCommentRecord? LoadComment(SqliteConnection connection, string commentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at,
                   assigned_to, review_due_at, last_transition_reason, review_revision,
                   conflict_flag, conflict_basis
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadFieldComment(reader) : null;
    }

    private static void ValidateReviewStatus(string status)
    {
        if (!ReviewStatuses.Contains(status, StringComparer.Ordinal))
        {
            throw new ArgumentOutOfRangeException(nameof(status), "Unsupported FieldComment status.");
        }
    }

    private static void ValidateTransition(
        string currentStatus,
        string targetStatus,
        string? normalizedContent,
        string? analysisContent,
        string? reason)
    {
        if (string.Equals(currentStatus, targetStatus, StringComparison.Ordinal))
        {
            return;
        }

        var allowed = currentStatus switch
        {
            "NEW" => new[] { "ASSIGNED", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED" },
            "ASSIGNED" => new[] { "NEW", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED" },
            "NEEDS_REVIEW" => new[] { "NEW", "ASSIGNED", "ANALYZED", "EXCLUDED" },
            "ANALYZED" => new[] { "NEW", "NEEDS_REVIEW", "REVIEWED", "EXCLUDED" },
            "REVIEWED" => new[] { "ANALYZED", "SELECTED", "EXCLUDED" },
            "SELECTED" => new[] { "REVIEWED", "EXCLUDED", "ARCHIVED" },
            "EXCLUDED" => new[] { "NEW", "ARCHIVED" },
            "ARCHIVED" => new[] { "EXCLUDED" },
            _ => []
        };
        if (!allowed.Contains(targetStatus, StringComparer.Ordinal))
        {
            throw new InvalidOperationException($"허용되지 않은 상태 전이입니다: {currentStatus} → {targetStatus}");
        }
        if (string.IsNullOrWhiteSpace(reason) || reason.Length < 3)
        {
            throw new InvalidOperationException("상태 변경 사유를 3자 이상 입력하세요.");
        }
        if (targetStatus is "ANALYZED" or "REVIEWED" or "SELECTED" && string.IsNullOrWhiteSpace(analysisContent))
        {
            throw new InvalidOperationException("분석완료 이후 상태에는 분석 내용이 필요합니다.");
        }
        if (targetStatus is "REVIEWED" or "SELECTED" && string.IsNullOrWhiteSpace(normalizedContent))
        {
            throw new InvalidOperationException("검토완료 이후 상태에는 정리 내용이 필요합니다.");
        }
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

    private static string? CleanNullable(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static FieldCommentAttachmentRecord ReadAttachment(SqliteDataReader reader)
    {
        return new FieldCommentAttachmentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetInt64(7),
            reader.GetString(8),
            reader.GetString(9),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11)),
            reader.GetString(12),
            DateTime.Parse(reader.GetString(13)),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : DateTime.Parse(reader.GetString(15)));
    }

    private static CommentTarget? LoadCommentTarget(SqliteConnection connection, string commentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT note.comment_id, note.document_id, document.title
            FROM field_comments AS note
            LEFT JOIN documents AS document ON document.document_id = note.document_id
            WHERE note.comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new CommentTarget(
            reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2));
    }

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        var hashBytes = SHA256.HashData(stream);
        return Convert.ToHexString(hashBytes).ToLowerInvariant();
    }

    private static string NormalizeAttachmentType(string? attachmentType, string extension)
    {
        if (!string.IsNullOrWhiteSpace(attachmentType))
        {
            var normalized = attachmentType.Trim().ToLowerInvariant();
            return normalized is "photo" or "document" or "other"
                ? normalized
                : throw new ArgumentOutOfRangeException(nameof(attachmentType), "Unsupported attachment type.");
        }

        return extension switch
        {
            ".jpg" or ".jpeg" or ".png" or ".gif" or ".bmp" or ".webp" => "photo",
            ".pdf" or ".txt" or ".md" => "document",
            _ => "other"
        };
    }

    private static string? ContentTypeFromExtension(string extension)
    {
        return extension switch
        {
            ".jpg" or ".jpeg" => "image/jpeg",
            ".png" => "image/png",
            ".gif" => "image/gif",
            ".bmp" => "image/bmp",
            ".webp" => "image/webp",
            ".pdf" => "application/pdf",
            ".txt" => "text/plain",
            ".md" => "text/markdown",
            _ => null
        };
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

    private static void AddFieldCommentNotification(
        SqliteConnection connection,
        string documentId,
        string actorName,
        string note,
        DateTime createdAt)
    {
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT title, created_by
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$document_id", documentId);

        using var reader = lookup.ExecuteReader();
        if (!reader.Read())
        {
            return;
        }

        var documentTitle = reader.GetString(0);
        var recipientName = reader.GetString(1);
        reader.Close();

        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO notifications (notification_id, recipient_name, actor_name, document_id, document_title, message, is_read, created_at)
            VALUES ($notification_id, $recipient_name, $actor_name, $document_id, $document_title, $message, 0, $created_at);
            """;
        command.Parameters.AddWithValue("$notification_id", $"notification-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$recipient_name", recipientName);
        command.Parameters.AddWithValue("$actor_name", actorName);
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$document_title", documentTitle);
        command.Parameters.AddWithValue("$message", $"{actorName} added a field comment to '{documentTitle}': {note}");
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    private sealed record CommentTarget(string CommentId, string? DocumentId, string? DocumentTitle);
}
