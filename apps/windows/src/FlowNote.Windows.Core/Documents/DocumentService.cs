using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Documents;

public sealed class DocumentService(FlowNoteLocalDatabase database)
{
    public DocumentRecord RegisterDocument(
        long folderId,
        string title,
        string fileName,
        string documentType,
        string createdBy)
    {
        var now = DateTime.UtcNow;
        var documentId = $"doc-{Guid.NewGuid():N}";

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO documents (document_id, folder_id, title, file_name, document_type, status, created_by, created_at)
            VALUES ($document_id, $folder_id, $title, $file_name, $document_type, 'WORKING', $created_by, $created_at);
            SELECT last_insert_rowid();
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$folder_id", folderId);
        command.Parameters.AddWithValue("$title", title);
        command.Parameters.AddWithValue("$file_name", fileName);
        command.Parameters.AddWithValue("$document_type", documentType);
        command.Parameters.AddWithValue("$created_by", createdBy);
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));

        var id = Convert.ToInt64(command.ExecuteScalar());
        return new DocumentRecord(id, documentId, folderId, title, fileName, documentType, "WORKING", createdBy, now);
    }

    public IReadOnlyList<DocumentRecord> ListDocuments(long? folderId = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = folderId is null
            ? """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
              FROM documents
              ORDER BY created_at DESC;
              """
            : """
              SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by, created_at
              FROM documents
              WHERE folder_id = $folder_id
              ORDER BY created_at DESC;
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
                DateTime.Parse(reader.GetString(8))));
        }

        return records;
    }
}
