using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Notifications;

public sealed class NotificationService(FlowNoteLocalDatabase database)
{
    public IReadOnlyList<NotificationRecord> ListNotifications(string recipientName)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, notification_id, recipient_name, actor_name, document_id, document_title, message, is_read, created_at
            FROM notifications
            WHERE recipient_name = $recipient_name
            ORDER BY created_at DESC, id DESC;
            """;
        command.Parameters.AddWithValue("$recipient_name", recipientName);

        using var reader = command.ExecuteReader();
        var records = new List<NotificationRecord>();
        while (reader.Read())
        {
            records.Add(new NotificationRecord(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetString(5),
                reader.GetString(6),
                reader.GetInt64(7) == 1,
                DateTime.Parse(reader.GetString(8))));
        }

        return records;
    }

    public int CountUnread(string recipientName)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT COUNT(1)
            FROM notifications
            WHERE recipient_name = $recipient_name AND is_read = 0;
            """;
        command.Parameters.AddWithValue("$recipient_name", recipientName);
        return Convert.ToInt32(command.ExecuteScalar());
    }

    public void MarkAllAsRead(string recipientName)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE notifications
            SET is_read = 1
            WHERE recipient_name = $recipient_name AND is_read = 0;
            """;
        command.Parameters.AddWithValue("$recipient_name", recipientName);
        command.ExecuteNonQuery();
    }
}
