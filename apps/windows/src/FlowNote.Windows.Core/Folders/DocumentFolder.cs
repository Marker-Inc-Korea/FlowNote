namespace FlowNote.Windows.Core.Folders;

public sealed record DocumentFolder(
    long Id,
    string FolderId,
    long? ParentId,
    string Name,
    string Path,
    bool IsSystem,
    DateTime CreatedAt);
