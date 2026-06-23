using FlowNote.Windows.Core.Auth;
using Microsoft.Data.Sqlite;
using SQLitePCL;

namespace FlowNote.Windows.Core.Storage;

public sealed class FlowNoteLocalDatabase
{
    public const string RootFolderId = "folder-root";
    public const string DocumentsFolderName = "문서";
    public const string HandoverFolderName = "인수인계";
    public const string WorkOrderFolderName = "작업순서";
    public const string PhotosFolderName = "사진";

    public static readonly IReadOnlyList<string> DefaultSystemFolderNames =
    [
        DocumentsFolderName,
        HandoverFolderName,
        WorkOrderFolderName,
        PhotosFolderName
    ];

    private static bool sqliteInitialized;

    public FlowNoteLocalDatabase(string databasePath)
    {
        DatabasePath = databasePath;
    }

    public string DatabasePath { get; }

    public static string DefaultDatabasePath
    {
        get
        {
            var directory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FlowNote");
            Directory.CreateDirectory(directory);
            return Path.Combine(directory, "flownote.local.sqlite");
        }
    }

    public SqliteConnection OpenConnection()
    {
        EnsureSqliteInitialized();
        var connection = new SqliteConnection($"Data Source={DatabasePath}");
        connection.Open();
        return connection;
    }

    public void Initialize()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(DatabasePath)!);

        using var connection = OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS user_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                login_id TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id TEXT NOT NULL UNIQUE,
                parent_id INTEGER NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL UNIQUE,
                folder_id INTEGER NOT NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL,
                document_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """;
        command.ExecuteNonQuery();

        SeedAdminUser(connection);
        var rootFolderId = SeedRootFolder(connection);
        SeedDefaultSystemFolders(connection, rootFolderId);
    }

    private static void EnsureSqliteInitialized()
    {
        if (sqliteInitialized)
        {
            return;
        }

        Batteries_V2.Init();
        sqliteInitialized = true;
    }

    private static void SeedAdminUser(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO user_accounts (user_id, login_id, display_name, password_hash, role, status, created_at)
            SELECT $user_id, 'admin', 'Administrator', $password_hash, 'system-admin', 'ACTIVE', $created_at
            WHERE NOT EXISTS (SELECT 1 FROM user_accounts WHERE login_id = 'admin');
            """;
        command.Parameters.AddWithValue("$user_id", $"user-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$password_hash", PasswordHasher.Hash("1234"));
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static long SeedRootFolder(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO document_folders (folder_id, parent_id, name, path, is_system, created_at)
            SELECT $folder_id, NULL, 'Root', '/', 1, $created_at
            WHERE NOT EXISTS (SELECT 1 FROM document_folders WHERE folder_id = $folder_id);
            """;
        command.Parameters.AddWithValue("$folder_id", RootFolderId);
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();

        using var lookup = connection.CreateCommand();
        lookup.CommandText = "SELECT id FROM document_folders WHERE folder_id = $folder_id LIMIT 1;";
        lookup.Parameters.AddWithValue("$folder_id", RootFolderId);
        return Convert.ToInt64(lookup.ExecuteScalar());
    }

    private static void SeedDefaultSystemFolders(SqliteConnection connection, long rootFolderId)
    {
        foreach (var folderName in DefaultSystemFolderNames)
        {
            EnsureDefaultSystemFolder(connection, rootFolderId, folderName);
        }
    }

    private static void EnsureDefaultSystemFolder(SqliteConnection connection, long rootFolderId, string folderName)
    {
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT id
            FROM document_folders
            WHERE parent_id = $parent_id AND name = $name
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$parent_id", rootFolderId);
        lookup.Parameters.AddWithValue("$name", folderName);
        var existingId = lookup.ExecuteScalar();

        if (existingId is not null)
        {
            using var update = connection.CreateCommand();
            update.CommandText = """
                UPDATE document_folders
                SET path = $path,
                    is_system = 1
                WHERE id = $id;
                """;
            update.Parameters.AddWithValue("$path", $"/{folderName}");
            update.Parameters.AddWithValue("$id", Convert.ToInt64(existingId));
            update.ExecuteNonQuery();
            return;
        }

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO document_folders (folder_id, parent_id, name, path, is_system, created_at)
            VALUES ($folder_id, $parent_id, $name, $path, 1, $created_at);
            """;
        insert.Parameters.AddWithValue("$folder_id", $"folder-system-{Guid.NewGuid():N}");
        insert.Parameters.AddWithValue("$parent_id", rootFolderId);
        insert.Parameters.AddWithValue("$name", folderName);
        insert.Parameters.AddWithValue("$path", $"/{folderName}");
        insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        insert.ExecuteNonQuery();
    }
}
