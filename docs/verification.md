# 검증 자동화

이 문서는 테스트 DB와 산출물 보존 규칙을 지키면서 FlowNote의 현재 검증 순서를 한 번에 실행하는 기준이다. 실패하더라도 SQLite DB, 로그, 테스트 입력 파일, 출력 파일, 렌더링 결과, 스모크 테스트 산출물은 삭제하지 않는다.

## 표준 실행

저장소 루트에서 다음 명령을 실행한다.

```powershell
.\scripts\verify-preserved-tests.ps1
```

스크립트는 다음 순서로 실행한다.

1. `.gitignore`가 알려진 테스트/빌드 산출물 경로를 제외하는지 점검한다.
2. 실행 전 `git status --porcelain=v1 --untracked-files=all`에서 SQLite 예외 외 테스트 산출물, 빌드 결과, 개인 로컬 경로가 잡히지 않는지 점검한다.
3. `services/api`에서 FastAPI pytest 수집 개수가 현재 기준선인 75개인지 확인한다.
4. `services/api`에서 FastAPI pytest를 실행한다.
5. WPF 앱을 빌드한다.
6. WPF 스모크 테스트를 실행한다.
7. 실행 후 `git status`를 다시 점검한다.

개별 명령은 다음과 같다.

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest
cd ..\..
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
git status --short
```

2026-07-14 현재 FastAPI 코드는 75건이 수집된다. 기존 68건 기준선에 AI 근거 검색 ground-truth 회귀 평가 1건과 controlled copy 보안·감사 회귀 6건이 추가된 결과다. 표준 PowerShell 스크립트도 같은 75건을 요구한다.

## 2026-07-14 작업 102 현재 코드 재대조

작업 시작 시 Git 작업 트리는 깨끗했으므로 미커밋 변경을 추정 반영하지 않고 현재 FastAPI, Windows WPF, Android 코드와 상위 제품 문서의 구현 범위를 다시 대조했다. Android 문서 본문 뷰어 미구현, WPF controlled copy 저장·SHA-256 검증, AI 근거 평가와 외부 호출 전 안전장치 골격 등 기존 구현 설명은 코드와 일치한다. 최신 Windows 코드의 보존 FAILED 큐 전환 기능은 독립 운영 문서와 데이터 모델·결정 기록에는 있었지만 Windows 문서 색인, 구현 목록, 로컬 SQLite 설명, 시스템 맵과 로드맵 연결이 부족해 해당 문서를 보강했다.

FastAPI OpenAPI는 루트 `GET /` 1개를 포함해 총 71개 method/path이며, 이 중 `/api/v1`은 70개 method/path와 55개 고유 path다. 아래 2026-07-13 기록의 “71개”는 이 전체 수를 뜻하므로 범위를 명확히 했다. `services/api`에서 `pytest --collect-only -q`를 다시 실행해 75건 수집도 확인했다. 이번 요청에는 코드 변경이 없어 전체 pytest, WPF 빌드·스모크와 Android 빌드·단위 테스트는 새로 실행하지 않았고 기존 테스트 데이터와 산출물은 삭제하지 않았다.

## 2026-07-13 전체 Markdown 코드 정합성 갱신

Git으로 추적하는 Markdown 문서 전체를 현재 FastAPI, Windows WPF, Android 코드와 다시 대조했다. 저장소 작업 규칙인 `AGENTS.md`는 제품 문서가 아니므로 내용 수정 대상에서 제외했고, 날짜별 작업·검증 수치는 당시 이력으로 보존하면서 현재 기능을 설명하는 문장만 최신 코드에 맞췄다.

주요 정정은 Android의 문서 기능을 파일 본문 열람으로 과장하지 않고 공개 문서 목록·상세 메타데이터 조회와 FieldComment 문서/버전 연결 범위로 명시한 것, 서버 DB 문서에 외부 AI 질의·근거 snapshot·인용·호출 감사·전송 승인 및 `controlled_copy_grants` 테이블을 추가한 것, WPF controlled copy가 로컬 원본 복사나 동기화 큐가 아니라 서버의 사용자·세션 바인딩 1회성 스트리밍과 저장 후 SHA-256 검증임을 반영한 것이다.

FastAPI OpenAPI의 루트 `GET /`를 포함한 전체 method/path 71개가 `docs/api.md` 또는 `services/api/README.md`에 모두 존재하고, 서버 ORM의 모든 `__tablename__`이 DB 스키마 문서 3곳에 빠짐없이 명시된 것도 확인했다. 추적 Markdown의 상대 파일 링크와 `git diff --check`도 통과했다.

`services/api`에서 `pytest --collect-only -q`로 75건을 확인한 뒤 전체 pytest를 실행해 75건이 모두 통과했다. 이번 작업은 문서와 예제 환경 변수 갱신이므로 WPF 빌드·스모크와 Android 빌드·단위 테스트는 새로 실행하지 않았다. 기존 SQLite, 로그, pytest cache와 테스트 산출물은 삭제하지 않았다.

## 2026-07-13 AI 근거 검색 회귀 평가 반영

문서 갱신 과정에서 추가된 `test_ai_search_ground_truth_evaluation_is_reproducible_and_persisted`는 안정 candidate ID와 content hash, 재생성 전후 순위, 네 원천 커버, 제외 근거, `INSUFFICIENT_EVIDENCE`, 평가 실행·케이스 SQLite 누적을 검증한다.

controlled copy 구현 후 `services/api`의 `pytest --collect-only -q`와 전체 pytest에서 75건 수집·통과를 확인했다. 이 환경에는 `dotnet` 명령이 없어 WPF 빌드와 WPF 스모크는 실행하지 못했다. 기존 DB, 로그, 테스트 산출물과 pytest cache는 삭제하지 않았다.

## 2026-07-13 외부 AI 질의 안전장치 검증

`scripts/verify-preserved-tests.ps1`의 FastAPI 수집 기대값을 58개에서 68개로 갱신했다. `services/api`에서 테스트를 다시 수집해 68개를 확인했고 전체 pytest 68건이 통과했다. 추가 기준에는 AI 근거 검색 2개와 외부 AI 질의의 비활성 기본값, 금지 목적, 전송 승인, 근거 snapshot, 응답 미저장, 권한, 프롬프트 불변성 검증 8개가 포함된다. 이번 실행에서는 WPF 빌드와 WPF 스모크를 실행하지 않았고 기존 DB, 로그, 파일과 실패 흔적은 삭제하지 않았다.

## 2026-07-13 표준 보존형 검증 기준 갱신

`scripts/verify-preserved-tests.ps1`의 FastAPI 수집 기대값을 53개에서 58개로 갱신했다. 테스트 파일의 최상위 `test_*` 함수를 파일별로 확인한 결과 합계는 58개였고, 기존 기준선 이후 추가된 테스트는 다음 5개다.

- `tests/test_auth_api.py`: 승인된 Android 단말 로그인과 미승인·비활성 단말 로그인 거부 2개
- `tests/test_terminal_devices_api.py`: 관리자 단말 등록·조회·변경·비활성화, 단말 교체·폐기 상태 불변식, 비관리자 접근 거부 3개

이번에는 테스트 수집 개수와 보존 상태만 점검했으므로 전체 회귀 통과 기록으로 판정하지 않는다. 표준 검증이 가능한 환경에서 `.\scripts\verify-preserved-tests.ps1`의 시작부터 Git 사후 점검까지 통과한 결과를 추가로 남겨야 한다.

실행 가능한 보존 점검에서는 공통 SQLite `data/local/flownote.local.sqlite`의 `PRAGMA quick_check`가 `ok`, `PRAGMA foreign_key_check` 결과가 0건이었다. `data/local/flownote.local.sqlite`, `data/local/Files/`, WPF `bin/`과 `obj/` probe 경로에 Git 제외 규칙이 적용됨을 확인했다. `git status --short --untracked-files=all`에는 이번 문서와 표준 스크립트 변경만 표시되었고, `git diff --cached --name-only`는 비어 있었다. 기존 DB, 로그, 파일과 실패 흔적은 삭제하지 않았다.

## 2026-07-10 코드-문서 정합성 재점검

현재 FastAPI 테스트를 다시 수집한 결과 58개가 정상 수집되었다. 이번 문서 갱신에서는 전체 pytest, WPF 빌드, WPF 스모크를 새로 실행하지 않았으며 기존 DB와 테스트 산출물도 삭제하거나 초기화하지 않았다.

현재 코드의 라우터, 서버 ORM 모델, Windows 서버 API 클라이언트와 Android 최소 앱을 상위 문서와 대조했다. 승인 단말 관리, 채널/인수인계, Android outbox, AI 근거 후보 read model은 구현 범위로 유지한다. `/api/v1/ai/queries` 생성·조회, `ai_queries` 계열 모델, 기능 플래그·목적·외부 전송 승인·근거 snapshot 검사는 안전장치 골격으로 검증한다. 운영 provider client, 네트워크 호출과 질의 재생성은 아직 검증 범위가 아니다.

## WPF 스모크 필수 조건

WPF 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 사용한다. 표준 스크립트는 실행 중 `FLOWNOTE_LOCAL_DATA_DIR`와 `FLOWNOTE_LOCAL_DATABASE_PATH`를 비워 임시 SQLite가 아니라 공통 SQLite에 누적 기록되도록 한다.

현재 스모크 테스트는 다음 항목을 필수로 검증한다.

- 오늘 날짜의 인수인계 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 오늘 날짜의 사진 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 기존 인수인계 또는 사진 날짜 폴더 중 과거 날짜 폴더를 랜덤 선택하고, 그 안의 기존 문서에 버전 코멘트를 추가해 버전 번호가 1 증가했는지 확인한다.
- 과거 날짜 검증은 기존 날짜 폴더와 기존 문서만 대상으로 하며, 과거 날짜 폴더나 과거 날짜 문서를 새로 만들지 않는다.
- TXT/PDF/XLSX/이미지 미리보기 샘플 기준을 확인하고, 각 유형별 열람 종료, 자동 닫힘, 다운로드 차단 로그를 공통 SQLite에 누적한다.
- 실행 출력의 `Preview audit smoke` 줄에 파일 유형, 샘플 파일 경로, 로그 ID가 남는다.
- `FLOWNOTE_API_BASE_URL`이 없더라도 `http://127.0.0.1:5184` 로컬 FastAPI 서버가 실행 중이면 서버 로그인, 문서 등록, 버전, 공개 조회를 검증한다.
- 서버 URL이 없으면 WPF 로컬 계정 fallback이 허용되는지 확인한다.
- 서버 로그인 응답이 401 또는 403이면 같은 로그인 ID의 WPF 로컬 계정으로 우회하지 않는지 확인한다.

