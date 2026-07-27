using FlowNote.Windows.Core.FieldComments;

internal static class FieldCommentSmokeReview
{
    public static FieldCommentRecord SelectForReport(
        FieldCommentService service,
        FieldCommentRecord comment,
        string actorName)
    {
        const string normalized = "정방향 큐 재시도 보고서 근거";
        const string analysis = "공개된 v2 문서와 대조해 보고서 source로 선정함.";
        comment = service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "ANALYZED",
            actorName,
            "정방향 큐 보고서 근거 분석");
        comment = service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "REVIEWED",
            actorName,
            "정방향 큐 보고서 근거 검토");
        return service.UpdateReview(
            comment.CommentId,
            normalized,
            analysis,
            "SELECTED",
            actorName,
            "정방향 큐 보고서 근거 선정");
    }
}
