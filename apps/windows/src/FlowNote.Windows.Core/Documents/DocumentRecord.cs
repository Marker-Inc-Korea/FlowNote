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
    DateTime CreatedAt,
    DateTime UpdatedAt,
    string? LocalPath,
    int VersionNo,
    string? LatestComment,
    IReadOnlyList<string>? Tags = null,
    int? PublishedVersionNo = null)
{
    public IReadOnlyList<string> TagList { get; } = Tags ?? [];

    public string TagText => TagList.Count == 0 ? string.Empty : string.Join(", ", TagList);

    public string PublishedVersionLabel => PublishedVersionNo is null ? string.Empty : $"v{PublishedVersionNo}";
}