controlled copy API 회귀는 `tests/test_controlled_copy_api.py`에서 전체 기본 role의 허용·거부, 정확한 공개 버전, SHA-256 일치, 만료·재사용·다른 사용자/세션·문서/버전 불일치·Range·경로 순회·전송 전 파일 변경을 검증한다. WPF 수동 확인에서는 허용 role의 서버 저장과 해시 검증 안내, 비허용 role의 기존 차단 안내를 확인하고 `document_access_logs`와 `activity_history`의 사용자·단말·버전·사유를 대조한다.

과거 날짜 후보가 하나도 없으면 스모크 테스트는 실패한다. 이 경우 DB를 삭제하지 말고 누적 데이터 상태를 확인해 다음 분석에 사용한다.

## 2026-07-08 누적 스모크 기록

공통 SQLite `data/local/flownote.local.sqlite`에는 2026-07-08 15:25 KST 기준 `smoke-102-human-20260708-132307`, `smoke-102-20260708143141`, `102-20260708143304`, `smoke-102-human-20260708-152335` 실행 기록이 누적되어 있다. 이 기록은 삭제하지 않고 이후 회귀 검증의 기준 데이터로 사용한다.

- `smoke-102-human-20260708-132307` 실행에서는 오늘 날짜 폴더 기준으로 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달` 문서가 등록되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 라인A 계량기 사진은 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `사진/2026-06-29` 문서 `사진당일라인A20260629113103758`의 버전을 v4로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- `102-20260708143304` 실행에서는 오늘 날짜 기준 인수인계/사진 문서 12건과 보고서 문서 6건이 추가되었다. 이 중 3건은 v2가 `PUBLISHED`인 공개 문서, 9건은 `WORKING`, 보고서 6건은 `IN_REVIEW` 상태다.
- `102-20260708143304` 실행에서는 FieldComment 24건이 추가되었고 검토 상태는 `ANALYZED` 8건, `REVIEWED` 8건, `SELECTED` 8건으로 남았다. 신호등식 입력도 `green`, `yellow`, `red`가 각각 8건씩 누적되었다.
- `102 사람형 스모크 작업순서 20260708143304` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 작업순서 항목은 `COMPLETED` 1건, `HOLD` 1건으로 남았다. 변경 이력은 보드 생성 1건, 항목 추가 2건, 상태 변경 3건, 보류 사유 변경 1건이다.
- `102 AI 근거 축적 보고서 20260708143304-01`부터 `-06`까지 6개 보고서 문서는 각각 `report_sources` 4건을 보존한다. 전체 source 구성은 FieldComment 12건, 문서 6건, 작업순서 이력 6건이다.
- `smoke-102-human-20260708-152335` 실행은 2026-07-08 15:23 KST에 시작된 사람형 다중 actor 스모크다. 실행 전 누적은 `documents` 1574건, `document_versions` 2308건, `field_comments` 1409건, 검토 준비 FieldComment 226건, `reports` 61건, `report_sources` 237건, `document_view_logs` 2090건, `activity_history` 68415건, `work_sequence_change_history` 580건이었다.
- 같은 실행에서는 오늘 날짜 기준 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달`, `AI 근거 축적 보고서` 문서가 추가되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 사진 문서는 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-06` 문서 `doc-ba4f93c8dd0d46a19a57b53cd2f211a8`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- 같은 실행에서는 FieldComment 6건이 추가되었고 검토 준비 상태는 `ANALYZED` 2건, `REVIEWED` 2건, `SELECTED` 2건이다. 신호등식 입력은 `green` 3건, `yellow` 3건으로 남았다.
- `102 사람형 스모크 작업순서 20260708-152335` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 실행 전후 `work_sequence_change_history`가 580건에서 582건으로 증가했다.
- `smoke-102-human-20260708-152335 AI 근거 축적 보고서` 문서 `doc-e1500f91f8284e03a31c3e2f3c3e96d0`는 `report_sources` 9건을 보존한다.
- 2026-07-08 15:25 KST 기준 누적 테이블 수는 `documents` 1578건, `document_versions` 2315건, `field_comments` 1415건, `field_comment_attachments` 109건, `report_sources` 246건, `notifications` 1557건, `server_sync_queue` 771건, `work_sequence_boards` 116건, `work_sequence_items` 232건, `work_sequence_change_history` 582건, `work_sequence_notification_candidates` 237건이다.
- 2026-07-08 15:25 KST 기준 전체 FieldComment 상태는 `NEW` 1181건, `ANALYZED` 78건, `REVIEWED` 77건, `SELECTED` 77건, `EXCLUDED` 1건, `ARCHIVED` 1건이다. 신호등식 입력 누적은 `green` 302건, `yellow` 162건, `red` 70건이다.

## 2026-07-09 서버 동기화 스모크 기록

2026-07-09 KST에 FastAPI 서버를 `http://127.0.0.1:5184`로 실행한 상태에서 WPF 스모크 테스트를 실행했다. 스모크는 오늘 날짜 인수인계/사진 등록, 과거 날짜 기존 사진 문서 버전 증가, 문서 최초 등록 이후 버전/공개/상태/FieldComment/첨부/접근 로그/보고서 큐 순서 재시도, 서버 ID 매핑 복구, 보고서 중복 재전송 방지를 검증했다.

