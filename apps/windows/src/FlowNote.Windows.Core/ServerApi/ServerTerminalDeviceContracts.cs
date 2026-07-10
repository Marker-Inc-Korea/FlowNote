using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerTerminalDeviceResponse
{
    [JsonPropertyName("device_id")]
    public string DeviceId { get; init; } = string.Empty;

    [JsonPropertyName("device_name")]
    public string DeviceName { get; init; } = string.Empty;

    [JsonPropertyName("device_mode")]
    public string DeviceMode { get; init; } = string.Empty;

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("group_id")]
    public string? GroupId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("last_seen_at")]
    public DateTimeOffset? LastSeenAt { get; init; }

    [JsonPropertyName("registered_by")]
    public string? RegisteredBy { get; init; }

    [JsonPropertyName("updated_by")]
    public string? UpdatedBy { get; init; }

    [JsonPropertyName("replaced_device_id")]
    public string? ReplacedDeviceId { get; init; }

    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTimeOffset UpdatedAt { get; init; }

    public string StatusLabel => Status switch
    {
        "ACTIVE" => "사용",
        "INACTIVE" => "비활성",
        "RETIRED" => "폐기",
        _ => Status
    };

    public string LastSeenLabel => LastSeenAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss") ?? "접속 기록 없음";
}

public sealed record ServerTerminalDeviceCreateRequest
{
    [JsonPropertyName("device_id")]
    public string DeviceId { get; init; } = string.Empty;

    [JsonPropertyName("device_name")]
    public string DeviceName { get; init; } = string.Empty;

    [JsonPropertyName("device_mode")]
    public string DeviceMode { get; init; } = "viewer";

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("group_id")]
    public string? GroupId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "ACTIVE";
}

public sealed record ServerTerminalDeviceUpdateRequest
{
    [JsonPropertyName("device_name")]
    public string DeviceName { get; init; } = string.Empty;

    [JsonPropertyName("device_mode")]
    public string DeviceMode { get; init; } = "viewer";

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("group_id")]
    public string? GroupId { get; init; }

    [JsonPropertyName("change_reason")]
    public string? ChangeReason { get; init; }
}

public sealed record ServerTerminalDeviceStatusRequest(
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("change_reason")] string? ChangeReason);

public sealed record ServerTerminalDeviceReplaceRequest
{
    [JsonPropertyName("device_id")]
    public string DeviceId { get; init; } = string.Empty;

    [JsonPropertyName("device_name")]
    public string DeviceName { get; init; } = string.Empty;

    [JsonPropertyName("device_mode")]
    public string DeviceMode { get; init; } = "viewer";

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("group_id")]
    public string? GroupId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "ACTIVE";

    [JsonPropertyName("change_reason")]
    public string? ChangeReason { get; init; }
}
