using System.Data;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Xml.Linq;
using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.FieldNotes;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using Microsoft.Win32;
using UglyToad.PdfPig;

namespace FlowNote.Windows.App;

public partial class DocumentViewWindow : Window
{
    private const long MaxPreviewBytes = 128 * 1024;
    private const int AutoCloseDelaySeconds = 30;
    private readonly FieldNoteService? fieldNoteService;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly ServerSyncService? serverSyncService;
    private readonly DocumentViewLogService? documentViewLogService;
    private readonly DispatcherTimer autoCloseTimer;
    private readonly List<string> selectedAttachmentPaths = [];
    private readonly string actorName;
    private ExplorerDocument document;
    private long? documentViewLogId;
    private bool documentViewLogClosed;
    private string documentViewCloseReason = "window_closed";

    public DocumentViewWindow(ExplorerDocument document)
        : this(null, null, null, document, string.Empty)
    {
    }

    public DocumentViewWindow(FieldNoteService? fieldNoteService, ExplorerDocument document, string actorName)
        : this(fieldNoteService, null, null, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldNoteService? fieldNoteService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        ExplorerDocument document,
        string actorName)
        : this(fieldNoteService, serverDocumentClient, null, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldNoteService? fieldNoteService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        DocumentViewLogService? documentViewLogService,
        ExplorerDocument document,
        string actorName)
        : this(fieldNoteService, serverDocumentClient, null, documentViewLogService, document, actorName)
    {
    }

