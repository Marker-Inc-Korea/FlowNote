namespace FlowNote.Windows.Core.Reports;

public sealed record ReportSourceFreezeResult(
    IReadOnlyList<ReportSourceCandidateRecord> Sources,
    IReadOnlyList<ReportSourceVerificationRecord> Verifications)
{
    public bool Valid => Verifications.Count > 0 && Verifications.All(item => item.Valid);
}
