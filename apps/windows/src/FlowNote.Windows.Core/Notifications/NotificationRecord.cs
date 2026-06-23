namespace FlowNote.Windows.Core.Notifications;

public sealed record NotificationRecord(
    long Id,
    string NotificationId,
    string RecipientName,
    string ActorName,
    string DocumentId,
    string DocumentTitle,
    string Message,
    bool IsRead,
    DateTime CreatedAt);
