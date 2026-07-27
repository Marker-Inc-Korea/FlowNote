using System.Security.Cryptography;
using Microsoft.Data.Sqlite;

internal static class ServerSmokeSystemAdmin
{
    public const string DatabasePathEnvironmentVariable =
        "FLOWNOTE_SMOKE_SERVER_DATABASE_PATH";

    public static void EnsureAccount(
        string username,
        string displayName,
        string password)
    {
        RequireTestEnvironment();
        var databasePath = ResolveDatabasePath();
        using var connection = new SqliteConnection(
            new SqliteConnectionStringBuilder { DataSource = databasePath }.ToString());
        connection.Open();

        using var existing = connection.CreateCommand();
        existing.CommandText =
            "SELECT COUNT(*) FROM user_accounts WHERE login_id = $login_id;";
        existing.Parameters.AddWithValue("$login_id", username);
        if (Convert.ToInt64(existing.ExecuteScalar()) > 0)
        {
            return;
        }

        using var command = connection.CreateCommand();
        command.CommandText =
            """
            INSERT INTO user_accounts (
                user_id,
                username,
                login_id,
                display_name,
                role,
                password_hash,
                is_active,
                status,
                must_change_password,
                created_at,
                updated_at
            )
            VALUES (
                $user_id,
                $username,
                $login_id,
                $display_name,
                'system-admin',
                $password_hash,
                1,
                'ACTIVE',
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            );
            """;
        command.Parameters.AddWithValue("$user_id", $"user-{username}");
        command.Parameters.AddWithValue("$username", username);
        command.Parameters.AddWithValue("$login_id", username);
        command.Parameters.AddWithValue("$display_name", displayName);
        command.Parameters.AddWithValue("$password_hash", HashPassword(password));
        command.ExecuteNonQuery();
    }

    private static void RequireTestEnvironment()
    {
        if (!string.Equals(
                Environment.GetEnvironmentVariable("FLOWNOTE_ENVIRONMENT"),
                "test",
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "스모크 system-admin 준비는 FLOWNOTE_ENVIRONMENT=test에서만 허용됩니다.");
        }
    }

    private static string ResolveDatabasePath()
    {
        var value = Environment.GetEnvironmentVariable(
            DatabasePathEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException(
                $"{DatabasePathEnvironmentVariable}가 필요합니다.");
        }

        var fullPath = Path.GetFullPath(value);
        if (!string.Equals(
                Path.GetFileName(fullPath),
                "flownote.windows-smoke.sqlite3",
                StringComparison.OrdinalIgnoreCase) ||
            !File.Exists(fullPath))
        {
            throw new InvalidOperationException(
                "승인된 Windows 스모크 서버 SQLite 경로가 아닙니다.");
        }
        return fullPath;
    }

    private static string HashPassword(string password)
    {
        const int iterations = 100_000;
        var salt = Convert.ToHexString(RandomNumberGenerator.GetBytes(16))
            .ToLowerInvariant();
        var digest = Rfc2898DeriveBytes.Pbkdf2(
            password,
            System.Text.Encoding.UTF8.GetBytes(salt),
            iterations,
            HashAlgorithmName.SHA256,
            32);
        return $"pbkdf2_sha256${iterations}${salt}$" +
            Convert.ToHexString(digest).ToLowerInvariant();
    }
}
