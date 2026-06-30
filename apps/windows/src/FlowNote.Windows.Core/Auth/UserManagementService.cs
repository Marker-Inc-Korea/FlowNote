using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Auth;

public sealed class UserManagementService(FlowNoteLocalDatabase database)
{
    public IReadOnlyList<UserAccountRecord> ListUsers()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT user_id, login_id, display_name, role, status
            FROM user_accounts
            ORDER BY
                CASE role
                    WHEN 'admin' THEN 0
                    WHEN 'system-admin' THEN 1
                    WHEN 'document-admin' THEN 2
                    ELSE 3
                END,
                login_id;
            """;

        using var reader = command.ExecuteReader();
        var records = new List<UserAccountRecord>();
        while (reader.Read())
        {
            records.Add(new UserAccountRecord(
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4)));
        }

        return records;
    }

    public UserAccountRecord UpdateUserProfile(
        string userId,
        string displayName,
        string? newPassword,
        string actorName)
    {
        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new ArgumentException("사용자 ID가 필요합니다.", nameof(userId));
        }

        var normalizedDisplayName = displayName.Trim();
        if (string.IsNullOrWhiteSpace(normalizedDisplayName))
        {
            throw new ArgumentException("사용자 이름을 입력하세요.", nameof(displayName));
        }

        var shouldChangePassword = !string.IsNullOrWhiteSpace(newPassword);
        if (shouldChangePassword && string.IsNullOrWhiteSpace(newPassword!.Trim()))
        {
            throw new ArgumentException("새 비밀번호를 입력하세요.", nameof(newPassword));
        }

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = shouldChangePassword
            ? """
                UPDATE user_accounts
                SET display_name = $display_name,
                    password_hash = $password_hash
                WHERE user_id = $user_id;
                """
            : """
                UPDATE user_accounts
                SET display_name = $display_name
                WHERE user_id = $user_id;
                """;
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$display_name", normalizedDisplayName);
        if (shouldChangePassword)
        {
            command.Parameters.AddWithValue("$password_hash", PasswordHasher.Hash(newPassword!.Trim()));
        }

        if (command.ExecuteNonQuery() == 0)
        {
            throw new InvalidOperationException("사용자를 찾을 수 없습니다.");
        }

        RecordUserManagementHistory(connection, userId, normalizedDisplayName, actorName, shouldChangePassword);
        return GetUser(connection, userId)
            ?? throw new InvalidOperationException("저장 후 사용자 정보를 읽을 수 없습니다.");
    }

    private static UserAccountRecord? GetUser(Microsoft.Data.Sqlite.SqliteConnection connection, string userId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT user_id, login_id, display_name, role, status
            FROM user_accounts
            WHERE user_id = $user_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$user_id", userId);

        using var reader = command.ExecuteReader();
        return reader.Read()
            ? new UserAccountRecord(
                reader.GetString(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4))
            : null;
    }

    private static void RecordUserManagementHistory(
        Microsoft.Data.Sqlite.SqliteConnection connection,
        string userId,
        string displayName,
        string actorName,
        bool passwordChanged)
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
                'user.updated',
                $actor_name,
                'user',
                $target_id,
                $target_title,
                $message,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$history_id", $"history-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$actor_name", string.IsNullOrWhiteSpace(actorName) ? "admin" : actorName);
        command.Parameters.AddWithValue("$target_id", userId);
        command.Parameters.AddWithValue("$target_title", displayName);
        command.Parameters.AddWithValue(
            "$message",
            passwordChanged
                ? $"{displayName} 사용자 이름과 비밀번호를 변경했습니다."
                : $"{displayName} 사용자 이름을 변경했습니다.");
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }
}
