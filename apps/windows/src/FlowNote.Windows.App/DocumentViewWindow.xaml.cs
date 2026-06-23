using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Media.Imaging;
using System.Xml.Linq;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;

namespace FlowNote.Windows.App;

public partial class DocumentViewWindow : Window
{
    private const long MaxPreviewBytes = 128 * 1024;
    private readonly DocumentService? documentService;
    private readonly string actorName;
    private ExplorerDocument document;

    public DocumentViewWindow(ExplorerDocument document)
        : this(null, document, string.Empty)
    {
    }

    public DocumentViewWindow(DocumentService? documentService, ExplorerDocument document, string actorName)
    {
        InitializeComponent();
        this.documentService = documentService;
        this.document = document;
        this.actorName = actorName;
        SaveCommentButton.IsEnabled = documentService is not null && !string.IsNullOrWhiteSpace(document.DocumentId);
        RefreshHeader();
        LoadPreview(document);
        RefreshCombinedComments();
    }

    public bool CommentSaved { get; private set; }

    private void RefreshHeader()
    {
        Title = $"파일 보기 - {document.FileName}";
        TitleTextBlock.Text = document.FileName;
        MetaTextBlock.Text = $"{document.Status} | {document.VersionLabel} | {document.UpdatedBy} | {document.UpdatedAt:yyyy-MM-dd HH:mm}";
    }

    private void LoadPreview(ExplorerDocument document)
    {
        var resolvedPath = ResolveLocalPath(document.LocalPath);
        if (IsImage(resolvedPath))
        {
            ContentTextBox.Text = BuildMetadataPreview(document, "사진 문서입니다. 아래 이미지와 누적 코멘트를 함께 확인할 수 있습니다.");
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

        return Path.IsPathRooted(path) ? path : Path.Combine(AppContext.BaseDirectory, path);
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

    private static string LoadPreviewText(ExplorerDocument document, string? resolvedPath)
    {
        if (string.IsNullOrWhiteSpace(resolvedPath) || !File.Exists(resolvedPath))
        {
            return BuildMetadataPreview(document, "이 문서는 메타데이터만 등록되어 있습니다. 현재 로컬 클라이언트에서 파일 본문을 열 수 없습니다.");
        }

        var fileInfo = new FileInfo(resolvedPath);
        var extension = Path.GetExtension(resolvedPath).ToLowerInvariant();
        if (extension == ".xlsx")
        {
            return PreviewXlsx(document, resolvedPath);
        }

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

    private static string PreviewXlsx(ExplorerDocument document, string path)
    {
        try
        {
            using var archive = ZipFile.OpenRead(path);
            var sheetEntry = archive.GetEntry("xl/worksheets/sheet1.xml");
            if (sheetEntry is null)
            {
                return BuildMetadataPreview(document, "엑셀 첫 번째 시트를 찾을 수 없습니다.");
            }

            using var stream = sheetEntry.Open();
            var xml = XDocument.Load(stream);
            XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
            var rows = xml.Descendants(ns + "row")
                .Take(30)
                .Select(row => string.Join(" | ", row.Elements(ns + "c")
                    .Select(ReadCellText)
                    .Where(value => !string.IsNullOrWhiteSpace(value))))
                .Where(line => !string.IsNullOrWhiteSpace(line))
                .ToList();

            return rows.Count == 0
                ? BuildMetadataPreview(document, "엑셀 시트에 표시할 텍스트가 없습니다.")
                : string.Join(Environment.NewLine, rows);
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or System.Xml.XmlException)
        {
            return BuildMetadataPreview(document, $"엑셀 미리보기를 생성할 수 없습니다.\n\n{ex.Message}");
        }
    }

    private static string ReadCellText(XElement cell)
    {
        XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        var inlineText = cell.Descendants(ns + "t").FirstOrDefault()?.Value;
        if (!string.IsNullOrWhiteSpace(inlineText))
        {
            return inlineText;
        }

        return cell.Element(ns + "v")?.Value ?? string.Empty;
    }

    private static string PreviewPdf(ExplorerDocument document, string path)
    {
        try
        {
            var text = File.ReadAllText(path, Encoding.UTF8);
            var matches = Regex.Matches(text, @"\((?<text>(?:\\.|[^\\)])*)\)")
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
        if (documentService is null || string.IsNullOrWhiteSpace(document.DocumentId))
        {
            CombinedCommentTextBox.Text = "DB에 저장되지 않은 업로드 후보입니다.";
            return;
        }

        var versions = documentService.ListVersions(document.DocumentId)
            .Where(version => !string.IsNullOrWhiteSpace(version.Comment))
            .OrderByDescending(version => version.VersionNo)
            .ToList();
        if (versions.Count == 0)
        {
            CombinedCommentTextBox.Text = "아직 등록된 코멘트가 없습니다.";
            return;
        }

        var builder = new StringBuilder();
        foreach (var version in versions)
        {
            builder.AppendLine($"[{version.CreatedAt:yyyy-MM-dd HH:mm}] {version.CreatedBy} / v{version.VersionNo}");
            builder.AppendLine(version.Comment);
            builder.AppendLine();
        }

        CombinedCommentTextBox.Text = builder.ToString().TrimEnd();
    }

    private void SaveCommentButton_Click(object sender, RoutedEventArgs e)
    {
        if (documentService is null || string.IsNullOrWhiteSpace(document.DocumentId))
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

        var updated = documentService.AddCommentVersion(document.DocumentId, comment, actorName);
        document = document with
        {
            UpdatedAt = updated.UpdatedAt,
            VersionLabel = $"v{updated.VersionNo}",
            LatestComment = updated.LatestComment
        };
        CommentSaved = true;
        CommentTextBox.Clear();
        RefreshHeader();
        RefreshCombinedComments();
        LoadPreview(document);
        MessageBox.Show("코멘트를 문서 아래에 추가하고 버전을 올렸습니다.", "FlowNote", MessageBoxButton.OK, MessageBoxImage.Information);
    }
}
