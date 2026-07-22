using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.Storage;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class FieldCommentWorkbenchTests
{
    private static readonly string DatabasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        "field-comment-workbench-core-tests.sqlite");

    [Fact]
    public void SavedViewPersistsConflictAndOperationalFiltersAcrossRestart()
    {
        var database = new FlowNoteLocalDatabase(DatabasePath);
        database.Initialize();
        var service = new FieldCommentService(database);
        var name = $"상충 우선 보기 {Guid.NewGuid():N}";
        var expected = new FieldCommentReviewFilter(
            Status: "NEEDS_REVIEW",
            AssignedTo: "user-admin",
            LineText: "line-a",
            EquipmentText: "press-01",
            ProcessText: "forming",
            ErrorTypeText: "alignment",
            Overdue: true,
            Conflict: true,
            PriorityOrder: true,
            Limit: 200);

        service.SaveView(name, expected);

        var restarted = new FieldCommentService(new FlowNoteLocalDatabase(DatabasePath));
        var actual = Assert.Single(restarted.ListSavedViews(), item => item.Name == name).Filter;
        Assert.Equal(expected, actual);
    }
}
