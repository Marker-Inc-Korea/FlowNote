using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Tags;
using FlowNote.Windows.Core.History;

namespace FlowNote.Windows.Core.Documents;

public sealed class DocumentService(FlowNoteLocalDatabase database)
{
    public DocumentRecord RegisterDocument(
        long folderId,
        string title,
        string fileName,
        string documentType,
        string createdBy,
        string? localPath = null,
        IEnumerable<string>? tags = null)
    {
        var now = DateTime.UtcNow;
        var documentId = $"doc-{Guid.NewGuid():N}";

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO documents (document_id, folder_id, title, file_name, document_type, status, created_by, created_at, updated_at, local_path, version_no, published_version_no, latest_comment)
            VALUES ($document_id, $folder_id, $title, $file_name, $document_type, 'WORKING', $created_by, $created_at, $updated_at, $local_path, 1, NULL, NULL);
            SELECT last_insert_rowid();
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$folder_id", folderId);
        command.Parameters.AddWithValue("$title", title);
        command.Parameters.AddWithValue("$file_name", fileName);
        command.Parameters.AddWithValue("$document_type", documentType);
        command.Parameters.AddWithValue("$created_by", createdBy);
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));
        command.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        command.Parameters.AddWithValue("$local_path", string.IsNullOrWhiteSpace(localPath) ? DBNull.Value : localPath);

        var id = Convert.ToInt64(command.ExecuteScalar());

        using var version = connection.CreateCommand();
        version.CommandText = """
            INSERT INTO document_versions (document_id, version_no, file_name, local_path, comment, version_status, is_latest, is_published, published_at, created_by, created_at)
            VALUES ($document_id, 1, $file_name, $local_path, NULL, 'WORKING', 1, 0, NULL, $created_by, $created_at);
            """;
        version.Parameters.AddWithValue("$document_id", documentId);
        version.Parameters.AddWithValue("$file_name", fileName);
        version.Parameters.AddWithValue("$local_path", string.IsNullOrWhiteSpace(localPath) ? DBNull.Value : localPath);
        version.Parameters.AddWithValue("$created_by", createdBy);
        version.Parameters.AddWithValue("$created_at", now.ToString("O"));
        version.ExecuteNonQuery();

        var cleanedTags = TagService.CleanTags(tags);
        TagService.ReplaceDocumentTags(connection, documentId, cleanedTags);
        HistoryService.Record(
            connection,
            "document.registered",
            createdBy,
            "document",
            documentId,
            title,
            $"문서 등록: {title} ({fileName})",
            now);

        return new DocumentRecord(
            id,
            documentId,
            folderId,
            title,
            fileName,
            documentType,
            "WORKING",
            createdBy,
            now,
            now,
            localPath,
            1,
            null,
            cleanedTags);
    }

    public IReadOnlyList<DocumentRecord> ListDocuments(long? folderId = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = folderId is null
            ? """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
                   , updated_at, local_path, version_no, latest_comment, published_version_no
              FROM documents
              ORDER BY updated_at DESC;
              """
            : """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
                   , updated_at, local_path, version_no, latest_comment, published_version_no
              FROM documents
              WHERE folder_id = $folder_id
              ORDER BY updated_at DESC;
              """;

        if (folderId is not null)
        {
            command.Parameters.AddWithValue("$folder_id", folderId.Value);
        }

        using var reader = command.ExecuteReader();
        var records = new List<DocumentRecord>();
        while (reader.Read())
        {
            var documentId = reader.GetString(1);
            records.Add(new DocumentRecord(
                reader.GetInt64(0),
                documentId,
                reader.GetInt64(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetString(5),
                reader.GetString(6),
                reader.GetString(7),
                DateTime.Parse(reader.GetString(8)),
                DateTime.Parse(reader.GetString(9)),
                reader.IsDBNull(10) ? null : reader.GetString(10),
                reader.GetInt32(11),
                reader.IsDBNull(12) ? null : reader.GetString(12),
                TagService.ListDocumentTags(connection, documentId),
                reader.IsDBNull(13) ? null : reader.GetInt32(13)));
        }

        return records;
    }

    public DocumentRecord AddCommentVersion(string documentId, string comment, string createdBy)
    {
        if (string.IsNullOrWhiteSpace(comment))
        {
            throw new ArgumentException("Comment is required.", nameof(comment));
        }

        using var connection = database.OpenConnection();
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT id, folder_id, title, file_name, document_type, status, created_by, created_at, updated_at, local_path, version_no, published_version_no
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$document_id", documentId);

        using var reader = lookup.ExecuteReader();
        if (!reader.Read())
        {
            throw new InvalidOperationException($"Document not found: {documentId}");
        }

        var id = reader.GetInt64(0);
        var folderId = reader.GetInt64(1);
        var title = reader.GetString(2);
        var fileName = reader.GetString(3);
        var documentType = reader.GetString(4);
        var status = reader.GetString(5);
        var originalCreatedBy = reader.GetString(6);
        var createdAt = DateTime.Parse(reader.GetString(7));
        var localPath = reader.IsDBNull(9) ? null : reader.GetString(9);
        var currentVersion = reader.GetInt32(10);
        int? publishedVersionNo = reader.IsDBNull(11) ? null : reader.GetInt32(11);
        var nextVersion = currentVersion + 1;
        reader.Close();

        var previousVersionAuthor = FindVersionAuthor(connection, documentId, currentVersion) ?? originalCreatedBy;

        var now = DateTime.UtcNow;
        using var markPreviousLatest = connection.CreateCommand();
        markPreviousLatest.CommandText = """
            UPDATE document_versions
            SET is_latest = 0,
                version_status = CASE
                    WHEN is_published = 1 THEN 'PUBLISHED'
                    ELSE 'SUPERSEDED'
                END
            WHERE document_id = $document_id AND is_latest = 1;
            """;
        markPreviousLatest.Parameters.AddWithValue("$document_id", documentId);
        markPreviousLatest.ExecuteNonQuery();

        using var insertVersion = connection.CreateCommand();
        insertVersion.CommandText = """
            INSERT INTO document_versions (document_id, version_no, file_name, local_path, comment, version_status, is_latest, is_published, published_at, created_by, created_at)
            VALUES ($document_id, $version_no, $file_name, $local_path, $comment, 'WORKING', 1, 0, NULL, $created_by, $created_at);
            """;
        insertVersion.Parameters.AddWithValue("$document_id", documentId);
        insertVersion.Parameters.AddWithValue("$version_no", nextVersion);
        insertVersion.Parameters.AddWithValue("$file_name", fileName);
        insertVersion.Parameters.AddWithValue("$local_path", string.IsNullOrWhiteSpace(localPath) ? DBNull.Value : localPath);
        insertVersion.Parameters.AddWithValue("$comment", comment.Trim());
        insertVersion.Parameters.AddWithValue("$created_by", createdBy);
        insertVersion.Parameters.AddWithValue("$created_at", now.ToString("O"));
        insertVersion.ExecuteNonQuery();

        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE documents
            SET version_no = $version_no,
                latest_comment = $comment,
                updated_at = $updated_at
            WHERE document_id = $document_id;
            """;
        update.Parameters.AddWithValue("$version_no", nextVersion);
        update.Parameters.AddWithValue("$comment", comment.Trim());
        update.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        update.Parameters.AddWithValue("$document_id", documentId);
        update.ExecuteNonQuery();

        AddCommentNotification(
            connection,
            previousVersionAuthor,
            createdBy,
            documentId,
            title,
            nextVersion,
            comment.Trim(),
            now);
        HistoryService.Record(
            connection,
            "document.version_added",
            createdBy,
            "document",
            documentId,
            title,
            $"문서 버전 증가: {title} v{nextVersion}",
            now);

        return new DocumentRecord(
            id,
            documentId,
            folderId,
            title,
            fileName,
            documentType,
            status,
            originalCreatedBy,
            createdAt,
            now,
            localPath,
            nextVersion,
            comment.Trim(),
            TagService.ListDocumentTags(connection, documentId),
            publishedVersionNo);
    }

    private static string? FindVersionAuthor(Microsoft.Data.Sqlite.SqliteConnection connection, string documentId, int versionNo)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT created_by
            FROM document_versions
            WHERE document_id = $document_id AND version_no = $version_no
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        return command.ExecuteScalar() as string;
    }

    private static void AddCommentNotification(
        Microsoft.Data.Sqlite.SqliteConnection connection,
        string recipientName,
        string actorName,
        string documentId,
        string documentTitle,
        int versionNo,
        string comment,
        DateTime createdAt)
    {
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
        command.Parameters.AddWithValue("$message", $"{actorName}님이 '{documentTitle}' 문서에 v{versionNo} 코멘트를 남겼습니다: {comment}");
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    public DocumentRecord UpdateDocumentStatus(string documentId, string status, string actorName)
    {
        var normalizedStatus = NormalizeDocumentStatus(status);
        using var connection = database.OpenConnection();
        var existing = LoadDocument(connection, documentId)
            ?? throw new InvalidOperationException($"Document not found: {documentId}");

        if (normalizedStatus == "PUBLISHED" && existing.PublishedVersionNo is null)
        {
            throw new InvalidOperationException("Document cannot be published without a published version.");
        }

        if (string.Equals(existing.Status, normalizedStatus, StringComparison.Ordinal))
        {
            return existing;
        }

        var now = DateTime.UtcNow;
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE documents
            SET status = $status,
                updated_at = $updated_at
            WHERE document_id = $document_id;
            """;
        update.Parameters.AddWithValue("$status", normalizedStatus);
        update.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        update.Parameters.AddWithValue("$document_id", documentId);
        update.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "document.status_changed",
            actorName,
            "document",
            documentId,
            existing.Title,
            $"Document status changed: {existing.Status} -> {normalizedStatus}",
            now);

        return LoadDocument(connection, documentId)
            ?? throw new InvalidOperationException($"Document not found after status update: {documentId}");
    }

    public DocumentRecord PublishVersion(string documentId, int versionNo, string actorName)
    {
        using var connection = database.OpenConnection();
        var existing = LoadDocument(connection, documentId)
            ?? throw new InvalidOperationException($"Document not found: {documentId}");
        var version = ListVersions(documentId).FirstOrDefault(item => item.VersionNo == versionNo)
            ?? throw new InvalidOperationException($"Document version not found: {documentId} v{versionNo}");

        var now = DateTime.UtcNow;
        using var clearPublished = connection.CreateCommand();
        clearPublished.CommandText = """
            UPDATE document_versions
            SET is_published = 0,
                published_at = NULL,
                version_status = CASE
                    WHEN is_latest = 1 THEN 'WORKING'
                    ELSE 'SUPERSEDED'
                END
            WHERE document_id = $document_id AND is_published = 1;
            """;
        clearPublished.Parameters.AddWithValue("$document_id", documentId);
        clearPublished.ExecuteNonQuery();

        using var publish = connection.CreateCommand();
        publish.CommandText = """
            UPDATE document_versions
            SET is_published = 1,
                published_at = $published_at,
                version_status = 'PUBLISHED'
            WHERE document_id = $document_id AND version_no = $version_no;

            UPDATE documents
            SET status = 'PUBLISHED',
                published_version_no = $version_no,
                updated_at = $updated_at
            WHERE document_id = $document_id;
            """;
        publish.Parameters.AddWithValue("$published_at", now.ToString("O"));
        publish.Parameters.AddWithValue("$document_id", documentId);
        publish.Parameters.AddWithValue("$version_no", versionNo);
        publish.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        publish.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "document.version_published",
            actorName,
            "document",
            documentId,
            existing.Title,
            $"Document version published: {existing.Title} v{version.VersionNo}",
            now);

        if (!string.Equals(existing.Status, "PUBLISHED", StringComparison.Ordinal))
        {
            HistoryService.Record(
                connection,
                "document.status_changed",
                actorName,
                "document",
                documentId,
                existing.Title,
                $"Document status changed: {existing.Status} -> PUBLISHED",
                now);
        }

        return LoadDocument(connection, documentId)
            ?? throw new InvalidOperationException($"Document not found after publish: {documentId}");
    }

    public IReadOnlyList<DocumentVersionRecord> ListVersions(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, file_name, local_path, comment, created_by, created_at,
                   version_status, is_latest, is_published, published_at
            FROM document_versions
            WHERE document_id = $document_id
            ORDER BY version_no DESC;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);

        using var reader = command.ExecuteReader();
        var records = new List<DocumentVersionRecord>();
        while (reader.Read())
        {
            records.Add(new DocumentVersionRecord(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetInt32(2),
                reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.GetString(6),
                DateTime.Parse(reader.GetString(7)),
                reader.GetString(8),
                reader.GetInt32(9) == 1,
                reader.GetInt32(10) == 1,
                reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11))));
        }

        return records;
    }

    private static DocumentRecord? LoadDocument(Microsoft.Data.Sqlite.SqliteConnection connection, string documentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by,
                   created_at, updated_at, local_path, version_no, latest_comment, published_version_no
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt64(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.GetString(6),
            reader.GetString(7),
            DateTime.Parse(reader.GetString(8)),
            DateTime.Parse(reader.GetString(9)),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.GetInt32(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            TagService.ListDocumentTags(connection, documentId),
            reader.IsDBNull(13) ? null : reader.GetInt32(13));
    }

    private static string NormalizeDocumentStatus(string status)
    {
        var normalized = status.Trim().ToUpperInvariant();
        return normalized switch
        {
            "WORKING" or "IN_REVIEW" or "PUBLISHED" or "ARCHIVED" => normalized,
            _ => throw new ArgumentOutOfRangeException(nameof(status), "Unsupported document status.")
        };
    }
}
