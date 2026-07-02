namespace FlowNote.Windows.Core.Documents;

public sealed record DocumentPreviewExceptionSampleCriterion(
    string FileType,
    string CaseName,
    string AnonymousSampleFileName,
    string DocumentType,
    DocumentPreviewKind PreviewKind,
    string SampleBasis,
    string ExpectedResult,
    bool RecordsPreviewFailed);
