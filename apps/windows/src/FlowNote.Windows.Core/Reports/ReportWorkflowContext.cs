namespace FlowNote.Windows.Core.Reports;

public sealed record ReportWorkflowContext(
    string DraftReportId,
    int BaseReportRevision,
    string ContentHashSha256,
    string SourceSetHashSha256,
    string TargetStatus = "APPROVED");
