using System.Net;
using System.Text.Json;

namespace FlowNote.Windows.Core.ServerApi;

public static class ServerAccessDenialPolicy
{
    public static string ErrorCode(string? responseBody)
    {
        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return "SERVER_REQUEST_DENIED";
        }

        try
        {
            using var json = JsonDocument.Parse(responseBody);
            if (json.RootElement.TryGetProperty("detail", out var detail))
            {
                if (detail.ValueKind == JsonValueKind.Object
                    && detail.TryGetProperty("code", out var code)
                    && code.ValueKind == JsonValueKind.String)
                {
                    return code.GetString() ?? "SERVER_REQUEST_DENIED";
                }

                if (detail.ValueKind == JsonValueKind.String
                    && detail.GetString()?.Contains(
                        "Terminal device is not approved",
                        StringComparison.OrdinalIgnoreCase) == true)
                {
                    return "DEVICE_NOT_APPROVED";
                }
            }
        }
        catch (JsonException)
        {
            // Unstructured server bodies are deliberately not shown to the user.
        }

        return "SERVER_REQUEST_DENIED";
    }

    public static string Message(HttpStatusCode statusCode, string? responseBody)
    {
        var code = ErrorCode(responseBody);
        return code switch
        {
            "DEVICE_NOT_APPROVED" =>
                "승인되지 않았거나 비활성 상태인 단말입니다. 관리자에게 단말 승인 상태를 확인하세요.",
            "PERMISSION_DENIED" or "ACCOUNT_NOT_ACTIVE" =>
                "현재 계정에는 이 작업 권한이 없습니다. 관리자에게 역할과 계정 상태를 확인하세요.",
            "SCOPE_NOT_FOUND" =>
                "현재 서버와 다른 고객·현장 범위입니다. 서버 주소와 현장 설정을 확인하세요.",
            "SOURCE_NOT_VISIBLE" or "RESOURCE_NOT_FOUND" =>
                "요청한 원천을 찾을 수 없거나 공개되지 않았습니다. 목록을 새로 조회하거나 관리자에게 공개 상태를 확인하세요.",
            _ when statusCode == HttpStatusCode.Unauthorized =>
                "로그인 정보가 만료되었거나 올바르지 않습니다. 다시 로그인하세요.",
            _ when statusCode == HttpStatusCode.Forbidden =>
                "현재 계정에는 이 작업 권한이 없습니다. 관리자에게 역할과 계정 상태를 확인하세요.",
            _ when statusCode == HttpStatusCode.NotFound =>
                "요청한 항목을 찾을 수 없거나 공개되지 않았습니다. 목록을 새로 조회하세요.",
            _ => "서버 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요."
        };
    }

    public static Exception CreateException(HttpStatusCode statusCode, string? responseBody)
    {
        var message = Message(statusCode, responseBody);
        if (statusCode == HttpStatusCode.Unauthorized)
        {
            return new FlowNoteServerAuthenticationException(message);
        }

        return new FlowNoteServerAccessException(
            statusCode,
            ErrorCode(responseBody),
            message);
    }
}

public sealed class FlowNoteServerAccessException(
    HttpStatusCode statusCode,
    string errorCode,
    string message) : InvalidOperationException(message)
{
    public HttpStatusCode StatusCode { get; } = statusCode;

    public string ErrorCode { get; } = errorCode;
}
