using System.Text.Json;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;

var options = ParseArguments(args);
if (options.ShowHelp)
{
    Console.WriteLine("""
        FlowNote 보존 동기화 실패 전환 도구

        dry-run (기본, DB 변경 0건):
          dotnet run --project apps/windows/src/FlowNote.Windows.SyncMigrationTool -- [--database PATH]

        승인 실행:
          dotnet run --project apps/windows/src/FlowNote.Windows.SyncMigrationTool -- \
            --execute --database PATH --approve 79,85 --approved-by "관리자" --plan-hash HASH

        --approve는 dry-run 결과의 sourceRowId만 받습니다. 구 FieldNote 첨부는 부모 본문 row도 함께
        승인해야 합니다. 승인 실행은 원본 큐와 파일을 수정·삭제하지 않고 신규 큐와 감사 행만 추가합니다.
        """);
    return;
}

var service = new LegacySyncMigrationService(options.DatabasePath);
var serializerOptions = new JsonSerializerOptions
{
    WriteIndented = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase
};

if (!options.Execute)
{
    var plan = service.CreateDryRunPlan();
    Console.WriteLine(JsonSerializer.Serialize(plan, serializerOptions));
    return;
}

if (options.ApprovedRowIds.Count == 0 || string.IsNullOrWhiteSpace(options.ApprovedBy) || string.IsNullOrWhiteSpace(options.PlanHash))
{
    throw new ArgumentException("승인 실행에는 --approve, --approved-by, --plan-hash가 모두 필요합니다.");
}

var result = service.ExecuteApproved(options.ApprovedRowIds, options.ApprovedBy, options.PlanHash);
Console.WriteLine(JsonSerializer.Serialize(result, serializerOptions));

static ToolOptions ParseArguments(string[] args)
{
    var databasePath = FlowNoteLocalDatabase.DefaultDatabasePath;
    var execute = false;
    var showHelp = false;
    var approvedIds = new SortedSet<long>();
    string? approvedBy = null;
    string? planHash = null;

    for (var index = 0; index < args.Length; index++)
    {
        switch (args[index])
        {
            case "--database":
                databasePath = RequireValue(args, ref index, "--database");
                break;
            case "--execute":
                execute = true;
                break;
            case "--approve":
                foreach (var value in RequireValue(args, ref index, "--approve").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                {
                    if (!long.TryParse(value, out var id) || id <= 0)
                    {
                        throw new ArgumentException($"승인 row ID가 올바르지 않습니다: {value}");
                    }
                    approvedIds.Add(id);
                }
                break;
            case "--approved-by":
                approvedBy = RequireValue(args, ref index, "--approved-by");
                break;
            case "--plan-hash":
                planHash = RequireValue(args, ref index, "--plan-hash");
                break;
            case "--help":
            case "-h":
                showHelp = true;
                break;
            default:
                throw new ArgumentException($"알 수 없는 인수입니다: {args[index]}");
        }
    }

    return new ToolOptions(Path.GetFullPath(databasePath), execute, showHelp, approvedIds.ToArray(), approvedBy, planHash);
}

static string RequireValue(string[] args, ref int index, string option)
{
    if (++index >= args.Length || string.IsNullOrWhiteSpace(args[index]))
    {
        throw new ArgumentException($"{option} 뒤에 값이 필요합니다.");
    }
    return args[index];
}

internal sealed record ToolOptions(
    string DatabasePath,
    bool Execute,
    bool ShowHelp,
    IReadOnlyList<long> ApprovedRowIds,
    string? ApprovedBy,
    string? PlanHash);