    public DocumentViewWindow(
        FieldNoteService? fieldNoteService,
        FlowNoteServerDocumentClient? serverDocumentClient,
        ServerSyncService? serverSyncService,
        DocumentViewLogService? documentViewLogService,
        ExplorerDocument document,
        string actorName)
    {
        InitializeComponent();
        this.fieldNoteService = fieldNoteService;
        this.serverDocumentClient = serverDocumentClient;
        this.serverSyncService = serverSyncService;
        this.documentViewLogService = documentViewLogService;
        this.document = document;
        this.actorName = actorName;
        autoCloseTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(AutoCloseDelaySeconds)
        };
        Loaded += DocumentViewWindow_Loaded;
        autoCloseTimer.Tick += AutoCloseTimer_Tick;
        SaveCommentButton.IsEnabled = fieldNoteService is not null && !string.IsNullOrWhiteSpace(document.DocumentId);
        SelectAttachmentButton.IsEnabled = SaveCommentButton.IsEnabled;
        ClearAttachmentButton.IsEnabled = false;
        StartDocumentViewLog();
        RefreshHeader();
        LoadPreview(document);
        RefreshCombinedComments();
        RefreshAttachmentSummary();
    }

    public bool CommentSaved { get; private set; }

    protected override void OnClosed(EventArgs e)
    {
        Loaded -= DocumentViewWindow_Loaded;
        autoCloseTimer.Stop();
        autoCloseTimer.Tick -= AutoCloseTimer_Tick;
        CloseDocumentViewLog(documentViewCloseReason);
        base.OnClosed(e);
    }

    private void DocumentViewWindow_Loaded(object sender, RoutedEventArgs e)
    {
        autoCloseTimer.Stop();
        autoCloseTimer.Start();
    }

    private void AutoCloseTimer_Tick(object? sender, EventArgs e)
    {
        autoCloseTimer.Stop();
        documentViewCloseReason = "auto_closed";
        Close();
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
    }

    private void LoadPreview(ExplorerDocument document)
    {
        var resolvedPath = ResolveLocalPath(document.LocalPath);
        PdfPreview.Visibility = Visibility.Collapsed;
        PdfPreview.Source = null;
        SpreadsheetPreview.Visibility = Visibility.Collapsed;
        SpreadsheetPreview.ItemsSource = null;

        if (IsPdf(resolvedPath))
        {
            ShowPdfPreview(document, resolvedPath!);
            return;
        }

        if (IsSpreadsheet(resolvedPath))
        {
            ShowSpreadsheetPreview(document, resolvedPath!);
            return;
        }

        if (IsImage(resolvedPath))
        {
            ContentTextBox.Text = BuildMetadataPreview(document, "사진 문서입니다. 아래 이미지와 누적 코멘트를 함께 확인할 수 있습니다.");
            ContentTextBox.Visibility = Visibility.Visible;
            ImagePreview.Visibility = Visibility.Visible;
            ImagePreview.Source = new BitmapImage(new Uri(resolvedPath!, UriKind.Absolute));
            return;
        }

        ImagePreview.Visibility = Visibility.Collapsed;
        ImagePreview.Source = null;
        ContentTextBox.Visibility = Visibility.Visible;
        ContentTextBox.Text = LoadPreviewText(document, resolvedPath);
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

    private static bool IsImage(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return false;
        }

        var extension = Path.GetExtension(path).ToLowerInvariant();
        return extension is ".jpg" or ".jpeg" or ".png" or ".bmp" or ".gif";
    }

    private static bool IsPdf(string? path)
    {
        return !string.IsNullOrWhiteSpace(path) &&
            File.Exists(path) &&
            Path.GetExtension(path).Equals(".pdf", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsSpreadsheet(string? path)
    {
        return !string.IsNullOrWhiteSpace(path) &&
            File.Exists(path) &&
            Path.GetExtension(path).Equals(".xlsx", StringComparison.OrdinalIgnoreCase);
    }

    private void ShowPdfPreview(ExplorerDocument document, string resolvedPath)
    {
        try
        {
            ImagePreview.Visibility = Visibility.Collapsed;
            ImagePreview.Source = null;
            ContentTextBox.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.Visibility = Visibility.Collapsed;
            SpreadsheetPreview.ItemsSource = null;
            PdfPreview.Visibility = Visibility.Visible;
            PdfPreview.Source = new Uri(resolvedPath, UriKind.Absolute);
        }
        catch (Exception ex) when (ex is UriFormatException or InvalidOperationException)
        {
            PdfPreview.Visibility = Visibility.Collapsed;
            ContentTextBox.Visibility = Visibility.Visible;
            ContentTextBox.Text = PreviewPdf(document, resolvedPath);
        }
    }

    private void ShowSpreadsheetPreview(ExplorerDocument document, string resolvedPath)
    {
        try
        {
            var table = LoadSpreadsheetTable(resolvedPath);
            if (table.Rows.Count == 0)
            {
                ContentTextBox.Visibility = Visibility.Visible;
                ContentTextBox.Text = BuildMetadataPreview(document, "엑셀 첫 번째 시트에 표시할 데이터가 없습니다.");
                return;
            }

            ContentTextBox.Visibility = Visibility.Collapsed;
            ImagePreview.Visibility = Visibility.Collapsed;
            ImagePreview.Source = null;
            SpreadsheetPreview.Visibility = Visibility.Visible;
            SpreadsheetPreview.ItemsSource = table.DefaultView;
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or System.Xml.XmlException)
        {
            SpreadsheetPreview.Visibility = Visibility.Collapsed;
            ContentTextBox.Visibility = Visibility.Visible;
            ContentTextBox.Text = BuildMetadataPreview(document, $"엑셀 미리보기를 생성할 수 없습니다.\n\n{ex.Message}");
        }
    }

    private static string LoadPreviewText(ExplorerDocument document, string? resolvedPath)
    {
        if (string.IsNullOrWhiteSpace(resolvedPath) || !File.Exists(resolvedPath))
        {
            return BuildMetadataPreview(document, "이 문서는 메타데이터만 등록되어 있습니다. 현재 로컬 클라이언트에서 파일 본문을 열 수 없습니다.");
        }

        var fileInfo = new FileInfo(resolvedPath);
        var extension = Path.GetExtension(resolvedPath).ToLowerInvariant();
        if (extension == ".pdf")
        {
            return PreviewPdf(document, resolvedPath);
        }

        if (fileInfo.Length > MaxPreviewBytes)
        {
            return BuildMetadataPreview(document, $"파일 크기: {fileInfo.Length:N0} bytes\n현재 클라이언트 미리보기는 작은 텍스트 파일만 지원합니다.");
        }

        try
        {
            using var reader = new StreamReader(resolvedPath, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
            return reader.ReadToEnd();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            return BuildMetadataPreview(document, $"현재 클라이언트에서 이 파일을 미리 볼 수 없습니다.\n\n{ex.Message}");
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

    private static DataTable LoadSpreadsheetTable(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        var sheetEntry = archive.GetEntry("xl/worksheets/sheet1.xml");
        if (sheetEntry is null)
        {
            throw new InvalidDataException("엑셀 첫 번째 시트를 찾을 수 없습니다.");
        }

        var sharedStrings = LoadSharedStrings(archive);
        using var stream = sheetEntry.Open();
        var xml = XDocument.Load(stream);
        XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        var rowValues = xml.Descendants(ns + "row")
            .Take(100)
            .Select(row => ReadSpreadsheetRow(row, sharedStrings))
            .Where(row => row.Any(value => !string.IsNullOrWhiteSpace(value)))
            .ToList();

        var columnCount = Math.Max(1, rowValues.Count == 0 ? 0 : rowValues.Max(row => row.Count));
        var table = new DataTable();
        for (var column = 1; column <= columnCount; column++)
        {
            table.Columns.Add(ColumnName(column));
        }

        foreach (var row in rowValues)
        {
            var dataRow = table.NewRow();
            for (var index = 0; index < Math.Min(row.Count, columnCount); index++)
            {
                dataRow[index] = row[index];
            }

            table.Rows.Add(dataRow);
        }

        return table;
    }

    private static IReadOnlyList<string> LoadSharedStrings(ZipArchive archive)
    {
        var sharedStringEntry = archive.GetEntry("xl/sharedStrings.xml");
        if (sharedStringEntry is null)
        {
            return [];
        }

        using var stream = sharedStringEntry.Open();
        var xml = XDocument.Load(stream);
        XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        return xml.Descendants(ns + "si")
            .Select(item => string.Concat(item.Descendants(ns + "t").Select(text => text.Value)))
            .ToList();
    }

    private static List<string> ReadSpreadsheetRow(XElement row, IReadOnlyList<string> sharedStrings)
    {
        XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        var values = new List<string>();
        var nextColumn = 1;
        foreach (var cell in row.Elements(ns + "c"))
        {
            var reference = cell.Attribute("r")?.Value;
            var columnIndex = string.IsNullOrWhiteSpace(reference) ? nextColumn : ColumnIndexFromCellReference(reference);
            while (values.Count < columnIndex - 1)
            {
                values.Add(string.Empty);
            }

            values.Add(ReadCellText(cell, sharedStrings));
            nextColumn = columnIndex + 1;
        }

        return values;
    }

    private static string ReadCellText(XElement cell, IReadOnlyList<string> sharedStrings)
    {
        XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        var inlineText = cell.Descendants(ns + "t").FirstOrDefault()?.Value;
        if (!string.IsNullOrWhiteSpace(inlineText))
        {
            return inlineText;
        }

        var value = cell.Element(ns + "v")?.Value ?? string.Empty;
        var dataType = cell.Attribute("t")?.Value;
        if (dataType == "s" && int.TryParse(value, out var sharedStringIndex) && sharedStringIndex < sharedStrings.Count)
        {
            return sharedStrings[sharedStringIndex];
        }

        return value;
    }

    private static int ColumnIndexFromCellReference(string reference)
    {
        var columnLetters = new string(reference.TakeWhile(char.IsLetter).ToArray()).ToUpperInvariant();
        var index = 0;
        foreach (var letter in columnLetters)
        {
            index = (index * 26) + letter - 'A' + 1;
        }

        return Math.Max(index, 1);
    }

    private static string ColumnName(int index)
    {
        var name = string.Empty;
        while (index > 0)
        {
            index--;
            name = (char)('A' + index % 26) + name;
            index /= 26;
        }

        return name;
    }

    private static string PreviewPdf(ExplorerDocument document, string path)
    {
        try
        {
            using var pdf = PdfDocument.Open(path);
            var pageTexts = pdf.GetPages()
                .Take(30)
                .Select(page => page.Text)
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .ToList();

            if (pageTexts.Count > 0)
            {
                var parsedText = string.Join(Environment.NewLine + Environment.NewLine, pageTexts);
                return LooksCorruptedPdfText(parsedText) ? PreviewSimplePdfText(document, path) : parsedText;
            }

            return PreviewSimplePdfText(document, path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or UglyToad.PdfPig.Core.PdfDocumentFormatException)
        {
            return BuildMetadataPreview(document, $"PDF 미리보기를 생성할 수 없습니다.\n\n{ex.Message}");
        }
    }

    private static bool LooksCorruptedPdfText(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        var suspiciousCharacters = text.Count(character =>
            character == '\uFFFD' ||
            character is >= '\u0080' and <= '\u00FF' ||
            char.GetUnicodeCategory(character) == System.Globalization.UnicodeCategory.Control &&
            character is not '\r' and not '\n' and not '\t');

        return suspiciousCharacters > Math.Max(4, text.Length / 8);
    }

    private static string PreviewSimplePdfText(ExplorerDocument document, string path)
    {
        try
        {
            var rawText = File.ReadAllText(path, Encoding.UTF8);
            var matches = Regex.Matches(rawText, @"\((?<text>(?:\\.|[^\\)])*)\)")
                .Select(match => match.Groups["text"].Value
                    .Replace("\\(", "(", StringComparison.Ordinal)
                    .Replace("\\)", ")", StringComparison.Ordinal)
                    .Replace("\\\\", "\\", StringComparison.Ordinal))
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Take(50)
                .ToList();

            return matches.Count == 0
                ? BuildMetadataPreview(document, "PDF에서 표시할 텍스트를 찾지 못했습니다.")
                : string.Join(Environment.NewLine, matches);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            return BuildMetadataPreview(document, $"PDF 미리보기를 생성할 수 없습니다.\n\n{ex.Message}");
        }
    }

    private void RefreshCombinedComments()
    {
        if (fieldNoteService is null || string.IsNullOrWhiteSpace(document.DocumentId))
        {
            CombinedCommentTextBox.Text = "DB에 저장되지 않은 로컬 파일입니다.";
            return;
        }

        var notes = fieldNoteService.ListDocumentNotes(document.DocumentId).ToList();
        if (notes.Count == 0)
        {
            CombinedCommentTextBox.Text = "아직 등록된 코멘트가 없습니다.";
            return;
        }

        var builder = new StringBuilder();
        foreach (var note in notes)
        {
            var versionLabel = note.DocumentVersionNo is null ? "문서" : $"v{note.DocumentVersionNo}";
            var attachments = fieldNoteService.ListAttachments(note.NoteId);
            var attachmentText = attachments.Count == 0 ? string.Empty : $" / attachments:{attachments.Count}";
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

    private async Task<string> TrySendFieldNoteToServerAsync(FieldNoteRecord savedNote)
    {
        if (serverSyncService is null)
        {
            return "Server sync service is not configured. The field note remains saved locally.";
        }

        var result = await serverSyncService.QueueAndTrySyncFieldNoteAsync(
            savedNote,
            serverDocumentClient);
        return result.Success
            ? "Server field note send completed."
            : $"Server field note send queued. Local save is kept. {result.Message}";
    }

    private async Task<string> TrySendAttachmentToServerAsync(FieldNoteAttachmentRecord attachment)
    {
        if (serverSyncService is null)
        {
            return "Server sync service is not configured. The field note attachment remains saved locally.";
        }

        var result = await serverSyncService.QueueAndTrySyncFieldNoteAttachmentAsync(
            attachment,
            serverDocumentClient);
        return result.Success
            ? "Server field note attachment send completed."
            : $"Server field note attachment send queued. Local save is kept. {result.Message}";
    }

    private void SelectAttachmentButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Multiselect = true,
            Filter = "Supported attachments|*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp;*.pdf;*.txt;*.md|Images|*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.webp|PDF files|*.pdf|Text files|*.txt;*.md|All files|*.*"
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
            ? "No attachments"
            : $"{selectedAttachmentPaths.Count} attachment(s): {string.Join(", ", selectedAttachmentPaths.Select(Path.GetFileName))}";
    }

    private async void SaveCommentButton_Click(object sender, RoutedEventArgs e)
    {
        if (fieldNoteService is null || string.IsNullOrWhiteSpace(document.DocumentId))
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

        var savedNote = fieldNoteService.AddDocumentNote(document.DocumentId, comment, actorName);
        var serverStatus = await TrySendFieldNoteToServerAsync(savedNote);
        var attachmentStatuses = new List<string>();
        foreach (var attachmentPath in selectedAttachmentPaths.ToList())
        {
            var attachment = fieldNoteService.AddAttachment(
                savedNote.NoteId,
                attachmentPath,
                actorName);
            attachmentStatuses.Add(await TrySendAttachmentToServerAsync(attachment));
        }

        document = document with
        {
            UpdatedAt = savedNote.CreatedAt,
            LatestComment = savedNote.RawContent
        };
        CommentSaved = true;
        CommentTextBox.Clear();
        selectedAttachmentPaths.Clear();
        RefreshAttachmentSummary();
        RefreshHeader();
        var attachmentStatus = attachmentStatuses.Count == 0
            ? string.Empty
            : $" | attachments={attachmentStatuses.Count}";
        MetaTextBlock.Text = $"{MetaTextBlock.Text} | {serverStatus}{attachmentStatus}";
        RefreshCombinedComments();
        LoadPreview(document);
        MessageBox.Show("현장 코멘트를 문서 아래에 저장했습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
    }
}