- 서버 연결 재시도 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 284건이다.
- 실패 큐는 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 20건으로 분류된다. 서버 URL 미설정 실패는 서버 연결 재시도 후 남아 있지 않다.
- `server_id_mappings`는 648건이며 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다.
- 누적 테이블 수는 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `notifications` 1576건, `server_sync_queue` 804건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `work_sequence_notification_candidates` 239건이다.

## 2026-07-09 사람형 AI 근거 스모크 기록

2026-07-09 08:55 KST에 `smoke-102-human-20260709-085509` 사람형 다중 actor 스모크를 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-085509` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-085509.out.log`와 `.err.log`에 남겼다.

- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 성공 이력을 `activity_history`에 남겼다.
- 실행 전 누적은 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `notifications` 1576건, `server_sync_queue` 804건이었다.
- 실행 후 누적은 `documents` 1619건, `document_versions` 2366건, `field_comments` 1461건, `field_comment_attachments` 114건, `report_sources` 278건, `document_view_logs` 2156건, `activity_history` 78943건, `work_sequence_boards` 118건, `work_sequence_items` 238건, `work_sequence_change_history` 592건, `notifications` 1586건, `server_sync_queue` 854건이다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 5건, 사진 5건이 되었다. 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 신호등식 기록은 `green` 8건, `yellow` 8건, `red` 8건으로 남겼다.
- `102 사람형 스모크 작업순서 20260709-085509` 보드 1건과 작업 항목 4건을 추가했다. 작업순서 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-7485b983de164d9b9aeb56a8385ee7dd`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- FastAPI pytest는 `services/api`에서 51개 테스트를 실행해 51개 모두 통과했다. 이 실행 환경에는 `dotnet` 명령이 없어 WPF C# 스모크 테스트는 실행하지 못했다.

## 2026-07-09 사람형 AI 근거 스모크 추가 기록

2026-07-09 09:41 KST에 `smoke-102-human-20260709-094127` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-094127` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-094127.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 166건, `documents` 1619건, `document_versions` 2366건, `field_comments` 1461건, `field_comment_attachments` 114건, `report_sources` 278건, `document_view_logs` 2156건, `activity_history` 78943건, `work_sequence_boards` 118건, `work_sequence_items` 238건, `work_sequence_change_history` 592건, `notifications` 1586건, `server_sync_queue` 854건이었다.
- 실행 후 누적은 `user_accounts` 174건, `documents` 1629건, `document_versions` 2377건, `field_comments` 1485건, `field_comment_attachments` 117건, `report_sources` 296건, `document_view_logs` 2168건, `activity_history` 79026건, `work_sequence_boards` 119건, `work_sequence_items` 242건, `work_sequence_change_history` 597건, `notifications` 1596건, `server_sync_queue` 904건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 9건, 사진 9건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 신호등식 기록은 `green` 8건, `yellow` 8건, `red` 8건으로 남겼다.
- `102 사람형 스모크 작업순서 20260709-094127` 보드 1건과 작업 항목 4건을 추가했다. 공통 SQLite에 직접 남은 항목 상태는 `TODO` 1건, `IN_PROGRESS` 1건, `HOLD` 1건, `COMPLETED` 1건이다. 단, 현재 FastAPI와 WPF 코드의 정식 작업순서 대기 상태는 `WAITING`이며 `TODO`는 새 API/화면에서 허용하는 상태가 아니다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-e95a9f4b10d347f588132370f663f3ae`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 2026-07-09 09:41 KST 실행 후 전체 FieldComment 상태는 `NEW` 1221건, `ANALYZED` 88건, `REVIEWED` 86건, `SELECTED` 86건, `EXCLUDED` 2건, `ARCHIVED` 2건이다. 신호등식 입력 누적은 `green` 323건, `yellow` 180건, `red` 87건이다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 284건, `PENDING` 100건이다. 실패 큐 분류는 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 10건, 구 FieldNote 첨부 큐 10건이다.

## 2026-07-09 사람형 AI 근거 스모크 11:34 기록

2026-07-09 11:34 KST에 `smoke-102-human-20260709-113417` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-113417` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-113417.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 184건, `documents` 1661건, `document_versions` 2416건, `field_comments` 1563건, `field_comment_attachments` 121건, `report_sources` 318건, `document_view_logs` 2229건, `activity_history` 79312건, `work_sequence_boards` 121건, `work_sequence_items` 248건, `work_sequence_change_history` 607건, `notifications` 1624건, `server_sync_queue` 963건이었다.
- 실행 후 누적은 `user_accounts` 192건, `documents` 1671건, `document_versions` 2427건, `field_comments` 1587건, `field_comment_attachments` 124건, `report_sources` 336건, `document_view_logs` 2241건, `activity_history` 79395건, `work_sequence_boards` 122건, `work_sequence_items` 252건, `work_sequence_change_history` 612건, `notifications` 1634건, `server_sync_queue` 1013건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 18건, 사진 18건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1294건, `ANALYZED` 97건, `REVIEWED` 95건, `SELECTED` 95건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 344건, `yellow` 198건, `red` 104건이다.
- `102 사람형 스모크 작업순서 20260709-113417` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-07` 문서 `doc-74cdbc614996469fb09542dcb50e10f5`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 200건이다.
- FastAPI pytest는 `services/api`에서 53개 테스트를 실행해 53개 모두 통과했다. 이 실행 환경에는 `dotnet` 명령이 없어 WPF C# 스모크 테스트는 실행하지 못했다.

## 2026-07-09 사람형 AI 근거 스모크 13:19 기록

2026-07-09 13:19 KST에 `smoke-102-human-20260709-131928` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-131928` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-131928.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 192건, `documents` 1671건, `document_versions` 2427건, `field_comments` 1587건, `field_comment_attachments` 124건, `report_sources` 336건, `document_view_logs` 2241건, `activity_history` 79395건, `work_sequence_boards` 122건, `work_sequence_items` 252건, `work_sequence_change_history` 612건, `notifications` 1634건, `server_sync_queue` 1013건이었다.
- 실행 후 누적은 `user_accounts` 200건, `documents` 1681건, `document_versions` 2438건, `field_comments` 1611건, `field_comment_attachments` 127건, `report_sources` 354건, `document_view_logs` 2253건, `activity_history` 79478건, `work_sequence_boards` 123건, `work_sequence_items` 256건, `work_sequence_change_history` 617건, `notifications` 1644건, `server_sync_queue` 1063건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 22건, 사진 22건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1306건, `ANALYZED` 101건, `REVIEWED` 99건, `SELECTED` 99건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 352건, `yellow` 206건, `red` 112건이다.
- `102 사람형 스모크 작업순서 20260709-131928` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-4fb6550f9d02455aacec9bd90fc9dd96`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 250건이다.
- 실행 로그의 마지막 결과는 `Smoke 102 human-like AI evidence run passed.`이며 `.err.log`는 비어 있다.

## 2026-07-09 사람형 AI 근거 스모크 14:28 기록

2026-07-09 14:28 KST에 `smoke-102-human-20260709-142853` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-142853` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-142853.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 200건, `documents` 1681건, `document_versions` 2438건, `field_comments` 1611건, `field_comment_attachments` 127건, `report_sources` 354건, `document_view_logs` 2253건, `activity_history` 79478건, `work_sequence_boards` 123건, `work_sequence_items` 256건, `work_sequence_change_history` 617건, `notifications` 1644건, `server_sync_queue` 1063건이었다.
- 실행 후 누적은 `user_accounts` 208건, `documents` 1691건, `document_versions` 2449건, `field_comments` 1635건, `field_comment_attachments` 130건, `report_sources` 372건, `document_view_logs` 2265건, `activity_history` 79561건, `work_sequence_boards` 124건, `work_sequence_items` 260건, `work_sequence_change_history` 622건, `notifications` 1654건, `server_sync_queue` 1113건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 26건, 사진 26건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1318건, `ANALYZED` 105건, `REVIEWED` 103건, `SELECTED` 103건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 360건, `yellow` 214건, `red` 120건이다.
- `102 사람형 스모크 작업순서 20260709-142853` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-687b7fd7ea144242be4345e5e7013d97`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 300건이다. `server_id_mappings`는 648건이고 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다.
- 구 FieldNote 잔존 데이터는 `field_notes` 345건, `field_note_attachments` 20건이며, 새 작업 대상이 아닌 보존 테스트 기록으로 유지한다.
- 실행 로그의 마지막 결과는 `Smoke 102 human-like AI evidence run passed.`이며 `.err.log`는 비어 있다.

## 2026-07-10 서버-WPF 동기화 큐 정리 기록

공통 SQLite `data/local/flownote.local.sqlite`의 큐와 매핑을 삭제 없이 점검했다. 실행 전 상태는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 300건이었다. 기존 실패 293건은 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 20건, 실제 서버/설정 오류 9건으로 분류했다. 실제 서버/설정 오류 9건은 현재 모두 서버 URL 미설정 사유다.

`PENDING` 300건은 모두 초기 로컬 큐의 `action = create` 형식이었다. 구성은 문서 60건, 문서 버전 6건, 문서 열람 로그 72건, FieldComment 144건, FieldComment 첨부 18건이다. 현재 서버 동기화 계약으로 임의 변환하지 않고 `FAILED`와 구 형식 별도 마이그레이션 보류 사유로 분류했다. 300행과 연결 로컬 데이터는 삭제하지 않았고 `attempt_count`는 전부 0을 유지했으며, `activity_history`에 `server_sync.legacy_queue_classified` 요약 이력을 추가했다.

정리 후 상태는 `SYNCED` 520건, `FAILED` 593건, `PENDING` 0건이다. `server_id_mappings`는 648건이고 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건을 유지했다. WPF 재시도 코드는 구 형식 `create` 큐와 선행 서버 ID가 없는 후행 큐를 서버 호출 및 시도 횟수 증가 전에 보류하도록 확인했다. 정식 재시도 순서는 문서 최초 등록, 버전, 공개, 상태, FieldComment, 검토 변경, 첨부, 접근 로그, 보고서다.

FastAPI 전체 pytest 55건이 모두 통과했다. WPF Core, 스모크, WPF 앱 빌드도 모두 경고·오류 0건을 확인했다. 스모크는 누적 사용자와 500행 목록 한도를 가정하던 검증을 전체 시드/전체 큐 기준으로 보강하고, 존재하지 않는 서버 operator/device ID를 보내던 AI 품질 입력을 정리한 뒤 로컬 FastAPI `http://127.0.0.1:5184`와 함께 최종 통과했다.

