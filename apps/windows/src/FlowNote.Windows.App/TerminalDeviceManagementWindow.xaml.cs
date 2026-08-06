using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class TerminalDeviceManagementWindow : Window
{
    private readonly FlowNoteServerTerminalDeviceClient? client;
    private readonly string? initialDeviceId;
    private ServerTerminalDeviceResponse? selectedDevice;
    private string? replacementForDeviceId;

    public TerminalDeviceManagementWindow(
        FlowNoteServerTerminalDeviceClient? client,
        string? initialDeviceId = null)
    {
        InitializeComponent();
        this.client = client;
        this.initialDeviceId = initialDeviceId;
        DeviceModeComboBox.SelectedIndex = 0;
        StatusComboBox.SelectedIndex = 0;
        Loaded += Window_Loaded;
    }

    private async void Window_Loaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync(initialDeviceId);
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync(selectedDevice?.DeviceId);
    }

    private void NewButton_Click(object sender, RoutedEventArgs e)
    {
        DeviceGrid.SelectedItem = null;
        ClearForm();
        StatusTextBlock.Text = "새 승인 단말 정보를 입력하세요.";
    }

    private void DeviceGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (DeviceGrid.SelectedItem is not ServerTerminalDeviceResponse device)
        {
            return;
        }

        selectedDevice = device;
        replacementForDeviceId = null;
        DeviceIdTextBox.Text = device.DeviceId;
        DeviceIdTextBox.IsReadOnly = true;
        DeviceNameTextBox.Text = device.DeviceName;
        LocationCodeTextBox.Text = device.LocationCode ?? string.Empty;
        GroupIdTextBox.Text = device.GroupId ?? string.Empty;
        SelectComboValue(DeviceModeComboBox, device.DeviceMode);
        SelectComboValue(StatusComboBox, device.Status);
        ChangeReasonTextBox.Clear();
        FormTitleTextBlock.Text = "승인 단말 상세";
        SaveButton.Content = "정보 저장";
        AuditTextBlock.Text = BuildAuditText(device);
    }

    private async void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null)
        {
            ShowServerRequired();
            return;
        }

        var deviceId = DeviceIdTextBox.Text.Trim();
        var deviceName = DeviceNameTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(deviceId) || string.IsNullOrWhiteSpace(deviceName))
        {
            StatusTextBlock.Text = "device_id와 단말명을 입력하세요.";
            return;
        }

        try
        {
            ServerTerminalDeviceResponse saved;
            if (!string.IsNullOrWhiteSpace(replacementForDeviceId))
            {
                saved = await client.ReplaceAsync(
                    replacementForDeviceId,
                    new ServerTerminalDeviceReplaceRequest
                    {
                        DeviceId = deviceId,
                        DeviceName = deviceName,
                        DeviceMode = GetSelectedValue(DeviceModeComboBox, "viewer"),
                        LocationCode = CleanOptional(LocationCodeTextBox.Text),
                        GroupId = CleanOptional(GroupIdTextBox.Text),
                        Status = "ACTIVE",
                        ChangeReason = CleanOptional(ChangeReasonTextBox.Text)
                    });
                StatusTextBlock.Text = $"교체 단말을 등록하고 기존 단말을 폐기 처리했습니다: {saved.DeviceName}";
            }
            else if (selectedDevice is null)
            {
                saved = await client.CreateAsync(
                    new ServerTerminalDeviceCreateRequest
                    {
                        DeviceId = deviceId,
                        DeviceName = deviceName,
                        DeviceMode = GetSelectedValue(DeviceModeComboBox, "viewer"),
                        LocationCode = CleanOptional(LocationCodeTextBox.Text),
                        GroupId = CleanOptional(GroupIdTextBox.Text),
                        Status = GetSelectedValue(StatusComboBox, "ACTIVE")
                    });
                StatusTextBlock.Text = $"승인 단말을 등록했습니다: {saved.DeviceName}";
            }
            else
            {
                saved = await client.UpdateAsync(
                    selectedDevice.DeviceId,
                    new ServerTerminalDeviceUpdateRequest
                    {
                        DeviceName = deviceName,
                        DeviceMode = GetSelectedValue(DeviceModeComboBox, "viewer"),
                        LocationCode = CleanOptional(LocationCodeTextBox.Text),
                        GroupId = CleanOptional(GroupIdTextBox.Text),
                        ChangeReason = CleanOptional(ChangeReasonTextBox.Text)
                    });
                StatusTextBlock.Text = $"승인 단말 정보를 저장했습니다: {saved.DeviceName}";
            }

            replacementForDeviceId = null;
            await RefreshAsync(saved.DeviceId);
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = exception.Message;
        }
    }

    private async void ApplyStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null)
        {
            ShowServerRequired();
            return;
        }
        if (selectedDevice is null || replacementForDeviceId is not null)
        {
            StatusTextBlock.Text = "상태를 변경할 기존 단말을 목록에서 선택하세요.";
            return;
        }

        try
        {
            var saved = await client.ChangeStatusAsync(
                selectedDevice.DeviceId,
                new ServerTerminalDeviceStatusRequest(
                    GetSelectedValue(StatusComboBox, selectedDevice.Status),
                    CleanOptional(ChangeReasonTextBox.Text)));
            StatusTextBlock.Text = $"단말 상태를 {saved.StatusLabel}(으)로 변경했습니다.";
            await RefreshAsync(saved.DeviceId);
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = exception.Message;
        }
    }

    private void PrepareReplacementButton_Click(object sender, RoutedEventArgs e)
    {
        if (selectedDevice is null)
        {
            StatusTextBlock.Text = "교체할 기존 단말을 먼저 선택하세요.";
            return;
        }
        if (selectedDevice.Status == "RETIRED")
        {
            StatusTextBlock.Text = "이미 폐기된 단말은 다시 교체 처리할 수 없습니다.";
            return;
        }

        replacementForDeviceId = selectedDevice.DeviceId;
        DeviceIdTextBox.Clear();
        DeviceIdTextBox.IsReadOnly = false;
        DeviceNameTextBox.Text = $"{selectedDevice.DeviceName} 교체 단말";
        StatusComboBox.SelectedIndex = 0;
        ChangeReasonTextBox.Clear();
        FormTitleTextBlock.Text = $"교체 단말 등록 · 기존 {selectedDevice.DeviceId}";
        SaveButton.Content = "교체 등록";
        StatusTextBlock.Text = "새 단말의 device_id와 변경 사유를 입력하세요.";
    }

    private async Task RefreshAsync(string? selectDeviceId = null)
    {
        if (client is null)
        {
            DeviceGrid.ItemsSource = Array.Empty<ServerTerminalDeviceResponse>();
            ShowServerRequired();
            return;
        }

        try
        {
            var devices = await client.ListAsync();
            DeviceGrid.ItemsSource = devices;
            var target = devices.FirstOrDefault(device => device.DeviceId == selectDeviceId);
            if (target is not null)
            {
                DeviceGrid.SelectedItem = target;
                DeviceGrid.ScrollIntoView(target);
            }
            StatusTextBlock.Text = $"승인 단말 {devices.Count}개를 조회했습니다.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = exception.Message;
        }
    }

    private void ClearForm()
    {
        selectedDevice = null;
        replacementForDeviceId = null;
        DeviceIdTextBox.Clear();
        DeviceIdTextBox.IsReadOnly = false;
        DeviceNameTextBox.Clear();
        LocationCodeTextBox.Clear();
        GroupIdTextBox.Clear();
        DeviceModeComboBox.SelectedIndex = 0;
        StatusComboBox.SelectedIndex = 0;
        ChangeReasonTextBox.Clear();
        AuditTextBlock.Text = "등록 후 등록자와 변경자, 마지막 접속 시각을 확인할 수 있습니다.";
        FormTitleTextBlock.Text = "신규 승인 단말";
        SaveButton.Content = "등록";
    }

    private void ShowServerRequired()
    {
        StatusTextBlock.Text = "서버 URL이 설정된 관리자 계정으로 로그인해야 승인 단말을 관리할 수 있습니다.";
    }

    private static string BuildAuditText(ServerTerminalDeviceResponse device)
    {
        var registeredAt = device.CreatedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        var updatedAt = device.UpdatedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        return $"등록: {device.RegisteredBy ?? "기록 없음"} · {registeredAt}\n" +
               $"변경: {device.UpdatedBy ?? "기록 없음"} · {updatedAt}\n" +
               $"마지막 접속: {device.LastSeenLabel}";
    }

    private static string? CleanOptional(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static string GetSelectedValue(ComboBox comboBox, string fallback)
    {
        return (comboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? fallback;
    }

    private static void SelectComboValue(ComboBox comboBox, string value)
    {
        comboBox.SelectedItem = comboBox.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => string.Equals(item.Tag?.ToString(), value, StringComparison.Ordinal));
    }
}
