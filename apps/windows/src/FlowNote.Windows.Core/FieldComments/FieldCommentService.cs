using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.FieldComments;

public sealed class FieldCommentService
{
    private readonly FieldCommentRepository repository;
    private readonly FieldCommentWorkbenchQuery workbench;

    public FieldCommentService(FlowNoteLocalDatabase database)
    {
        repository = new FieldCommentRepository(database);
        workbench = new FieldCommentWorkbenchQuery(database);
    }

    public static IReadOnlyList<string> ReviewStatuses =>
        FieldCommentWorkflowService.ReviewStatuses;

    public FieldCommentRecord AddDocumentComment(
        string documentId,
        string rawContent,
        string authorName,
        string commentType = "issue",
        string inputMode = "free_text",
        string entrySource = "field_user",
        string? signalLevel = null,
        string? reportedBy = null,
        string? operatorName = null,
        string? deviceId = null,
        string? locationCode = null) =>
        repository.AddDocumentComment(
            documentId, rawContent, authorName, commentType, inputMode, entrySource,
            signalLevel, reportedBy, operatorName, deviceId, locationCode);

    public IReadOnlyList<FieldCommentRecord> ListDocumentComments(string documentId) =>
        repository.ListDocumentComments(documentId);

    public IReadOnlyList<FieldCommentReviewRecord> ListForReview(
        FieldCommentReviewFilter? filter = null) =>
        workbench.ListForReview(filter);

    public string? GetServerCommentId(string commentId) =>
        repository.GetServerCommentId(commentId);

    public IReadOnlyList<FieldCommentSavedView> ListSavedViews() =>
        repository.ListSavedViews();

    public void SaveView(string name, FieldCommentReviewFilter filter) =>
        repository.SaveView(name, filter);

    public FieldCommentRecord UpdateReview(
        string commentId,
        string? normalizedContent,
        string? analysisContent,
        string status,
        string actorName,
        string transitionReason,
        string? assignedTo = null,
        DateTime? reviewDueAt = null,
        bool conflictFlag = false,
        string? conflictBasis = null) =>
        repository.UpdateReview(
            commentId, normalizedContent, analysisContent, status, actorName,
            transitionReason, assignedTo, reviewDueAt, conflictFlag, conflictBasis);

    public void ApplyServerReviewResult(
        string commentId,
        string? normalizedContent,
        string? analysisContent,
        string status,
        string? assignedTo,
        DateTime? reviewDueAt,
        string? transitionReason,
        int reviewRevision,
        bool conflictFlag,
        string? conflictBasis,
        string actorName) =>
        repository.ApplyServerReviewResult(
            commentId, normalizedContent, analysisContent, status, assignedTo,
            reviewDueAt, transitionReason, reviewRevision, conflictFlag,
            conflictBasis, actorName);

    public FieldCommentAttachmentRecord AddAttachment(
        string commentId,
        string sourcePath,
        string createdBy,
        string? caption = null,
        DateTime? capturedAt = null,
        string? attachmentType = null) =>
        repository.AddAttachment(
            commentId, sourcePath, createdBy, caption, capturedAt, attachmentType);

    public IReadOnlyList<FieldCommentAttachmentRecord> ListAttachments(string commentId) =>
        repository.ListAttachments(commentId);
}