최종 통과 실행은 오늘 `2026-07-10` 사진과 인수인계 문서를 등록·조회했고, 기존 `인수인계/2026-07-01` 문서를 새 폴더나 문서 생성 없이 v1에서 v2로 증가시켰다. 서버 재시도와 성공 이력도 `activity_history`에 누적됐다. 반복 검증 실행까지 포함한 최종 큐는 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이며, 실패는 구 형식 create 300건, 선행 문서/근거 미동기화 229건, 선행 FieldComment 미동기화 20건, 로컬 파일 누락 20건, 구 FieldNote 20건이다. `server_id_mappings`는 767건이고 중복 그룹은 0건이다. 공통 SQLite `PRAGMA quick_check`는 `ok`, 외래 키 위반은 0건이었으며 기존 SQLite와 테스트 산출물은 그대로 보존했다.

## 2026-07-10 사람형 AI 근거 스모크 14:33 기록

2026-07-10 14:33 KST에 `smoke-101-human-20260710-143343` 사람형 다중 actor 스모크를 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke101/2026-07-10/smoke-101-human-20260710-143343` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-101-20260710-143343.out.log`와 `.err.log`에 남겼다.

- 직전 `smoke-101-human-20260710-143325` 시도는 문서 등록 SQL 매개변수 수 불일치로 중단되었다. 중단 전에 생성된 계정 8건, 로그인 이력 8건, 입력 파일 1건과 오류 로그는 삭제하지 않고 실패 재현 기록으로 보존했다.
- 정상 실행 전 누적은 `user_accounts` 221건, `documents` 1798건, `document_versions` 2586건, `field_comments` 1745건, `field_comment_attachments` 136건, `report_sources` 408건, `document_view_logs` 2463건, `activity_history` 122030건, `work_sequence_boards` 128건, `work_sequence_items` 268건, `work_sequence_change_history` 642건, `notifications` 1728건이었다.
- 정상 실행 후 누적은 `user_accounts` 229건, `documents` 1808건, `document_versions` 2597건, `field_comments` 1769건, `field_comment_attachments` 139건, `report_sources` 426건, `document_view_logs` 2487건, `activity_history` 122120건, `work_sequence_boards` 129건, `work_sequence_items` 272건, `work_sequence_change_history` 646건, `notifications` 1752건이다.
- 정상 실행에서 승인 단말 로그인 계정 8건, 문서 10건, 문서 버전 11건, FieldComment 24건, 첨부 3건, 보고서 근거 18건, 문서 열람 로그 24건, 활동 이력 90건, 작업순서 보드 1건과 항목 4건, 작업순서 변경 이력 4건, FieldComment 알림 24건이 증가했다.
- 오늘 날짜 `2026-07-10` 기준 인수인계 문서 4건과 사진 문서 4건을 등록·조회했다. 정상 실행 후 오늘 날짜 폴더의 인수인계와 사진 문서는 각각 8건이다. 인수인계 2건은 `PUBLISHED`, 나머지 인수인계 2건과 사진 4건은 `WORKING` 상태로 남겼다.
- FieldComment 상태는 `NEW`, `ANALYZED`, `REVIEWED`, `SELECTED`가 각각 6건이며, 신호등식 입력은 `green` 12건, `yellow` 9건, `red` 3건이다. 24건의 문서 열람 로그는 모두 `window_closed` 종료 사유를 보존한다.
- `101 사람형 스모크 작업순서 20260710-143343` 보드는 `LINE-A`, `2026-07-10`, `ACTIVE` 기준으로 생성했다. 항목 상태는 `WAITING`, `IN_PROGRESS`, `HOLD`, `COMPLETED`가 각각 1건이며 변경 이력은 항목 추가 4건이다.
- `101 AI 근거 축적 보고서 20260710-143343-01`, `-02` 문서를 `Report`, `IN_REVIEW` 상태로 만들었다. 각 보고서는 FieldComment 4건, 문서 3건, 작업순서 이력 2건으로 source 9건을 보존하며, 전체 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이다.
- 과거 날짜 무작위 검증은 기존 `사진/2026-07-07` 문서 `doc-0b1c18ed52b345bd98e331aebb50fefb`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 이 실행은 서버 동기화 큐를 추가하거나 재시도하지 않았다. 실행 후 큐는 기존과 같은 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이고 `server_id_mappings`는 767건이다.
- 공통 SQLite `PRAGMA quick_check`는 `ok`, 외래 키 위반은 0건이다. 정상 실행 결과 JSON은 `.out.log`에 남았고 `.err.log`는 비어 있다.

