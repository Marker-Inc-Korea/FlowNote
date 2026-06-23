namespace FlowNote.Windows.Core.Explorer;

public sealed class ExplorerFolder(
    long id,
    string name,
    string path,
    bool isSystem,
    IReadOnlyList<ExplorerFolder> children,
    bool isExpanded = false)
{
    public long Id { get; } = id;

    public string Name { get; } = name;

    public string Path { get; } = path;

    public bool IsSystem { get; } = isSystem;

    public IReadOnlyList<ExplorerFolder> Children { get; } = children;

    public bool IsExpanded { get; set; } = isExpanded;

    public string IconGlyph => "\uE8B7";
}
