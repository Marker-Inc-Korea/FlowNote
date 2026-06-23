namespace FlowNote.Windows.Core.Explorer;

public sealed record ExplorerFolder(
    string Name,
    string Path,
    IReadOnlyList<ExplorerFolder> Children);
