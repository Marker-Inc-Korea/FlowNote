using System.Net;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Auth;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerAccountUiPolicyTests
{
    [Fact]
    public void ConnectedAndLocalModesHaveExplicitKoreanGuidance()
    {
        Assert.Contains("서버", ServerAccountUiPolicy.ConnectedMessage);
        Assert.Contains("로컬", ServerAccountUiPolicy.LocalMessage);
    }

    [Theory]
    [InlineData("admin", true)]
    [InlineData("system-admin", true)]
    [InlineData("manager", false)]
    [InlineData("viewer", false)]
    public void AccountButtonsFollowServerRole(string role, bool expected)
    {
        Assert.Equal(expected, ServerAccountUiPolicy.CanManageAccounts(role));
    }

    [Fact]
    public void UnauthorizedAndForbiddenHaveDifferentKoreanGuidance()
    {
        Assert.Contains("다시 로그인", ServerAccountUiPolicy.ErrorMessage(HttpStatusCode.Unauthorized));
        Assert.Contains("권한", ServerAccountUiPolicy.ErrorMessage(HttpStatusCode.Forbidden));
    }

    [Theory]
    [InlineData("admin", true)]
    [InlineData("document-admin", true)]
    [InlineData("department-manager", true)]
    [InlineData("line-foreman", false)]
    [InlineData("team-lead", false)]
    [InlineData("viewer", false)]
    public void DocumentGovernanceMatchesServerPolicy(string role, bool expected)
    {
        Assert.Equal(expected, RolePermissionPolicy.CanGovernDocuments(role));
    }
}
