using System.IO;
using System.Net.Http;
using System.Windows;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class DocumentViewWindow
{
    private async void DownloadCopyButton_Click(object sender, RoutedEventArgs e)
    {
        if (!canDownloadDocument)
        {
            RecordDownloadBlocked($"역할 '{(string.IsNullOrWhiteSpace(userRole) ? "알 수 없음" : userRole)}'은 문서를 다운로드할 수 없습니다.");
            MessageBox.Show("이 역할은 문서 다운로드가 차단됩니다. 차단 시도는 이력에 기록했습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (serverDocumentClient is null || serverSyncService is null)
        {
            MessageBox.Show("서버 연결이 설정되지 않아 통제된 복사본을 받을 수 없습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var mapping = serverSyncService.GetControlledCopyServerMapping(document.DocumentId, document.VersionNo);
        if (mapping is null)
        {
            MessageBox.Show("현재 문서 버전의 서버 동기화 정보가 없습니다. 문서와 공개 버전을 먼저 서버에 동기화하세요.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var dialog = new SaveFileDialog
        {
            FileName = document.FileName,
            Filter = "모든 파일|*.*",
            OverwritePrompt = true
        };

        if (dialog.ShowDialog(this) != true)
        {
            return;
        }

        DownloadCopyButton.IsEnabled = false;
        try
        {
            var result = await serverDocumentClient.DownloadControlledCopyAsync(
                mapping.ServerDocumentId,
                mapping.ServerVersionId,
                dialog.FileName);
            historyService?.Record(
                "document.downloaded",
                actorName,
                "document",
                document.DocumentId,
                document.FileName,
                $"서버 통제 문서 복사본 저장: {document.FileName} / SHA-256 {result.HashSha256}");
            MessageBox.Show("서버가 승인한 문서 복사본을 저장하고 해시를 검증했습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex) when (ex is HttpRequestException or InvalidOperationException or IOException or UnauthorizedAccessException or OperationCanceledException)
        {
            const string safeFailureMessage =
                "통제된 복사본을 저장하지 못했습니다. 원본과 열람 이력은 보존됩니다. " +
                "현장 관리자에게 서버 연결, 문서 권한과 파일 무결성 확인을 요청하세요.";
            historyService?.Record(
                "document.download_failed",
                actorName,
                "document",
                document.DocumentId,
                document.FileName,
                "서버 통제 문서 복사본 저장 실패");
            MessageBox.Show(safeFailureMessage, "FlowNote", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        finally
        {
            DownloadCopyButton.IsEnabled = true;
        }
    }

    private void RecordDownloadBlocked(string reason)
    {
        if (string.IsNullOrWhiteSpace(document.DocumentId))
        {
            historyService?.Record(
                "document.download_blocked",
                actorName,
                "document",
                null,
                document.FileName,
                reason);
            return;
        }

        if (documentViewLogService is null)
        {
            historyService?.Record(
                "document.download_blocked",
                actorName,
                "document",
                document.DocumentId,
                document.FileName,
                reason);
            return;
        }

        var blockedLogId = documentViewLogService.RecordDownloadBlocked(
            document.DocumentId,
            document.VersionNo,
            actorName,
            reason);
        if (serverSyncService is not null &&
            documentViewLogService.GetLog(blockedLogId) is { } accessLog)
        {
            _ = serverSyncService.QueueAndTrySyncAccessLogAsync(
                accessLog,
                "download_blocked",
                serverDocumentClient);
        }
    }
}
