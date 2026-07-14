using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Notifications;

public sealed class ServerNotificationCursorService(FlowNoteLocalDatabase database)
{
    public const string ActiveStatus = "ACTIVE";
    public const string ResetRequiredStatus = "RESET_REQUIRED";

    public static string NormalizeServerScope(Uri baseAddress)
    {
        if (!baseAddress.IsAbsoluteUri)
        {
            throw new ArgumentException("서버 URL은 절대 URL이어야 합니다.", nameof(baseAddress));
        }

        var builder = new UriBuilder(baseAddress)
        {
            Fragment = string.Empty,
            Query = string.Empty,
            UserName = string.Empty,
            Password = string.Empty,
            Host = baseAddress.IdnHost.ToLowerInvariant()
        };
        var path = builder.Path.TrimEnd('/');
        builder.Path = string.IsNullOrEmpty(path) ? "/" : $"{path}/";
        return builder.Uri.AbsoluteUri;
    }

    public ServerNotificationCursorRecord Get(string serverScope, string userId)
    {
        var key = ValidateKey(serverScope, userId);
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT last_success_cursor, observed_server_cursor, status,
                   initial_sync_completed, updated_at, reset_confirmed_by, reset_confirmed_at
            FROM server_notification_cursors
            WHERE server_scope = $server_scope AND user_id = $user_id;
            """;
        command.Parameters.AddWithValue("$server_scope", key.ServerScope);
        command.Parameters.AddWithValue("$user_id", key.UserId);
        using var reader = command.ExecuteReader();
        return reader.Read()
            ? ReadState(reader, key.ServerScope, key.UserId)
            : EmptyState(key.ServerScope, key.UserId);
    }

    public ServerNotificationBatchResult ProcessBatch(
        string serverScope,
        string userId,
        ServerNotificationPage page,
        bool reachedServerCursor,
        Action<ServerUserNotificationResponse>? processMessage = null)
    {
        ArgumentNullException.ThrowIfNull(page);
        var key = ValidateKey(serverScope, userId);
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        var state = Get(connection, transaction, key.ServerScope, key.UserId);

        if (state.ResetRequired || page.ServerCursor < state.LastSuccessCursor)
        {
            var resetState = MarkResetRequired(
                connection,
                transaction,
                state,
                page.ServerCursor,
                DateTimeOffset.UtcNow);
            transaction.Commit();
            return new ServerNotificationBatchResult(resetState, page.Items.Count, 0, 0, true);
        }

        var processed = 0;
        var duplicates = 0;
        var nextCursor = state.LastSuccessCursor;
        foreach (var notification in page.Items.OrderBy(item => item.Cursor))
        {
            ValidateNotification(notification, page.ServerCursor);
            if (IsProcessed(connection, transaction, key.ServerScope, key.UserId, notification.MessageId))
            {
                duplicates++;
                nextCursor = Math.Max(nextCursor, notification.Cursor);
                continue;
            }

            if (notification.Cursor <= state.LastSuccessCursor)
            {
                throw new InvalidOperationException("처리되지 않은 알림의 cursor가 이미 저장된 위치보다 낮습니다.");
            }

            processMessage?.Invoke(notification);
            InsertProcessed(connection, transaction, key.ServerScope, key.UserId, notification);
            processed++;
            nextCursor = Math.Max(nextCursor, notification.Cursor);
        }

        if (reachedServerCursor)
        {
            nextCursor = page.ServerCursor;
        }

        var updated = UpsertState(
            connection,
            transaction,
            key.ServerScope,
            key.UserId,
            nextCursor,
            page.ServerCursor,
            state.InitialSyncCompleted || reachedServerCursor,
            DateTimeOffset.UtcNow);
        transaction.Commit();
        return new ServerNotificationBatchResult(updated, page.Items.Count, processed, duplicates, false);
    }

    public ServerNotificationCursorRecord ResetAfterAdministratorConfirmation(
        string serverScope,
        string userId,
        string administratorUserId)
    {
        var key = ValidateKey(serverScope, userId);
        if (string.IsNullOrWhiteSpace(administratorUserId))
        {
            throw new ArgumentException("확인한 관리자 ID가 필요합니다.", nameof(administratorUserId));
        }

        var now = DateTimeOffset.UtcNow;
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        using (var delete = connection.CreateCommand())
        {
            delete.Transaction = transaction;
            delete.CommandText = """
                DELETE FROM server_notification_messages
                WHERE server_scope = $server_scope AND user_id = $user_id;
                """;
            delete.Parameters.AddWithValue("$server_scope", key.ServerScope);
            delete.Parameters.AddWithValue("$user_id", key.UserId);
            delete.ExecuteNonQuery();
        }

        using (var upsert = connection.CreateCommand())
        {
            upsert.Transaction = transaction;
            upsert.CommandText = """
                INSERT INTO server_notification_cursors (
                    server_scope, user_id, last_success_cursor, observed_server_cursor,
                    status, initial_sync_completed, updated_at, reset_confirmed_by, reset_confirmed_at)
                VALUES ($server_scope, $user_id, 0, 0, 'ACTIVE', 0, $updated_at, $confirmed_by, $confirmed_at)
                ON CONFLICT(server_scope, user_id) DO UPDATE SET
                    last_success_cursor = 0,
                    observed_server_cursor = 0,
                    status = 'ACTIVE',
                    initial_sync_completed = 0,
                    updated_at = excluded.updated_at,
                    reset_confirmed_by = excluded.reset_confirmed_by,
                    reset_confirmed_at = excluded.reset_confirmed_at;
                """;
            upsert.Parameters.AddWithValue("$server_scope", key.ServerScope);
            upsert.Parameters.AddWithValue("$user_id", key.UserId);
            upsert.Parameters.AddWithValue("$updated_at", now.ToString("O"));
            upsert.Parameters.AddWithValue("$confirmed_by", administratorUserId.Trim());
            upsert.Parameters.AddWithValue("$confirmed_at", now.ToString("O"));
            upsert.ExecuteNonQuery();
        }

        transaction.Commit();
        return Get(key.ServerScope, key.UserId);
    }

    private static ServerNotificationCursorRecord Get(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string serverScope,
        string userId)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT last_success_cursor, observed_server_cursor, status,
                   initial_sync_completed, updated_at, reset_confirmed_by, reset_confirmed_at
            FROM server_notification_cursors
            WHERE server_scope = $server_scope AND user_id = $user_id;
            """;
        command.Parameters.AddWithValue("$server_scope", serverScope);
        command.Parameters.AddWithValue("$user_id", userId);
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadState(reader, serverScope, userId) : EmptyState(serverScope, userId);
    }

