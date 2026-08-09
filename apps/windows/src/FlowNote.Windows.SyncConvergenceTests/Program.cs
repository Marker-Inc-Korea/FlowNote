using System.Globalization;
using System.Net.Http.Headers;
using System.Text.Json;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

var runId = Environment.GetEnvironmentVariable("FLOWNOTE_SYNC_CONVERGENCE_RUN_ID")
    ?? $"sync-convergence-{DateTime.UtcNow:yyyyMMddHHmmssfff}";
var outputPath = Environment.GetEnvironmentVariable("FLOWNOTE_SYNC_CONVERGENCE_OUTPUT")
    ?? Path.Combine("tmp", "run-logs", $"{runId}-convergence.json");
var serverDatabasePath = Environment.GetEnvironmentVariable("FLOWNOTE_SERVER_DATABASE_PATH")
    ?? Path.GetFullPath(Path.Combine("services", "api", "data", "flownote.sqlite3"));
var serverBaseUrl = Environment.GetEnvironmentVariable(FlowNoteServerApiEnvironment.ApiBaseUrlEnvironmentVariable)
    ?? FlowNoteServerApiEnvironment.DefaultServerExampleUrl;
var databasePath = FlowNoteLocalDatabase.DefaultDatabasePath;
var actor = $"동기화 수렴 검증 {runId}";

Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? ".");
var services = new FlowNoteLocalServices(databasePath);
var documentsFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName);
var generalFolder = services.Folders.ListFolders()
    .Single(folder =>
        folder.ParentId == documentsFolder.Id &&
        folder.Name == FlowNoteLocalDatabase.GeneralDocumentFolderName);
