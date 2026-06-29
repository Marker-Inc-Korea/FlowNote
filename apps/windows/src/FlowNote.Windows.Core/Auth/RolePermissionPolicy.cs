namespace FlowNote.Windows.Core.Auth;

public static class RolePermissionPolicy
{
    private static readonly HashSet<string> DocumentRegistrationRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "manager",
        "system-admin",
        "document-admin",
        "assistant-manager",
        "department-manager",
        "line-foreman",
        "team-lead"
    };

    public static bool CanRegisterDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentRegistrationRoles.Contains(role);
    }
}
