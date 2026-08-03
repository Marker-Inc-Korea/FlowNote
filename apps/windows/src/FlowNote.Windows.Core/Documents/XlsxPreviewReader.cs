using System.Data;
using System.IO.Compression;
using System.Xml.Linq;

namespace FlowNote.Windows.Core.Documents;

public sealed record XlsxPreviewSheet(
    string Name,
    DataTable Table,
    IReadOnlyList<string> MergedRanges,
    int FormulaCellCount)
{
    public string Summary =>
        $"표시 행 {Table.Rows.Count:N0}개 · 수식 셀 {FormulaCellCount:N0}개 · " +
        (MergedRanges.Count == 0
            ? "병합 범위 없음"
            : $"병합 범위 {string.Join(", ", MergedRanges.Take(5))}{(MergedRanges.Count > 5 ? " 외" : string.Empty)}");
}

public sealed record XlsxPreviewWorkbook(
    IReadOnlyList<XlsxPreviewSheet> Sheets,
    bool SheetListTruncated);

public static class XlsxPreviewReader
{
    private static readonly XNamespace SpreadsheetNamespace =
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private static readonly XNamespace RelationshipNamespace =
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace PackageRelationshipNamespace =
        "http://schemas.openxmlformats.org/package/2006/relationships";

    public static XlsxPreviewWorkbook Read(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        var workbookXml = LoadXml(archive, "xl/workbook.xml");
        var relationshipsXml = LoadXml(archive, "xl/_rels/workbook.xml.rels");
        var relationships = relationshipsXml
            .Descendants(PackageRelationshipNamespace + "Relationship")
            .Where(element => element.Attribute("Id") is not null && element.Attribute("Target") is not null)
            .ToDictionary(
                element => element.Attribute("Id")!.Value,
                element => NormalizeWorkbookTarget(element.Attribute("Target")!.Value),
                StringComparer.Ordinal);
        var sharedStrings = LoadSharedStrings(archive);
        var sheetDefinitions = workbookXml
            .Descendants(SpreadsheetNamespace + "sheet")
            .Select(element => new
            {
                Name = element.Attribute("name")?.Value?.Trim(),
                RelationshipId = element.Attribute(RelationshipNamespace + "id")?.Value
            })
            .Where(item => !string.IsNullOrWhiteSpace(item.RelationshipId))
            .ToList();

        var sheets = new List<XlsxPreviewSheet>();
        foreach (var definition in sheetDefinitions.Take(DocumentPreviewPolicy.MaxSpreadsheetPreviewSheets))
        {
            if (!relationships.TryGetValue(definition.RelationshipId!, out var entryName))
            {
                throw new InvalidDataException("Workbook relationship is missing.");
            }

            var sheetXml = LoadXml(archive, entryName);
            sheets.Add(ReadSheet(definition.Name ?? $"시트 {sheets.Count + 1}", sheetXml, sharedStrings));
        }

        if (sheets.Count == 0)
        {
            throw new InvalidDataException("Workbook has no readable worksheets.");
        }

        return new XlsxPreviewWorkbook(
            sheets,
            sheetDefinitions.Count > DocumentPreviewPolicy.MaxSpreadsheetPreviewSheets);
    }

