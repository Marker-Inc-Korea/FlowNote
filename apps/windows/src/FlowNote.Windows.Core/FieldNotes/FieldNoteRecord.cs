namespace FlowNote.Windows.Core.FieldNotes;

public sealed record FieldNoteRecord(
    long Id,
    string NoteId,
    string? DocumentId,
    int? DocumentVersionNo,
    string NoteType,
    string InputMode,
    string? SignalLevel,
    string RawContent,
    string? NormalizedContent,
    string? AnalysisContent,
    string AuthorName,
    string? ReportedBy,
    string? OperatorName,
    string EntrySource,
    string? DeviceId,
    string? LocationCode,
    string Status,
    DateTime CreatedAt,
    DateTime? SyncedAt);