## 산출물 보존과 Git 점검

테스트가 생성한 DB, 로그, 입력 파일, 출력 파일은 보존한다. 단, Git에는 다음 원칙을 적용한다.

- SQLite와 WAL/SHM 보조 파일은 테스트/개발 검증 기록으로 로컬에 보존하되 경로와 관계없이 Git으로 추적하거나 커밋하지 않는다.
- PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/`, `services/api/storage/`, `bin/`, `obj/` 하위 파일은 Git 제외 대상이다.
- 새 테스트 산출물 경로가 생기면 삭제하지 말고 먼저 `.gitignore` 제외 규칙을 추가한다.
- 이미 Git에 잡힌 테스트 산출물은 파일을 삭제하지 말고 `git rm --cached`로 추적만 해제한다.

표준 스크립트의 Git 점검은 금지 패턴이 `git status`나 추적 파일 목록에 잡히면 실패한다. 실패 메시지는 보존 대상 파일을 지우라는 뜻이 아니라 `.gitignore` 보강 또는 추적 해제가 필요하다는 뜻이다.

## WPF MSI 패키징 검증

WPF MSI는 Windows 배포 준비 PC에서 다음 순서로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.files.txt
git status --short --untracked-files=all
```

`.files.txt`에는 앱 실행 파일, `.deps.json`, `.runtimeconfig.json`, 앱 DLL, 의존 DLL, 네이티브 DLL만 있어야 한다. 다음 항목이 포함되면 `package-wpf-msi.ps1`가 실패해야 한다.

