using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
using UglyToad.PdfPig;

namespace FlowNote.Windows.App;

public partial class DocumentViewWindow : Window
{
    private readonly FieldCommentService? fieldCommentService;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly ServerSyncService? serverSyncService;
    private readonly DocumentViewLogService? documentViewLogService;
    private readonly HistoryService? historyService;
    private readonly List<string> selectedAttachmentPaths = [];
    private readonly string actorName;
    private readonly string userRole;
    private readonly bool canDownloadDocument;
    private readonly bool canWriteFieldComments;
    private ExplorerDocument document;
    private long? documentViewLogId;
    private bool documentViewLogClosed;
    private bool pdfPreviewSecurityConfigured;
    private string? currentResolvedPath;
    private string? recordedPreviewFailureCode;
    private string documentViewCloseReason = "window_closed";

    public DocumentViewWindow(ExplorerDocument document)
        : this(null, null, null, null, null, document, string.Empty)
    {
    }

    public DocumentViewWindow(FieldCommentService? fieldCommentService, ExplorerDocument document, string actorName)
        : this(fieldCommentService, null, null, null, null, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldCommentService? fieldCommentService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        ExplorerDocument document,
        string actorName)
        : this(fieldCommentService, serverDocumentClient, null, null, null, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldCommentService? fieldCommentService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        DocumentViewLogService? documentViewLogService,
        ExplorerDocument document,
        string actorName)
        : this(fieldCommentService, serverDocumentClient, null, documentViewLogService, null, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldCommentService? fieldCommentService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        ServerSyncService? serverSyncService,
        DocumentViewLogService? documentViewLogService,
        HistoryService? historyService,
        ExplorerDocument document,
        string actorName,
        string? userRole = null)
    {
        InitializeComponent();
        this.fieldCommentService = fieldCommentService;
        this.serverDocumentClient = serverDocumentClient;
        this.serverSyncService = serverSyncService;
        this.documentViewLogService = documentViewLogService;
        this.historyService = historyService;
        this.document = document;
        this.actorName = actorName;
        this.userRole = userRole ?? string.Empty;
        canDownloadDocument = RolePermissionPolicy.CanDownloadDocuments(this.userRole);
        canWriteFieldComments = RolePermissionPolicy.CanWriteFieldComments(this.userRole);
        SaveCommentButton.IsEnabled = canWriteFieldComments && fieldCommentService is not null && !string.IsNullOrWhiteSpace(document.DocumentId);
        SelectAttachmentButton.IsEnabled = SaveCommentButton.IsEnabled;
        ClearAttachmentButton.IsEnabled = false;
        ApprovalWorkbenchButton.IsEnabled =
            serverDocumentClient is not null &&
            serverSyncService is not null &&
            RolePermissionPolicy.CanRegisterDocuments(this.userRole);
        StartDocumentViewLog();
        RefreshHeader();
        LoadPreview(document);
        RefreshCombinedComments();
        RefreshAttachmentSummary();
    }

    public bool CommentSaved { get; private set; }

