namespace FlowNote.Windows.Core.Tags;

public sealed record TagRecord(
    long Id,
    string TagId,
    string TagType,
    string Code,
    string Name,
    string? ParentTagId,
    bool IsActive,
    DateTime CreatedAt);