- 로컬 SQLite, WAL, SHM, DB 파일
- `Data\`, `Files\`, `storage\`, `logs\` 계열 경로
- `test`, `smoke`, `sample-registration`, `customer`가 들어간 파일
- PDF, Office, HWP, DWG, 이미지, 압축 파일, TXT/MD 같은 고객 파일 또는 테스트 산출물

self-contained 패키지가 필요한 PC는 별도 MSI로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.files.txt
```

설치 후에는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고 앱을 실행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

검증 기준은 다음과 같다.

- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에는 실행 파일과 의존 파일만 있다.
- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App` 아래에는 `flownote.local.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, `Files\`가 생기지 않는다.
- `C:\FlowNote\LocalData\flownote.local.sqlite`와 `C:\FlowNote\LocalData\Files`가 생성된다.
- .NET Windows Desktop Runtime이 없는 PC에서는 framework-dependent MSI 실행 실패를 기록하고, self-contained MSI 실행 결과를 별도로 기록한다.
- WebView2 Runtime이 없는 PC에서는 문서 뷰어 실패 안내가 표시되는지 확인하고, WebView2 Runtime 설치 후 같은 문서 열람이 성공하는지 기록한다.
- `git status`에서 `artifacts\wpf-msi`, publish 산출물, MSI 파일, `.wixpdb`가 추적 대상으로 잡히지 않는다.

설치 후 자동 점검은 다음 스크립트로 수행한다. 이 스크립트는 MSI 산출물 목록의 금지 패턴, 설치 폴더의 로컬 DB/`Files` 혼입 여부, `FLOWNOTE_LOCAL_DATA_DIR` 기준 로컬 데이터 생성 여부, .NET Windows Desktop Runtime, WebView2 Runtime, 선택적 서명 검증을 확인한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"
```

framework-dependent MSI 실패 양상은 .NET Windows Desktop Runtime이 없는 Windows PC에서 다음 기준으로 남긴다.

- MSI 설치 자체가 성공하더라도 앱 실행 시 .NET Desktop Runtime 요구 오류가 표시되는지 기록한다.
- `dotnet --list-runtimes` 결과에 `Microsoft.WindowsDesktop.App 10.`이 없는 상태임을 기록한다.
- 같은 PC에서 self-contained MSI 설치 후 앱 실행 성공 여부를 별도로 기록한다.

WebView2 Runtime 유무 검증은 같은 PDF 문서로 두 번 수행한다.

- WebView2 Runtime 미설치 또는 제거 상태에서 문서를 열어 `문서 뷰어를 시작할 수 없습니다.` 안내가 표시되는지 확인한다.
- Microsoft Edge WebView2 Runtime 설치 후 같은 문서가 WebView2 PDF 뷰어로 표시되고 저장/인쇄/외부 창 열기 차단이 유지되는지 확인한다.

코드 서명 검증은 서명 인증서가 준비된 배포 준비 PC에서 수행한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

서명 인증서가 준비된 PC에서는 같은 설치 후 점검에 `-CheckSignature`를 추가한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -CheckSignature
```

## Windows MSI 실기 검증 기록

2026-07-08 KST 기준 현재 이 저장소 작업 환경은 macOS이며 `pwsh`, `dotnet`, `wix`, `msiexec`, `signtool`이 없어 Windows MSI 실기 검증을 완료할 수 없다. 아래 기록은 Windows 배포 준비 PC와 설치 대상 PC에서 채운 뒤 운영 배포 확정 근거로 사용한다. 실제 실행 전까지 MSI 운영 배포 상태는 `대기`다.

### 실행 명령

배포 준비 PC에서 기본 MSI와 self-contained MSI를 모두 생성한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
```

설치 대상 PC에서는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고, 앱을 한 번 실행해 로컬 DB와 `Files\` 생성까지 확인한 뒤 자동 점검을 수행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
$env:FLOWNOTE_LOCAL_DATA_DIR = "C:\FlowNote\LocalData"
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

msiexec /x .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

git status --short --untracked-files=all
```

서명 인증서가 준비된 경우에는 `-Sign`으로 패키징하고 EXE와 MSI를 모두 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

### 결과 표

