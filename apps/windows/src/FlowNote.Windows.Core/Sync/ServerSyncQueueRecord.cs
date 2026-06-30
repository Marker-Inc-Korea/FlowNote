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
    string? ServerCommentId,
    string? ServerAttachmentId,
    string? ServerLogId);
