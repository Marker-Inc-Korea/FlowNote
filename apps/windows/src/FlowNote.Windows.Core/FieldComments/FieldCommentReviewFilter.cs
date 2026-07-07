namespace FlowNote.Windows.Core.FieldComments;

public sealed record FieldCommentReviewFilter(
    string? Status = null,
    string? DocumentText = null,
    string? AuthorText = null,
    string? TagText = null,
    DateTime? CreatedFrom = null,
    DateTime? CreatedTo = null,
    int Limit = 300);
