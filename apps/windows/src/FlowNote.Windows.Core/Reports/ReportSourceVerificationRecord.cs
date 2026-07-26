namespace FlowNote.Windows.Core.Reports;

public sealed record ReportSourceVerificationRecord(
    string SourceType,
    string SourceId,
    string? SourceVersionId,
    int? SourceRevision,
    string? SourceHashSha256,
    bool Valid,
    string Result)
{
    public string HashLabel =>
        string.IsNullOrWhiteSpace(SourceHashSha256)
            ? "없음"
            : $"{SourceHashSha256[..Math.Min(16, SourceHashSha256.Length)]}…";
}