    private static ServerNotificationCursorRecord UpsertState(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string serverScope,
        string userId,
        long cursor,
        long serverCursor,
        bool initialSyncCompleted,
        DateTimeOffset updatedAt)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO server_notification_cursors (
                server_scope, user_id, last_success_cursor, observed_server_cursor,
                status, initial_sync_completed, updated_at)
            VALUES ($server_scope, $user_id, $cursor, $server_cursor, 'ACTIVE', $completed, $updated_at)
            ON CONFLICT(server_scope, user_id) DO UPDATE SET
                last_success_cursor = excluded.last_success_cursor,
                observed_server_cursor = excluded.observed_server_cursor,
                status = 'ACTIVE',
                initial_sync_completed = excluded.initial_sync_completed,
                updated_at = excluded.updated_at;
            """;
        command.Parameters.AddWithValue("$server_scope", serverScope);
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$cursor", cursor);
        command.Parameters.AddWithValue("$server_cursor", serverCursor);
        command.Parameters.AddWithValue("$completed", initialSyncCompleted ? 1 : 0);
        command.Parameters.AddWithValue("$updated_at", updatedAt.ToString("O"));
        command.ExecuteNonQuery();
        return Get(connection, transaction, serverScope, userId);
    }

    private static ServerNotificationCursorRecord MarkResetRequired(
        SqliteConnection connection,
        SqliteTransaction transaction,
        ServerNotificationCursorRecord state,
        long serverCursor,
        DateTimeOffset updatedAt)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO server_notification_cursors (
                server_scope, user_id, last_success_cursor, observed_server_cursor,
                status, initial_sync_completed, updated_at)
            VALUES ($server_scope, $user_id, $cursor, $server_cursor, 'RESET_REQUIRED', $completed, $updated_at)
            ON CONFLICT(server_scope, user_id) DO UPDATE SET
                observed_server_cursor = excluded.observed_server_cursor,
                status = 'RESET_REQUIRED',
                updated_at = excluded.updated_at;
            """;
        command.Parameters.AddWithValue("$server_scope", state.ServerScope);
        command.Parameters.AddWithValue("$user_id", state.UserId);
        command.Parameters.AddWithValue("$cursor", state.LastSuccessCursor);
        command.Parameters.AddWithValue("$server_cursor", serverCursor);
        command.Parameters.AddWithValue("$completed", state.InitialSyncCompleted ? 1 : 0);
        command.Parameters.AddWithValue("$updated_at", updatedAt.ToString("O"));
        command.ExecuteNonQuery();
        return Get(connection, transaction, state.ServerScope, state.UserId);
    }

    private static bool IsProcessed(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string serverScope,
        string userId,
        string messageId)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT COUNT(*)
            FROM server_notification_messages
            WHERE server_scope = $server_scope AND user_id = $user_id AND message_id = $message_id;
            """;
        command.Parameters.AddWithValue("$server_scope", serverScope);
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$message_id", messageId);
        return Convert.ToInt64(command.ExecuteScalar()) > 0;
    }

    private static void InsertProcessed(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string serverScope,
        string userId,
        ServerUserNotificationResponse notification)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO server_notification_messages (
                server_scope, user_id, message_id, cursor, processed_at)
            VALUES ($server_scope, $user_id, $message_id, $cursor, $processed_at);
            """;
        command.Parameters.AddWithValue("$server_scope", serverScope);
        command.Parameters.AddWithValue("$user_id", userId);
        command.Parameters.AddWithValue("$message_id", notification.MessageId);
        command.Parameters.AddWithValue("$cursor", notification.Cursor);
        command.Parameters.AddWithValue("$processed_at", DateTimeOffset.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static void ValidateNotification(
        ServerUserNotificationResponse notification,
        long serverCursor)
    {
        if (string.IsNullOrWhiteSpace(notification.MessageId))
        {
            throw new InvalidOperationException("알림 message_id가 없어 처리 위치를 저장할 수 없습니다.");
        }

        if (notification.Cursor < 0 || notification.Cursor > serverCursor)
        {
            throw new InvalidOperationException("서버 알림 cursor 범위가 저장 위치와 일치하지 않습니다.");
        }
    }

    private static (string ServerScope, string UserId) ValidateKey(string serverScope, string userId)
    {
        if (!Uri.TryCreate(serverScope, UriKind.Absolute, out var scopeUri))
        {
            throw new ArgumentException("유효한 서버 scope가 필요합니다.", nameof(serverScope));
        }
        if (string.IsNullOrWhiteSpace(userId))
        {
            throw new ArgumentException("사용자 ID가 필요합니다.", nameof(userId));
        }
        return (NormalizeServerScope(scopeUri), userId.Trim());
    }

    private static ServerNotificationCursorRecord EmptyState(string serverScope, string userId) =>
        new(serverScope, userId, 0, 0, ActiveStatus, false, null, null, null);

    private static ServerNotificationCursorRecord ReadState(
        SqliteDataReader reader,
        string serverScope,
        string userId) =>
        new(
            serverScope,
            userId,
            reader.GetInt64(0),
            reader.GetInt64(1),
            reader.GetString(2),
            reader.GetInt64(3) == 1,
            DateTimeOffset.Parse(reader.GetString(4)),
            reader.IsDBNull(5) ? null : reader.GetString(5),
            reader.IsDBNull(6) ? null : DateTimeOffset.Parse(reader.GetString(6)));
}
