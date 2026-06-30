using FlowNote.Windows.Core.Auth;
using Microsoft.Data.Sqlite;
using SQLitePCL;

namespace FlowNote.Windows.Core.Storage;

public sealed class FlowNoteLocalDatabase
{
    public const string LocalDatabaseFileName = "flownote.local.sqlite";
    public const string LocalDataDirectoryEnvironmentVariable = "FLOWNOTE_LOCAL_DATA_DIR";
    public const string LocalDatabasePathEnvironmentVariable = "FLOWNOTE_LOCAL_DATABASE_PATH";

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

    public static string DefaultDataDirectory
    {
        get
        {
            var configuredDataDirectory = Environment.GetEnvironmentVariable(LocalDataDirectoryEnvironmentVariable);
            if (!string.IsNullOrWhiteSpace(configuredDataDirectory))
            {
                var configuredDirectory = Path.GetFullPath(configuredDataDirectory);
                Directory.CreateDirectory(configuredDirectory);
                return configuredDirectory;
            }

            var configuredDatabasePath = Environment.GetEnvironmentVariable(LocalDatabasePathEnvironmentVariable);
            if (!string.IsNullOrWhiteSpace(configuredDatabasePath))
            {
                var databaseDirectory = Path.GetDirectoryName(Path.GetFullPath(configuredDatabasePath));
                if (!string.IsNullOrWhiteSpace(databaseDirectory))
                {
                    Directory.CreateDirectory(databaseDirectory);
                    return databaseDirectory;
                }
            }

            var repositoryRoot = TryFindRepositoryRoot(Environment.CurrentDirectory)
                ?? TryFindRepositoryRoot(AppContext.BaseDirectory);
            if (!string.IsNullOrWhiteSpace(repositoryRoot))
            {
                var sharedDataDirectory = Path.Combine(repositoryRoot, "data", "local");
                Directory.CreateDirectory(sharedDataDirectory);
                return sharedDataDirectory;
            }

            var runtimeDataDirectory = Path.Combine(AppContext.BaseDirectory, "Data");
            Directory.CreateDirectory(runtimeDataDirectory);
            return runtimeDataDirectory;
        }
    }

    public static string DefaultDatabasePath
    {
        get
        {
            var configuredDatabasePath = Environment.GetEnvironmentVariable(LocalDatabasePathEnvironmentVariable);
            if (!string.IsNullOrWhiteSpace(configuredDatabasePath))
            {
                var databasePath = Path.GetFullPath(configuredDatabasePath);
                Directory.CreateDirectory(Path.GetDirectoryName(databasePath)!);
                return databasePath;
            }

            return Path.Combine(DefaultDataDirectory, LocalDatabaseFileName);
        }
    }

