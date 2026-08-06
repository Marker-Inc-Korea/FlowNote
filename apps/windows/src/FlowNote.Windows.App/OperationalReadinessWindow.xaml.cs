using System.Net.Http;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class OperationalReadinessWindow : Window
{
    private readonly FlowNoteServerAuditClient serverAudit;
    private readonly Action<ServerOperationalReadinessItem> openAction;
    private readonly List<string?> previousCursors = [];
    private string? currentCursor;
    private string? nextCursor;
    private bool loading;

    public OperationalReadinessWindow(
        FlowNoteServerAuditClient serverAudit,
        Action<ServerOperationalReadinessItem> openAction)
    {
        InitializeComponent();
        this.serverAudit = serverAudit;
        this.openAction = openAction;
        Loaded += OperationalReadinessWindow_Loaded;
    }

    private async void OperationalReadinessWindow_Loaded(object sender, RoutedEventArgs e)
    {
        AreaComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("DOCUMENT_PUBLICATION", "문서 공개"),
            ("FIELD_COMMENT", "FieldComment 검토"), ("REPORT", "보고서·정정"),
            ("WORK_SEQUENCE", "작업순서 전달"), ("CHANNEL_HANDOVER", "채널·인수인계"),
            ("TERMINAL_DEVICE", "승인 단말"), ("SYNC", "동기화·재결합"),
            ("AUDIT", "감사 완전성·최근 실패"));
        SeverityComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("BLOCKED", "차단"), ("WARNING", "주의"));
        foreach (var combo in new[] { AreaComboBox, SeverityComboBox })
        {
            combo.DisplayMemberPath = nameof(FilterOption.Label);
            combo.SelectedValuePath = nameof(FilterOption.Value);
            combo.SelectedValue = "ALL";
        }
        await LoadPageAsync(null, true);
    }

    private static IReadOnlyList<FilterOption> Options(
        params (string Value, string Label)[] values) =>
        values.Select(value => new FilterOption(value.Value, value.Label)).ToList();

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) =>
        await LoadPageAsync(null, true);

    private async void ApplyFilterButton_Click(object sender, RoutedEventArgs e) =>
        await LoadPageAsync(null, true);

    private async void ResetFilterButton_Click(object sender, RoutedEventArgs e)
    {
        AreaComboBox.SelectedValue = "ALL";
        SeverityComboBox.SelectedValue = "ALL";
        BlockerCodeTextBox.Clear();
        await LoadPageAsync(null, true);
    }

    private async void NextPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (nextCursor is null) return;
        previousCursors.Add(currentCursor);
        await LoadPageAsync(nextCursor, false);
    }

    private async void PreviousPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (previousCursors.Count == 0) return;
        var cursor = previousCursors[^1];
        previousCursors.RemoveAt(previousCursors.Count - 1);
        await LoadPageAsync(cursor, false);
    }

    private async Task LoadPageAsync(string? cursor, bool clearHistory)
    {
        if (loading) return;
        loading = true;
        SetNavigationEnabled(false);
        if (clearHistory) previousCursors.Clear();
        try
        {
            var page = await serverAudit.ListOperationalReadinessAsync(BuildQuery(cursor));
            currentCursor = cursor;
            nextCursor = page.NextCursor;
            AreaDataGrid.ItemsSource = page.Areas;
            ActionDataGrid.ItemsSource = page.Items;
            SummaryTextBlock.Text =
                $"차단 {page.Counts.Blocked}건 · 주의 {page.Counts.Warning}건 · " +
                $"현재 필터 {page.FilteredTotalCount}건";
            SnapshotTextBlock.Text = page.RefreshRequired
                ? $"⚠ {page.RefreshReason} · 기준 시각 {page.AsOf.LocalDateTime:yyyy-MM-dd HH:mm:ss}"
                : $"✓ 최신 snapshot · 기준 시각 {page.AsOf.LocalDateTime:yyyy-MM-dd HH:mm:ss}";
            StatusTextBlock.Text =
                $"원천 {page.SourceAuthority} · snapshot {page.SnapshotAnchorId} · " +
                $"cursor 만료 {page.CursorExpiresAt.LocalDateTime:HH:mm:ss}";
            ShowAIReadiness(page.AIFieldReadiness);
            if (page.Items.Count > 0) ActionDataGrid.SelectedIndex = 0;
            else ClearDetail("현재 필터에 해당하고 권한으로 볼 수 있는 조치 항목이 없습니다.");
        }
        catch (Exception exception) when (
            exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            AreaDataGrid.ItemsSource = null;
            ActionDataGrid.ItemsSource = null;
            ClearDetail("운영 준비도를 조회하지 못했습니다. 원천 데이터와 기존 큐는 변경되지 않았습니다.");
            StatusTextBlock.Text = exception.Message;
        }
        finally
        {
            loading = false;
            SetNavigationEnabled(true);
        }
    }

    private ServerOperationalReadinessQuery BuildQuery(string? cursor) => new()
    {
        AreaCode = SelectedFilter(AreaComboBox),
        Severity = SelectedFilter(SeverityComboBox),
        BlockerCode = Clean(BlockerCodeTextBox.Text)?.ToUpperInvariant(),
        Limit = 50,
        Cursor = cursor
    };

    private void ShowAIReadiness(ServerAIFieldReadinessSummary value)
    {
        AIStatusTextBlock.Text = value.StatusLabel;
        AICountTextBlock.Text = value.Failure is null
            ? $"실제 현장 ground-truth {value.GroundTruthCount ?? 0}건 · 부족 {value.GroundTruthGap ?? 0}건"
            : $"{value.Failure.Message} 담당: {value.Failure.ResponsibleRole}";
        AISeparationTextBlock.Text = value.SeparationNotice;
    }

    private void ActionDataGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ActionDataGrid.SelectedItem is not ServerOperationalReadinessItem item)
        {
            ClearDetail("조치 항목을 선택하세요.");
            return;
        }
        DetailTitleTextBlock.Text = $"{item.SeverityDisplay} · {item.TargetTitle}";
        DetailTextBox.Text = new StringBuilder()
            .AppendLine($"영역: {item.AreaName}")
            .AppendLine($"차단 코드: {item.BlockerDisplay}")
            .AppendLine($"현재 상태 / revision: {item.CurrentStatus} / {item.SourceRevision?.ToString() ?? "-"}")
            .AppendLine($"담당 역할 / 담당자: {item.ResponsibleRole} / {item.Assignee}")
            .AppendLine($"가장 오래된 항목: {item.OldestAtLabel}")
            .AppendLine()
            .AppendLine($"다음 행동: {item.NextAction}")
            .AppendLine($"해결 판정: {item.ResolvedWhen}")
            .AppendLine($"감사 event: {item.LatestEventId ?? "-"}")
            .ToString();
        OpenActionButton.IsEnabled = item.ActionRoute != "AUDIT_DETAIL";
    }

    private void OpenActionButton_Click(object sender, RoutedEventArgs e)
    {
        if (ActionDataGrid.SelectedItem is ServerOperationalReadinessItem item)
            openAction(item);
    }

    private void ClearDetail(string message)
    {
        DetailTitleTextBlock.Text = message;
        DetailTextBox.Clear();
        OpenActionButton.IsEnabled = false;
    }

    private void SetNavigationEnabled(bool enabled)
    {
        PreviousPageButton.IsEnabled = enabled && previousCursors.Count > 0;
        NextPageButton.IsEnabled = enabled && nextCursor is not null;
    }

    private static string? SelectedFilter(ComboBox combo) =>
        combo.SelectedValue?.ToString() is { } value && value != "ALL" ? value : null;

    private static string? Clean(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record FilterOption(string Value, string Label);
}
