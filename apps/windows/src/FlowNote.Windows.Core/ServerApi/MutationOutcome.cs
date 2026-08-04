namespace FlowNote.Windows.Core.ServerApi;

public enum MutationOutcomeStatus
{
    Success,
    PartialSuccess,
    Conflict,
    Rejected
}

public sealed record MutationOutcome<T>(
    MutationOutcomeStatus Status,
    string Code,
    string Message,
    T? Value = default,
    string? Receipt = null,
    int? Revision = null,
    bool SourcePreserved = true,
    string? ResponsibleRole = null,
    string? ActionRoute = null,
    IReadOnlyList<string>? RetryItemIds = null)
{
    public const string SchemaVersion = "mutation-outcome-v1";

    public bool Succeeded =>
        Status is MutationOutcomeStatus.Success or MutationOutcomeStatus.PartialSuccess;

    public IReadOnlyList<string> FailedItemIds => RetryItemIds ?? [];
}
