using System.Windows;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.App;

public partial class HistoryWindow : Window
{
    private readonly HistoryService history;
    private readonly ServerSyncService serverSync;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly string? serverUserId;

    public HistoryWindow(
        HistoryService history,
        ServerSyncService serverSync,
        FlowNoteServerDocumentClient? serverDocumentClient,
        string? serverUserId)
    {
        InitializeComponent();
        this.history = history;
        this.serverSync = serverSync;
        this.serverDocumentClient = serverDocumentClient;
        this.serverUserId = serverUserId;
        RefreshAll();
    }

    private void RefreshAll()
    {
        RefreshHistory();
        RefreshSyncQueue();
    }

    private void RefreshHistory()
    {
        var items = history.ListHistory();
        HistoryGrid.ItemsSource = items;
        SummaryTextBlock.Text = $"전체 이력 {items.Count}건";
    }

    private void RefreshSyncQueue()
    {
        var items = serverSync.ListQueueItems().Select(SyncQueueRow.FromRecord).ToList();
        SyncQueueGrid.ItemsSource = items;

        var pendingCount = items.Count(item => item.Status == "PENDING");
        var failedCount = items.Count(item => item.Status == "FAILED");
        var syncedCount = items.Count(item => item.Status == "SYNCED");
        SyncQueueSummaryTextBlock.Text =
            $"대기 {pendingCount}건, 실패 {failedCount}건, 완료 {syncedCount}건. 앱 시작 자동 재시도 결과는 상태 표시줄에 요약되고 상세 이력은 이 화면에 남습니다.";
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshAll();
    }

    private async void RetrySyncButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null)
        {
            RefreshSyncQueue();
            SyncQueueSummaryTextBlock.Text = "서버 URL 또는 로그인 정보가 없어 재시도할 수 없습니다. 서버 설정과 로그인을 확인하세요. 로컬 데이터는 삭제되지 않습니다.";
            return;
        }

        var result = await serverSync.RetryPendingAsync(serverDocumentClient, serverUserId);
        RefreshAll();
        SyncQueueSummaryTextBlock.Text = result.Message;
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private sealed record SyncQueueRow(
        string Status,
        string StatusText,
        string EntityText,
        string ActionText,
        int AttemptCount,
        DateTime? LastAttemptAt,
        string LastError)
    {
        public static SyncQueueRow FromRecord(ServerSyncQueueRecord record)
        {
            return new SyncQueueRow(
                record.Status,
                FormatStatus(record.Status),
                $"{FormatEntityType(record.EntityType)} / {record.EntityId}",
                FormatAction(record.Action),
                record.AttemptCount,
                record.LastAttemptAt,
                record.LastError ?? "-");
        }

        private static string FormatStatus(string status)
        {
            return status switch
            {
                "PENDING" => "대기",
                "FAILED" => "실패",
                "SYNCED" => "완료",
                _ => status
            };
        }

        private static string FormatEntityType(string entityType)
        {
            return entityType switch
            {
                "document" => "문서",
                "field_comment" => "FieldComment",
                "field_comment_attachment" => "FieldComment 첨부",
                "document_access_log" => "접근 로그",
                _ => entityType
            };
        }

        private static string FormatAction(string action)
        {
            return action switch
            {
                "register_document" => "문서 전송",
                "register_field_comment" => "FieldComment 전송",
                "register_field_comment_attachment" => "첨부 전송",
                "register_access_log_started" => "열람 시작 전송",
                "register_access_log_closed" => "열람 종료 전송",
                "register_access_log_auto_closed" => "자동 종료 전송",
                "register_access_log_download_blocked" => "다운로드 차단 전송",
                _ => action
            };
        }
    }
}