| 항목 | 상태 | 기록할 증거 |
| --- | --- | --- |
| 기본 MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| self-contained MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| 기본 MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| self-contained MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| 설치 폴더에 실행 파일과 의존 파일만 존재 | 대기 | `verify-wpf-msi-install.ps1` 출력 |
| 로컬 DB와 `Files\`가 `C:\FlowNote\LocalData`에만 생성 | 대기 | `verify-wpf-msi-install.ps1` 출력, 실제 경로 |
| .NET Windows Desktop Runtime 없는 PC의 framework-dependent 실행 실패 양상 | 대기 | `dotnet --list-runtimes` 결과, 오류 메시지 또는 스크린샷 설명 |
| 같은 PC의 self-contained MSI 실행 결과 | 대기 | 실행 성공/실패, 오류 메시지 |
| WebView2 Runtime 미설치 상태 PDF 열람 안내 | 대기 | 안내 문구, PC명, Windows 버전 |
| WebView2 Runtime 설치 후 같은 PDF 정상 열람 | 대기 | WebView2 버전, 열람 결과, 다운로드/인쇄/외부 창 차단 유지 여부 |
| 코드 서명 검증 | 선택 | 인증서 주체 또는 지문, `signtool verify /pa` 결과 |
| Git 산출물 제외 확인 | 대기 | `git status --short --untracked-files=all` 출력 |

### 배포 판정

다음 조건을 모두 만족하면 Windows WPF MSI 운영 배포 조건을 충족한 것으로 본다.

- 기본 MSI와 self-contained MSI가 모두 생성된다.
- MSI 포함 파일 목록에 SQLite, WAL/SHM, `Data\Files`, `storage`, `logs`, 테스트/샘플/고객 파일이 없다.
- 설치 폴더에는 실행 파일과 의존 파일만 있고, 로컬 DB와 `Files\`는 지정한 LocalData 경로에만 생성된다.
- framework-dependent MSI는 .NET Windows Desktop Runtime 필요 조건을 명확히 드러내고, 런타임 없는 PC에는 self-contained MSI를 배포 기준으로 선택할 수 있다.
- WebView2 Runtime 유무에 따른 안내와 설치 후 정상 PDF 열람이 확인된다.
- 서명 인증서가 준비된 배포에서는 EXE와 MSI가 모두 `signtool verify /pa`를 통과한다.
- Git 상태에 빌드/배포 산출물과 테스트 산출물이 추적 대상으로 잡히지 않는다.

## 현재 비Windows 환경 확인

2026-07-08 KST 기준 현재 macOS 개발 환경에서는 `wix`, `pwsh`, `dotnet`, `msiexec`, `signtool`이 없어 실제 MSI 생성과 설치 검증은 수행하지 못했다. 대신 다음 항목을 확인했다.

- `dotnet publish` framework-dependent: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet publish` self-contained: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet build` WPF 앱: 성공, 경고 0개
- `dotnet build` WPF 스모크 테스트: 성공, NuGet 취약성 데이터 조회 경고 2개
- `artifacts/wpf-msi` 하위 파일명 기준 금지 패턴 검사: 0건

위 항목은 이전 비Windows 사전 점검 기록이며, 운영 배포 확정 근거로는 부족하다. 남은 실기 검증은 Windows 배포 준비 PC 또는 현장 검증 PC에서 `package-wpf-msi.ps1` 기본 MSI와 `-SelfContained` MSI를 실제 생성하고, 위 설치 후 점검 스크립트와 수동 WebView2 열람 확인으로 완료한다.

## 2026-07-09 Windows MSI 실기 검증 시도 기록

2026-07-09 KST 기준 현재 작업 환경은 macOS `Darwin arm64`이며 `pwsh`, `dotnet`, `wix`, `msiexec`, `signtool` 명령이 모두 PATH에 없다. 따라서 이 환경에서는 `scripts/package-wpf-msi.ps1`, `scripts/verify-wpf-msi-install.ps1`, Windows 설치, .NET Windows Desktop Runtime 미설치 PC 실행, WebView2 Runtime 미설치/설치 후 PDF 열람, `signtool verify /pa`를 수행할 수 없다.

현재 로컬 `artifacts/wpf-msi`에는 2026-07-03 07:05 KST 생성 시각의 `FlowNote.Windows.App-0.1.0-win-x64.msi`, `FlowNote.Windows.App-0.1.0-win-x64.wixpdb`, `FlowNote.Windows.App.wxs`가 남아 있다. 이 산출물은 `.gitignore`의 `artifacts/`, `*.msi`, `*.wixpdb` 규칙으로 Git 추적 대상에서 제외된다. 다만 이 산출물에는 최신 스크립트가 생성하는 `.files.txt` manifest가 없고, self-contained MSI 파일도 없어 현재 완료 기준의 증거로 사용할 수 없다.

이번 환경 점검에서 확인한 사항은 다음과 같다.

- Windows 실기 검증 상태: `미완료`
- 배포 판정: `대기`
- 기본 MSI 기존 로컬 파일 SHA256: `d529b24993d3999d4b5224e107309995b2af701ec6d95476abb6b59d43f5d7fb`
- 기존 로컬 `wixpdb` SHA256: `c82b07e3f98d9d7ff95c7231135356d6ac3d840a991338a666f0e2c39406cc49`
- 기존 로컬 `.wxs` SHA256: `f4b2f28b0d5591b51fb96b05221811a18d2c22a7ba530b68e3422f1afc908d22`
- `artifacts/wpf-msi` 하위 배포 산출물은 현재 Git 추적 대상이 아니다.

Windows 배포 준비 PC에서 새로 검증할 때는 위 기존 로컬 산출물을 근거로 삼지 말고, 같은 작업일에 기본 MSI와 self-contained MSI를 다시 생성한 뒤 `Get-FileHash`, `.files.txt`, `verify-wpf-msi-install.ps1`, Runtime/WebView2 조건별 앱 실행 결과를 이 문서의 Windows MSI 실기 검증 기록 표에 반영한다.

## 2026-07-10 승인 단말 관리 API와 WPF 운영 화면 검증

FastAPI 승인 단말 관리 구현 후 `services/api/.venv/bin/python -m pytest -q`를 실행해 58건 전체 통과를 확인했다. 단말 전용 테스트는 다음 항목을 검증한다.

- `admin`, `system-admin`의 목록, 등록, 상세, 정보 변경, 상태 변경, 마지막 접속 조회 허용
- `viewer`의 단말 관리 API 403 거부
- 등록·정보 변경·비활성화와 교체 시 `activity_history`의 `terminal_device.*` 이벤트, actor, 변경 사유 기록
- 비활성화·폐기·교체 시 해당 단말의 기존 활성 인증 세션 `REVOKED` 처리
- 교체 시 기존 단말 `RETIRED`, 새 단말 `ACTIVE`, `replaced_device_id` 연결 및 폐기 단말 재활성화 409 거부
- 미등록, `INACTIVE`, `RETIRED` Android 단말 로그인 403
- 등록된 `ACTIVE` 단말의 반복 로그인 200, 로그인별 `auth_sessions.device_id` 2건 생성, 매 로그인 `last_seen_at` 유지·갱신

WPF는 `dotnet build apps/windows/src/FlowNote.Windows.App/FlowNote.Windows.App.csproj --no-restore -p:EnableWindowsTargeting=true`로 빌드했고 경고 0개, 오류 0개로 통과했다. 첫 실행은 `EnableWindowsTargeting` 미지정으로 `NETSDK1100`이 발생했으며, Windows 대상 빌드 속성을 명시한 재실행 결과를 통과 근거로 사용한다.

WPF 운영 화면의 소스·빌드 기준 확인 결과는 다음과 같다.

| 확인 항목 | 결과 | 근거 |
| --- | --- | --- |
| 관리자 메뉴 노출 | 통과 | `admin`, `system-admin`의 `CanManageUsers` 정책으로 `승인 단말` 버튼 표시 |
| 목록 필드 | 통과 | 단말명, device_id, 위치, 상태, 마지막 접속, 등록자, 변경자 컬럼 포함 |
| 운영 동작 연결 | 통과 | 등록, 정보 저장, 상태 적용, 교체 등록이 서버 전용 클라이언트에 연결 |
| 로컬 로그인 오등록 방지 | 통과 | 서버 URL·Bearer token이 없으면 서버 로그인 필요 안내만 표시 |
| Windows 실제 창 조작 | 대기 | 자동화 검증 범위에는 포함되지 않아 실기 확인 필요 |

Windows 실기 수동 검증에서는 서버 로그인 `admin`으로 `승인 단말` 창을 열고 신규 등록 → 목록/상세/등록자 확인 → Android 로그인 후 마지막 접속 새로고침 → 비활성화 후 로그인 403 → 교체 등록 후 기존 단말 폐기·새 단말 사용 상태를 순서대로 확인한다. 이 실기 결과는 Windows 검증 PC에서 실행한 시각, 사용자 ID, 대상 테스트 device_id와 함께 이 절에 추가한다. 기존 SQLite와 테스트 산출물은 삭제하지 않았다.

## 2026-07-10 삭제 문서의 AI 검색 근거 제외 검증

현재 코드와 문서의 정합성을 확인하면서 `services/api/.venv/bin/python -m pytest -q`를 실행했고 FastAPI 전체 58건이 5.13초에 통과했다. AI 검색 근거 테스트는 다음 조건을 함께 검증한다.

- 삭제되지 않은 공개 문서 버전은 `PUBLISHED_DOCUMENT_VERSION` 후보에 포함된다.
- `status = DELETED`이고 `deleted_at`이 설정된 문서는 직접 문서 후보에 포함되지 않는다.
- 삭제 문서를 원천으로 가리키는 `REPORT_SOURCE`는 보고서가 승인 상태로 남아 있어도 후보에 포함되지 않는다.
- 삭제 문서 원천과 실제로 존재하지 않는 원천은 `report_source_missing_origin` 제외 사유에 집계된다.
- 후보 재생성 응답과 품질 응답의 source별 후보 수, 제외 사유, 운영 안내가 일치한다.

이번 문서 정합성 검증에서는 기존 SQLite와 테스트 산출물을 삭제하지 않았다.

## 2026-07-10 Android 현장 단말 빌드·outbox·채널/인수인계 검증

Android Studio 내장 JBR 21과 Android SDK를 사용해 `apps/android`에서 `./gradlew testDebugUnitTest`와 `./gradlew assembleDebug`를 실행했고 모두 통과했다. JDK 21이 Java 8 source/target 지원 폐기 예정 경고를 출력했지만 테스트와 debug APK 생성에는 오류가 없었다. 생성 APK와 Gradle 로그는 `apps/android/app/build/` 아래에 보존되며 `.gitignore`의 `build/`, `*.apk` 규칙으로 Git에서 제외된다.

Android API 37.1 `Medium_Phone` AVD에 debug APK를 설치하고 로컬 FastAPI `http://10.0.2.2:5185` 및 보존 DB `services/api/data/flownote.android-verification.sqlite3`와 연결했다. 실행 식별자는 `20260710180354`이며, 승인 단말 `android-emulator-20260710180354` 로그인은 200, 미등록 단말과 `android-inactive-20260710180354` 로그인은 각각 403이었다. 비활성 단말은 앱 화면에서도 403을 확인했으며, 서버 영문 오류 본문이 노출되던 문제를 한글 현장 안내로 변환한 뒤 `요청이 거부되었습니다. 승인 단말 상태와 사용자 권한을 확인하세요. (HTTP 403)` 표시를 재확인했다.

