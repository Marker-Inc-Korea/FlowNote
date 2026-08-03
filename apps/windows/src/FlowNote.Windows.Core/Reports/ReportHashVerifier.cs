using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.Core.Reports;

public static class ReportHashVerifier
{
    private static readonly JsonSerializerOptions CanonicalJson = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
    };

    public static void Verify(ServerReportResponse response)
    {
        if (response.ReportRevision < 1 || response.ContentHashSha256?.Length != 64 ||
            response.SourceSetHashSha256?.Length != 64)
        {
            throw new InvalidOperationException(
                "서버 보고서 revision/content/source-set hash read-back이 불완전합니다.");
        }

        var contentHash = ComputeContentHash(response);
        if (!string.Equals(contentHash, response.ContentHashSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new FlowNoteServerConflictException(
                "REPORT_CONTENT_HASH_MISMATCH",
                "서버 보고서 content read-back hash가 aggregate hash와 다릅니다.",
                null, response.ReportRevision, response.Status, null, null,
                $"server={response.ContentHashSha256}; readBack={contentHash}");
        }

        var sourceSetHash = ComputeSourceSetHash(response.Sources);
        if (!string.Equals(sourceSetHash, response.SourceSetHashSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new FlowNoteServerConflictException(
                "REPORT_SOURCE_SET_HASH_MISMATCH",
                "서버 보고서 source read-back hash가 aggregate hash와 다릅니다.",
                null, response.ReportRevision, response.Status, null, null,
                $"server={response.SourceSetHashSha256}; readBack={sourceSetHash}");
        }
    }

    public static string ComputeContentHash(ServerReportResponse response)
    {
        var normalized = new SortedDictionary<string, object?>
        {
            ["action_plan"] = response.ActionPlan,
            ["analysis_content"] = response.AnalysisContent,
            ["conclusion"] = response.Conclusion,
            ["period_end"] = response.PeriodEnd?.ToString("O"),
            ["period_start"] = response.PeriodStart?.ToString("O"),
            ["report_type"] = response.ReportType,
            ["status"] = response.Status,
            ["structure_item_id"] = response.StructureItemId,
            ["summary"] = response.Summary,
            ["title"] = response.Title,
            ["work_record_id"] = response.WorkRecordId
        };
        return Sha256(JsonSerializer.Serialize(normalized, CanonicalJson));
    }

    public static string ComputeSourceSetHash(IEnumerable<ServerReportSourceResponse> sources)
    {
        var normalized = sources
            .Select(source => new SortedDictionary<string, object?>
            {
                ["relation_type"] = source.RelationType,
                ["source_hash_sha256"] = source.SourceHashSha256,
                ["source_id"] = source.SourceId,
                ["source_revision"] = source.SourceRevision,
                ["source_type"] = source.SourceType,
                ["source_version_id"] = source.SourceVersionId
            })
            .OrderBy(item => Convert.ToString(item["source_type"], System.Globalization.CultureInfo.InvariantCulture))
            .ThenBy(item => Convert.ToString(item["source_id"], System.Globalization.CultureInfo.InvariantCulture))
            .ThenBy(item => Convert.ToString(item["source_version_id"], System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)
            .ThenBy(item => Convert.ToString(item["relation_type"], System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)
            .ThenBy(item => Convert.ToString(item["source_hash_sha256"], System.Globalization.CultureInfo.InvariantCulture))
            .ToList();
        return Sha256(JsonSerializer.Serialize(normalized, CanonicalJson));
    }

    private static string Sha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
