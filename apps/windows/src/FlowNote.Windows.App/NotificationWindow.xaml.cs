using System.Windows;
using FlowNote.Windows.Core.Notifications;

namespace FlowNote.Windows.App;

public partial class NotificationWindow : Window
{
    private readonly NotificationService notifications;
    private readonly string recipientName;

    public NotificationWindow(NotificationService notifications, string recipientName)
    {
        InitializeComponent();
        this.notifications = notifications;
        this.recipientName = recipientName;
        RefreshNotifications();
    }

    private void RefreshNotifications()
    {
        var items = notifications.ListNotifications(recipientName);
        NotificationGrid.ItemsSource = items;
        SummaryTextBlock.Text = $"{recipientName}: {items.Count} notifications, {items.Count(item => !item.IsRead)} unread";
    }

    private void MarkSelectedReadButton_Click(object sender, RoutedEventArgs e)
    {
        if (NotificationGrid.SelectedItem is NotificationRecord notification)
        {
            notifications.MarkAsRead(notification.NotificationId, recipientName);
            RefreshNotifications();
        }
    }

    private void MarkAllReadButton_Click(object sender, RoutedEventArgs e)
    {
        notifications.MarkAllAsRead(recipientName);
        RefreshNotifications();
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }
}
