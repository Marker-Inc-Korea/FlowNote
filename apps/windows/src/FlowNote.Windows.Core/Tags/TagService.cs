using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Tags;

public sealed class TagService(FlowNoteLocalDatabase database)
{
    public IReadOnlyList<TagRecord> ListTags(string? tagType = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = string.IsNullOrWhiteSpace(tagType)
            ? """
              SELECT id, tag_id, tag_type, code, name, parent_tag_id, is_active, created_at
              FROM tag_definitions
              WHERE is_active = 1
              ORDER BY tag_type, name;
              """
            : """
              SELECT id, tag_id, tag_type, code, name, parent_tag_id, is_active, created_at
              FROM tag_definitions
              WHERE is_active = 1 AND tag_type = $tag_type
              ORDER BY name;
              """;
        if (!string.IsNullOrWhiteSpace(tagType))
        {
            command.Parameters.AddWithValue("$tag_type", tagType);
        }

        using var reader = command.ExecuteReader();
        var tags = new List<TagRecord>();
        while (reader.Read())
        {
            tags.Add(ReadTag(reader));
        }

        return tags;
    }

    public IReadOnlyList<string> ListDocumentTags(string documentId)
    {
        using var connection = database.OpenConnection();
        return ListDocumentTags(connection, documentId);
    }

    public void ReplaceDocumentTags(string documentId, IEnumerable<string> tags)
    {
        using var connection = database.OpenConnection();
        ReplaceDocumentTags(connection, documentId, tags);
    }

    internal static IReadOnlyList<string> ListDocumentTags(SqliteConnection connection, string documentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT tag.name
            FROM document_tags AS document_tag
            JOIN tag_definitions AS tag ON tag.tag_id = document_tag.tag_id
            WHERE document_tag.document_id = $document_id
              AND tag.is_active = 1
            ORDER BY tag.name;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);

        using var reader = command.ExecuteReader();
        var tags = new List<string>();
        while (reader.Read())
        {
            tags.Add(reader.GetString(0));
        }

        return tags;
    }

    internal static void ReplaceDocumentTags(
        SqliteConnection connection,
        string documentId,
        IEnumerable<string> tags)
    {
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM document_tags WHERE document_id = $document_id;";
        delete.Parameters.AddWithValue("$document_id", documentId);
        delete.ExecuteNonQuery();

        foreach (var tagName in CleanTags(tags))
        {
            var tagId = EnsureTag(connection, tagName);
            using var insert = connection.CreateCommand();
            insert.CommandText = """
                INSERT OR IGNORE INTO document_tags (document_id, tag_id, created_at)
                VALUES ($document_id, $tag_id, $created_at);
                """;
            insert.Parameters.AddWithValue("$document_id", documentId);
            insert.Parameters.AddWithValue("$tag_id", tagId);
            insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
            insert.ExecuteNonQuery();
        }
    }

    public static IReadOnlyList<string> CleanTags(IEnumerable<string>? tags)
    {
        if (tags is null)
        {
            return [];
        }

        var cleanedTags = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var tag in tags)
        {
            foreach (var item in tag.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                if (string.IsNullOrWhiteSpace(item))
                {
                    continue;
                }

                var normalized = NormalizeCode(item);
                if (!seen.Add(normalized))
                {
                    continue;
                }

                cleanedTags.Add(item.Trim());
            }
        }

        return cleanedTags;
    }

    public static string NormalizeCode(string value)
    {
        return string.Join("-", value.Trim().ToLowerInvariant().Split(
            ' ',
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
    }

    private static string EnsureTag(SqliteConnection connection, string tagName)
    {
        var code = NormalizeCode(tagName);
        using (var lookup = connection.CreateCommand())
        {
            lookup.CommandText = """
                SELECT tag_id
                FROM tag_definitions
                WHERE tag_type = 'custom' AND code = $code
                LIMIT 1;
                """;
            lookup.Parameters.AddWithValue("$code", code);
            if (lookup.ExecuteScalar() is string existingTagId)
            {
                using var update = connection.CreateCommand();
                update.CommandText = """
                    UPDATE tag_definitions
                    SET name = $name,
                        is_active = 1
                    WHERE tag_id = $tag_id;
                    """;
                update.Parameters.AddWithValue("$name", tagName);
                update.Parameters.AddWithValue("$tag_id", existingTagId);
                update.ExecuteNonQuery();
                return existingTagId;
            }
        }

        var tagId = $"tag-{Guid.NewGuid():N}";
        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO tag_definitions (tag_id, tag_type, code, name, parent_tag_id, is_active, created_at)
            VALUES ($tag_id, 'custom', $code, $name, NULL, 1, $created_at);
            """;
        insert.Parameters.AddWithValue("$tag_id", tagId);
        insert.Parameters.AddWithValue("$code", code);
        insert.Parameters.AddWithValue("$name", tagName);
        insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        insert.ExecuteNonQuery();
        return tagId;
    }

    private static TagRecord ReadTag(SqliteDataReader reader)
    {
        return new TagRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.IsDBNull(5) ? null : reader.GetString(5),
            reader.GetInt32(6) == 1,
            DateTime.Parse(reader.GetString(7)));
    }
}
