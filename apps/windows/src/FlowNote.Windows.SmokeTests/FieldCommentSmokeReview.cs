using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.Sync;

internal static class FieldCommentSmokeReview
{
    public const string ExpectedOrderedAttemptOrder =
        "document:register_document|" +
        "document_version:register_document_version|" +
        "document_publish:publish_document_version|" +
        "document_status:update_document_status|" +
        "field_comment:register_field_comment|" +
        "field_comment_review:update_field_comment_review|" +
        "field_comment_review:update_field_comment_review|" +
        "field_comment_review:update_field_comment_review|" +
        "field_comment_attachment:register_field_comment_attachment|" +
        "document_access_log:register_access_log_started|" +
        "document_access_log:register_access_log_closed|" +
        "report:register_report";

    public static async Task<FieldCommentRecord> SelectForReportAsync(
        FieldCommentService service,
        ServerSyncService sync,
        FieldCommentRecord comment,
        string actorName)
    {
        const string normalized = "정방향 큐 재시도 보고서 근거";
        const string analysis = "공개된 v2 문서와 대조해 보고서 source로 선정함.";
        var changedAt = DateTime.UtcNow;
        comment = service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "ANALYZED",
            actorName,
            "정방향 큐 보고서 근거 분석");
        await sync.QueueAndTrySyncFieldCommentReviewAsync(
            comment,
            null,
            changedAt: changedAt);
        comment = service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "REVIEWED",
            actorName,
            "정방향 큐 보고서 근거 검토");
        await sync.QueueAndTrySyncFieldCommentReviewAsync(
            comment,
            null,
            changedAt: changedAt.AddTicks(1));
        comment = service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "SELECTED",
            actorName,
            "정방향 큐 보고서 근거 선정");
        await sync.QueueAndTrySyncFieldCommentReviewAsync(
            comment,
            null,
            changedAt: changedAt.AddTicks(2));
        return comment;
    }
}
