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

    public static readonly IReadOnlyList<DefaultGroupSeed> DefaultGroupSeeds =
    [
        new("group-admin", "admin", "관리자 그룹", "admin", null),
        new("group-line-a", "line-a", "반장 A 작업조", "work_team", "user-foreman-a"),
        new("group-line-b", "line-b", "반장 B 작업조", "work_team", "user-foreman-b"),
        new("group-line-c", "line-c", "반장 C 작업조", "work_team", "user-foreman-c")
    ];

    public static readonly IReadOnlyList<DefaultUserSeed> DefaultUserSeeds =
    [
        new("user-admin", "admin", "Administrator", "system-admin", "group-admin", null),
        new("user-deputy", "deputy", "차장", "assistant-manager", "group-admin", null),
        new("user-depthead", "depthead", "부장", "department-manager", "group-admin", null),
        new("user-manager", "manager", "관리자", "document-admin", "group-admin", null),

        new("user-foreman-a", "foreman-a", "반장 A", "line-foreman", "group-line-a", null),
        new("user-lead-a1", "lead-a1", "조장 A-1", "team-lead", "group-line-a", "user-foreman-a"),
        new("user-member-a1", "member-a1", "조원 A-1", "team-member", "group-line-a", "user-foreman-a"),
        new("user-member-a2", "member-a2", "조원 A-2", "team-member", "group-line-a", "user-foreman-a"),
        new("user-member-a3", "member-a3", "조원 A-3", "team-member", "group-line-a", "user-foreman-a"),
        new("user-member-a4", "member-a4", "조원 A-4", "team-member", "group-line-a", "user-foreman-a"),

        new("user-foreman-b", "foreman-b", "반장 B", "line-foreman", "group-line-b", null),
        new("user-lead-b1", "lead-b1", "조장 B-1", "team-lead", "group-line-b", "user-foreman-b"),
        new("user-lead-b2", "lead-b2", "조장 B-2", "team-lead", "group-line-b", "user-foreman-b"),
        new("user-member-b1", "member-b1", "조원 B-1", "team-member", "group-line-b", "user-foreman-b"),
        new("user-member-b2", "member-b2", "조원 B-2", "team-member", "group-line-b", "user-foreman-b"),
        new("user-member-b3", "member-b3", "조원 B-3", "team-member", "group-line-b", "user-foreman-b"),
        new("user-member-b4", "member-b4", "조원 B-4", "team-member", "group-line-b", "user-foreman-b"),

        new("user-foreman-c", "foreman-c", "반장 C", "line-foreman", "group-line-c", null),
        new("user-lead-c1", "lead-c1", "조장 C-1", "team-lead", "group-line-c", "user-foreman-c"),
        new("user-member-c1", "member-c1", "조원 C-1", "team-member", "group-line-c", "user-foreman-c"),
        new("user-member-c2", "member-c2", "조원 C-2", "team-member", "group-line-c", "user-foreman-c"),
        new("user-member-c3", "member-c3", "조원 C-3", "team-member", "group-line-c", "user-foreman-c")
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
            var developmentAppDirectory = TryFindDevelopmentAppDirectory(AppContext.BaseDirectory);
            if (!string.IsNullOrWhiteSpace(developmentAppDirectory))
            {
                var developmentDataDirectory = Path.Combine(developmentAppDirectory, "Data");
                Directory.CreateDirectory(developmentDataDirectory);
                return Path.Combine(developmentDataDirectory, "flownote.local.sqlite");
            }

            var directory = Path.Combine(AppContext.BaseDirectory, "Data");
            Directory.CreateDirectory(directory);
            return Path.Combine(directory, "flownote.local.sqlite");
        }
    }

    public static string? TryFindDevelopmentAppDirectory(string startDirectory)
    {
        var directory = new DirectoryInfo(startDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "FlowNote.Windows.App.csproj")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        return null;
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
                group_id TEXT NULL,
                supervisor_user_id TEXT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL UNIQUE,
                group_code TEXT NOT NULL UNIQUE,
                group_name TEXT NOT NULL,
                group_type TEXT NOT NULL,
                leader_user_id TEXT NULL,
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

            CREATE TABLE IF NOT EXISTS field_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id TEXT NOT NULL UNIQUE,
                document_id TEXT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                document_version_no INTEGER NULL,
                note_type TEXT NOT NULL,
                input_mode TEXT NOT NULL,
                signal_level TEXT NULL,
                raw_content TEXT NOT NULL,
                normalized_content TEXT NULL,
                analysis_content TEXT NULL,
                author_name TEXT NOT NULL,
                reported_by TEXT NULL,
                operator_name TEXT NULL,
                entry_source TEXT NOT NULL,
                device_id TEXT NULL,
                location_code TEXT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                synced_at TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_field_notes_document_created
                ON field_notes (document_id, created_at);

            CREATE TABLE IF NOT EXISTS document_view_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                version_no INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                view_started_at TEXT NOT NULL,
                closed_at TEXT NULL,
                close_reason TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_document_view_logs_document_started
                ON document_view_logs (document_id, view_started_at);

            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NULL,
                target_title TEXT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_activity_history_created
                ON activity_history (created_at, id);

            CREATE INDEX IF NOT EXISTS ix_activity_history_target
                ON activity_history (target_type, target_id);

            CREATE TABLE IF NOT EXISTS tag_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_id TEXT NOT NULL UNIQUE,
                tag_type TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_tag_id TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(tag_type, code)
            );

            CREATE TABLE IF NOT EXISTS document_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES tag_definitions(tag_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, tag_id)
            );

            CREATE INDEX IF NOT EXISTS ix_document_tags_document
                ON document_tags (document_id);

            CREATE INDEX IF NOT EXISTS ix_document_tags_tag
                ON document_tags (tag_id);

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT NOT NULL UNIQUE,
                recipient_name TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """;
        command.ExecuteNonQuery();
        EnsureColumn(connection, "user_accounts", "group_id", "TEXT NULL");
        EnsureColumn(connection, "user_accounts", "supervisor_user_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "updated_at", "TEXT NULL");
        EnsureColumn(connection, "documents", "local_path", "TEXT NULL");
        EnsureColumn(connection, "documents", "version_no", "INTEGER NOT NULL DEFAULT 1");
        EnsureColumn(connection, "documents", "latest_comment", "TEXT NULL");
        EnsureDocumentUpdatedAt(connection);
        BackfillFieldNotesFromCommentVersions(connection);

        SeedDefaultGroups(connection);
        SeedDefaultUsers(connection);
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

    private static void BackfillFieldNotesFromCommentVersions(SqliteConnection connection)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO field_notes (
                note_id,
                document_id,
                document_version_no,
                note_type,
                input_mode,
                raw_content,
                author_name,
                entry_source,
                status,
                created_at
            )
            SELECT
                'note-legacy-' || lower(hex(randomblob(16))),
                document_id,
                version_no,
                'issue',
                'free_text',
                trim(comment),
                created_by,
                'field_user',
                'NEW',
                created_at
            FROM document_versions AS version
            WHERE comment IS NOT NULL
              AND trim(comment) <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM field_notes AS note
                  WHERE note.document_id = version.document_id
                    AND note.document_version_no = version.version_no
                    AND note.raw_content = trim(version.comment)
                    AND note.created_at = version.created_at
              );
            """;
        command.ExecuteNonQuery();
    }

    private static void SeedDefaultUsers(SqliteConnection connection)
    {
        foreach (var user in DefaultUserSeeds)
        {
            using var command = connection.CreateCommand();
            command.CommandText = """
                UPDATE user_accounts
                SET user_id = $user_id,
                    display_name = $display_name,
                    password_hash = $password_hash,
                    role = $role,
                    group_id = $group_id,
                    supervisor_user_id = $supervisor_user_id,
                    status = 'ACTIVE'
                WHERE login_id = $login_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM user_accounts
                      WHERE user_id = $user_id
                        AND login_id <> $login_id
                  );

                INSERT INTO user_accounts (
                    user_id,
                    login_id,
                    display_name,
                    password_hash,
                    role,
                    group_id,
                    supervisor_user_id,
                    status,
                    created_at
                )
                SELECT
                    $user_id,
                    $login_id,
                    $display_name,
                    $password_hash,
                    $role,
                    $group_id,
                    $supervisor_user_id,
                    'ACTIVE',
                    $created_at
                WHERE NOT EXISTS (SELECT 1 FROM user_accounts WHERE login_id = $login_id)
                  AND NOT EXISTS (SELECT 1 FROM user_accounts WHERE user_id = $user_id);
                """;
            command.Parameters.AddWithValue("$user_id", user.UserId);
            command.Parameters.AddWithValue("$login_id", user.LoginId);
            command.Parameters.AddWithValue("$display_name", user.DisplayName);
            command.Parameters.AddWithValue("$password_hash", PasswordHasher.Hash("1234"));
            command.Parameters.AddWithValue("$role", user.Role);
            command.Parameters.AddWithValue("$group_id", user.GroupId);
            command.Parameters.AddWithValue("$supervisor_user_id", (object?)user.SupervisorUserId ?? DBNull.Value);
            command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
        }
    }

    private static void SeedDefaultGroups(SqliteConnection connection)
    {
        foreach (var group in DefaultGroupSeeds)
        {
            using var command = connection.CreateCommand();
            command.CommandText = """
                UPDATE user_groups
                SET group_code = $group_code,
                    group_name = $group_name,
                    group_type = $group_type,
                    leader_user_id = $leader_user_id
                WHERE group_id = $group_id;

                INSERT INTO user_groups (
                    group_id,
                    group_code,
                    group_name,
                    group_type,
                    leader_user_id,
                    created_at
                )
                SELECT
                    $group_id,
                    $group_code,
                    $group_name,
                    $group_type,
                    $leader_user_id,
                    $created_at
                WHERE NOT EXISTS (SELECT 1 FROM user_groups WHERE group_id = $group_id);
                """;
            command.Parameters.AddWithValue("$group_id", group.GroupId);
            command.Parameters.AddWithValue("$group_code", group.GroupCode);
            command.Parameters.AddWithValue("$group_name", group.GroupName);
            command.Parameters.AddWithValue("$group_type", group.GroupType);
            command.Parameters.AddWithValue("$leader_user_id", (object?)group.LeaderUserId ?? DBNull.Value);
            command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
        }
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

    public sealed record DefaultGroupSeed(
        string GroupId,
        string GroupCode,
        string GroupName,
        string GroupType,
        string? LeaderUserId);

    public sealed record DefaultUserSeed(
        string UserId,
        string LoginId,
        string DisplayName,
        string Role,
        string GroupId,
        string? SupervisorUserId);
}
