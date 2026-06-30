using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Notifications;

public sealed class NotificationService(FlowNoteLocalDatabase database)
{
    public IReadOnlyList<NotificationRecord> ListNotifications(string recipientName)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id,
                   notification_id,
                   COALESCE(notification_type, 'document'),
                   recipient_name,
                   actor_name,
                   document_id,
                   document_title,
                   target_type,
                   target_id,
                   target_title,
                   source_candidate_id,
                   message,
                   is_read,
                   created_at
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
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : reader.GetString(9),
                reader.IsDBNull(10) ? null : reader.GetString(10),
                reader.GetString(11),
                reader.GetInt64(12) == 1,
                DateTime.Parse(reader.GetString(13))));
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

    public void MarkAsRead(string notificationId, string recipientName)
    {
        using var connection = database.OpenConnection();
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT COALESCE(notification_type, 'document'),
                   target_type,
                   target_id,
                   COALESCE(target_title, document_title),
                   message
            FROM notifications
            WHERE notification_id = $notification_id
              AND recipient_name = $recipient_name
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$notification_id", notificationId);
        lookup.Parameters.AddWithValue("$recipient_name", recipientName);

        string? notificationType;
        string? targetType;
        string? targetId;
        string? targetTitle;
        string? message;
        using (var reader = lookup.ExecuteReader())
        {
            if (!reader.Read())
            {
                return;
            }

            notificationType = reader.GetString(0);
            targetType = reader.IsDBNull(1) ? null : reader.GetString(1);
            targetId = reader.IsDBNull(2) ? null : reader.GetString(2);
            targetTitle = reader.IsDBNull(3) ? null : reader.GetString(3);
            message = reader.GetString(4);
        }

        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE notifications
            SET is_read = 1
            WHERE notification_id = $notification_id
              AND recipient_name = $recipient_name
              AND is_read = 0;
            """;
        command.Parameters.AddWithValue("$notification_id", notificationId);
        command.Parameters.AddWithValue("$recipient_name", recipientName);
        var changed = command.ExecuteNonQuery();
        if (changed > 0)
        {
            HistoryService.Record(
                connection,
                notificationType == "work_sequence" ? "work_sequence.notification_read" : "notification.read",
                recipientName,
                string.IsNullOrWhiteSpace(targetType) ? "notification" : targetType,
                string.IsNullOrWhiteSpace(targetId) ? notificationId : targetId,
                targetTitle,
                $"Notification read: {message}",
                DateTime.UtcNow);
        }
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
        var changed = command.ExecuteNonQuery();
        if (changed > 0)
        {
            HistoryService.Record(
                connection,
                "notification.read_all",
                recipientName,
                "notification",
                null,
                recipientName,
                $"All notifications read: {recipientName} ({changed})",
                DateTime.UtcNow);
        }
    }
}
