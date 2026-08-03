using System.Security.Cryptography;
using System.Text;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ReportHashVerifierTests
{
    [Fact]
    public void ServerContentAndSourceSetHashesMatchCanonicalWpfReadBack()
    {
        var response = new ServerReportResponse
        {
            ReportId = "report-hash-test",
            ReportType = "field_review",
            Title = "보고서",
            Summary = "요약",
            AnalysisContent = "분석",
            Status = "APPROVED",
            ReportRevision = 3,
            Sources =
            [
                new ServerReportSourceResponse
                {
                    SourceType = "FIELD_COMMENT",
                    SourceId = "comment-1",
                    SourceVersionId = "version-1",
                    SourceRevision = 4,
                    SourceHashSha256 = new string('b', 64),
                    RelationType = "primary",
                    TraceId = "trace-2"
                },
                new ServerReportSourceResponse
                {
                    SourceType = "DOCUMENT",
                    SourceId = "document-1",
                    SourceVersionId = "version-2",
                    SourceHashSha256 = new string('a', 64),
                    RelationType = "related_document",
                    TraceId = "trace-1"
                }
            ]
        };
        const string canonicalContent =
            "{\"action_plan\":null,\"analysis_content\":\"분석\",\"conclusion\":null," +
            "\"period_end\":null,\"period_start\":null,\"report_type\":\"field_review\"," +
            "\"status\":\"APPROVED\",\"structure_item_id\":null,\"summary\":\"요약\"," +
            "\"title\":\"보고서\",\"work_record_id\":null}";
        var canonicalSources =
            "[{\"relation_type\":\"related_document\",\"source_hash_sha256\":\"" + new string('a', 64) +
            "\",\"source_id\":\"document-1\",\"source_revision\":null,\"source_type\":\"DOCUMENT\"," +
            "\"source_version_id\":\"version-2\"},{\"relation_type\":\"primary\"," +
            "\"source_hash_sha256\":\"" + new string('b', 64) +
            "\",\"source_id\":\"comment-1\",\"source_revision\":4,\"source_type\":\"FIELD_COMMENT\"," +
            "\"source_version_id\":\"version-1\"}]";
        response = response with
        {
            ContentHashSha256 = Sha256(canonicalContent),
            SourceSetHashSha256 = Sha256(canonicalSources)
        };

        ReportHashVerifier.Verify(response);

        var exception = Assert.Throws<FlowNoteServerConflictException>(
            () => ReportHashVerifier.Verify(response with { Title = "변경된 보고서" }));
        Assert.Equal("REPORT_CONTENT_HASH_MISMATCH", exception.ConflictCode);
    }

    private static string Sha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