outbox 실기 검증은 공개 문서 `doc_5fd2fb924dfd448aa48199bf2b2b73de`와 Android 파일 선택기로 고른 PNG 사진을 사용했다. 서버 포트를 연결 불가능한 값으로 바꾼 첫 전송에서는 outbox row가 `FAILED`, `attempt_count = 1`, `server_id = NULL`로 남고 사진 URI와 오류가 보존되었다. 15초 backoff 이후 정상 서버 주소로 재전송하자 같은 row가 `SYNCED`, `attempt_count = 2`, `server_id = comment_a65715b28fb749df932c8bf803233a8f`로 전환됐다. 서버 DB에는 다음 연결이 남았다.

- FieldComment: `comment_a65715b28fb749df932c8bf803233a8f`, `input_mode = signal`, `signal_level = yellow`, 승인 단말 ID와 Android idempotency key 기록
- 첨부: `att_2e804d51c3d949278118eecb3198d84c`, 위 comment ID 참조, `attachment_type = photo`, 파일 크기 8,460 bytes
- 보존 파일: `services/api/storage/android-verification/field-comments/comment_a65715b28fb749df932c8bf803233a8f/attachments/0e7916e07cf8416d8996df2aa4797362_field-photo.jpg`
- 실패/성공 outbox 스냅샷: `services/api/data/test-artifacts/android-verification-2026-07-10/20260710180354/`

채널 `channel_14090d18809d4668913f99fef315e743`의 Android 알림을 앱에서 읽음 처리한 뒤 `notification_channel_members.last_read_message_id`가 `chmsg_ad1b7d0deb0a47eea59f200f43bab271`로 저장된 것을 확인했다. 인수인계 `handover_97d53669291f4ec3a7d15471efeeafc3`의 receipt `hreceipt_e7e3ce69ab294532bae8376a6b9a330e`는 앱 버튼으로 `READ` → `ACKNOWLEDGED` → `FOLLOW_UP_REQUIRED`를 순서대로 변경했고, 각 단계 직후 서버 DB 상태를 대조했다. 최종 row에는 `read_at`, `acknowledged_at`, `follow_up_required_at`, `updated_by`가 모두 남았다.

재시도 단위 테스트는 최대 자동 시도 12회와 `15초 → 30초 → 60초 → ... → 최대 15분` 지수 backoff 값을 명시적으로 검증하도록 보강했다. 한글 오류 안내 테스트를 포함한 Android 단위 테스트와 debug 빌드를 다시 통과했으며, FastAPI 관련 회귀 테스트 `test_auth_api.py`, `test_terminal_devices_api.py`, `test_field_comments_api.py`, `test_channels_api.py`는 25건 모두 통과했다.

이번 결과는 에뮬레이터와 로컬 HTTP 서버를 사용한 개발 실기 검증이다. 운영 승인된 실제 태블릿 또는 러기드 단말의 카메라, 사내 Wi-Fi, HTTPS 인증서, MDM/운영 서명 APK 검증은 아직 대기 상태이며 운영 배포 확정 근거와 분리한다. SQLite, 업로드 사진, outbox 스냅샷, APK와 빌드 로그는 삭제하지 않았고 모두 Git 제외 경로에 보존했다.