var artifactRoot = Path.Combine(
    Path.GetDirectoryName(databasePath)!,
    "Files",
    "SyncConvergence",
    DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
Directory.CreateDirectory(artifactRoot);

var originalFile = Path.Combine(artifactRoot, $"{runId}-v1.txt");
var versionFile = Path.Combine(artifactRoot, $"{runId}-v2.txt");
var attachmentFile = Path.Combine(artifactRoot, $"{runId}-attachment.txt");
File.WriteAllText(originalFile, $"FlowNote sync convergence v1. run={runId}");
File.WriteAllText(versionFile, $"FlowNote sync convergence v2. run={runId}");
File.WriteAllText(attachmentFile, $"FlowNote FieldComment attachment. run={runId}");

var document = services.Documents.RegisterDocument(
    generalFolder.Id,
    $"동기화 수렴 {runId}",
    Path.GetFileName(originalFile),
    "Text",
    actor,
    originalFile,
    ["sync-convergence", runId]);
var version = services.Documents.AddFileVersion(
    document.DocumentId,
    Path.GetFileName(versionFile),
    versionFile,
    "v2",
    $"동기화 수렴 버전 run={runId}",
    actor);
var published = services.Documents.PublishVersion(document.DocumentId, version.VersionNo, actor);
var authoritativeTarget = services.Documents.UpdateDocumentStatus(document.DocumentId, "PUBLISHED", actor);
services.Tags.ReplaceDocumentTags(document.DocumentId, ["server-authority", runId]);
var tagged = services.Documents.ListDocuments(generalFolder.Id)
    .Single(item => item.DocumentId == document.DocumentId);

var fieldComment = services.FieldComments.AddDocumentComment(
    document.DocumentId,
    $"동기화 수렴 FieldComment run={runId}",
    actor);
var analyzedFieldComment = services.FieldComments.UpdateReview(
    fieldComment.CommentId,
    null,
    "공개 버전과 대조해 분석함.",
    "ANALYZED",
    actor,
    $"동기화 수렴 분석 run={runId}");
var reviewedFieldComment = services.FieldComments.UpdateReview(
    fieldComment.CommentId,
    "동기화 수렴 검토",
    "공개 버전과 대조해 보고서 근거로 승인함.",
    "REVIEWED",
    actor,
    $"동기화 수렴 검토 run={runId}");
var selectedFieldComment = services.FieldComments.UpdateReview(
    fieldComment.CommentId,
    "동기화 수렴 검토",
    "공개 버전과 대조해 보고서 근거로 승인함.",
    "SELECTED",
    actor,
    $"동기화 수렴 검토 run={runId}");
fieldComment = selectedFieldComment;
var attachment = services.FieldComments.AddAttachment(
    fieldComment.CommentId,
    attachmentFile,
    actor,
    $"동기화 수렴 첨부 run={runId}");
var accessLogId = services.DocumentViewLogs.StartDocumentView(
    document.DocumentId,
    version.VersionNo,
    actor);
var accessStarted = services.DocumentViewLogs.GetLog(accessLogId)
    ?? throw new InvalidOperationException("접근 시작 로그를 읽을 수 없습니다.");
services.DocumentViewLogs.CloseDocumentView(accessLogId, "window_closed");
var accessClosed = services.DocumentViewLogs.GetLog(accessLogId)
    ?? throw new InvalidOperationException("접근 종료 로그를 읽을 수 없습니다.");

var reportSources = new[]
{
    new ReportSourceCandidateRecord(
        "FIELD_COMMENT",
        fieldComment.CommentId,
        document.Title,
        fieldComment.RawContent,
        fieldComment.CreatedAt,
        fieldComment.DocumentVersionNo?.ToString(CultureInfo.InvariantCulture),
        "primary"),
    new ReportSourceCandidateRecord(
        "DOCUMENT",
        document.DocumentId,
        document.Title,
        version.FileName,
        version.UpdatedAt,
        version.VersionNo.ToString(CultureInfo.InvariantCulture),
        "related_document")
};
var reportContent = services.Reports.BuildDraftContent(
    $"동기화 수렴 보고서 {runId}",
    "FieldComment와 공개 문서 상태의 서버 수렴을 검증한다.",
    reportSources,
    actor);
var report = services.Reports.SaveDraftAsDocument(
    generalFolder.Id,
    $"동기화 수렴 보고서 {runId}",
    reportContent,
    actor,
    reportSources,
    $"동기화 수렴 run={runId}");

await services.ServerSync.QueueAndTrySyncReportAsync(report, null);
await services.ServerSync.QueueAndTrySyncAccessLogAsync(accessClosed, "view_closed", null);
await services.ServerSync.QueueAndTrySyncAccessLogAsync(accessStarted, "view_started", null);
await services.ServerSync.QueueAndTrySyncFieldCommentAttachmentAsync(attachment, null);
await services.ServerSync.QueueAndTrySyncFieldCommentAsync(fieldComment, null);
var reviewChangedAt = DateTime.UtcNow;
await services.ServerSync.QueueAndTrySyncFieldCommentReviewAsync(
    analyzedFieldComment,
    null,
    "user-admin",
    reviewChangedAt);
await services.ServerSync.QueueAndTrySyncFieldCommentReviewAsync(
    reviewedFieldComment,
    null,
    "user-admin",
    reviewChangedAt.AddTicks(1));
await services.ServerSync.QueueAndTrySyncFieldCommentReviewAsync(
    selectedFieldComment,
    null,
    "user-admin",
    reviewChangedAt.AddTicks(2));
await services.ServerSync.QueueAndTrySyncDocumentTagsAsync(tagged, null);
await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(authoritativeTarget, null);
await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(published, null);
await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(version, null);
await services.ServerSync.QueueAndTrySyncDocumentAsync(document, null);

using var httpClient = FlowNoteServerApiEnvironment.CreateHttpClient(serverBaseUrl, TimeSpan.FromSeconds(30))
    ?? throw new InvalidOperationException($"서버 URL이 올바르지 않습니다: {serverBaseUrl}");
var auth = new FlowNoteServerAuthClient(httpClient);
var login = await auth.TryLoginAsync("admin", "1234")
    ?? throw new InvalidOperationException("검증용 admin 로그인이 실패했습니다.");
httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
var serverClient = new FlowNoteServerDocumentClient(httpClient);

var firstRetry = await services.ServerSync.RetryPendingAsync(serverClient, login.UserId);
var firstEvidence = ReadEvidence(
    services.Database,
    serverDatabasePath,
    document.DocumentId,
    fieldComment.CommentId,
    attachment.AttachmentId,
    accessLogId,
    report.DocumentId);
Require(firstEvidence.RunQueueCount == 13, $"이번 run 큐는 13건이어야 합니다: {firstEvidence.RunQueueCount}");
Require(firstEvidence.RunSyncedCount == 13, $"이번 run 큐가 모두 SYNCED가 아닙니다: {firstEvidence.RunSyncedCount}/13");
Require(firstEvidence.DuplicateServerDocuments == 0, "서버 문서가 중복 생성되었습니다.");
Require(firstEvidence.DuplicateServerVersions == 0, "서버 문서 버전이 중복 생성되었습니다.");
Require(firstEvidence.DuplicateMutationReceipts == 0, "서버 mutation receipt가 중복 생성되었습니다.");
Require(firstEvidence.OrphanReportSources == 0, "이번 run 보고서에 orphan source가 있습니다.");

var authoritative = await serverClient.GetDocumentAsync(firstEvidence.ServerDocumentId!);
Require(authoritative.Status == "PUBLISHED", $"서버 문서 상태가 PUBLISHED가 아닙니다: {authoritative.Status}");
Require(
    authoritative.PublishedVersionId == firstEvidence.ServerVersionId,
    "서버 공개 버전과 WPF 공개 버전 mapping이 다릅니다.");
Require(
    authoritative.Tags.Order(StringComparer.OrdinalIgnoreCase)
        .SequenceEqual(tagged.TagList.Order(StringComparer.OrdinalIgnoreCase), StringComparer.OrdinalIgnoreCase),
    "서버 태그와 WPF 태그가 다릅니다.");

var secondRetry = await services.ServerSync.RetryPendingAsync(serverClient, login.UserId);
var secondEvidence = ReadEvidence(
    services.Database,
    serverDatabasePath,
    document.DocumentId,
    fieldComment.CommentId,
    attachment.AttachmentId,
    accessLogId,
    report.DocumentId);
Require(secondEvidence.RunSyncedCount == 13, "같은 큐 재실행 뒤 SYNCED 상태가 바뀌었습니다.");
Require(secondEvidence.ServerDocumentCount == firstEvidence.ServerDocumentCount, "재실행으로 서버 문서가 늘었습니다.");
Require(secondEvidence.ServerVersionCount == firstEvidence.ServerVersionCount, "재실행으로 서버 버전이 늘었습니다.");
Require(secondEvidence.MutationReceiptCount == firstEvidence.MutationReceiptCount, "재실행으로 mutation receipt가 늘었습니다.");
Require(secondEvidence.ServerRevision == firstEvidence.ServerRevision, "재실행으로 서버 revision이 늘었습니다.");

var result = new
{
    runId,
    databasePath,
    serverDatabasePath,
    serverBaseUrl,
    documentId = document.DocumentId,
    reportDocumentId = report.DocumentId,
    firstRetry,
    secondRetry,
    firstEvidence,
    secondEvidence,
    serverAuthority = new
    {
        authoritative.DocumentId,
        authoritative.Status,
        authoritative.Revision,
        authoritative.PublishedVersionId,
        authoritative.Tags
    },
    passed = true,
    completedAt = DateTimeOffset.UtcNow
};
File.WriteAllText(outputPath, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"동기화 수렴 검증 통과: run={runId}, evidence={Path.GetFullPath(outputPath)}");

static ConvergenceEvidence ReadEvidence(
    FlowNoteLocalDatabase database,
    string serverDatabasePath,
    string documentId,
    string commentId,
    string attachmentId,
    long accessLogId,
    string reportDocumentId)
{
    using var local = database.OpenConnection();
    var entityIds = new[] { documentId, commentId, attachmentId, accessLogId.ToString(), reportDocumentId };
    var placeholders = string.Join(", ", entityIds.Select((_, index) => $"$id{index}"));
    using var queue = local.CreateCommand();
    queue.CommandText = $"""
        SELECT COUNT(*),
               SUM(CASE WHEN status = 'SYNCED' THEN 1 ELSE 0 END),
               MAX(CASE WHEN local_document_id = $document_id THEN server_document_id END),
               MAX(CASE
                   WHEN local_document_id = $document_id
                    AND entity_type = 'document_publish'
                   THEN server_version_id
               END)
        FROM server_sync_queue
        WHERE entity_id IN ({placeholders});
        """;
    queue.Parameters.AddWithValue("$document_id", documentId);
    for (var index = 0; index < entityIds.Length; index++)
    {
        queue.Parameters.AddWithValue($"$id{index}", entityIds[index]);
    }

    using var reader = queue.ExecuteReader();
    reader.Read();
    var queueCount = reader.GetInt32(0);
    var syncedCount = reader.IsDBNull(1) ? 0 : reader.GetInt32(1);
    var serverDocumentId = reader.IsDBNull(2) ? null : reader.GetString(2);
    var serverVersionId = reader.IsDBNull(3) ? null : reader.GetString(3);
    reader.Close();
    Require(!string.IsNullOrWhiteSpace(serverDocumentId), "서버 문서 mapping이 없습니다.");
    Require(!string.IsNullOrWhiteSpace(serverVersionId), "서버 버전 mapping이 없습니다.");

    var idempotencyKeys = ReadIdempotencyKeys(local, entityIds);
    var sourceOrphans = Scalar(
        local,
        """
        SELECT COUNT(*)
        FROM report_sources
        WHERE local_report_document_id = $report_id
          AND (trace_id IS NULL OR source_hash_sha256 IS NULL);
        """,
        ("$report_id", reportDocumentId));

    var serverBuilder = new SqliteConnectionStringBuilder
    {
        DataSource = serverDatabasePath,
        Mode = SqliteOpenMode.ReadOnly
    };
    using var server = new SqliteConnection(serverBuilder.ToString());
    server.Open();
    var documentCount = Scalar(
        server,
        "SELECT COUNT(*) FROM documents WHERE idempotency_key = $key;",
        ("$key", idempotencyKeys["document"]));
    var versionCount = Scalar(
        server,
        "SELECT COUNT(*) FROM document_versions WHERE idempotency_key = $key;",
        ("$key", idempotencyKeys["document_version"]));
    var receiptKeys = idempotencyKeys
        .Where(item => item.Key is "document_publish" or "document_status" or "document_tags")
        .Select(item => item.Value)
        .ToArray();
    var receiptCount = receiptKeys.Sum(key => Scalar(
        server,
        "SELECT COUNT(*) FROM document_mutation_receipts WHERE mutation_key = $key;",
        ("$key", key)));
    var revision = Scalar(
        server,
        "SELECT revision FROM documents WHERE document_id = $document_id;",
        ("$document_id", serverDocumentId!));

    return new ConvergenceEvidence(
        queueCount,
        syncedCount,
        serverDocumentId,
        serverVersionId,
        documentCount,
        versionCount,
        receiptCount,
        Math.Max(0, documentCount - 1),
        Math.Max(0, versionCount - 1),
        Math.Max(0, receiptCount - receiptKeys.Length),
        sourceOrphans,
        revision);
}

static Dictionary<string, string> ReadIdempotencyKeys(SqliteConnection connection, IReadOnlyList<string> entityIds)
{
    var placeholders = string.Join(", ", entityIds.Select((_, index) => $"$keyId{index}"));
    using var command = connection.CreateCommand();
    command.CommandText = $"""
        SELECT entity_type, idempotency_key
        FROM server_sync_queue
        WHERE entity_id IN ({placeholders})
          AND entity_type IN ('document', 'document_version', 'document_publish', 'document_status', 'document_tags');
        """;
    for (var index = 0; index < entityIds.Count; index++)
    {
        command.Parameters.AddWithValue($"$keyId{index}", entityIds[index]);
    }

    using var reader = command.ExecuteReader();
    var result = new Dictionary<string, string>(StringComparer.Ordinal);
    while (reader.Read())
    {
        result[reader.GetString(0)] = reader.GetString(1);
    }

    return result;
}

static int Scalar(SqliteConnection connection, string sql, params (string Name, object Value)[] parameters)
{
    using var command = connection.CreateCommand();
    command.CommandText = sql;
    foreach (var (name, value) in parameters)
    {
        command.Parameters.AddWithValue(name, value);
    }

    return Convert.ToInt32(command.ExecuteScalar(), CultureInfo.InvariantCulture);
}

static void Require(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}

internal sealed record ConvergenceEvidence(
    int RunQueueCount,
    int RunSyncedCount,
    string? ServerDocumentId,
    string? ServerVersionId,
    int ServerDocumentCount,
    int ServerVersionCount,
    int MutationReceiptCount,
    int DuplicateServerDocuments,
    int DuplicateServerVersions,
    int DuplicateMutationReceipts,
    int OrphanReportSources,
    int ServerRevision);