    public static string ResolveLocalContentPath(string storedPath)
    {
        if (Path.IsPathRooted(storedPath))
        {
            return storedPath;
        }

        foreach (var root in EnumerateLocalContentRoots())
        {
            var candidate = Path.GetFullPath(Path.Combine(root, storedPath));
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return Path.GetFullPath(Path.Combine(DefaultDataDirectory, storedPath));
    }

    public static string? TryFindRepositoryRoot(string startDirectory)
    {
        var directory = new DirectoryInfo(startDirectory);
        while (directory is not null)
        {
            var appProjectPath = Path.Combine(
                directory.FullName,
                "apps",
                "windows",
                "src",
                "FlowNote.Windows.App",
                "FlowNote.Windows.App.csproj");
            if (File.Exists(Path.Combine(directory.FullName, "AGENTS.md")) && File.Exists(appProjectPath))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        return null;
    }

    private static IEnumerable<string> EnumerateLocalContentRoots()
    {
        yield return DefaultDataDirectory;
        yield return AppContext.BaseDirectory;

        var developmentAppDirectory = TryFindDevelopmentAppDirectory(AppContext.BaseDirectory);
        if (!string.IsNullOrWhiteSpace(developmentAppDirectory))
        {
            yield return developmentAppDirectory;
        }

        var repositoryRoot = TryFindRepositoryRoot(Environment.CurrentDirectory)
            ?? TryFindRepositoryRoot(AppContext.BaseDirectory);
        if (!string.IsNullOrWhiteSpace(repositoryRoot))
        {
            yield return Path.Combine(repositoryRoot, "data", "local");
            yield return repositoryRoot;
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
                published_version_no INTEGER NULL,
                latest_comment TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS document_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                version_no INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                local_path TEXT NULL,
                comment TEXT NULL,
                version_status TEXT NOT NULL DEFAULT 'WORKING',
                is_latest INTEGER NOT NULL DEFAULT 0,
                is_published INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NULL,
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

            CREATE TABLE IF NOT EXISTS field_note_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attachment_id TEXT NOT NULL UNIQUE,
                note_id TEXT NOT NULL REFERENCES field_notes(note_id) ON DELETE CASCADE,
                local_path TEXT NOT NULL,
                original_file_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                content_type TEXT NULL,
                size_bytes INTEGER NOT NULL,
                hash_sha256 TEXT NOT NULL,
                attachment_type TEXT NOT NULL,
                caption TEXT NULL,
                captured_at TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                server_attachment_id TEXT NULL,
                synced_at TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_field_note_attachments_note
                ON field_note_attachments (note_id, created_at);

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

            CREATE TABLE IF NOT EXISTS file_watch_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL UNIQUE,
                source_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                last_write_time_utc TEXT NOT NULL,
                status TEXT NOT NULL,
                document_id TEXT NULL REFERENCES documents(document_id) ON DELETE SET NULL,
                detected_by TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                version_label TEXT NULL,
                change_reason TEXT NULL,
                resolved_by TEXT NULL,
                resolved_at TEXT NULL,
                UNIQUE(source_path, status)
            );

            CREATE INDEX IF NOT EXISTS ix_file_watch_candidates_status
                ON file_watch_candidates (status, detected_at);

            CREATE INDEX IF NOT EXISTS ix_file_watch_candidates_document
                ON file_watch_candidates (document_id, status);

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

            CREATE TABLE IF NOT EXISTS work_sequence_boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NULL,
                line_code TEXT NULL,
                board_date TEXT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_boards_updated
                ON work_sequence_boards (updated_at, id);

            CREATE TABLE IF NOT EXISTS work_sequence_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NULL,
                work_order_no TEXT NULL,
                document_id TEXT NULL,
                status TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                assigned_to TEXT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(board_id, sort_order)
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_items_board_order
                ON work_sequence_items (board_id, sort_order);

            CREATE TABLE IF NOT EXISTS work_sequence_change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                item_id TEXT NULL REFERENCES work_sequence_items(item_id) ON DELETE SET NULL,
                change_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                before_value TEXT NULL,
                after_value TEXT NULL,
                change_reason TEXT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_history_board_created
                ON work_sequence_change_history (board_id, created_at);

            CREATE TABLE IF NOT EXISTS work_sequence_notification_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL UNIQUE,
                board_id TEXT NOT NULL REFERENCES work_sequence_boards(board_id) ON DELETE CASCADE,
                item_id TEXT NULL REFERENCES work_sequence_items(item_id) ON DELETE SET NULL,
                event_type TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_work_sequence_notify_board_created
                ON work_sequence_notification_candidates (board_id, created_at);

            CREATE TABLE IF NOT EXISTS server_sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_id TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                local_document_id TEXT NULL,
                local_version_no INTEGER NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NULL,
                created_at TEXT NOT NULL,
                last_attempt_at TEXT NULL,
                synced_at TEXT NULL,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_note_id TEXT NULL,
                server_attachment_id TEXT NULL,
                server_log_id TEXT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_server_sync_queue_status
                ON server_sync_queue (status, id);

            CREATE TABLE IF NOT EXISTS server_id_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                local_id TEXT NOT NULL,
                local_version_no INTEGER NOT NULL DEFAULT 0,
                server_document_id TEXT NULL,
                server_version_id TEXT NULL,
                server_note_id TEXT NULL,
                server_attachment_id TEXT NULL,
                server_log_id TEXT NULL,
                synced_at TEXT NOT NULL,
                UNIQUE(entity_type, local_id, local_version_no)
            );
            """;
        command.ExecuteNonQuery();
        EnsureColumn(connection, "user_accounts", "group_id", "TEXT NULL");
        EnsureColumn(connection, "user_accounts", "supervisor_user_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "updated_at", "TEXT NULL");
        EnsureColumn(connection, "documents", "local_path", "TEXT NULL");
        EnsureColumn(connection, "documents", "version_no", "INTEGER NOT NULL DEFAULT 1");
        EnsureColumn(connection, "documents", "published_version_no", "INTEGER NULL");
        EnsureColumn(connection, "documents", "latest_comment", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_document_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "server_version_id", "TEXT NULL");
        EnsureColumn(connection, "documents", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "version_status", "TEXT NOT NULL DEFAULT 'WORKING'");
        EnsureColumn(connection, "document_versions", "is_latest", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "document_versions", "is_published", "INTEGER NOT NULL DEFAULT 0");
        EnsureColumn(connection, "document_versions", "published_at", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "version_label", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "server_version_id", "TEXT NULL");
        EnsureColumn(connection, "document_versions", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "field_notes", "server_note_id", "TEXT NULL");
        EnsureColumn(connection, "field_notes", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "field_note_attachments", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "field_note_attachments", "synced_at", "TEXT NULL");
        EnsureColumn(connection, "server_sync_queue", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "server_id_mappings", "server_attachment_id", "TEXT NULL");
        EnsureColumn(connection, "document_view_logs", "server_start_log_id", "INTEGER NULL");
        EnsureColumn(connection, "document_view_logs", "server_close_log_id", "INTEGER NULL");
        EnsureColumn(connection, "document_view_logs", "synced_at", "TEXT NULL");
        EnsureDocumentUpdatedAt(connection);
        EnsureDocumentVersionState(connection);
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

    private static void EnsureDocumentVersionState(SqliteConnection connection)
    {
        using var latest = connection.CreateCommand();
        latest.CommandText = """
            UPDATE document_versions
            SET is_latest = CASE
                    WHEN version_no = (
                        SELECT MAX(inner_version.version_no)
                        FROM document_versions AS inner_version
                        WHERE inner_version.document_id = document_versions.document_id
                    ) THEN 1
                    ELSE 0
                END
            WHERE is_latest IS NULL OR is_latest = 0;
            """;
        latest.ExecuteNonQuery();

        using var status = connection.CreateCommand();
        status.CommandText = """
            UPDATE document_versions
            SET version_status = CASE
                    WHEN is_published = 1 THEN 'PUBLISHED'
                    WHEN is_latest = 1 THEN COALESCE(NULLIF(version_status, ''), 'WORKING')
                    ELSE CASE
                        WHEN version_status = 'PUBLISHED' THEN 'PUBLISHED'
                        ELSE 'SUPERSEDED'
                    END
                END
            WHERE version_status IS NULL OR version_status = '' OR is_latest = 0;
            """;
        status.ExecuteNonQuery();
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
