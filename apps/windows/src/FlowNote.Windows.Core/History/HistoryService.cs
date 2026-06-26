using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.History;

public sealed class HistoryService(FlowNoteLocalDatabase database)
{
    public IReadOnlyList<HistoryRecord> ListHistory(int limit = 500)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, history_id, event_type, actor_name, target_type, target_id, target_title, message, created_at
            FROM activity_history
            ORDER BY created_at DESC, id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", limit);

        using var reader = command.ExecuteReader();
        var records = new List<HistoryRecord>();
        while (reader.Read())
        {
            records.Add(new HistoryRecord(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.GetString(7),
                DateTime.Parse(reader.GetString(8))));
        }

        return records;
    }

    public void Record(
        string eventType,
        string? actorName,
        string targetType,
        string? targetId,
        string? targetTitle,
        string message)
    {
        using var connection = database.OpenConnection();
        Record(
            connection,
            eventType,
            actorName,
            targetType,
            targetId,
            targetTitle,
            message,
            DateTime.UtcNow);
    }

    public static void Record(
        SqliteConnection connection,
        string eventType,
        string? actorName,
        string targetType,
        string? targetId,
        string? targetTitle,
        string message,
        DateTime createdAt)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO activity_history (
                history_id,
                event_type,
                actor_name,
                target_type,
                target_id,
                target_title,
                message,
                created_at
            )
            VALUES (
                $history_id,
                $event_type,
                $actor_name,
                $target_type,
                $target_id,
                $target_title,
                $message,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$history_id", $"history-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$event_type", Normalize(eventType, "unknown"));
        command.Parameters.AddWithValue("$actor_name", Normalize(actorName, "system"));
        command.Parameters.AddWithValue("$target_type", Normalize(targetType, "unknown"));
        command.Parameters.AddWithValue("$target_id", string.IsNullOrWhiteSpace(targetId) ? DBNull.Value : targetId.Trim());
        command.Parameters.AddWithValue("$target_title", string.IsNullOrWhiteSpace(targetTitle) ? DBNull.Value : targetTitle.Trim());
        command.Parameters.AddWithValue("$message", Normalize(message, eventType));
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static string Normalize(string? value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
    }
}
