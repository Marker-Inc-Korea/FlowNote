namespace FlowNote.Windows.Core.Documents;

public enum DocumentPreviewFailureCategory
{
    MissingFile,
    AccessDenied,
    Encrypted,
    Corrupted,
    UnsupportedContent,
    InvalidEncoding,
    ResourceLimit,
    ViewerUnavailable,
    Unexpected
}

public sealed record DocumentPreviewFailure(
    DocumentPreviewKind FileKind,
    DocumentPreviewFailureCategory Category,
    string Summary,
    string NextAction)
{
    public string FileType => DocumentPreviewPolicy.DisplayName(FileKind);

    public string CategoryName => Category switch
    {
        DocumentPreviewFailureCategory.MissingFile => "원본 위치 확인 필요",
        DocumentPreviewFailureCategory.AccessDenied => "열람 권한 또는 파일 접근 실패",
        DocumentPreviewFailureCategory.Encrypted => "암호화된 문서",
        DocumentPreviewFailureCategory.Corrupted => "손상되었거나 불완전한 문서",
        DocumentPreviewFailureCategory.UnsupportedContent => "지원하지 않는 내부 형식",
        DocumentPreviewFailureCategory.InvalidEncoding => "문자 인코딩 확인 필요",
        DocumentPreviewFailureCategory.ResourceLimit => "안전 미리보기 한도 초과",
        DocumentPreviewFailureCategory.ViewerUnavailable => "필수 뷰어 구성요소 없음",
        _ => "미리보기 처리 실패"
    };

    public string AuditCode => $"{FileKind.ToString().ToUpperInvariant()}_{Category.ToString().ToUpperInvariant()}";

    public const string PreservationMessage =
        "원본 파일, 문서 버전과 열람 이력은 그대로 보존되며 앱 세션도 계속 사용할 수 있습니다.";

    public static DocumentPreviewFailure Create(
        DocumentPreviewKind kind,
        DocumentPreviewFailureCategory category)
    {
        var summary = category switch
        {
            DocumentPreviewFailureCategory.MissingFile =>
                "현재 PC에서 원본 파일을 확인할 수 없어 본문을 표시하지 않았습니다.",
            DocumentPreviewFailureCategory.AccessDenied =>
                "승인된 열람 경로에서 파일을 읽을 수 없어 본문을 표시하지 않았습니다.",
            DocumentPreviewFailureCategory.Encrypted =>
                "암호가 필요한 문서는 앱 안에서 자동으로 해제하지 않으므로 본문을 표시하지 않았습니다.",
            DocumentPreviewFailureCategory.Corrupted =>
                "파일 구조가 손상되었거나 일부만 저장되어 안전하게 미리 볼 수 없습니다.",
            DocumentPreviewFailureCategory.UnsupportedContent =>
                "확장자는 지원 대상이지만 내부 형식은 현재 미리보기에서 처리할 수 없습니다.",
            DocumentPreviewFailureCategory.InvalidEncoding =>
                "지원하는 문자 인코딩으로 본문을 안전하게 해석할 수 없습니다.",
            DocumentPreviewFailureCategory.ResourceLimit =>
                "파일 크기나 문서 구조가 안전 미리보기 한도를 넘어 본문을 표시하지 않았습니다.",
            DocumentPreviewFailureCategory.ViewerUnavailable =>
                "승인된 앱 내부 뷰어 구성요소를 시작할 수 없습니다.",
            _ =>
                "미리보기 처리 중 문제가 발생해 본문을 표시하지 않았습니다."
        };

        var nextAction = category switch
        {
            DocumentPreviewFailureCategory.MissingFile =>
                "현장 관리자에게 서버 또는 등록 PC의 원본 보존 상태 확인을 요청하세요.",
            DocumentPreviewFailureCategory.AccessDenied =>
                "현장 관리자에게 문서 권한과 서버 저장소 접근 상태 확인을 요청하세요.",
            DocumentPreviewFailureCategory.Encrypted =>
                "문서 관리자에게 승인된 비암호 사본을 새 버전으로 등록해 달라고 요청하세요.",
            DocumentPreviewFailureCategory.Corrupted =>
                "문서 관리자에게 원본 무결성을 확인하고 정상 파일을 새 버전으로 등록해 달라고 요청하세요.",
            DocumentPreviewFailureCategory.UnsupportedContent =>
                "문서 관리자에게 지원 형식으로 변환한 승인본 등록을 요청하세요. 외부 앱은 자동으로 열리지 않습니다.",
            DocumentPreviewFailureCategory.InvalidEncoding =>
                "문서 관리자에게 UTF-8, UTF-16 또는 CP949 형식으로 저장한 승인본 등록을 요청하세요.",
            DocumentPreviewFailureCategory.ResourceLimit =>
                "문서 관리자에게 문서를 나누거나 해상도를 조정한 승인본 등록을 요청하세요.",
            DocumentPreviewFailureCategory.ViewerUnavailable =>
                "Windows 설치 담당자에게 승인된 WebView2 Runtime 설치 상태 확인을 요청하세요.",
            _ =>
                "같은 문서를 반복해서 열지 말고 현장 관리자에게 미리보기 점검을 요청하세요."
        };

        return new DocumentPreviewFailure(kind, category, summary, nextAction);
    }
}
