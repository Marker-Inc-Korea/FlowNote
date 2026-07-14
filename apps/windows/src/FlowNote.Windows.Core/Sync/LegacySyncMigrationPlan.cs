namespace FlowNote.Windows.Core.Sync;

public static class LegacySyncMigrationCategories
{
    public const string LegacyCreate = "구 형식 create";
    public const string LegacyFieldNote = "구 FieldNote/첨부";
    public const string MissingPredecessorServerId = "선행 서버 ID 누락";
    public const string MissingLocalFile = "로컬 파일 누락";
    public const string ServerOrAuthenticationError = "실제 서버/인증 오류";
}

public static class LegacySyncMigrationStates
{
    public const string AutomaticallyConvertible = "자동 전환 가능";
    public const string AdministratorReviewRequired = "관리자 확인 필요";
    public const string SourceMissingUnconvertible = "원본 누락으로 전환 불가";
    public const string KeepPreserved = "계속 보존";
}

public sealed record LegacySyncMigrationPlanItem(
    long SourceRowId,
    string SourceSyncId,
    string SourceEntityType,
    string SourceEntityId,
    string SourceAction,
    string SourceIdempotencyKey,
    int AttemptCount,
    string Category,
    string MigrationState,
    string Reason,
    string OperatorAction,
    bool SourceExists,
    bool? LocalFileExists,
    string? LocalFilePath,
    string? TargetEntityType,
    string? TargetEntityId,
    string? TargetAction,
    string? ExpectedIdempotencyKey,
    string? ParentSourceSyncId);

public sealed record LegacySyncMigrationPlan(
    string DatabasePath,
    int FailedCount,
    int ClassifiedCount,
    string PlanHash,
    IReadOnlyDictionary<string, int> CategoryCounts,
    IReadOnlyDictionary<string, int> MigrationStateCounts,
    IReadOnlyList<LegacySyncMigrationPlanItem> Items);

public sealed record LegacySyncMigrationExecutionResult(
    int RequestedCount,
    int ApprovedCount,
    int CreatedSourceCount,
    int CreatedQueueCount,
    int CreatedAuditCount,
    int AlreadyMigratedCount,
    int RejectedCount,
    IReadOnlyList<string> Messages);
