using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public static class DocumentConflictResolutionPolicy
{
    public const string KeepServer = "KEEP_SERVER";
    public const string RetryWithLatest = "RETRY_WITH_LATEST";
    public const string ReapplyTagDelta = "REAPPLY_TAG_DELTA";
    public const string RegisterNewVersion = "REGISTER_NEW_VERSION";

    public static IReadOnlyList<string> AllowedActions(
        string queueAction,
        string conflictCode,
        IReadOnlyList<string>? serverActions = null)
    {
        var actions = (serverActions ?? [])
            .Where(IsKnown)
            .Distinct(StringComparer.Ordinal)
            .ToList();
        if (actions.Count == 0)
        {
            actions.Add(KeepServer);
            if (queueAction == "replace_document_tags" ||
                queueAction is "publish_document_version" or "update_document_status")
            {
                actions.Add(RetryWithLatest);
            }
            if (queueAction == "replace_document_tags")
            {
                actions.Add(ReapplyTagDelta);
            }
            else if (queueAction == "register_document_version" &&
                conflictCode is "STALE_REVISION" or "STALE_BASE_VERSION" or "FILE_HASH_MISMATCH")
            {
                actions.Add(RegisterNewVersion);
            }
        }

        if (queueAction != "register_document_version")
        {
            actions.Remove(RegisterNewVersion);
        }
        if (queueAction is not ("replace_document_tags" or "publish_document_version" or "update_document_status"))
        {
            actions.Remove(RetryWithLatest);
        }
        if (queueAction != "replace_document_tags")
        {
            actions.Remove(ReapplyTagDelta);
        }
        if (conflictCode is "DOCUMENT_DELETED" or "IDEMPOTENCY_KEY_REUSED")
        {
            actions.RemoveAll(action => action != KeepServer);
        }
        return actions;
    }

    public static string ToJson(IReadOnlyList<string> actions) =>
        JsonSerializer.Serialize(actions);

    public static bool Contains(string? actionsJson, string action)
    {
        if (string.IsNullOrWhiteSpace(actionsJson))
        {
            return false;
        }
        try
        {
            return (JsonSerializer.Deserialize<List<string>>(actionsJson) ?? [])
                .Contains(action, StringComparer.Ordinal);
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public static void ValidateResolution(string resolvedBy, string reason, string resolvedRole)
    {
        if (string.IsNullOrWhiteSpace(resolvedBy))
        {
            throw new InvalidOperationException("충돌 해결에는 문서 관리 역할의 해결자 정보가 필요합니다.");
        }
        if (string.IsNullOrWhiteSpace(reason) || reason.Trim().Length < 10)
        {
            throw new InvalidOperationException("충돌 해결 사유를 10자 이상 입력하세요.");
        }
        if (!DocumentManagementRoles.Contains(resolvedRole.Trim()))
        {
            throw new InvalidOperationException(
                "문서 충돌 해결에는 admin, manager, system-admin, document-admin, assistant-manager 또는 department-manager 역할이 필요합니다. 사내 관리자에게 문의하세요.");
        }
    }

    private static bool IsKnown(string action) =>
        action is KeepServer or RetryWithLatest or ReapplyTagDelta or RegisterNewVersion;

    private static readonly HashSet<string> DocumentManagementRoles = new(
        ["admin", "manager", "system-admin", "document-admin", "assistant-manager", "department-manager"],
        StringComparer.OrdinalIgnoreCase);
}
