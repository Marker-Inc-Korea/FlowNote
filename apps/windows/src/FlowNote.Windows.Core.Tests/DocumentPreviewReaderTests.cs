using System.IO.Compression;
using System.Text;
using FlowNote.Windows.Core.Documents;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class DocumentPreviewReaderTests
{
    [Fact]
    public void FailureGuidanceContainsOnlySafeOperationalInformation()
    {
        var failure = DocumentPreviewFailure.Create(
            DocumentPreviewKind.Pdf,
            DocumentPreviewFailureCategory.Corrupted);

        Assert.Equal("PDF", failure.FileType);
        Assert.Contains("손상", failure.CategoryName);
        Assert.Contains("원본", DocumentPreviewFailure.PreservationMessage);
        Assert.Contains("문서 관리자", failure.NextAction);
        Assert.DoesNotContain("C:\\", failure.Summary);
        Assert.DoesNotContain("Exception", failure.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TextReaderSupportsCp949AndTruncatesVeryLongLines()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        var path = CreateArtifactPath("긴-CP949-문서.txt");
        var longLine = $"작업 기준 {new string('가', DocumentTextPreviewReader.MaxDisplayedLineCharacters + 100)}";
        File.WriteAllText(path, longLine, Encoding.GetEncoding(949));

        var result = DocumentTextPreviewReader.Read(path);

        Assert.Equal("ks_c_5601-1987", result.EncodingName);
        Assert.True(result.IsTruncated);
        Assert.Equal(1, result.TruncatedLineCount);
        Assert.Contains("작업 기준", result.Text);
        Assert.Contains("긴 행 일부 생략", result.Text);
    }

    [Fact]
    public void XlsxReaderReturnsMultipleSheetsCachedFormulasAndMergeRanges()
    {
        var path = CreateArtifactPath("다중-시트-수식-병합.xlsx");
        CreateWorkbook(path);

        var workbook = XlsxPreviewReader.Read(path);

        Assert.Equal(2, workbook.Sheets.Count);
        Assert.Equal("점검표", workbook.Sheets[0].Name);
        Assert.Equal("결과", workbook.Sheets[1].Name);
        Assert.Equal("합계", workbook.Sheets[0].Table.Rows[0][0]);
        Assert.Equal("30", workbook.Sheets[0].Table.Rows[0][1]);
        Assert.Equal(1, workbook.Sheets[0].FormulaCellCount);
        Assert.Contains("A2:B2", workbook.Sheets[0].MergedRanges);
        Assert.Equal("=TODAY()", workbook.Sheets[1].Table.Rows[0][0]);
    }

    private static string CreateArtifactPath(string fileName)
    {
        var directory = Path.Combine(
            Path.GetTempPath(),
            "flownote-preserved-tests",
            "document-preview",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        return Path.Combine(directory, fileName);
    }

    private static void CreateWorkbook(string path)
    {
        using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
        WriteEntry(
            archive,
            "xl/workbook.xml",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="점검표" sheetId="1" r:id="rId1" />
                <sheet name="결과" sheetId="2" r:id="rId2" />
              </sheets>
            </workbook>
            """);
        WriteEntry(
            archive,
            "xl/_rels/workbook.xml.rels",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet" />
              <Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="worksheet" />
            </Relationships>
            """);
        WriteEntry(
            archive,
            "xl/sharedStrings.xml",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>합계</t></si>
            </sst>
            """);
        WriteEntry(
            archive,
            "xl/worksheets/sheet1.xml",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>SUM(B2:B3)</f><v>30</v></c></row>
                <row r="2"><c r="A2" t="inlineStr"><is><t>병합</t></is></c></row>
              </sheetData>
              <mergeCells count="1"><mergeCell ref="A2:B2" /></mergeCells>
            </worksheet>
            """);
        WriteEntry(
            archive,
            "xl/worksheets/sheet2.xml",
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1"><c r="A1"><f>TODAY()</f></c></row></sheetData>
            </worksheet>
            """);
    }

    private static void WriteEntry(ZipArchive archive, string name, string content)
    {
        var entry = archive.CreateEntry(name);
        using var writer = new StreamWriter(entry.Open(), new UTF8Encoding(false));
        writer.Write(content);
    }
}
