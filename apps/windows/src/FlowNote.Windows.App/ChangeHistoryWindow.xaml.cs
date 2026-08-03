using System.Net.Http;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ChangeHistoryWindow : Window
{
    private readonly FlowNoteServerAuditClient serverAudit;
    private readonly Action<ServerChangeHistoryItem>? openAction;
    private readonly List<string?> previousCursors = [];
    private string? currentCursor;
    private string? nextCursor;
    private bool loading;

    public ChangeHistoryWindow(
        FlowNoteServerAuditClient serverAudit,
        Action<ServerChangeHistoryItem>? openAction = null)
    {
        InitializeComponent();
        this.serverAudit = serverAudit;
        this.openAction = openAction;
        Loaded += ChangeHistoryWindow_Loaded;
    }

    private async void ChangeHistoryWindow_Loaded(object sender, RoutedEventArgs e)
    {
        InitializeFilters();
        await LoadPageAsync(null, clearHistory: true);
    }

    private void InitializeFilters()
    {
        ActorRoleComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("admin", "관리자"), ("system-admin", "시스템 관리자"),
            ("document-admin", "문서 관리자"), ("manager", "관리자 역할"),
            ("assistant-manager", "차장"), ("department-manager", "부서장"),
            ("line-foreman", "반장"), ("team-lead", "조장"),
            ("team-member", "조원"), ("viewer", "열람자"));
        TargetTypeComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("document", "문서"), ("document_version", "문서 버전"),
            ("field_comment", "FieldComment"), ("report", "보고서"),
            ("work_sequence_board", "작업판"), ("work_sequence_item", "작업순서"));
        ResultComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("SUCCESS", "성공"), ("CONFLICT", "충돌"),
            ("REJECTED", "거부/실패"));
        RiskComboBox.ItemsSource = Options(
            ("ALL", "전체"), ("CRITICAL", "긴급"), ("HIGH", "높음"),
            ("MEDIUM", "보통"), ("LOW", "낮음"));
        foreach (var combo in new[]
                 { ActorRoleComboBox, TargetTypeComboBox, ResultComboBox, RiskComboBox })
        {
            combo.DisplayMemberPath = nameof(FilterOption.Label);
            combo.SelectedValuePath = nameof(FilterOption.Value);
            combo.SelectedValue = "ALL";
        }
        FromDatePicker.SelectedDate = DateTime.Today.AddDays(-30);
        ToDatePicker.SelectedDate = DateTime.Today;
    }

    private static IReadOnlyList<FilterOption> Options(
        params (string Value, string Label)[] values) =>
        values.Select(value => new FilterOption(value.Value, value.Label)).ToList();

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) =>
        await LoadPageAsync(null, clearHistory: true);

    private async void ApplyFilterButton_Click(object sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(RevisionTextBox.Text) &&
            (!int.TryParse(RevisionTextBox.Text.Trim(), out var revision) || revision < 1))
        {
            StatusTextBlock.Text = "revision은 1 이상의 숫자로 입력하세요.";
            return;
        }
        await LoadPageAsync(null, clearHistory: true);
    }

    private async void ResetFilterButton_Click(object sender, RoutedEventArgs e)
    {
        ActorIdTextBox.Clear();
        DeviceIdTextBox.Clear();
        TargetQueryTextBox.Clear();
        VersionIdTextBox.Clear();
        RevisionTextBox.Clear();
        RunIdTextBox.Clear();
        CorrelationIdTextBox.Clear();
        ActionRequiredCheckBox.IsChecked = false;
        ActorRoleComboBox.SelectedValue = "ALL";
        TargetTypeComboBox.SelectedValue = "ALL";
        ResultComboBox.SelectedValue = "ALL";
        RiskComboBox.SelectedValue = "ALL";
        FromDatePicker.SelectedDate = DateTime.Today.AddDays(-30);
        ToDatePicker.SelectedDate = DateTime.Today;
        await LoadPageAsync(null, clearHistory: true);
    }

    private async void NextPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (nextCursor is null) return;
        previousCursors.Add(currentCursor);
        await LoadPageAsync(nextCursor, clearHistory: false);
    }

    private async void PreviousPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (previousCursors.Count == 0) return;
        var cursor = previousCursors[^1];
        previousCursors.RemoveAt(previousCursors.Count - 1);
        await LoadPageAsync(cursor, clearHistory: false);
    }

    private async Task LoadPageAsync(string? cursor, bool clearHistory)
    {
        if (loading) return;
        loading = true;
        SetNavigationEnabled(false);
        if (clearHistory) previousCursors.Clear();
        try
        {
            var page = await serverAudit.ListChangeHistoryAsync(BuildQuery(cursor));
            currentCursor = cursor;
            nextCursor = page.NextCursor;
            HistoryDataGrid.ItemsSource = page.Items;
            SummaryTextBlock.Text =
                $"필터 합계 {page.TotalCount}건 · 조치 필요 {page.ActionRequiredCount}건 · " +
                $"충돌 {Count(page.TotalsByResult, "CONFLICT")}건 · 실패/거부 " +
                $"{Count(page.TotalsByResult, "REJECTED")}건 · 긴급 " +
                $"{Count(page.TotalsByRisk, "CRITICAL")}건 · 높음 " +
                $"{Count(page.TotalsByRisk, "HIGH")}건";
            StatusTextBlock.Text =
                $"원천 {page.SourceAuthority} · snapshot {page.SnapshotAnchorId} · " +
                $"조회 모델 v{page.ReadModelVersion} · 언제든 재생성 가능";
            if (page.Items.Count > 0) HistoryDataGrid.SelectedIndex = 0;
            else ClearDetail("조건에 맞고 현재 권한으로 볼 수 있는 변경 이력이 없습니다.");
        }
        catch (Exception exception) when (
            exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            HistoryDataGrid.ItemsSource = null;
            ClearDetail("변경 이력을 조회하지 못했습니다.");
            StatusTextBlock.Text = exception.Message;
        }
        finally
        {
            loading = false;
            SetNavigationEnabled(true);
        }
    }

    private ServerChangeHistoryQuery BuildQuery(string? cursor)
    {
        int? revision = int.TryParse(RevisionTextBox.Text.Trim(), out var parsedRevision)
            ? parsedRevision
            : null;
        return new ServerChangeHistoryQuery
        {
            OccurredFrom = StartOfDay(FromDatePicker.SelectedDate),
            OccurredTo = EndOfDay(ToDatePicker.SelectedDate),
            ActorId = Clean(ActorIdTextBox.Text),
            ActorRole = SelectedFilter(ActorRoleComboBox),
            DeviceId = Clean(DeviceIdTextBox.Text),
            TargetType = SelectedFilter(TargetTypeComboBox),
            TargetQuery = Clean(TargetQueryTextBox.Text),
            TargetVersionId = Clean(VersionIdTextBox.Text),
            TargetRevision = revision,
            Result = SelectedFilter(ResultComboBox),
            RiskLevel = SelectedFilter(RiskComboBox),
            RunId = Clean(RunIdTextBox.Text),
            CorrelationId = Clean(CorrelationIdTextBox.Text),
            ActionRequired = ActionRequiredCheckBox.IsChecked == true ? true : null,
            Limit = 50,
            Cursor = cursor
        };
    }

    private async void HistoryDataGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (HistoryDataGrid.SelectedItem is ServerChangeHistoryItem item)
        {
            await LoadDetailAsync(item.EventId);
        }
    }

    private async void ReloadDetailButton_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryDataGrid.SelectedItem is ServerChangeHistoryItem item)
            await LoadDetailAsync(item.EventId);
        else
            ClearDetail("원본 감사를 다시 조회할 항목을 선택하세요.");
    }

    private async Task LoadDetailAsync(string eventId)
    {
        try
        {
            var detail = await serverAudit.GetChangeHistoryDetailAsync(eventId);
            if (HistoryDataGrid.SelectedItem is not ServerChangeHistoryItem selected ||
                selected.EventId != eventId) return;
            DetailSummaryTextBlock.Text =
                $"{detail.Item.TargetTitle} · {detail.Item.ResultLabel} · " +
                $"현재 {detail.Item.CurrentStatus} · 담당 {detail.Item.Assignee}";
            AuditDetailTextBox.Text = FormatDetail(detail);
            OpenActionButton.IsEnabled = detail.Item.ActionRequired &&
                detail.Item.ActionRoute != "AUDIT_DETAIL" && openAction is not null;
        }
        catch (Exception exception) when (
            exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            ClearDetail("원본 감사 상세를 조회하지 못했습니다. 권한 또는 서버 연결을 확인하세요.");
            StatusTextBlock.Text = exception.Message;
        }
    }

    private static string FormatDetail(ServerChangeHistoryDetail detail)
    {
        var item = detail.Item;
        var audit = detail.AuditEnvelope;
        var text = new StringBuilder()
            .AppendLine($"영향: {item.Impact}")
            .AppendLine($"다음 행동: {item.NextAction}")
            .AppendLine($"문제 유형: {string.Join(", ", item.IssueKinds)}")
            .AppendLine($"필수 필드 누락: {string.Join(", ", item.MissingAuditFields)}")
            .AppendLine()
            .AppendLine($"event ID: {audit.EventId}")
            .AppendLine($"event type: {audit.EventType}")
            .AppendLine($"actor: {audit.ActorId} ({audit.ActorRole})")
            .AppendLine($"session / device: {audit.SessionId} / {audit.DeviceId ?? "-"}")
            .AppendLine($"target: {audit.TargetType} / {audit.TargetId}")
            .AppendLine($"version / revision: {audit.TargetVersionId ?? "-"} / {audit.TargetRevision?.ToString() ?? "-"}")
            .AppendLine($"result: {audit.Result} / {audit.ResultCode} / HTTP {audit.HttpStatus}")
            .AppendLine($"run / correlation: {audit.RunId ?? "-"} / {audit.CorrelationId}")
            .AppendLine($"domain audit: {audit.DomainAuditType ?? "-"} / {audit.DomainAuditId ?? "-"}")
            .AppendLine($"reason: {audit.Reason ?? "-"}")
            .AppendLine($"before hash: {audit.BeforeHashSha256 ?? "-"}")
            .AppendLine($"after hash: {audit.AfterHashSha256 ?? "-"}")
            .AppendLine($"safe payload: {audit.SafePayload.GetRawText()}");
        return text.ToString();
    }

    private void OpenActionButton_Click(object sender, RoutedEventArgs e)
    {
        if (HistoryDataGrid.SelectedItem is ServerChangeHistoryItem item &&
            item.ActionRequired && item.ActionRoute != "AUDIT_DETAIL")
        {
            openAction?.Invoke(item);
        }
    }

    private void ClearDetail(string message)
    {
        DetailSummaryTextBlock.Text = message;
        AuditDetailTextBox.Clear();
        OpenActionButton.IsEnabled = false;
    }

    private void SetNavigationEnabled(bool enabled)
    {
        PreviousPageButton.IsEnabled = enabled && previousCursors.Count > 0;
        NextPageButton.IsEnabled = enabled && nextCursor is not null;
    }

    private static int Count(IReadOnlyDictionary<string, int> totals, string key) =>
        totals.TryGetValue(key, out var value) ? value : 0;

    private static string? SelectedFilter(ComboBox combo) =>
        combo.SelectedValue?.ToString() is { } value && value != "ALL" ? value : null;

    private static string? Clean(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static DateTimeOffset? StartOfDay(DateTime? date) =>
        date is null ? null : new DateTimeOffset(date.Value.Date, TimeZoneInfo.Local.GetUtcOffset(date.Value.Date));

    private static DateTimeOffset? EndOfDay(DateTime? date) =>
        date is null ? null : StartOfDay(date)?.AddDays(1).AddTicks(-1);

    private sealed record FilterOption(string Value, string Label);
}
