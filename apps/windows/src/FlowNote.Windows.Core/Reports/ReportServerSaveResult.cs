using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.Core.Reports;

public sealed record ReportServerSaveResult(
    ServerReportResponse Draft,
    ServerReportResponse Saved,
    DocumentRecord? LocalDocument,
    IReadOnlyList<ReportSourceCandidateRecord> SkippedSources)
{
    public string ReportId => Saved.ReportId;

    public string? GeneratedDocumentId => Saved.GeneratedDocumentId;
}
