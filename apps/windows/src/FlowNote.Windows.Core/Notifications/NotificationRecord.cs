namespace FlowNote.Windows.Core.Notifications;

public sealed record NotificationRecord(
    long Id,
    string NotificationId,
    string NotificationType,
    string RecipientName,
    string ActorName,
    string DocumentId,
    string DocumentTitle,
    string? TargetType,
    string? TargetId,
    string? TargetTitle,
    string? SourceCandidateId,
    string Message,
    bool IsRead,
    DateTime CreatedAt)
{
    public string TypeLabel => string.Equals(NotificationType, "work_sequence", StringComparison.Ordinal)
        ? "Work Sequence"
        : "Document";

    public string DisplayTitle => string.IsNullOrWhiteSpace(TargetTitle) ? DocumentTitle : TargetTitle;
}
