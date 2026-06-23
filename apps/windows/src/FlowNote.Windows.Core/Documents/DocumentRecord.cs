namespace FlowNote.Windows.Core.Documents;

public sealed record DocumentRecord(
    long Id,
    string DocumentId,
    long FolderId,
    string Title,
    string FileName,
    string DocumentType,
    string Status,
    string CreatedBy,
    DateTime CreatedAt);
