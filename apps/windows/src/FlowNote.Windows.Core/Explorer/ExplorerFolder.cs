namespace FlowNote.Windows.Core.Explorer;

public sealed record ExplorerFolder(
    long Id,
    string Name,
    string Path,
    bool IsSystem,
    IReadOnlyList<ExplorerFolder> Children)
{
    public string IconGlyph => "\uE8B7";
}
