namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncQueueRecord(
    long Id,
    string SyncId,
    string EntityType,
    string EntityId,
    string Action,
    string? LocalDocumentId,
    int? LocalVersionNo,
    string IdempotencyKey,
    string Status,
    int AttemptCount,
    string? LastError,
    DateTime CreatedAt,
    DateTime? LastAttemptAt,
    DateTime? SyncedAt,
    string? ServerDocumentId,
    string? ServerVersionId,
    string? ServerReportId,
    string? ServerCommentId,
    string? ServerAttachmentId,
    string? ServerLogId,
    int? BaseServerRevision,
    string? ExpectedServerVersionId,
    string? ExpectedPublishedVersionId,
    string? LocalFileHashSha256,
    int? BaseDomainRevision,
    string? IntentHash,
    string? SourceSetHash,
    string? ConflictCode,
    string? ConflictDetails,
    string? ResolutionAction,
    string? ResolutionReason,
    string? ResolvedBy,
    DateTime? ResolvedAt)
{
    public ServerSyncQueueDiagnosis Diagnosis =>
        ServerSyncQueueDiagnostics.Classify(Status, EntityType, Action, LastError);
}