    private void ApprovalWorkbenchButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null || serverSyncService is null)
        {
            return;
        }
        var mapping = serverSyncService.GetControlledCopyServerMapping(
            document.DocumentId,
            document.VersionNo);
        var window = new DocumentApprovalWindow(
            serverDocumentClient.CreateApprovalClient(),
            RolePermissionPolicy.CanRegisterDocuments(userRole),
            RolePermissionPolicy.CanGovernDocuments(userRole),
            mapping?.ServerDocumentId,
            serverSyncService)
        {
            Owner = this
        };
        window.ShowDialog();
    }

    protected override void OnClosed(EventArgs e)
    {
        if (PdfPreview.CoreWebView2 is not null && pdfPreviewSecurityConfigured)
        {
            PdfPreview.CoreWebView2.DownloadStarting -= PdfPreview_DownloadStarting;
            PdfPreview.CoreWebView2.NewWindowRequested -= PdfPreview_NewWindowRequested;
            PdfPreview.CoreWebView2.NavigationStarting -= PdfPreview_NavigationStarting;
            PdfPreview.CoreWebView2.ProcessFailed -= PdfPreview_ProcessFailed;
        }

        CloseDocumentViewLog(documentViewCloseReason);
        base.OnClosed(e);
    }

    private void StartDocumentViewLog()
    {
        if (documentViewLogService is null || string.IsNullOrWhiteSpace(document.DocumentId))
        {
            return;
        }

        documentViewLogId = documentViewLogService.StartDocumentView(
            document.DocumentId,
            document.VersionNo,
            actorName);
        if (serverSyncService is not null &&
            documentViewLogService.GetLog(documentViewLogId.Value) is { } accessLog)
        {
            _ = serverSyncService.QueueAndTrySyncAccessLogAsync(
                accessLog,
                "view_started",
                serverDocumentClient);
        }
    }

    private void CloseDocumentViewLog(string closeReason)
    {
        if (documentViewLogClosed || documentViewLogId is null || documentViewLogService is null)
        {
            return;
        }

        documentViewLogService.CloseDocumentView(documentViewLogId.Value, closeReason);
        documentViewLogClosed = true;
        if (serverSyncService is not null &&
            documentViewLogService.GetLog(documentViewLogId.Value) is { } accessLog)
        {
            var action = string.Equals(closeReason, "auto_closed", StringComparison.Ordinal)
                ? "auto_closed"
                : "view_closed";
            _ = serverSyncService.QueueAndTrySyncAccessLogAsync(
                accessLog,
                action,
                serverDocumentClient);
        }
    }

    private void RefreshHeader()
    {
        Title = $"파일 보기 - {document.FileName}";
        TitleTextBlock.Text = document.FileName;
        MetaTextBlock.Text = $"{document.Status} | {document.VersionLabel} | {document.UpdatedBy} | {document.UpdatedAt:yyyy-MM-dd HH:mm}";
        SecurityPolicyTextBlock.Text = canDownloadDocument
            ? "다운로드 허용 | 자동 닫힘 없음"
            : "다운로드 차단 | 자동 닫힘 없음";
        DownloadCopyButton.ToolTip = canDownloadDocument
            ? "통제된 복사본을 저장하고 로컬 이력에 기록합니다."
            : "이 역할은 문서 다운로드가 차단되며 시도 이력이 기록됩니다.";
        ApprovalWorkbenchButton.ToolTip = ApprovalWorkbenchButton.IsEnabled
            ? "이 문서의 검토 요청, 승인, 반려, 공개와 보존된 상태 이력을 확인합니다."
            : "문서 작성 권한과 서버 연결이 필요합니다. 시스템 관리자에게 문의하세요.";
        SaveCommentButton.ToolTip = canWriteFieldComments
            ? "현장 코멘트를 저장하고 로컬 이력에 기록합니다."
            : "이 역할은 현장 코멘트를 저장할 수 없습니다.";
        SelectAttachmentButton.ToolTip = SaveCommentButton.ToolTip;
    }

    private void LoadPreview(ExplorerDocument document)
    {
        try
        {
            var resolvedPath = ResolveLocalPath(document.LocalPath);
            currentResolvedPath = File.Exists(resolvedPath) ? resolvedPath : null;
            ResetPreviewSurfaces();

            switch (DocumentPreviewPolicy.ClassifyPath(resolvedPath))
            {
                case DocumentPreviewKind.Pdf:
                    ShowPdfPreview(document, resolvedPath!);
                    return;
                case DocumentPreviewKind.Spreadsheet:
                    ShowSpreadsheetPreview(resolvedPath!);
                    return;
                case DocumentPreviewKind.Image:
                    ShowImagePreview(document, resolvedPath!);
                    return;
                case DocumentPreviewKind.Text:
                    ShowTextPreview(resolvedPath!);
                    return;
                case DocumentPreviewKind.Cad:
                case DocumentPreviewKind.Hwp:
                case DocumentPreviewKind.Unsupported:
                case DocumentPreviewKind.Missing:
                default:
                    ShowUnsupportedPreview(document, resolvedPath);
                    return;
            }
        }
        catch (Exception)
        {
            var kind = DocumentPreviewPolicy.ClassifyFileName(document.FileName);
            ShowPreviewFailure(DocumentPreviewFailure.Create(kind, DocumentPreviewFailureCategory.Unexpected));
        }
    }

    private void ResetPreviewSurfaces()
    {
        PdfPreview.Visibility = Visibility.Collapsed;
        PdfPreview.Source = null;
        SpreadsheetPreview.Visibility = Visibility.Collapsed;
        SpreadsheetPreview.ItemsSource = null;
        ImagePreview.Visibility = Visibility.Collapsed;
        ImagePreview.Source = null;
        PreviewFailurePanel.Visibility = Visibility.Collapsed;
        ContentTextBox.Visibility = Visibility.Visible;
        ContentTextBox.Text = string.Empty;
    }

    private static string? ResolveLocalPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        if (Path.IsPathRooted(path))
        {
            return path;
        }

        var localDataPath = FlowNoteLocalDatabase.ResolveLocalContentPath(path);
        if (File.Exists(localDataPath))
        {
            return localDataPath;
        }

        var runtimePath = Path.Combine(AppContext.BaseDirectory, path);
        if (File.Exists(runtimePath))
        {
            return runtimePath;
        }

        var developmentAppDirectory = FlowNoteLocalDatabase.TryFindDevelopmentAppDirectory(AppContext.BaseDirectory);
        if (!string.IsNullOrWhiteSpace(developmentAppDirectory))
        {
            var developmentPath = Path.Combine(developmentAppDirectory, path);
            if (File.Exists(developmentPath))
            {
                return developmentPath;
            }
        }

        return runtimePath;
    }

    private async void ShowPdfPreview(ExplorerDocument document, string resolvedPath)
    {
        try
        {
            if (!TryValidatePdf(resolvedPath, out var failureCategory))
            {
                ShowPreviewFailure(DocumentPreviewFailure.Create(DocumentPreviewKind.Pdf, failureCategory));
                return;
            }

            ImagePreview.Visibility = Visibility.Collapsed;
            ImagePreview.Source = null;
            ContentTextBox.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.ItemsSource = null;
            PdfPreview.Visibility = Visibility.Visible;
            await ConfigurePdfPreviewSecurityAsync();
            PdfPreview.Source = new Uri(resolvedPath, UriKind.Absolute);
        }
        catch (Exception ex) when (IsWebView2InitializationFailure(ex))
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Pdf,
                DocumentPreviewFailureCategory.ViewerUnavailable));
        }
        catch (Exception)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Pdf,
                DocumentPreviewFailureCategory.Unexpected));
        }
    }

    private static bool TryValidatePdf(string path, out DocumentPreviewFailureCategory failureCategory)
    {
        try
        {
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                Span<byte> header = stackalloc byte[5];
                if (stream.Read(header) != header.Length || !header.SequenceEqual("%PDF-"u8))
                {
                    failureCategory = DocumentPreviewFailureCategory.Corrupted;
                    return false;
                }
            }

            using var pdf = PdfDocument.Open(path);
            if (pdf.NumberOfPages < 1)
            {
                failureCategory = DocumentPreviewFailureCategory.Corrupted;
                return false;
            }

            failureCategory = default;
            return true;
        }
        catch (Exception ex) when (IsPdfPreviewReadFailure(ex))
        {
            failureCategory = IsEncryptedPdfFailure(ex)
                ? DocumentPreviewFailureCategory.Encrypted
                : ex is UnauthorizedAccessException
                    ? DocumentPreviewFailureCategory.AccessDenied
                    : DocumentPreviewFailureCategory.Corrupted;
            return false;
        }
    }

    private static bool IsPdfPreviewReadFailure(Exception ex)
    {
        return ex is IOException
            or UnauthorizedAccessException
            or UglyToad.PdfPig.Core.PdfDocumentFormatException
            or InvalidOperationException
            or NotSupportedException
            or ArgumentException;
    }

    private static bool IsEncryptedPdfFailure(Exception ex)
    {
        return ex.GetType().Name.Contains("Encrypt", StringComparison.OrdinalIgnoreCase) ||
               ex.Message.Contains("password", StringComparison.OrdinalIgnoreCase) ||
               ex.Message.Contains("encrypted", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsWebView2InitializationFailure(Exception ex)
    {
        return ex is InvalidOperationException
            or DllNotFoundException
            or FileNotFoundException
            or BadImageFormatException
            || ex.GetType().Name.Contains("WebView2RuntimeNotFound", StringComparison.OrdinalIgnoreCase);
    }

    private async Task ConfigurePdfPreviewSecurityAsync()
    {
        await PdfPreview.EnsureCoreWebView2Async();
        var core = PdfPreview.CoreWebView2;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.AreBrowserAcceleratorKeysEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.AreHostObjectsAllowed = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.HiddenPdfToolbarItems =
            CoreWebView2PdfToolbarItems.Save |
            CoreWebView2PdfToolbarItems.SaveAs |
            CoreWebView2PdfToolbarItems.Print;

        if (pdfPreviewSecurityConfigured)
        {
            return;
        }

        core.DownloadStarting += PdfPreview_DownloadStarting;
        core.NewWindowRequested += PdfPreview_NewWindowRequested;
        core.NavigationStarting += PdfPreview_NavigationStarting;
        core.ProcessFailed += PdfPreview_ProcessFailed;
        pdfPreviewSecurityConfigured = true;
    }

    private void PdfPreview_DownloadStarting(object? sender, CoreWebView2DownloadStartingEventArgs e)
    {
        e.Cancel = true;
        e.Handled = true;
        RecordDownloadBlocked("WebView2 PDF 다운로드를 차단했습니다.");
    }

    private void PdfPreview_NewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        e.Handled = true;
        RecordDownloadBlocked("WebView2 외부 창 열기 요청을 차단했습니다.");
    }

    private void PdfPreview_NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        if (string.Equals(e.Uri, "about:blank", StringComparison.OrdinalIgnoreCase) ||
            IsCurrentPdfNavigation(e.Uri))
        {
            return;
        }

        e.Cancel = true;
        RecordDownloadBlocked("WebView2 PDF 외부 이동 요청을 차단했습니다.");
    }

    private bool IsCurrentPdfNavigation(string? target)
    {
        if (string.IsNullOrWhiteSpace(target) ||
            string.IsNullOrWhiteSpace(currentResolvedPath) ||
            !Uri.TryCreate(target, UriKind.Absolute, out var uri) ||
            !uri.IsFile)
        {
            return false;
        }

        try
        {
            return string.Equals(
                Path.GetFullPath(uri.LocalPath),
                Path.GetFullPath(currentResolvedPath),
                StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception)
        {
            return false;
        }
    }

    private void PdfPreview_ProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs e)
    {
        ShowPreviewFailure(DocumentPreviewFailure.Create(
            DocumentPreviewKind.Pdf,
            DocumentPreviewFailureCategory.ViewerUnavailable));
    }

    private void ShowSpreadsheetPreview(string resolvedPath)
    {
        try
        {
            var workbook = XlsxPreviewReader.Read(resolvedPath);
            ContentTextBox.Visibility = Visibility.Visible;
            ContentTextBox.Text = workbook.SheetListTruncated
                ? $"XLSX 시트 {workbook.Sheets.Count:N0}개를 표시합니다. 안전 한도를 넘는 시트는 생략했으며 원본은 변경되지 않았습니다."
                : $"XLSX 시트 {workbook.Sheets.Count:N0}개를 앱 내부에서 읽기 전용으로 표시합니다.";
            ImagePreview.Visibility = Visibility.Collapsed;
            ImagePreview.Source = null;
            SpreadsheetPreview.Visibility = Visibility.Visible;
            SpreadsheetPreview.ItemsSource = workbook.Sheets;
        }
        catch (UnauthorizedAccessException)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Spreadsheet,
                DocumentPreviewFailureCategory.AccessDenied));
        }
        catch (Exception)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Spreadsheet,
                DocumentPreviewFailureCategory.Corrupted));
        }
    }

    private void ShowImagePreview(ExplorerDocument document, string resolvedPath)
    {
        try
        {
            PdfPreview.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.ItemsSource = null;
            var image = LoadSafeImage(resolvedPath, out var originalWidth, out var originalHeight, out var orientation);
            ContentTextBox.Text = BuildMetadataPreview(
                document,
                $"이미지 문서입니다. 원본 해상도 {originalWidth:N0}×{originalHeight:N0}, 회전 정보 {orientation}을 적용한 앱 내부 미리보기입니다. 지원하는 형식에서는 투명도를 유지합니다.");
            ContentTextBox.Visibility = Visibility.Visible;

            ImagePreview.Visibility = Visibility.Visible;
            ImagePreview.Source = image;
        }
        catch (UnauthorizedAccessException)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Image,
                DocumentPreviewFailureCategory.AccessDenied));
        }
        catch (Exception)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Image,
                DocumentPreviewFailureCategory.Corrupted));
        }
    }

    private static BitmapSource LoadSafeImage(
        string path,
        out int originalWidth,
        out int originalHeight,
        out ushort orientation)
    {
        using var metadataStream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete);
        var decoder = BitmapDecoder.Create(
            metadataStream,
            BitmapCreateOptions.PreservePixelFormat | BitmapCreateOptions.IgnoreColorProfile,
            BitmapCacheOption.None);
        var frame = decoder.Frames.First();
        originalWidth = frame.PixelWidth;
        originalHeight = frame.PixelHeight;
        orientation = ReadExifOrientation(frame.Metadata as BitmapMetadata);

        var decodeWidth = originalWidth;
        if (Math.Max(originalWidth, originalHeight) > DocumentPreviewPolicy.MaxImagePreviewPixelDimension)
        {
            decodeWidth = originalWidth >= originalHeight
                ? DocumentPreviewPolicy.MaxImagePreviewPixelDimension
                : Math.Max(
                    1,
                    (int)Math.Round(
                        originalWidth * (DocumentPreviewPolicy.MaxImagePreviewPixelDimension / (double)originalHeight)));
        }

        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.CreateOptions = BitmapCreateOptions.PreservePixelFormat | BitmapCreateOptions.IgnoreColorProfile;
        image.DecodePixelWidth = decodeWidth;
        image.UriSource = new Uri(path, UriKind.Absolute);
        image.EndInit();
        image.Freeze();

        Transform? transform = orientation switch
        {
            2 => new ScaleTransform(-1, 1),
            3 => new RotateTransform(180),
            4 => new ScaleTransform(1, -1),
            5 => BuildImageTransform(-1, 1, 90),
            6 => new RotateTransform(90),
            7 => BuildImageTransform(-1, 1, 270),
            8 => new RotateTransform(270),
            _ => null
        };
        if (transform is null)
        {
            return image;
        }

        var transformed = new TransformedBitmap(image, transform);
        transformed.Freeze();
        return transformed;
    }

    private static Transform BuildImageTransform(double scaleX, double scaleY, double rotation)
    {
        var group = new TransformGroup();
        group.Children.Add(new ScaleTransform(scaleX, scaleY));
        group.Children.Add(new RotateTransform(rotation));
        return group;
    }

    private static ushort ReadExifOrientation(BitmapMetadata? metadata)
    {
        try
        {
            return metadata?.GetQuery("/app1/ifd/{ushort=274}") switch
            {
                ushort value => value,
                uint value when value <= ushort.MaxValue => (ushort)value,
                _ => 1
            };
        }
        catch (Exception)
        {
            return 1;
        }
    }

    private void ShowTextPreview(string resolvedPath)
    {
        try
        {
            var result = DocumentTextPreviewReader.Read(resolvedPath);
            ContentTextBox.Visibility = Visibility.Visible;
            ContentTextBox.Text = result.Text;
        }
        catch (DecoderFallbackException)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Text,
                DocumentPreviewFailureCategory.InvalidEncoding));
        }
        catch (UnauthorizedAccessException)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Text,
                DocumentPreviewFailureCategory.AccessDenied));
        }
        catch (Exception)
        {
            ShowPreviewFailure(DocumentPreviewFailure.Create(
                DocumentPreviewKind.Text,
                DocumentPreviewFailureCategory.Unexpected));
        }
    }

    private void ShowUnsupportedPreview(ExplorerDocument document, string? resolvedPath)
    {
        var kind = DocumentPreviewPolicy.ClassifyPath(resolvedPath);
        if (kind == DocumentPreviewKind.Missing)
        {
            kind = DocumentPreviewPolicy.ClassifyFileName(document.FileName);
            if (kind is not (DocumentPreviewKind.Cad or DocumentPreviewKind.Hwp or DocumentPreviewKind.Unsupported))
            {
                kind = DocumentPreviewKind.Missing;
            }
        }

        var category = kind == DocumentPreviewKind.Missing
            ? DocumentPreviewFailureCategory.MissingFile
            : DocumentPreviewFailureCategory.UnsupportedContent;
        ShowPreviewFailure(DocumentPreviewFailure.Create(kind, category));
    }

    private void ShowPreviewFailure(DocumentPreviewFailure failure)
    {
        PdfPreview.Visibility = Visibility.Collapsed;
        PdfPreview.Source = null;
        SpreadsheetPreview.Visibility = Visibility.Collapsed;
        SpreadsheetPreview.ItemsSource = null;
        ImagePreview.Visibility = Visibility.Collapsed;
        ImagePreview.Source = null;
        ContentTextBox.Visibility = Visibility.Collapsed;
        PreviewFailurePanel.Visibility = Visibility.Visible;
        FailureFileTypeTextBlock.Text = $"파일 유형: {failure.FileType}";
        FailureCategoryTextBlock.Text = $"실패 범주: {failure.CategoryName}";
        FailureSummaryTextBlock.Text = failure.Summary;
        FailurePreservationTextBlock.Text = $"보존 상태: {DocumentPreviewFailure.PreservationMessage}";
        FailureNextActionTextBlock.Text = $"가능한 다음 행동: {failure.NextAction}";
        RecordPreviewFailed(failure);
    }

    private void RecordPreviewFailed(DocumentPreviewFailure failure)
    {
        if (string.Equals(recordedPreviewFailureCode, failure.AuditCode, StringComparison.Ordinal))
        {
            return;
        }

        recordedPreviewFailureCode = failure.AuditCode;
        if (string.IsNullOrWhiteSpace(document.DocumentId))
        {
            historyService?.Record(
                "document.preview_failed",
                actorName,
                "document",
                null,
                null,
                $"문서 미리보기 실패: {failure.AuditCode}");
            return;
        }

        if (documentViewLogService is null)
        {
            historyService?.Record(
                "document.preview_failed",
                actorName,
                "document",
                document.DocumentId,
                null,
                $"문서 미리보기 실패: {failure.AuditCode}");
            return;
        }

        var failureLogId = documentViewLogService.RecordPreviewFailed(
            document.DocumentId,
            document.VersionNo,
            actorName,
            failure.AuditCode);
        if (serverSyncService is not null &&
            documentViewLogService.GetLog(failureLogId) is { } accessLog)
        {
            _ = serverSyncService.QueueAndTrySyncAccessLogAsync(
                accessLog,
                "preview_failed",
                serverDocumentClient,
                reason: failure.AuditCode);
        }
    }

    private static string BuildMetadataPreview(ExplorerDocument document, string message)
    {
        var builder = new StringBuilder();
        builder.AppendLine(message);
        builder.AppendLine();
        builder.AppendLine($"파일명: {document.FileName}");
        builder.AppendLine($"제목: {document.Title}");
        builder.AppendLine($"유형: {document.DocumentType}");
        builder.AppendLine($"버전: {document.VersionLabel}");
        if (!string.IsNullOrWhiteSpace(document.LatestComment))
        {
            builder.AppendLine();
            builder.AppendLine("[최근 코멘트]");
            builder.AppendLine(document.LatestComment);
        }

        return builder.ToString();
    }

    private void RefreshCombinedComments()
    {
        if (fieldCommentService is null || string.IsNullOrWhiteSpace(document.DocumentId))
        {
            CombinedCommentTextBox.Text = "DB에 저장되지 않은 로컬 파일입니다.";
            return;
        }

        var notes = fieldCommentService.ListDocumentComments(document.DocumentId).ToList();
        if (notes.Count == 0)
        {
            CombinedCommentTextBox.Text = "아직 등록된 코멘트가 없습니다.";
            return;
        }

        var builder = new StringBuilder();
        foreach (var note in notes)
        {
            var versionLabel = note.DocumentVersionNo is null ? "문서" : $"v{note.DocumentVersionNo}";
            var attachments = fieldCommentService.ListAttachments(note.CommentId);
            var attachmentText = attachments.Count == 0 ? string.Empty : $" / 첨부:{attachments.Count}";
            builder.AppendLine($"[{note.CreatedAt:yyyy-MM-dd HH:mm}] {note.AuthorName} / {versionLabel} / {note.InputMode}{attachmentText}");
            builder.AppendLine(note.RawContent);
            foreach (var attachment in attachments)
            {
                builder.AppendLine($"- {attachment.OriginalFileName} ({attachment.SizeBytes:N0} bytes)");
            }
            builder.AppendLine();
        }

        CombinedCommentTextBox.Text = builder.ToString().TrimEnd();
    }

    private async Task<string> TrySendFieldCommentToServerAsync(FieldCommentRecord savedComment)
    {
        if (serverSyncService is null)
        {
            return "서버 동기화가 설정되지 않아 현장 코멘트는 로컬에만 저장되었습니다.";
        }

        var result = await serverSyncService.QueueAndTrySyncFieldCommentAsync(
            savedComment,
            serverDocumentClient);
        return result.Success
            ? "서버 현장 코멘트 전송을 완료했습니다."
            : $"서버 현장 코멘트 전송 대기열에 남겼습니다. 로컬 저장은 유지됩니다. {result.Message}";
    }

    private async Task<string> TrySendAttachmentToServerAsync(FieldCommentAttachmentRecord attachment)
    {
        if (serverSyncService is null)
        {
            return "서버 동기화가 설정되지 않아 현장 코멘트 첨부는 로컬에만 저장되었습니다.";
        }

        var result = await serverSyncService.QueueAndTrySyncFieldCommentAttachmentAsync(
            attachment,
            serverDocumentClient);
        return result.Success
            ? "서버 현장 코멘트 첨부 전송을 완료했습니다."
            : $"서버 현장 코멘트 첨부 전송 대기열에 남겼습니다. 로컬 저장은 유지됩니다. {result.Message}";
    }

    private void SelectAttachmentButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Multiselect = true,
            Filter = "지원 첨부 파일|*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp;*.pdf;*.txt;*.md|이미지|*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp|PDF 파일|*.pdf|텍스트 파일|*.txt;*.md|모든 파일|*.*"
        };

        if (dialog.ShowDialog(this) != true)
        {
            return;
        }

        foreach (var fileName in dialog.FileNames.Where(File.Exists))
        {
            if (!selectedAttachmentPaths.Contains(fileName, StringComparer.OrdinalIgnoreCase))
            {
                selectedAttachmentPaths.Add(fileName);
            }
        }

        RefreshAttachmentSummary();
    }

    private void ClearAttachmentButton_Click(object sender, RoutedEventArgs e)
    {
        selectedAttachmentPaths.Clear();
        RefreshAttachmentSummary();
    }

    private void RefreshAttachmentSummary()
    {
        ClearAttachmentButton.IsEnabled = selectedAttachmentPaths.Count > 0;
        AttachmentSummaryTextBlock.Text = selectedAttachmentPaths.Count == 0
            ? "첨부 없음"
            : $"{selectedAttachmentPaths.Count}개 첨부: {string.Join(", ", selectedAttachmentPaths.Select(Path.GetFileName))}";
    }

    private async void SaveCommentButton_Click(object sender, RoutedEventArgs e)
    {
        if (fieldCommentService is null || string.IsNullOrWhiteSpace(document.DocumentId))
        {
            MessageBox.Show("저장된 문서만 코멘트를 남길 수 있습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var comment = CommentTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(comment))
        {
            MessageBox.Show("코멘트를 입력하세요.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var savedComment = fieldCommentService.AddDocumentComment(document.DocumentId, comment, actorName);
        var serverStatus = await TrySendFieldCommentToServerAsync(savedComment);
        var attachmentStatuses = new List<string>();
        foreach (var attachmentPath in selectedAttachmentPaths.ToList())
        {
            var attachment = fieldCommentService.AddAttachment(
                savedComment.CommentId,
                attachmentPath,
                actorName);
            attachmentStatuses.Add(await TrySendAttachmentToServerAsync(attachment));
        }

        document = document with
        {
            UpdatedAt = savedComment.CreatedAt,
            LatestComment = savedComment.RawContent
        };
        CommentSaved = true;
        CommentTextBox.Clear();
        selectedAttachmentPaths.Clear();
        RefreshAttachmentSummary();
        RefreshHeader();
        var attachmentStatus = attachmentStatuses.Count == 0
            ? string.Empty
            : $" | 첨부={attachmentStatuses.Count}";
        MetaTextBlock.Text = $"{MetaTextBlock.Text} | {serverStatus}{attachmentStatus}";
        RefreshCombinedComments();
        LoadPreview(document);
        MessageBox.Show("현장 코멘트를 문서 아래에 저장했습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
    }
}
