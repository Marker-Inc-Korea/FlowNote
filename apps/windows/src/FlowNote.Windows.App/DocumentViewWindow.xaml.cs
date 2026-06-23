using System.IO;
using System.Text;
using System.Windows;
using FlowNote.Windows.Core.Explorer;

namespace FlowNote.Windows.App;

public partial class DocumentViewWindow : Window
{
    private const long MaxPreviewBytes = 128 * 1024;

    public DocumentViewWindow(ExplorerDocument document)
    {
        InitializeComponent();
        Title = $"파일 보기 - {document.FileName}";
        TitleTextBlock.Text = document.FileName;
        MetaTextBlock.Text = $"{document.Status} | {document.VersionLabel} | {document.UpdatedBy} | {document.UpdatedAt:yyyy-MM-dd HH:mm}";
        ContentTextBox.Text = LoadPreviewText(document);
    }

    private static string LoadPreviewText(ExplorerDocument document)
    {
        if (string.IsNullOrWhiteSpace(document.LocalPath) || !File.Exists(document.LocalPath))
        {
            return "이 문서는 메타데이터만 등록되어 있습니다. 현재 로컬 클라이언트에서 파일 본문을 열 수 없습니다.";
        }

        var fileInfo = new FileInfo(document.LocalPath);
        if (fileInfo.Length > MaxPreviewBytes)
        {
            return $"파일 크기: {fileInfo.Length:N0} bytes\n현재 클라이언트 미리보기는 작은 텍스트 파일만 지원합니다.";
        }

        try
        {
            using var reader = new StreamReader(document.LocalPath, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
            return reader.ReadToEnd();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            return $"현재 클라이언트에서 이 파일을 미리 볼 수 없습니다.\n\n{ex.Message}";
        }
    }
}
