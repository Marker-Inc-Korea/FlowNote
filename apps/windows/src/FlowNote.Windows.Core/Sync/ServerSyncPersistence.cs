using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Tags;
using Microsoft.Data.Sqlite;
using System.Security.Cryptography;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed partial class ServerSyncService
{
    private DocumentRecord? LoadDocument(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by,
                   created_at, updated_at, local_path, version_no, latest_comment, published_version_no
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt64(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.GetString(6),
            reader.GetString(7),
            DateTime.Parse(reader.GetString(8)),
            DateTime.Parse(reader.GetString(9)),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.GetInt32(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            TagService.ListDocumentTags(connection, documentId),
            reader.IsDBNull(13) ? null : reader.GetInt32(13));
    }

    private DocumentVersionRecord? LoadDocumentVersion(string documentId, int versionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, file_name, local_path, comment, created_by, created_at,
                   version_status, is_latest, is_published, published_at, version_label
            FROM document_versions
            WHERE document_id = $document_id AND version_no = $version_no
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentVersionRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt32(2),
            reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4),
            reader.IsDBNull(5) ? null : reader.GetString(5),
            reader.GetString(6),
            DateTime.Parse(reader.GetString(7)),
            reader.GetString(8),
            reader.GetInt32(9) == 1,
            reader.GetInt32(10) == 1,
            reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11)),
            reader.IsDBNull(12) ? null : reader.GetString(12));
    }

    private async Task<ServerDocumentVersionResponse?> TryFindServerVersionByNumberAsync(
        FlowNoteServerDocumentClient serverClient,
        string serverDocumentId,
        int versionNo,
        CancellationToken cancellationToken)
    {
        var versions = await serverClient.ListVersionsAsync(serverDocumentId, cancellationToken);
        return versions.FirstOrDefault(version => version.VersionNo == versionNo);
    }

    private void MarkDocumentVersionSynced(
        QueueItem item,
        DocumentRecord document,
        DocumentVersionRecord version,
        string serverDocumentId,
        string? serverVersionId,
        int? serverRevision,
        string? serverPublishedVersionId,
        DateTime syncedAt,
        ServerDocumentResponse? authoritative = null)
    {
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        if (authoritative is not null)
        {
            UpdateDocumentServerState(connection, document.DocumentId, authoritative, transaction);
            TagService.ReplaceDocumentTags(
                connection,
                document.DocumentId,
                authoritative.Tags,
                transaction);
        }
        using var update = connection.CreateCommand();
        update.Transaction = transaction;
        update.CommandText = """
            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND version_no = $version_no;

            UPDATE documents
            SET server_document_id = $server_document_id,
                server_version_id = CASE WHEN version_no = $version_no THEN $server_version_id ELSE server_version_id END,
                server_revision = COALESCE($server_revision, server_revision),
                server_published_version_id = $server_published_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id;
            """;
        update.Parameters.AddWithValue("$server_document_id", serverDocumentId);
        update.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        update.Parameters.AddWithValue("$server_revision", serverRevision is null ? DBNull.Value : serverRevision.Value);
        update.Parameters.AddWithValue("$server_published_version_id", string.IsNullOrWhiteSpace(serverPublishedVersionId) ? DBNull.Value : serverPublishedVersionId);
        update.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        update.Parameters.AddWithValue("$document_id", document.DocumentId);
        update.Parameters.AddWithValue("$version_no", version.VersionNo);
        update.ExecuteNonQuery();

        var serverFileHash = authoritative?.LatestVersion?.File.HashSha256;
        UpsertMapping(connection, "document_version", document.DocumentId, version.VersionNo, serverDocumentId, serverVersionId, null, null, null, syncedAt, serverRevision: serverRevision, serverFileHashSha256: serverFileHash, transaction: transaction);
        if (version.IsLatest || document.VersionNo == version.VersionNo)
        {
            UpsertMapping(connection, "document", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt, serverRevision: serverRevision, serverFileHashSha256: serverFileHash, transaction: transaction);
        }

        MarkQueueSynced(connection, item.Id, serverDocumentId, serverVersionId, null, null, syncedAt, transaction: transaction);
        if (serverRevision is not null)
        {
            AdvanceDependentDocumentBases(
                connection,
                document.DocumentId,
                serverRevision.Value,
                serverVersionId,
                serverPublishedVersionId,
                transaction);
        }
        RecordSyncHistory(connection, "server_sync.succeeded", "document_version", document.DocumentId, $"Server document version synced: {serverDocumentId} v{version.VersionNo}", syncedAt, transaction);
        transaction.Commit();
    }

    private static void UpdateDocumentServerState(
        SqliteConnection connection,
        string localDocumentId,
        ServerDocumentResponse response,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE documents
            SET server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                server_revision = $server_revision,
                server_published_version_id = $server_published_version_id,
                server_tags_json = $server_tags_json,
                synced_at = $synced_at
            WHERE document_id = $document_id;
            """;
        command.Parameters.AddWithValue("$server_document_id", response.DocumentId);
        command.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(response.LatestVersionId) ? DBNull.Value : response.LatestVersionId);
        command.Parameters.AddWithValue("$server_revision", response.Revision);
        command.Parameters.AddWithValue("$server_published_version_id", string.IsNullOrWhiteSpace(response.PublishedVersionId) ? DBNull.Value : response.PublishedVersionId);
        command.Parameters.AddWithValue("$server_tags_json", JsonSerializer.Serialize(response.Tags));
        command.Parameters.AddWithValue("$synced_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$document_id", localDocumentId);
        command.ExecuteNonQuery();
    }

    private FieldCommentRecord? LoadFieldComment(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at,
                   assigned_to, review_due_at, last_transition_reason, review_revision,
                   conflict_flag, conflict_basis
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new FieldCommentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetInt32(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.IsDBNull(9) ? null : reader.GetString(9),
            reader.GetString(10),
            reader.IsDBNull(11) ? null : reader.GetString(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            reader.GetString(13),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : reader.GetString(15),
            reader.GetString(16),
            DateTime.Parse(reader.GetString(17)),
            reader.IsDBNull(18) ? null : DateTime.Parse(reader.GetString(18)),
            reader.IsDBNull(19) ? null : reader.GetString(19),
            reader.IsDBNull(20) ? null : DateTime.Parse(reader.GetString(20)),
            reader.IsDBNull(21) ? null : reader.GetString(21),
            reader.GetInt32(22),
            reader.GetInt32(23) != 0,
            reader.IsDBNull(24) ? null : reader.GetString(24));
    }

    private FieldCommentAttachmentRecord? LoadFieldCommentAttachment(string attachmentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, attachment_id, comment_id, local_path, original_file_name, extension,
                   content_type, size_bytes, hash_sha256, attachment_type, caption,
                   captured_at, created_by, created_at, server_attachment_id, synced_at
            FROM field_comment_attachments
            WHERE attachment_id = $attachment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$attachment_id", attachmentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new FieldCommentAttachmentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetInt64(7),
            reader.GetString(8),
            reader.GetString(9),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11)),
            reader.GetString(12),
            DateTime.Parse(reader.GetString(13)),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : DateTime.Parse(reader.GetString(15)));
    }

    private DocumentViewLogRecord? LoadAccessLog(string entityId)
    {
        if (!long.TryParse(entityId, out var id))
        {
            return null;
        }

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, user_name, view_started_at, closed_at, close_reason
            FROM document_view_logs
            WHERE id = $id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$id", id);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentViewLogRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt32(2),
            reader.GetString(3),
            DateTime.Parse(reader.GetString(4)),
            reader.IsDBNull(5) ? null : DateTime.Parse(reader.GetString(5)),
            reader.IsDBNull(6) ? null : reader.GetString(6));
    }

    private IReadOnlyList<ServerReportSourceRequest> MapQueuedReportSources(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT source_type, local_source_id, source_version_id, relation_type,
                   source_revision, source_hash_sha256, snapshot_verified
            FROM report_sources
            WHERE local_report_document_id = $document_id
            ORDER BY id;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);

        using var reader = command.ExecuteReader();
        var sources = new List<ServerReportSourceRequest>();
        while (reader.Read())
        {
            var localSource = new LocalReportSource(
                reader.GetString(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetInt32(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.GetInt32(6) == 1);
            if (TryMapQueuedReportSource(connection, localSource) is { } mapped)
            {
                sources.Add(mapped);
            }
        }

        return sources;
    }

    private int CountQueuedReportSources(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT COUNT(*)
            FROM report_sources
            WHERE local_report_document_id = $document_id;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        return Convert.ToInt32(command.ExecuteScalar());
    }

    private static ServerReportSourceRequest? TryMapQueuedReportSource(
        SqliteConnection connection,
        LocalReportSource source)
    {
        var sourceType = Clean(source.SourceType)?.ToUpperInvariant();
        var sourceId = Clean(source.LocalSourceId);
        if (sourceType is null || sourceId is null)
        {
            return null;
        }

        return sourceType switch
        {
            "FIELD_COMMENT" => TryMapQueuedFieldCommentSource(connection, source, sourceId),
            "DOCUMENT" => TryMapQueuedDocumentSource(connection, source, sourceId),
            "WORK_SEQUENCE_ITEM" => TryMapQueuedLocalOnlySource(connection, "work_sequence_items", "item_id", source, sourceId),
            "WORK_SEQUENCE_HISTORY" => TryMapQueuedLocalOnlySource(connection, "work_sequence_change_history", "change_id", source, sourceId),
            "WORK_RECORD" or "WORK_RECORD_VERSION" => CreateQueuedReportSource(source, sourceType, sourceId),
            _ => null
        };
    }

    private static ServerReportSourceRequest? TryMapQueuedFieldCommentSource(
        SqliteConnection connection,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_comment_id
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", sourceId);
        var value = command.ExecuteScalar();
        if (value is null)
        {
            return CreateQueuedReportSource(source, "FIELD_COMMENT", sourceId);
        }

        var serverCommentId = value is DBNull ? null : Convert.ToString(value);
        return string.IsNullOrWhiteSpace(serverCommentId)
            ? null
            : CreateQueuedReportSource(source, "FIELD_COMMENT", serverCommentId);
    }

    private static ServerReportSourceRequest? TryMapQueuedDocumentSource(
        SqliteConnection connection,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id, server_revision,
                   server_published_version_id
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", sourceId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return CreateQueuedReportSource(source, "DOCUMENT", sourceId, source.SourceVersionId);
        }

        var serverDocumentId = reader.IsDBNull(0) ? null : reader.GetString(0);
        if (string.IsNullOrWhiteSpace(serverDocumentId))
        {
            return null;
        }

        var serverVersionId = reader.IsDBNull(1) ? source.SourceVersionId : reader.GetString(1);
        return CreateQueuedReportSource(source, "DOCUMENT", serverDocumentId, serverVersionId);
    }

    private static ServerReportSourceRequest? TryMapQueuedLocalOnlySource(
        SqliteConnection connection,
        string tableName,
        string idColumn,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"SELECT 1 FROM {tableName} WHERE {idColumn} = $source_id LIMIT 1;";
        command.Parameters.AddWithValue("$source_id", sourceId);
        var value = command.ExecuteScalar();
        return value is null
            ? CreateQueuedReportSource(source, source.SourceType.ToUpperInvariant(), sourceId, source.SourceVersionId)
            : null;
    }

    private static ServerReportSourceRequest CreateQueuedReportSource(
        LocalReportSource source,
        string sourceType,
        string sourceId,
        string? sourceVersionId = null)
    {
        return new ServerReportSourceRequest
        {
            SourceType = sourceType,
            SourceId = sourceId,
            SourceVersionId = Clean(sourceVersionId) ?? Clean(source.SourceVersionId),
            RelationType = Clean(source.RelationType) ?? DefaultReportRelationType(sourceType),
            SourceRevision = source.SnapshotVerified ? source.SourceRevision : null,
            SourceHashSha256 = source.SnapshotVerified ? Clean(source.SourceHashSha256) : null
        };
    }

    private static string DefaultReportRelationType(string sourceType)
    {
        return sourceType switch
        {
            "FIELD_COMMENT" => "primary",
            "DOCUMENT" => "related_document",
            "WORK_SEQUENCE_ITEM" => "work_sequence",
            "WORK_SEQUENCE_HISTORY" => "work_sequence_history",
            "WORK_RECORD" => "work_record",
            "WORK_RECORD_VERSION" => "work_record_version",
            _ => "related"
        };
    }

    private void LinkReportDocumentToServer(
        QueueItem item,
        DocumentRecord document,
        ServerReportResponse savedReport,
        DateTime syncedAt)
    {
        var generatedDocument = savedReport.GeneratedDocument;
        var serverDocumentId = savedReport.GeneratedDocumentId;
        var serverVersionId = generatedDocument?.LatestVersionId ?? generatedDocument?.PublishedVersionId;

        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE documents
            SET server_report_id = $server_report_id,
                server_report_revision = $server_report_revision,
                server_report_content_hash_sha256 = $server_report_content_hash_sha256,
                server_report_source_set_hash_sha256 = $server_report_source_set_hash_sha256,
                server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id;

            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND is_latest = 1;
            """;
        update.Parameters.AddWithValue("$server_report_id", savedReport.ReportId);
        update.Parameters.AddWithValue("$server_report_revision", savedReport.ReportRevision);
        update.Parameters.AddWithValue("$server_report_content_hash_sha256", savedReport.ContentHashSha256!);
        update.Parameters.AddWithValue("$server_report_source_set_hash_sha256", savedReport.SourceSetHashSha256!);
        update.Parameters.AddWithValue("$server_document_id", string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        update.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        update.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        update.Parameters.AddWithValue("$document_id", document.DocumentId);
        update.ExecuteNonQuery();

        UpsertMapping(connection, "document", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        UpsertMapping(connection, "document_version", document.DocumentId, 1, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        UpsertMapping(connection, "report", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        MarkQueueSynced(connection, item.Id, serverDocumentId, serverVersionId, null, null, syncedAt, serverReportId: savedReport.ReportId);
        RecordSyncHistory(connection, "server_sync.succeeded", "report", document.DocumentId, $"Server report synced: {savedReport.ReportId} / {serverDocumentId}", syncedAt);
    }

    private DocumentServerMapping? TryGetDocumentServerMapping(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id, server_revision,
                   server_published_version_id
            FROM documents
            WHERE document_id = $document_id
              AND server_document_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetInt32(2),
            reader.IsDBNull(3) ? null : reader.GetString(3));
    }

    private DocumentServerMapping? TryGetDocumentVersionServerMapping(string documentId, int versionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document.server_document_id, version.server_version_id,
                   document.server_revision, document.server_published_version_id
            FROM document_versions AS version
            JOIN documents AS document ON document.document_id = version.document_id
            WHERE version.document_id = $document_id
              AND version.version_no = $version_no
              AND document.server_document_id IS NOT NULL
              AND version.server_version_id IS NOT NULL
              AND version.synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return TryGetServerIdMapping("document_version", documentId, versionNo);
        }

        return new DocumentServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetInt32(2),
            reader.IsDBNull(3) ? null : reader.GetString(3));
    }

    private DocumentServerMapping? TryGetServerIdMapping(string entityType, string localId, int localVersionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id, server_revision,
                   server_published_version_id, server_file_hash_sha256
            FROM server_id_mappings
            WHERE entity_type = $entity_type
              AND local_id = $local_id
              AND local_version_no = $local_version_no
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$local_id", localId);
        command.Parameters.AddWithValue("$local_version_no", localVersionNo);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetInt32(2),
            reader.IsDBNull(3) ? null : reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4));
    }

    private string? TryGetFieldCommentServerId(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_comment_id
            FROM field_comments
            WHERE comment_id = $comment_id
              AND server_comment_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        return command.ExecuteScalar() as string;
    }

    private string? TryGetFieldCommentAttachmentServerId(string attachmentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_attachment_id
            FROM field_comment_attachments
            WHERE attachment_id = $attachment_id
              AND server_attachment_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$attachment_id", attachmentId);
        return command.ExecuteScalar() as string;
    }

    private string? TryGetAccessLogServerId(long id, bool closeAction)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = closeAction
            ? """
              SELECT server_close_log_id
              FROM document_view_logs
              WHERE id = $id AND server_close_log_id IS NOT NULL;
              """
            : """
              SELECT server_start_log_id
              FROM document_view_logs
              WHERE id = $id AND server_start_log_id IS NOT NULL;
              """;
        command.Parameters.AddWithValue("$id", id);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToString(value);
    }

    private ReportServerMapping? TryGetReportServerMapping(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_report_id, server_document_id, server_version_id
            FROM documents
            WHERE document_id = $document_id
              AND server_report_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return TryGetReportServerIdMapping(localReportDocumentId);
        }

        return new ReportServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2));
    }

    private ReportServerMapping? TryGetReportServerIdMapping(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_report_id, server_document_id, server_version_id
            FROM server_id_mappings
            WHERE entity_type = 'report'
              AND local_id = $local_id
              AND local_version_no = 0
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$local_id", localReportDocumentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new ReportServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2));
    }

    private void MarkAttempt(QueueItem item)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET attempt_count = attempt_count + 1,
                last_attempt_at = $last_attempt_at
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_attempt_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        RecordSyncHistory(
            connection,
            "server_sync.retry_attempted",
            item.EntityType,
            item.EntityId,
            $"Server sync retry attempted: {item.Action} ({item.IdempotencyKey})",
            DateTime.UtcNow);
    }

    private void MarkLatestFailure(string entityType, string entityId, string reason, bool countAttempt = false)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = CASE WHEN status = 'SYNCED' THEN status ELSE 'FAILED' END,
                last_error = CASE WHEN status = 'SYNCED' THEN last_error ELSE $last_error END,
                attempt_count = CASE
                    WHEN status = 'SYNCED' OR $count_attempt = 0 THEN attempt_count
                    ELSE attempt_count + 1
                END,
                last_attempt_at = CASE
                    WHEN status = 'SYNCED' OR $count_attempt = 0 THEN last_attempt_at
                    ELSE $last_attempt_at
                END
            WHERE id = (
                SELECT id
                FROM server_sync_queue
                WHERE entity_type = $entity_type AND entity_id = $entity_id
                ORDER BY id DESC
                LIMIT 1
            );
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$count_attempt", countAttempt ? 1 : 0);
        command.Parameters.AddWithValue("$last_attempt_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$entity_id", entityId);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", entityType, entityId, reason, DateTime.UtcNow);
    }

    private void MarkDependencyHold(QueueItem item, string reason)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'FAILED',
                last_error = $last_error
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", item.EntityType, item.EntityId, reason, DateTime.UtcNow);
    }

    private void RecordFailure(QueueItem item, string reason)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'FAILED',
                last_error = $last_error
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", item.EntityType, item.EntityId, reason, DateTime.UtcNow);
    }

    private void RecordConflict(
        QueueItem item,
        FlowNoteServerConflictException exception,
        string reason,
        ConflictServerReadBack? readBack = null)
    {
        var allowedActions = DocumentConflictResolutionPolicy.AllowedActions(
            item.Action,
            exception.ConflictCode,
            exception.AllowedActions);
        var retryNotBefore = exception.RetryNotBeforeSeconds > 0
            ? DateTime.UtcNow.AddSeconds(exception.RetryNotBeforeSeconds).ToString("O")
            : null;
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'CONFLICT',
                last_error = $last_error,
                conflict_code = $conflict_code,
                conflict_details = $conflict_details,
                server_conflict_hash_sha256 = COALESCE(
                    $server_conflict_hash_sha256,
                    server_conflict_hash_sha256),
                server_read_back_json = COALESCE($server_read_back_json, server_read_back_json),
                allowed_actions_json = $allowed_actions_json,
                retry_not_before = $retry_not_before
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$conflict_code", exception.ConflictCode);
        command.Parameters.AddWithValue("$conflict_details", exception.ResponseBody);
        command.Parameters.AddWithValue(
            "$server_conflict_hash_sha256",
            string.IsNullOrWhiteSpace(readBack?.HashSha256) ? DBNull.Value : readBack.HashSha256);
        command.Parameters.AddWithValue(
            "$server_read_back_json",
            string.IsNullOrWhiteSpace(readBack?.AuthorityJson) ? DBNull.Value : readBack.AuthorityJson);
        command.Parameters.AddWithValue(
            "$allowed_actions_json",
            DocumentConflictResolutionPolicy.ToJson(allowedActions));
        command.Parameters.AddWithValue(
            "$retry_not_before",
            retryNotBefore is null ? DBNull.Value : retryNotBefore);
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        if (exception.ConflictCode == "DOCUMENT_DELETED")
        {
            using var related = connection.CreateCommand();
            related.Transaction = transaction;
            related.CommandText = """
                UPDATE server_sync_queue
                SET status = 'CONFLICT',
                    last_error = $last_error,
                    conflict_code = 'DOCUMENT_DELETED',
                    conflict_details = $conflict_details,
                    server_read_back_json = COALESCE($server_read_back_json, server_read_back_json),
                    allowed_actions_json = '["KEEP_SERVER"]',
                    retry_not_before = NULL
                WHERE id <> $id
                  AND COALESCE(local_document_id, entity_id) = $local_document_id
                  AND status IN ('PENDING', 'FAILED');
                """;
            related.Parameters.AddWithValue(
                "$last_error",
                "서버 문서가 삭제되어 관련 미처리 요청은 자동 재전송하지 않습니다. 서버본 유지로 보존 종결하세요.");
            related.Parameters.AddWithValue("$conflict_details", exception.ResponseBody);
            related.Parameters.AddWithValue(
                "$server_read_back_json",
                string.IsNullOrWhiteSpace(readBack?.AuthorityJson)
                    ? DBNull.Value
                    : readBack.AuthorityJson);
            related.Parameters.AddWithValue("$id", item.Id);
            related.Parameters.AddWithValue(
                "$local_document_id",
                item.LocalDocumentId ?? item.EntityId);
            related.ExecuteNonQuery();
        }
        RecordSyncHistory(
            connection,
            "server_sync.conflict_detected",
            item.EntityType,
            item.EntityId,
            $"{reason} 기준 revision={exception.ExpectedRevision?.ToString() ?? "없음"}, 서버 revision={exception.CurrentRevision?.ToString() ?? "없음"}",
            DateTime.UtcNow,
            transaction);
        transaction.Commit();
    }

    private static string TranslateConflictCode(string code)
    {
        return code switch
        {
            "STALE_REVISION" => "서버 revision 변경 충돌",
            "FIELD_COMMENT_STALE_REVIEW_REVISION" => "FieldComment 검토 revision 충돌",
            "REPORT_STALE_REVISION" => "보고서 revision 충돌",
            "REPORT_SOURCE_STALE_OR_ORPHAN" => "보고서 원천 변경/고아 충돌",
            "REPORT_SOURCE_SET_HASH_MISMATCH" => "보고서 원천 집합 hash 불일치",
            "REPORT_CONTENT_HASH_MISMATCH" => "보고서 내용 hash 불일치",
            "ATTACHMENT_PARENT_MISMATCH" => "첨부 부모 FieldComment 불일치",
            "ATTACHMENT_FILE_HASH_MISMATCH" => "첨부 파일 SHA-256 불일치",
            "STALE_BASE_VERSION" => "기준 버전 변경 충돌",
            "PUBLISHED_VERSION_CHANGED" => "공개본 교체 경쟁 충돌",
            "DOCUMENT_DELETED" => "서버 삭제 문서 재전송 충돌",
            "IDEMPOTENCY_KEY_REUSED" => "멱등키 내용 불일치",
            "IDEMPOTENT_VERSION_BROKEN" => "멱등 버전 원천 불일치",
            "DOCUMENT_WRITE_CONFLICT" => "문서 저장 제약 충돌",
            "FILE_HASH_MISMATCH" => "파일 SHA-256 불일치",
            "DOCUMENT_READ_BACK_MISMATCH" => "서버 read-back 권위 불일치",
            "TAG_MERGE_CONFLICT" => "같은 태그의 추가·제거 경쟁 충돌",
            "TAG_UNAVAILABLE" => "비활성·삭제 태그 충돌",
            "TAG_BASE_UNAVAILABLE" => "태그 기준 revision 스냅샷 누락",
            "TAG_AGGREGATE_CHANGED" => "태그 외 문서 변경과의 aggregate revision 충돌",
            "TAG_INTENT_HASH_MISMATCH" => "태그 변경 의도 hash 불일치",
            "LEGACY_BASE_MISSING" => "구 큐 서버 기준값 누락",
            _ => "서버 문서 충돌"
        };
    }


}
