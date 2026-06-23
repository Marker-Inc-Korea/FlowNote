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
        Title = $"File view - {document.FileName}";
        TitleTextBlock.Text = document.FileName;
        MetaTextBlock.Text = $"{document.Status} | {document.VersionLabel} | {document.UpdatedBy} | {document.UpdatedAt:yyyy-MM-dd HH:mm}";
        ContentTextBox.Text = LoadPreviewText(document);
    }

    private static string LoadPreviewText(ExplorerDocument document)
    {
        if (string.IsNullOrWhiteSpace(document.LocalPath) || !File.Exists(document.LocalPath))
        {
            return "This file is registered as metadata only. File content is not available in the local client yet.";
        }

        var fileInfo = new FileInfo(document.LocalPath);
        if (fileInfo.Length > MaxPreviewBytes)
        {
            return $"The file is {fileInfo.Length:N0} bytes. Preview is limited to small text files in the current client.";
        }

        try
        {
            using var reader = new StreamReader(document.LocalPath, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
            return reader.ReadToEnd();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            return $"Unable to preview this file in the current client.\n\n{ex.Message}";
        }
    }
}
