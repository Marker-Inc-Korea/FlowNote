using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.FieldNotes;

public sealed class FieldNoteService(FlowNoteLocalDatabase database)
{
    public FieldNoteRecord AddDocumentNote(
        string documentId,
        string rawContent,
        string authorName,
        string noteType = "issue",
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
            throw new ArgumentException("Field note content is required.", nameof(rawContent));
        }

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT version_no
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$document_id", documentId);
        var versionValue = lookup.ExecuteScalar();
        if (versionValue is null)
        {
            throw new InvalidOperationException($"Document not found: {documentId}");
        }

        var documentVersionNo = Convert.ToInt32(versionValue);
        var noteId = $"note-{Guid.NewGuid():N}";

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO field_notes (
                note_id,
                document_id,
                document_version_no,
                note_type,
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
                $note_id,
                $document_id,
                $document_version_no,
                $note_type,
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
        insert.Parameters.AddWithValue("$note_id", noteId);
        insert.Parameters.AddWithValue("$document_id", documentId);
        insert.Parameters.AddWithValue("$document_version_no", documentVersionNo);
        insert.Parameters.AddWithValue("$note_type", noteType);
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

        AddFieldNoteNotification(connection, documentId, authorName, content, now);

        return new FieldNoteRecord(
            id,
            noteId,
            documentId,
            documentVersionNo,
            noteType,
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

    public IReadOnlyList<FieldNoteRecord> ListDocumentNotes(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, note_id, document_id, document_version_no, note_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at
            FROM field_notes
            WHERE document_id = $document_id
            ORDER BY created_at DESC, id DESC;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);

        using var reader = command.ExecuteReader();
        var records = new List<FieldNoteRecord>();
        while (reader.Read())
        {
            records.Add(ReadFieldNote(reader));
        }

        return records;
    }

    private static FieldNoteRecord ReadFieldNote(SqliteDataReader reader)
    {
        return new FieldNoteRecord(
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

    private static void AddFieldNoteNotification(
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
        command.Parameters.AddWithValue("$message", $"{actorName} added a field note to '{documentTitle}': {note}");
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();
    }
}