    private static XlsxPreviewSheet ReadSheet(
        string name,
        XDocument sheetXml,
        IReadOnlyList<string> sharedStrings)
    {
        var formulaCellCount = 0;
        var rows = new List<List<string>>();
        foreach (var row in sheetXml.Descendants(SpreadsheetNamespace + "row")
                     .Take(DocumentPreviewPolicy.MaxSpreadsheetPreviewRows))
        {
            var values = new List<string>();
            var nextColumn = 1;
            foreach (var cell in row.Elements(SpreadsheetNamespace + "c"))
            {
                var reference = cell.Attribute("r")?.Value;
                var columnIndex = string.IsNullOrWhiteSpace(reference)
                    ? nextColumn
                    : ColumnIndexFromCellReference(reference);
                if (columnIndex > DocumentPreviewPolicy.MaxSpreadsheetPreviewColumns)
                {
                    continue;
                }

                while (values.Count < columnIndex - 1)
                {
                    values.Add(string.Empty);
                }

                if (cell.Element(SpreadsheetNamespace + "f") is not null)
                {
                    formulaCellCount++;
                }

                values.Add(ReadCellText(cell, sharedStrings));
                nextColumn = columnIndex + 1;
            }

            if (values.Any(value => !string.IsNullOrWhiteSpace(value)))
            {
                rows.Add(values);
            }
        }

        var columnCount = Math.Max(1, rows.Count == 0 ? 0 : rows.Max(row => row.Count));
        var table = new DataTable(name);
        for (var column = 1; column <= columnCount; column++)
        {
            table.Columns.Add(ColumnName(column));
        }

        foreach (var row in rows)
        {
            var dataRow = table.NewRow();
            for (var index = 0; index < Math.Min(row.Count, columnCount); index++)
            {
                dataRow[index] = row[index];
            }

            table.Rows.Add(dataRow);
        }

        var mergedRanges = sheetXml
            .Descendants(SpreadsheetNamespace + "mergeCell")
            .Select(element => element.Attribute("ref")?.Value)
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Take(DocumentPreviewPolicy.MaxSpreadsheetMergeRanges)
            .Select(value => value!)
            .ToList();
        return new XlsxPreviewSheet(name, table, mergedRanges, formulaCellCount);
    }

    private static string ReadCellText(XElement cell, IReadOnlyList<string> sharedStrings)
    {
        var inlineText = cell.Descendants(SpreadsheetNamespace + "t").FirstOrDefault()?.Value;
        if (inlineText is not null)
        {
            return inlineText;
        }

        var value = cell.Element(SpreadsheetNamespace + "v")?.Value;
        var dataType = cell.Attribute("t")?.Value;
        if (dataType == "s" &&
            int.TryParse(value, out var sharedStringIndex) &&
            sharedStringIndex >= 0 &&
            sharedStringIndex < sharedStrings.Count)
        {
            return sharedStrings[sharedStringIndex];
        }

        if (!string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        var formula = cell.Element(SpreadsheetNamespace + "f")?.Value;
        return string.IsNullOrWhiteSpace(formula) ? string.Empty : $"={formula}";
    }

    private static IReadOnlyList<string> LoadSharedStrings(ZipArchive archive)
    {
        if (archive.GetEntry("xl/sharedStrings.xml") is null)
        {
            return [];
        }

        var xml = LoadXml(archive, "xl/sharedStrings.xml");
        return xml.Descendants(SpreadsheetNamespace + "si")
            .Select(item => string.Concat(item.Descendants(SpreadsheetNamespace + "t").Select(text => text.Value)))
            .ToList();
    }

    private static XDocument LoadXml(ZipArchive archive, string entryName)
    {
        var entry = archive.GetEntry(entryName)
            ?? throw new InvalidDataException("Required workbook part is missing.");
        if (entry.Length > DocumentPreviewPolicy.MaxSpreadsheetXmlPartBytes ||
            entry.Length > 1024 * 1024 &&
            entry.CompressedLength > 0 &&
            entry.Length / entry.CompressedLength > DocumentPreviewPolicy.MaxSpreadsheetCompressionRatio)
        {
            throw new InvalidDataException("Workbook part exceeds the safe preview limit.");
        }

        using var stream = entry.Open();
        return XDocument.Load(stream, LoadOptions.None);
    }

    private static string NormalizeWorkbookTarget(string target)
    {
        var normalized = target.Replace('\\', '/').TrimStart('/');
        if (!normalized.StartsWith("xl/", StringComparison.OrdinalIgnoreCase))
        {
            normalized = $"xl/{normalized}";
        }

        var parts = new List<string>();
        foreach (var part in normalized.Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            if (part == "..")
            {
                if (parts.Count == 0)
                {
                    throw new InvalidDataException("Workbook relationship target is invalid.");
                }

                parts.RemoveAt(parts.Count - 1);
            }
            else if (part != ".")
            {
                parts.Add(part);
            }
        }

        return string.Join('/', parts);
    }

    private static int ColumnIndexFromCellReference(string reference)
    {
        var index = 0;
        foreach (var letter in reference.TakeWhile(char.IsLetter))
        {
            index = (index * 26) + char.ToUpperInvariant(letter) - 'A' + 1;
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
}
