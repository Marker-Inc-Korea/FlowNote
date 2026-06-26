using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Audit;

public sealed class DocumentViewLogService(FlowNoteLocalDatabase database)
{
    public long StartDocumentView(string documentId, int versionNo, string userName)
    {
        if (string.IsNullOrWhiteSpace(documentId))
        {
            throw new ArgumentException("Document id is required.", nameof(documentId));
        }

        if (versionNo < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(versionNo), "Version number must be positive.");
        }

        var normalizedUserName = string.IsNullOrWhiteSpace(userName) ? "unknown" : userName.Trim();
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO document_view_logs (document_id, version_no, user_name, view_started_at, closed_at, close_reason)
            VALUES ($document_id, $version_no, $user_name, $view_started_at, NULL, NULL);
            SELECT last_insert_rowid();
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        command.Parameters.AddWithValue("$user_name", normalizedUserName);
        command.Parameters.AddWithValue("$view_started_at", now.ToString("O"));

        return Convert.ToInt64(command.ExecuteScalar());
    }

    public void CloseDocumentView(long id, string closeReason)
    {
        var normalizedReason = string.IsNullOrWhiteSpace(closeReason) ? "window_closed" : closeReason.Trim();
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE document_view_logs
            SET closed_at = $closed_at,
                close_reason = $close_reason
            WHERE id = $id
              AND closed_at IS NULL;
            """;
        command.Parameters.AddWithValue("$closed_at", now.ToString("O"));
        command.Parameters.AddWithValue("$close_reason", normalizedReason);
        command.Parameters.AddWithValue("$id", id);
        command.ExecuteNonQuery();
    }

    public DocumentViewLogRecord? GetLog(long id)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, user_name, view_started_at, closed_at, close_reason
            FROM document_view_logs
            WHERE id = $id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$id", id);

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentViewLogRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt32(2),
            reader.GetString(3),
            DateTime.Parse(reader.GetString(4)),
            reader.IsDBNull(5) ? null : DateTime.Parse(reader.GetString(5)),
            reader.IsDBNull(6) ? null : reader.GetString(6));
    }
}
