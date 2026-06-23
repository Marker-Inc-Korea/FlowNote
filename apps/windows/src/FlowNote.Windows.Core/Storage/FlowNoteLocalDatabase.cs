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
    public const string DrawingFolderName = "도면";
    public const string WorkStandardFolderName = "작업표준서";
    public const string CheckSheetFolderName = "점검표";
    public const string QualityFolderName = "품질검사";
    public const string SafetyFolderName = "안전수칙";
    public const string MaintenanceFolderName = "보전작업";
    public const string GeneralDocumentFolderName = "일반문서";

    public static readonly IReadOnlyList<string> DefaultSystemFolderNames =
    [
        DocumentsFolderName,
        HandoverFolderName,
        WorkOrderFolderName,
        PhotosFolderName
    ];

    public static readonly IReadOnlyList<string> DocumentCategoryFolderNames =
    [
        DrawingFolderName,
        WorkStandardFolderName,
        CheckSheetFolderName,
        QualityFolderName,
        SafetyFolderName,
        MaintenanceFolderName,
        GeneralDocumentFolderName
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
            var directory = Path.Combine(AppContext.BaseDirectory, "Data");
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                local_path TEXT NULL,
                version_no INTEGER NOT NULL DEFAULT 1,
                latest_comment TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS document_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                version_no INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                local_path TEXT NULL,
                comment TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """;
        command.ExecuteNonQuery();
        EnsureColumn(connection, "documents", "updated_at", "TEXT NULL");
        EnsureColumn(connection, "documents", "local_path", "TEXT NULL");
        EnsureColumn(connection, "documents", "version_no", "INTEGER NOT NULL DEFAULT 1");
        EnsureColumn(connection, "documents", "latest_comment", "TEXT NULL");
        EnsureDocumentUpdatedAt(connection);

        SeedAdminUser(connection);
        var rootFolderId = SeedRootFolder(connection);
        SeedDefaultSystemFolders(connection, rootFolderId);
        var documentsFolderId = EnsureDefaultSystemFolder(connection, rootFolderId, DocumentsFolderName);
        SeedDocumentCategoryFolders(connection, documentsFolderId);
        MigrateDirectDocumentsToCategoryFolders(connection, documentsFolderId);
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

    private static void EnsureColumn(SqliteConnection connection, string tableName, string columnName, string definition)
    {
        using var lookup = connection.CreateCommand();
        lookup.CommandText = $"PRAGMA table_info({tableName});";

        using var reader = lookup.ExecuteReader();
        while (reader.Read())
        {
            if (string.Equals(reader.GetString(1), columnName, StringComparison.OrdinalIgnoreCase))
            {
                return;
            }
        }

        using var alter = connection.CreateCommand();
        alter.CommandText = $"ALTER TABLE {tableName} ADD COLUMN {columnName} {definition};";
        alter.ExecuteNonQuery();
    }

    private static void EnsureDocumentUpdatedAt(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE documents
            SET updated_at = created_at
            WHERE updated_at IS NULL OR updated_at = '';
            """;
        command.ExecuteNonQuery();
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

    private static long EnsureDefaultSystemFolder(SqliteConnection connection, long rootFolderId, string folderName)
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
            return Convert.ToInt64(existingId);
        }

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO document_folders (folder_id, parent_id, name, path, is_system, created_at)
            VALUES ($folder_id, $parent_id, $name, $path, 1, $created_at);
            SELECT last_insert_rowid();
            """;
        insert.Parameters.AddWithValue("$folder_id", $"folder-system-{Guid.NewGuid():N}");
        insert.Parameters.AddWithValue("$parent_id", rootFolderId);
        insert.Parameters.AddWithValue("$name", folderName);
        insert.Parameters.AddWithValue("$path", $"/{folderName}");
        insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        return Convert.ToInt64(insert.ExecuteScalar());
    }

    private static void SeedDocumentCategoryFolders(SqliteConnection connection, long documentsFolderId)
    {
        foreach (var folderName in DocumentCategoryFolderNames)
        {
            EnsureSystemChildFolder(connection, documentsFolderId, $"/{DocumentsFolderName}", folderName);
        }
    }

    private static long EnsureSystemChildFolder(
        SqliteConnection connection,
        long parentId,
        string parentPath,
        string folderName)
    {
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT id
            FROM document_folders
            WHERE parent_id = $parent_id AND name = $name
            LIMIT 1;
            """;
        lookup.Parameters.AddWithValue("$parent_id", parentId);
        lookup.Parameters.AddWithValue("$name", folderName);
        var existingId = lookup.ExecuteScalar();
        var path = parentPath == "/" ? $"/{folderName}" : $"{parentPath}/{folderName}";

        if (existingId is not null)
        {
            using var update = connection.CreateCommand();
            update.CommandText = """
                UPDATE document_folders
                SET path = $path,
                    is_system = 1
                WHERE id = $id;
                """;
            update.Parameters.AddWithValue("$path", path);
            update.Parameters.AddWithValue("$id", Convert.ToInt64(existingId));
            update.ExecuteNonQuery();
            return Convert.ToInt64(existingId);
        }

        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO document_folders (folder_id, parent_id, name, path, is_system, created_at)
            VALUES ($folder_id, $parent_id, $name, $path, 1, $created_at);
            SELECT last_insert_rowid();
            """;
        insert.Parameters.AddWithValue("$folder_id", $"folder-system-{Guid.NewGuid():N}");
        insert.Parameters.AddWithValue("$parent_id", parentId);
        insert.Parameters.AddWithValue("$name", folderName);
        insert.Parameters.AddWithValue("$path", path);
        insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        return Convert.ToInt64(insert.ExecuteScalar());
    }

    private static void MigrateDirectDocumentsToCategoryFolders(SqliteConnection connection, long documentsFolderId)
    {
        using var lookup = connection.CreateCommand();
        lookup.CommandText = """
            SELECT id, title, file_name, document_type
            FROM documents
            WHERE folder_id = $folder_id;
            """;
        lookup.Parameters.AddWithValue("$folder_id", documentsFolderId);

        using var reader = lookup.ExecuteReader();
        var documents = new List<(long Id, string Title, string FileName, string DocumentType)>();
        while (reader.Read())
        {
            documents.Add((
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3)));
        }

        foreach (var document in documents)
        {
            var categoryName = ResolveDocumentCategoryName(document.Title, document.FileName, document.DocumentType);
            var categoryFolderId = EnsureSystemChildFolder(
                connection,
                documentsFolderId,
                $"/{DocumentsFolderName}",
                categoryName);

            using var update = connection.CreateCommand();
            update.CommandText = """
                UPDATE documents
                SET folder_id = $target_folder_id
                WHERE id = $document_id;
                """;
            update.Parameters.AddWithValue("$target_folder_id", categoryFolderId);
            update.Parameters.AddWithValue("$document_id", document.Id);
            update.ExecuteNonQuery();
        }
    }

    public static string ResolveDocumentCategoryName(string title, string fileName, string documentType)
    {
        var text = $"{title} {fileName} {documentType}";
        if (ContainsAny(text, "도면", "배치", "배관", "전장", "센서위치", "에어라인"))
        {
            return DrawingFolderName;
        }

        if (ContainsAny(text, "작업표준", "표준서"))
        {
            return WorkStandardFolderName;
        }

        if (ContainsAny(text, "점검", "점검표", "체크"))
        {
            return CheckSheetFolderName;
        }

        if (ContainsAny(text, "품질", "검사기준", "검사"))
        {
            return QualityFolderName;
        }

        if (ContainsAny(text, "안전", "교육"))
        {
            return SafetyFolderName;
        }

        if (ContainsAny(text, "보전", "정비", "수리"))
        {
            return MaintenanceFolderName;
        }

        return GeneralDocumentFolderName;
    }

    private static bool ContainsAny(string text, params string[] values)
    {
        return values.Any(value => text.Contains(value, StringComparison.OrdinalIgnoreCase));
    }
}
