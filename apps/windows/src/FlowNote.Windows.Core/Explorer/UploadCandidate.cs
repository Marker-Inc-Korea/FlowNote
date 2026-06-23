namespace FlowNote.Windows.Core.Explorer;

public sealed record UploadCandidate(
    string FileName,
    string FullPath,
    string Extension,
    long SizeBytes,
    DateTime AddedAt);
