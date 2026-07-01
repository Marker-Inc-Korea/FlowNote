using System.IO;

namespace FlowNote.Windows.Core.Documents;

public static class DocumentPreviewPolicy
{
    public const long MaxTextPreviewBytes = 128 * 1024;
    public const int MaxSpreadsheetPreviewRows = 100;
    public const long LargeSampleBytes = 5 * 1024 * 1024;

    private static readonly HashSet<string> TextExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".txt",
        ".md",
        ".csv",
        ".log"
    };

    private static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".webp"
    };

    private static readonly HashSet<string> CadExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".dwg",
        ".dxf",
        ".step",
        ".stp",
        ".iges",
        ".igs"
    };

    private static readonly HashSet<string> HwpExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".hwp",
        ".hwpx"
    };

    public static DocumentPreviewKind ClassifyPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return DocumentPreviewKind.Missing;
        }

        return ClassifyExtension(Path.GetExtension(path));
    }

    public static DocumentPreviewKind ClassifyFileName(string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName))
        {
            return DocumentPreviewKind.Unsupported;
        }

        return ClassifyExtension(Path.GetExtension(fileName));
    }

    public static string DisplayName(DocumentPreviewKind kind)
    {
        return kind switch
        {
            DocumentPreviewKind.Text => "TXT",
            DocumentPreviewKind.Pdf => "PDF",
            DocumentPreviewKind.Spreadsheet => "XLSX",
            DocumentPreviewKind.Image => "이미지",
            DocumentPreviewKind.Cad => "CAD",
            DocumentPreviewKind.Hwp => "HWP",
            DocumentPreviewKind.Missing => "파일 없음",
            _ => "미지원 파일"
        };
    }

    public static string BuildPreviewUnavailableMessage(DocumentPreviewKind kind, string fileName)
    {
        return kind switch
        {
            DocumentPreviewKind.Cad =>
                $"CAD 고급 뷰어는 현재 MVP 범위에서 제외되어 있습니다. 파일 첨부와 열람 이력은 유지되며, 관리자는 원본 파일명과 문서 메타데이터를 확인할 수 있습니다.\n파일명: {fileName}",
            DocumentPreviewKind.Hwp =>
                $"HWP 고급 뷰어는 현재 MVP 범위에서 제외되어 있습니다. 파일 첨부와 열람 이력은 유지되며, 관리자는 원본 파일명과 문서 메타데이터를 확인할 수 있습니다.\n파일명: {fileName}",
            DocumentPreviewKind.Missing =>
                "로컬 파일을 찾을 수 없어 문서 메타데이터만 표시합니다. 서버 또는 등록 PC의 파일 보존 상태를 확인하세요.",
            _ =>
                $"현재 클라이언트에서 이 파일 형식은 본문 미리보기를 지원하지 않습니다. 파일 첨부와 열람 이력은 유지됩니다.\n파일명: {fileName}"
        };
    }

    public static string BuildLargeTextMessage(long sizeBytes)
    {
        return $"TXT 파일이 미리보기 기준보다 큽니다.\n파일 크기: {sizeBytes:N0} bytes\n현재 클라이언트는 {MaxTextPreviewBytes:N0} bytes 이하 텍스트만 본문으로 표시하고, 큰 파일은 메타데이터와 열람 이력만 남깁니다.";
    }

    public static IReadOnlyList<DocumentPreviewSampleCriterion> SampleCriteria { get; } =
    [
        new("TXT", "정상", ".txt UTF-8 본문, 128 KiB 이하", "본문 표시, 열람 시작/종료/다운로드 차단/자동 닫힘 로그"),
        new("TXT", "비정상", ".txt 확장자이지만 UTF-8로 읽을 수 없거나 접근 불가", "한글 오류 안내와 document.preview_failed 이력"),
        new("TXT", "한글 파일명", "예: 작업표준서-혼합공정.txt", "파일명과 본문 한글 표시"),
        new("TXT", "큰 파일", "128 KiB 초과", "본문 대신 메타데이터 표시와 제한 이력"),
        new("PDF", "정상", ".pdf 형식 검증 통과", "WebView2 표시, PDF 저장/인쇄 도구 숨김, 다운로드 이벤트 차단"),
        new("PDF", "비정상", ".pdf 확장자이지만 PDF 파서가 열 수 없음", "WebView2 이동 없이 한글 오류 안내와 실패 이력"),
        new("PDF", "한글 파일명", "예: 도면-프레스A-금형배치.pdf", "파일명 한글 유지와 열람 로그"),
        new("PDF", "큰 파일", "5 MiB 이상 또는 현장 기준 대용량", "앱 종료 없이 WebView2 표시 또는 실패 안내"),
        new("XLSX", "정상", "sheet1.xml이 있는 .xlsx", "첫 번째 시트 최대 100행 표시"),
        new("XLSX", "비정상", "ZIP/XML 구조가 깨진 .xlsx", "한글 오류 안내와 실패 이력"),
        new("XLSX", "한글 파일명", "예: 품질점검표-라인A.xlsx", "파일명 한글 유지와 첫 시트 표시"),
        new("XLSX", "큰 파일", "5 MiB 이상 또는 행/열이 많은 파일", "최대 100행 표시, 앱 종료 없음"),
        new("이미지", "정상", ".jpg/.png/.bmp/.gif/.tif/.webp", "이미지 표시와 메타데이터 표시"),
        new("이미지", "비정상", "이미지 디코더가 읽을 수 없는 파일", "한글 오류 안내와 실패 이력"),
        new("이미지", "한글 파일명", "예: 사진-설비점검-라인A.jpg", "파일명 한글 유지와 이미지 표시"),
        new("이미지", "큰 파일", "5 MiB 이상 또는 고해상도", "앱 종료 없이 이미지 표시 또는 실패 안내")
    ];

    private static DocumentPreviewKind ClassifyExtension(string extension)
    {
        if (string.IsNullOrWhiteSpace(extension))
        {
            return DocumentPreviewKind.Unsupported;
        }

        if (TextExtensions.Contains(extension))
        {
            return DocumentPreviewKind.Text;
        }

        if (extension.Equals(".pdf", StringComparison.OrdinalIgnoreCase))
        {
            return DocumentPreviewKind.Pdf;
        }

        if (extension.Equals(".xlsx", StringComparison.OrdinalIgnoreCase))
        {
            return DocumentPreviewKind.Spreadsheet;
        }

        if (ImageExtensions.Contains(extension))
        {
            return DocumentPreviewKind.Image;
        }

        if (CadExtensions.Contains(extension))
        {
            return DocumentPreviewKind.Cad;
        }

        if (HwpExtensions.Contains(extension))
        {
            return DocumentPreviewKind.Hwp;
        }

        return DocumentPreviewKind.Unsupported;
    }
}
