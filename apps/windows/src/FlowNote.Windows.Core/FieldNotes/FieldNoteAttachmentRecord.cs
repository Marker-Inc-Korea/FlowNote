namespace FlowNote.Windows.Core.FieldNotes;

public sealed record FieldNoteAttachmentRecord(
    long Id,
    string AttachmentId,
    string NoteId,
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
