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
        return UpdateUserProfile(userId, displayName, null, newPassword, actorName);
    }

    public UserAccountRecord UpdateUserProfile(
        string userId,
        string displayName,
        string? role,
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

        var normalizedRole = string.IsNullOrWhiteSpace(role) ? null : role.Trim();
        if (normalizedRole is not null && !RolePermissionPolicy.IsAllowedUserRole(normalizedRole))
        {
            throw new ArgumentException("사용자 권한을 선택하세요.", nameof(role));
        }

        var shouldChangePassword = !string.IsNullOrWhiteSpace(newPassword);
        if (shouldChangePassword && string.IsNullOrWhiteSpace(newPassword!.Trim()))
        {
            throw new ArgumentException("새 비밀번호를 입력하세요.", nameof(newPassword));
        }

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        var setClauses = new List<string> { "display_name = $display_name" };
        if (normalizedRole is not null)
        {
            setClauses.Add("role = $role");
        }

        if (shouldChangePassword)
        {
            setClauses.Add("password_hash = $password_hash");
        }

        command.CommandText = $"""
            UPDATE user_accounts
            SET {string.Join(", ", setClauses)}
            WHERE user_id = $user_id;
            """;
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$display_name", normalizedDisplayName);
        if (normalizedRole is not null)
        {
            command.Parameters.AddWithValue("$role", normalizedRole);
        }

        if (shouldChangePassword)
        {
            command.Parameters.AddWithValue("$password_hash", PasswordHasher.Hash(newPassword!.Trim()));
        }

        if (command.ExecuteNonQuery() == 0)
        {
            throw new InvalidOperationException("사용자를 찾을 수 없습니다.");
        }

        RecordUserManagementHistory(
            connection,
            userId,
            normalizedDisplayName,
            actorName,
            "user.updated",
            shouldChangePassword
                ? $"{normalizedDisplayName} 사용자 정보를 변경했습니다. 비밀번호도 함께 변경했습니다."
                : $"{normalizedDisplayName} 사용자 정보를 변경했습니다.");
        return GetUser(connection, userId)
            ?? throw new InvalidOperationException("저장 후 사용자 정보를 읽을 수 없습니다.");
    }

    public UserAccountRecord CreateUser(
        string loginId,
        string displayName,
        string role,
        string password,
        string actorName)
    {
        var normalizedLoginId = NormalizeLoginId(loginId);
        var normalizedDisplayName = displayName.Trim();
        var normalizedRole = role.Trim();
        var normalizedPassword = password.Trim();

        if (string.IsNullOrWhiteSpace(normalizedDisplayName))
        {
            throw new ArgumentException("사용자 이름을 입력하세요.", nameof(displayName));
        }

        if (!RolePermissionPolicy.IsAllowedUserRole(normalizedRole))
        {
            throw new ArgumentException("사용자 권한을 선택하세요.", nameof(role));
        }

        if (string.IsNullOrWhiteSpace(normalizedPassword))
        {
            throw new ArgumentException("새 사용자의 비밀번호를 입력하세요.", nameof(password));
        }

        var userId = $"user-{normalizedLoginId}";
        using var connection = database.OpenConnection();
        if (LoginIdExists(connection, normalizedLoginId))
        {
            throw new InvalidOperationException("이미 사용 중인 로그인 ID입니다.");
        }

        if (UserIdExists(connection, userId))
        {
            throw new InvalidOperationException("자동 생성된 사용자 ID가 이미 존재합니다. 다른 로그인 ID를 입력하세요.");
        }

        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO user_accounts (
                user_id,
                login_id,
                display_name,
                password_hash,
                role,
                status,
                created_at
            )
            VALUES (
                $user_id,
                $login_id,
                $display_name,
                $password_hash,
                $role,
                'ACTIVE',
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$login_id", normalizedLoginId);
        command.Parameters.AddWithValue("$display_name", normalizedDisplayName);
        command.Parameters.AddWithValue("$password_hash", PasswordHasher.Hash(normalizedPassword));
        command.Parameters.AddWithValue("$role", normalizedRole);
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();

        RecordUserManagementHistory(
            connection,
            userId,
            normalizedDisplayName,
            actorName,
            "user.created",
            $"{normalizedDisplayName} 사용자를 추가했습니다.");
        return GetUser(connection, userId)
            ?? throw new InvalidOperationException("추가 후 사용자 정보를 읽을 수 없습니다.");
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

    private static string NormalizeLoginId(string loginId)
    {
        var normalized = loginId.Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            throw new ArgumentException("로그인 ID를 입력하세요.", nameof(loginId));
        }

        if (normalized.Any(char.IsWhiteSpace))
        {
            throw new ArgumentException("로그인 ID에는 공백을 사용할 수 없습니다.", nameof(loginId));
        }

        if (normalized.Any(character => !(char.IsLetterOrDigit(character) || character is '-' or '_' or '.')))
        {
            throw new ArgumentException("로그인 ID는 영문, 숫자, 하이픈, 밑줄, 점만 사용할 수 있습니다.", nameof(loginId));
        }

        return normalized;
    }

    private static bool LoginIdExists(Microsoft.Data.Sqlite.SqliteConnection connection, string loginId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1 FROM user_accounts WHERE login_id = $login_id LIMIT 1;";
        command.Parameters.AddWithValue("$login_id", loginId);
        return command.ExecuteScalar() is not null;
    }

    private static bool UserIdExists(Microsoft.Data.Sqlite.SqliteConnection connection, string userId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1 FROM user_accounts WHERE user_id = $user_id LIMIT 1;";
        command.Parameters.AddWithValue("$user_id", userId);
        return command.ExecuteScalar() is not null;
    }

    private static void RecordUserManagementHistory(
        Microsoft.Data.Sqlite.SqliteConnection connection,
        string userId,
        string displayName,
        string actorName,
        string eventType,
        string message)
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
                'user',
                $target_id,
                $target_title,
                $message,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$history_id", $"history-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$event_type", eventType);
        command.Parameters.AddWithValue("$actor_name", string.IsNullOrWhiteSpace(actorName) ? "admin" : actorName);
        command.Parameters.AddWithValue("$target_id", userId);
        command.Parameters.AddWithValue("$target_title", displayName);
        command.Parameters.AddWithValue("$message", message);
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }
}
