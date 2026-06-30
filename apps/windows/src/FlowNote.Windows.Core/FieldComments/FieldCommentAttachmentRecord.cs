namespace FlowNote.Windows.Core.FieldComments;

public sealed record FieldCommentAttachmentRecord(
    long Id,
    string AttachmentId,
    string CommentId,
    string LocalPath,
    string OriginalFileName,
    string Extension,
    string? ContentType,
    long SizeBytes,
    string HashSha256,
    string AttachmentType,
    string? Caption,
    DateTime? CapturedAt,
    string CreatedBy,
    DateTime CreatedAt,
    string? ServerAttachmentId,
    DateTime? SyncedAt);
