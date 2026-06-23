using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Folders;

public sealed class FolderService(FlowNoteLocalDatabase database)
{
    public DocumentFolder CreateFolder(string name, long? parentId = null, bool isSystem = false)
    {
        var now = DateTime.UtcNow;
        var path = BuildPath(parentId, name);
        var folderId = $"folder-{Guid.NewGuid():N}";

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO document_folders (folder_id, parent_id, name, path, is_system, created_at)
            VALUES ($folder_id, $parent_id, $name, $path, $is_system, $created_at);
            SELECT last_insert_rowid();
            """;
        command.Parameters.AddWithValue("$folder_id", folderId);
        command.Parameters.AddWithValue("$parent_id", parentId is null ? DBNull.Value : parentId.Value);
        command.Parameters.AddWithValue("$name", name);
        command.Parameters.AddWithValue("$path", path);
        command.Parameters.AddWithValue("$is_system", isSystem ? 1 : 0);
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));

        var id = Convert.ToInt64(command.ExecuteScalar());
        return new DocumentFolder(id, folderId, parentId, name, path, isSystem, now);
    }

    public IReadOnlyList<DocumentFolder> ListFolders()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, folder_id, parent_id, name, path, is_system, created_at
            FROM document_folders
            ORDER BY parent_id, name;
            """;

        using var reader = command.ExecuteReader();
        var records = new List<DocumentFolder>();
        while (reader.Read())
        {
            records.Add(new DocumentFolder(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetInt64(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetInt64(5) == 1,
                DateTime.Parse(reader.GetString(6))));
        }

        return records;
    }

    public bool DeleteFolder(long folderId)
    {
        using var connection = database.OpenConnection();
        using var lookup = connection.CreateCommand();
        lookup.CommandText = "SELECT is_system FROM document_folders WHERE id = $id LIMIT 1;";
        lookup.Parameters.AddWithValue("$id", folderId);
        var isSystem = lookup.ExecuteScalar();
        if (isSystem is null || Convert.ToInt64(isSystem) == 1)
        {
            return false;
        }

        using var childLookup = connection.CreateCommand();
        childLookup.CommandText = """
            SELECT
                (SELECT COUNT(1) FROM document_folders WHERE parent_id = $id) +
                (SELECT COUNT(1) FROM documents WHERE folder_id = $id);
            """;
        childLookup.Parameters.AddWithValue("$id", folderId);
        if (Convert.ToInt64(childLookup.ExecuteScalar()) > 0)
        {
            return false;
        }

        using var command = connection.CreateCommand();
        command.CommandText = "DELETE FROM document_folders WHERE id = $id;";
        command.Parameters.AddWithValue("$id", folderId);
        return command.ExecuteNonQuery() == 1;
    }

    public DocumentFolder GetRootFolder()
    {
        return ListFolders().Single(folder => folder.FolderId == FlowNoteLocalDatabase.RootFolderId);
    }

    private string BuildPath(long? parentId, string name)
    {
        if (parentId is null)
        {
            return name == "Root" ? "/" : $"/{name}";
        }

        var parent = ListFolders().Single(folder => folder.Id == parentId.Value);
        return parent.Path == "/" ? $"/{name}" : $"{parent.Path}/{name}";
    }
}
