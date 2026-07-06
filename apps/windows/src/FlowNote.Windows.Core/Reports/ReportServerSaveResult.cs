using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.Core.Reports;

public sealed record ReportServerSaveResult(
    ServerReportResponse? Saved,
    DocumentRecord LocalDocument,
    IReadOnlyList<ReportSourceCandidateRecord> SkippedSources,
    ServerSyncResult SyncResult)
{
    public string? ReportId => Saved?.ReportId;

    public string? GeneratedDocumentId => Saved?.GeneratedDocumentId;
}
