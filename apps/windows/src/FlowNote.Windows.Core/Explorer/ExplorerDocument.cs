namespace FlowNote.Windows.Core.Explorer;

public sealed record ExplorerDocument(
    string Title,
    string FileName,
    string DocumentType,
    string Status,
    string UpdatedBy,
    DateTime UpdatedAt,
    string VersionLabel,
    string? LocalPath);
