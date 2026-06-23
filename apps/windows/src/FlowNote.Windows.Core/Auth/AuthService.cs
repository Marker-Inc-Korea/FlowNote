using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Auth;

public sealed class AuthService(FlowNoteLocalDatabase database)
{
    public LoginResult Login(string loginId, string password)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT user_id, login_id, display_name, password_hash, role, status
            FROM user_accounts
            WHERE login_id = $login_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$login_id", loginId);

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return LoginResult.Failed("Invalid login id or password.");
        }

        var status = reader.GetString(5);
        if (!string.Equals(status, "ACTIVE", StringComparison.OrdinalIgnoreCase))
        {
            return LoginResult.Failed("This account is not active.");
        }

        var passwordHash = reader.GetString(3);
        if (!string.Equals(passwordHash, PasswordHasher.Hash(password), StringComparison.Ordinal))
        {
            return LoginResult.Failed("Invalid login id or password.");
        }

        return new LoginResult(
            true,
            reader.GetString(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(4),
            null);
    }
}
