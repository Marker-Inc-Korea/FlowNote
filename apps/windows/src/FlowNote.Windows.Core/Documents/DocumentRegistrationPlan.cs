using FlowNote.Windows.Core.Folders;

namespace FlowNote.Windows.Core.Documents;

public sealed record DocumentRegistrationPlan(
    DocumentFolder Folder,
    string Title);
