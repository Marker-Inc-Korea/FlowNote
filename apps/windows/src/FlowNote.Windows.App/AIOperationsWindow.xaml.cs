using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class AIOperationsWindow : Window
{
    private readonly FlowNoteServerAIOperationsClient? client;
    private ServerAIQueryDetailResponse? selectedQueryDetail;
    private bool mutationInProgress;

    public AIOperationsWindow(FlowNoteServerAIOperationsClient? client)
    {
        InitializeComponent();
        this.client = client;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (client is null) { StatusTextBlock.Text = "서버 URL과 시스템 관리자 로그인이 필요합니다."; return; }
        try
        {
            var policies = await client.ListPoliciesAsync();
            PolicyGrid.ItemsSource = policies;
            ApprovalGrid.ItemsSource = await client.ListApprovalsAsync();
            PromptGrid.ItemsSource = await client.ListPromptsAsync();
            AuditGrid.ItemsSource = await client.ListQueryAuditAsync();
            StatusTextBlock.Text = $"정책 {policies.Count}개와 외부 AI 운영 감사 메타데이터를 조회했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private void PolicyGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PolicyGrid.SelectedItem is not ServerAIPolicyResponse p) return;
        SelectTag(PolicyScopeComboBox, p.ScopeType); KillSwitchCheckBox.IsChecked = p.KillSwitchEnabled;
        RequestLimitTextBox.Text = p.MaxRequestsPerDay.ToString(); ConcurrencyTextBox.Text = p.MaxConcurrency.ToString();
        TimeoutTextBox.Text = p.TimeoutSeconds.ToString(); CostBudgetTextBox.Text = p.DailyCostBudgetMicros.ToString();
        QueryRetentionTextBox.Text = p.QueryPayloadRetentionDays.ToString(); ResponseRetentionTextBox.Text = p.ResponseRetentionDays.ToString();
        AuditRetentionTextBox.Text = p.AuditRetentionDays.ToString(); AllowExportCheckBox.IsChecked = p.AllowAuditExport;
        PolicyReasonTextBox.Text = p.Reason;
    }

    private async void SavePolicy_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        if (!TryInt(RequestLimitTextBox, out var requests) || !TryInt(ConcurrencyTextBox, out var concurrency) ||
            !TryInt(TimeoutTextBox, out var timeout) || !long.TryParse(CostBudgetTextBox.Text, out var cost) ||
            !TryInt(QueryRetentionTextBox, out var queryDays) || !TryInt(ResponseRetentionTextBox, out var responseDays) ||
            !TryInt(AuditRetentionTextBox, out var auditDays) || string.IsNullOrWhiteSpace(PolicyReasonTextBox.Text))
        { StatusTextBlock.Text = "모든 한도와 변경 사유를 올바르게 입력하세요."; return; }
        try
        {
            await client.SavePolicyAsync(new ServerAIPolicyUpdateRequest { ScopeType = SelectedTag(PolicyScopeComboBox), KillSwitchEnabled = KillSwitchCheckBox.IsChecked == true,
                MaxRequestsPerDay = requests, MaxConcurrency = concurrency, TimeoutSeconds = timeout, DailyCostBudgetMicros = cost,
                QueryPayloadRetentionDays = queryDays, ResponseRetentionDays = responseDays, AuditRetentionDays = auditDays,
                AllowAuditExport = AllowExportCheckBox.IsChecked == true, Reason = PolicyReasonTextBox.Text.Trim() });
            await RefreshAsync(); StatusTextBlock.Text = "외부 AI 운영 정책을 저장하고 감사 이력을 남겼습니다.";
        } catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void CreateApproval_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        if (!DateTimeOffset.TryParse(ApprovalExpiryTextBox.Text, CultureInfo.CurrentCulture, DateTimeStyles.AssumeLocal, out var expires))
        { StatusTextBlock.Text = "승인 만료 날짜를 확인하세요."; return; }
        try
        {
            await client.CreateApprovalAsync(new ServerAIApprovalCreateRequest { CustomerScope = ApprovalCustomerTextBox.Text.Trim(), SiteScope = ApprovalSiteTextBox.Text.Trim(),
                Provider = ApprovalProviderTextBox.Text.Trim(), ModelScope = ApprovalModelTextBox.Text.Trim(), ExpiresAt = expires,
                Purposes = Split(ApprovalPurposeTextBox.Text), SourceTypes = Split(ApprovalSourcesTextBox.Text),
                DataHandlingPolicyVersion = ApprovalPolicyVersionTextBox.Text.Trim(), Reason = ApprovalReasonTextBox.Text.Trim() });
            await RefreshAsync(); StatusTextBlock.Text = "범위가 고정된 전송 승인을 생성했습니다.";
        } catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void RevokeApproval_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || ApprovalGrid.SelectedItem is not ServerAIApprovalResponse selected) { StatusTextBlock.Text = "폐기할 승인을 선택하세요."; return; }
        try { await client.RevokeApprovalAsync(selected.ApprovalId, ApprovalReasonTextBox.Text.Trim()); await RefreshAsync(); StatusTextBlock.Text = "승인을 즉시 폐기했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private void PromptGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PromptGrid.SelectedItem is not ServerAIPromptResponse p) return;
        PromptNameTextBox.Text = p.Name; PromptVersionTextBox.Text = p.Version; PromptTemplateTextBox.Text = p.TemplateText;
        SelectTag(PromptPurposeComboBox, p.AllowedPurpose);
    }

    private async void CreatePrompt_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        try { await client.CreatePromptAsync(new ServerAIPromptCreateRequest { Name = PromptNameTextBox.Text.Trim(), Version = PromptVersionTextBox.Text.Trim(),
            TemplateText = PromptTemplateTextBox.Text, AllowedPurpose = SelectedTag(PromptPurposeComboBox) }); await RefreshAsync(); StatusTextBlock.Text = "새 불변 프롬프트 버전을 등록했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void PromptAction_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || PromptGrid.SelectedItem is not ServerAIPromptResponse selected || sender is not Button { Tag: string action })
        { StatusTextBlock.Text = "상태를 변경할 프롬프트를 선택하세요."; return; }
        try { await client.ChangePromptAsync(selected.PromptVersionId, action, PromptReasonTextBox.Text.Trim()); await RefreshAsync(); StatusTextBlock.Text = "프롬프트 lifecycle 상태를 변경했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void ExportAudit_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        var dialog = new SaveFileDialog { Filter = "CSV 파일 (*.csv)|*.csv", FileName = $"FlowNote-AI-감사-{DateTime.Now:yyyyMMdd-HHmmss}.csv" };
        if (dialog.ShowDialog(this) != true) return;
        try { await File.WriteAllBytesAsync(dialog.FileName, await client.ExportAuditAsync()); StatusTextBlock.Text = "정책에 따라 원문 없는 감사 메타데이터를 내보냈습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void RunRetention_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        try { var result = await client.RunRetentionAsync(); await RefreshAsync(); StatusTextBlock.Text = $"보존 작업 완료: 질의 비식별화 {result.QueryPayloadsDeidentified}건, 응답 삭제 {result.ResponsesDeleted}건"; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void AuditGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (AuditGrid.SelectedItem is not ServerAIQueryAuditResponse selected) return;
        await LoadQueryDetailAsync(selected.QueryId);
    }

    private async void RefreshQueryDetail_Click(object sender, RoutedEventArgs e)
    {
        if (AuditGrid.SelectedItem is not ServerAIQueryAuditResponse selected)
        { StatusTextBlock.Text = "상세 조회할 질의를 선택하세요."; return; }
        await LoadQueryDetailAsync(selected.QueryId);
    }

    private async Task LoadQueryDetailAsync(string queryId)
    {
        if (client is null) return;
        try
        {
            ShowQueryDetail(await client.GetQueryDetailAsync(queryId));
            StatusTextBlock.Text = "서버에서 질의 상태, legal hold 원본 이력과 감사 이벤트를 다시 조회했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private void ShowQueryDetail(ServerAIQueryDetailResponse detail)
    {
        selectedQueryDetail = detail;
        var holdStatus = detail.ActiveHold is null
            ? (detail.Holds.Count == 0 ? "hold 없음" : "hold 해제됨")
            : $"활성 hold · 근거 {detail.ActiveHold.AuthorityReference}";
        QueryScopeTextBlock.Text = $"질의 {detail.QueryId}\n고객 {detail.CustomerScope} / 현장 {detail.SiteScope} · 상태 {detail.Status} · {holdStatus}";
        QueryRetentionTextBlock.Text = $"질의 보존 예정 {detail.RetentionUntil.LocalDateTime:G} / 응답 보존 예정 {(detail.ResponseRetentionUntil?.LocalDateTime.ToString("G") ?? "별도 시각 없음")} · 질의 원문 {(detail.QueryPayloadExpired ? "만료됨" : "보존 중")}";
        HoldGrid.ItemsSource = detail.Holds;
        RetentionAuditGrid.ItemsSource = detail.RetentionAudits;
        OperationAuditGrid.ItemsSource = detail.AuditEvents;
        PlaceHoldButton.IsEnabled = !mutationInProgress && detail.ActiveHold is null && !detail.QueryPayloadExpired;
        ReleaseHoldButton.IsEnabled = !mutationInProgress && detail.ActiveHold is not null;
        ExpireQueryButton.IsEnabled = !mutationInProgress && detail.ActiveHold is null && !detail.QueryPayloadExpired;
    }

    private async void PlaceHold_Click(object sender, RoutedEventArgs e)
    {
        if (!TryPrepareMutation("legal hold 설정", needsAuthorityReference: true, out var detail, out var reason)) return;
        if (!ConfirmTwice("legal hold 설정", detail.QueryId, "활성 hold는 자동·일괄·단일 만료보다 우선합니다.")) return;
        var request = new ServerAILegalHoldCreateRequest
        {
            Reason = reason, AuthorityReference = HoldAuthorityReferenceTextBox.Text.Trim(),
            ExpectedStateTag = detail.StateTag,
            OperationKey = AIOperationMutationPolicy.NewOperationKey("hold-place", detail.QueryId)
        };
        await RunMutationAsync("legal hold를 설정", () => client!.PlaceLegalHoldAndReadBackAsync(detail.QueryId, request));
    }

    private async void ReleaseHold_Click(object sender, RoutedEventArgs e)
    {
        if (!TryPrepareMutation("legal hold 해제", needsAuthorityReference: false, out var detail, out var reason)) return;
        if (detail.ActiveHold is null) { StatusTextBlock.Text = "활성 legal hold가 없거나 이미 해제되었습니다."; return; }
        if (!ConfirmTwice("legal hold 해제", detail.QueryId, "해제 뒤 보존 예정 시각이 지난 데이터는 정책 실행 시 만료됩니다.")) return;
        var request = new ServerAIQueryMutationRequest
        {
            Reason = reason, ExpectedStateTag = detail.StateTag,
            OperationKey = AIOperationMutationPolicy.NewOperationKey("hold-release", detail.QueryId)
        };
        await RunMutationAsync("legal hold를 해제", () => client!.ReleaseLegalHoldAndReadBackAsync(detail.QueryId, detail.ActiveHold.HoldId, request));
    }

    private async void ExpireQuery_Click(object sender, RoutedEventArgs e)
    {
        if (!TryPrepareMutation("단일 즉시 만료", needsAuthorityReference: false, out var detail, out var reason)) return;
        if (detail.QueryPayloadExpired) { StatusTextBlock.Text = "이미 만료된 질의입니다."; return; }
        if (detail.ActiveHold is not null) { StatusTextBlock.Text = "활성 legal hold가 있어 만료할 수 없습니다."; return; }
        if (!ConfirmTwice("단일 즉시 만료", detail.QueryId, "질의 원문은 비식별화되고 보존 응답은 삭제됩니다.")) return;
        var request = new ServerAIQueryMutationRequest
        {
            Reason = reason, ExpectedStateTag = detail.StateTag,
            OperationKey = AIOperationMutationPolicy.NewOperationKey("expire", detail.QueryId)
        };
        await RunMutationAsync("질의를 즉시 만료", () => client!.ExpireQueryAndReadBackAsync(detail.QueryId, request));
    }

    private bool TryPrepareMutation(
        string action, bool needsAuthorityReference,
        out ServerAIQueryDetailResponse detail, out string reason)
    {
        detail = selectedQueryDetail!;
        reason = QueryMutationReasonTextBox.Text.Trim();
        if (client is null || selectedQueryDetail is null)
        { StatusTextBlock.Text = $"{action}할 질의를 선택하고 상세를 조회하세요."; return false; }
        detail = selectedQueryDetail;
        if (string.IsNullOrWhiteSpace(reason))
        { StatusTextBlock.Text = "감사에 남길 조작 사유를 입력하세요."; return false; }
        if (needsAuthorityReference && string.IsNullOrWhiteSpace(HoldAuthorityReferenceTextBox.Text))
        { StatusTextBlock.Text = "legal hold 근거 번호를 입력하세요."; return false; }
        return true;
    }

    private bool ConfirmTwice(string action, string queryId, string consequence)
    {
        if (MessageBox.Show(this, $"질의 {queryId}에 {action}을 수행합니까?\n\n{consequence}",
                "고위험 AI 보존 조작 확인", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            return false;
        return MessageBox.Show(this, $"마지막 확인입니다. 서버의 최신 상태와 경합을 검사한 뒤 {action}을 실행합니다.",
            "조작 실행 최종 확인", MessageBoxButton.YesNo, MessageBoxImage.Warning) == MessageBoxResult.Yes;
    }

    private async Task RunMutationAsync(
        string completedAction, Func<Task<ServerAIQueryDetailResponse>> mutation)
    {
        if (mutationInProgress) { StatusTextBlock.Text = "이전 보존 조작을 처리 중입니다."; return; }
        mutationInProgress = true;
        if (selectedQueryDetail is not null) ShowQueryDetail(selectedQueryDetail);
        try
        {
            var readBack = await mutation();
            ShowQueryDetail(readBack);
            AuditGrid.ItemsSource = await client!.ListQueryAuditAsync();
            StatusTextBlock.Text = $"서버에서 {completedAction}한 뒤 질의 상태, hold row와 감사 이벤트를 재조회했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
        finally
        {
            mutationInProgress = false;
            if (selectedQueryDetail is not null) ShowQueryDetail(selectedQueryDetail);
        }
    }

    private static List<string> Split(string value) => value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
    private static bool TryInt(TextBox box, out int value) => int.TryParse(box.Text, out value) && value >= 0;
    private static string SelectedTag(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? string.Empty;
    private static void SelectTag(ComboBox box, string value) { foreach (var item in box.Items.OfType<ComboBoxItem>()) if (string.Equals(item.Tag?.ToString(), value, StringComparison.Ordinal)) { box.SelectedItem = item; break; } }
}
