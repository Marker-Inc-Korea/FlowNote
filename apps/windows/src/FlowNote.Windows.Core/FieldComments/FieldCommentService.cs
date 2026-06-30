using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;
using FlowNote.Windows.Core.History;
using System.Security.Cryptography;

namespace FlowNote.Windows.Core.FieldComments;

public sealed class FieldCommentService(FlowNoteLocalDatabase database)
{
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
            null);
    }

    public IReadOnlyList<FieldCommentRecord> ListDocumentComments(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at
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
            reader.IsDBNull(18) ? null : DateTime.Parse(reader.GetString(18)));
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
