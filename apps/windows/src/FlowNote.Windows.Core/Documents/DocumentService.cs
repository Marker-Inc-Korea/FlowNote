using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Documents;

public sealed class DocumentService(FlowNoteLocalDatabase database)
{
    public DocumentRecord RegisterDocument(
        long folderId,
        string title,
        string fileName,
        string documentType,
        string createdBy,
        string? localPath = null)
    {
        var now = DateTime.UtcNow;
        var documentId = $"doc-{Guid.NewGuid():N}";

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO documents (document_id, folder_id, title, file_name, document_type, status, created_by, created_at, updated_at, local_path, version_no, latest_comment)
            VALUES ($document_id, $folder_id, $title, $file_name, $document_type, 'WORKING', $created_by, $created_at, $updated_at, $local_path, 1, NULL);
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
            INSERT INTO document_versions (document_id, version_no, file_name, local_path, comment, created_by, created_at)
            VALUES ($document_id, 1, $file_name, $local_path, NULL, $created_by, $created_at);
            """;
        version.Parameters.AddWithValue("$document_id", documentId);
        version.Parameters.AddWithValue("$file_name", fileName);
        version.Parameters.AddWithValue("$local_path", string.IsNullOrWhiteSpace(localPath) ? DBNull.Value : localPath);
        version.Parameters.AddWithValue("$created_by", createdBy);
        version.Parameters.AddWithValue("$created_at", now.ToString("O"));
        version.ExecuteNonQuery();

        return new DocumentRecord(id, documentId, folderId, title, fileName, documentType, "WORKING", createdBy, now, now, localPath, 1, null);
    }

    public IReadOnlyList<DocumentRecord> ListDocuments(long? folderId = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = folderId is null
            ? """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
                   , updated_at, local_path, version_no, latest_comment
              FROM documents
              ORDER BY updated_at DESC;
              """
            : """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
                   , updated_at, local_path, version_no, latest_comment
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
            records.Add(new DocumentRecord(
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
                reader.IsDBNull(12) ? null : reader.GetString(12)));
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
            SELECT id, folder_id, title, file_name, document_type, status, created_by, created_at, updated_at, local_path, version_no
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
        var nextVersion = reader.GetInt32(10) + 1;
        reader.Close();

        var now = DateTime.UtcNow;
        using var insertVersion = connection.CreateCommand();
        insertVersion.CommandText = """
            INSERT INTO document_versions (document_id, version_no, file_name, local_path, comment, created_by, created_at)
            VALUES ($document_id, $version_no, $file_name, $local_path, $comment, $created_by, $created_at);
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

        return new DocumentRecord(id, documentId, folderId, title, fileName, documentType, status, originalCreatedBy, createdAt, now, localPath, nextVersion, comment.Trim());
    }

    public IReadOnlyList<DocumentVersionRecord> ListVersions(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, file_name, local_path, comment, created_by, created_at
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
                DateTime.Parse(reader.GetString(7))));
        }

        return records;
    }
}
