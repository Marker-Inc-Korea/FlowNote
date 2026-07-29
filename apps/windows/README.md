# Windows App

`apps/windows/`는 FlowNote Windows WPF 클라이언트 영역이다. 현장/관리자 PC에 설치해 사용하는 네이티브 앱을 기준으로 한다.

현재 프로젝트는 WPF UI `net10.0-windows`, Core와 스모크 테스트 `net10.0`을 대상으로 한다. 현재 기능 목록은 `FlowNote.Windows.App`, `FlowNote.Windows.Core`, `FlowNote.Windows.SmokeTests` 코드에 실제 연결된 범위만 포함한다.

이 문서는 2026-07-28 현재 코드 기준이다. 운영 설치나 현장 검증이 남은 내용은 현재 구현과 분리해 후속 제품 방향에만 둔다.

## 현재 구현

- 로그인 화면과 메인 탐색기 화면. 로그인 역할에 맞춘 첫 업무 3개와 기존 업무 창 바로 가기, 파일명·제목·태그·사용자·최근 코멘트 검색, 문서 상태 필터, 권한 문의 안내, 동기화 미완료 건수·로컬 보존·다음 조치 표시를 포함한다.
- 로컬 SQLite 초기화와 기본 계정/그룹/폴더 시드
- 사용자 관리: 서버 로그인 시 서버 계정 생성, 이름/역할/상태 변경, 임시 비밀번호 재설정, 활성 세션 조회/폐기. 서버 미연결 로컬 로그인 시 로컬 계정 관리
- 승인 단말 관리: 서버 단말 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체
- 시작 실패 안내: WebView2 Runtime 누락과 서버 주소·인증서·연결 오류를 `누락 항목`, `보존된 데이터`, `담당자`, `다음 조치`로 나누어 표시하고 로컬 계정으로 자동 전환하지 않음
- 폴더 트리와 문서 목록. 기본 폴더는 `문서`, `인수인계`, `작업순서`, `사진`이다.
- 새 폴더 생성
- 샘플 문서 등록, 파일 업로드, Drag & Drop 등록
- 문서 상태 변경과 공개 버전 지정
- 문서 태그 저장과 표시
- TXT, PDF, XLSX, 이미지 미리보기
- 문서 열람 시작/종료 로그
- viewer 수동 닫힘과 다운로드 차단 로그
- 허용 role의 서버 1회성 controlled copy 저장과 SHA-256 검증, 비허용 role의 기존 차단 안내·이력
- FieldComment 작성과 첨부 저장, 원천 불변 검증, 단계형 관리자 검토, 담당자·기한 지정, 다중 선택 일괄 변경, 감사·품질 작업함
- 알림, 전체 이력
- 관리자 파일 감시 후보 처리
- 작업순서 관리자 화면과 TV 화면. 서버 snapshot·`board_revision`을 권위 원천으로 사용하고 mutation key와 `baseBoardRevision`으로 직접 변경하며, 미연결/조회 실패 시 로컬 row는 읽기 캐시·초안으로만 표시하고 모든 확정 변경을 차단
- 보고서 초안 생성 보조, 문서 저장, 서버 보고서 저장 시도. 재시도 큐는 source 집합 hash를 고정하고 서버 응답의 report revision·내용 hash·source 집합 hash를 로컬 문서에 보존
- 채널함: 서버 내 채널, 채널 메시지/알림, 인수인계 조회, 읽음/수신 확인, 원천 링크 복사, 후속 FieldComment 생성. 같은 인수인계·작성자·내용은 안정된 요청 식별값을 재사용하고 채널 알림 실패를 부분 성공으로 구분해 원천 코멘트 중복을 막는다.
- 채널 관리: 서버 채널 생성, 멤버 추가/제외
- 인수인계 확인 현황: 수신자별 receipt 상태 변경, 후속 FieldComment 생성과 원천/수신 확인 보존·다음 행동 안내
- FastAPI 서버 인증과 승인 단말/문서/controlled copy/FieldComment/첨부/접근 로그/보고서/작업순서/채널·인수인계/AI 검색 근거·회귀 평가/외부 AI 운영 API 클라이언트
- AI 근거 후보 운영 점검: 서버 후보 재생성, 품질 지표, 제외 사유, 후보 목록, 원천 추적값 복사
- `AI 정답셋`: 후보 포함 근거와 수동 제외 원천으로 사례 구성, 독립 2인 사례 승인, 불변 dataset version 작성·검토·2단계 승인·대체·폐기, 평가 run 실행·이전 run 비교, 실제 익명 현장 24칸 독립 표본 검토와 불일치 제3 합의
- `system-admin` 전용 `AI 운영` 화면: 전송 승인 생성·철회, 프롬프트 검토·승인·활성화·폐기, 전역/현재 현장 kill switch와 호출·비용·보존 정책, 정제 감사 조회/CSV 내보내기, 만료 보존 일괄 실행, 고객/현장 질의 상세, 단일 즉시 만료와 legal hold 설정·해제·감사 read-back
- 서버 동기화 큐: 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, 문서 태그, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장. 공개·상태·태그 mutation receipt와 read-back, FieldComment 검토 base revision·mutation key, 첨부 부모·파일 SHA-256, 보고서 source 집합 hash, 문서 버전·첨부 idempotency key 전달과 큐 깊이·최장 대기·최근 처리량·실패 분포·row별 운영 상태 표시 포함
- 서버 복구 경계 보호: sync manifest의 instance/epoch/API contract와 알림 cursor를 URL별 binding에 저장하고, URL·instance·epoch 변경, cursor 역행 또는 `partial_restore`·`old_database_new_files`·`missing_file`·`wrong_server_epoch` 복구 장애 신호 시 자동 전송과 polling 중지
- 이력 창 `서버 재결합`: 차단 원인, 보존된 원천, 승인 전 금지 행동, 다음 단계를 분리해 표시하고 전체 큐 inventory의 `CONFIRMED`/`ABSENT`/`DIVERGED` 판정과 `REBOUND`/`REQUEUE`/`CONFLICT` 제안 검토, 관리자 사유 승인 뒤 mapping·큐·binding 적용과 cursor 0 재추적
- 보존 동기화 실패 전환 CLI: FAILED 큐를 읽기 전용 dry-run으로 분류하고, plan hash와 row별 운영자 승인을 받은 구 `create`/FieldNote 항목만 현재 action의 별도 큐로 무손실 전환
- 동기화 backlog 읽기 전용 감사: 큐 운영 상태·담당자·처리 기한·자동 재시도 한도·수동 종결 기준과 DB 전후 SHA-256, 무결성, 중복, 고아 mapping/source를 JSON으로 보존

WPF에는 `/api/v1/ai/queries`를 호출하는 실제 외부 AI 질의 실행 화면이나 운영 provider client가 없다. AI 화면은 외부 호출 없는 근거 후보 운영 점검, `AI 정답셋`, `system-admin` 전용 운영 제어 화면으로 분리되어 있다.

AI 검색 근거 후보는 현재 FastAPI 서버 API, WPF 서버 클라이언트, `AI 근거 후보 운영 점검` 화면에 구현되어 있다. 이 화면은 `/api/v1/ai-search/candidates/rebuild`, `/api/v1/ai-search/quality`, `/api/v1/ai-search/candidates`, `/api/v1/ai-search/readiness`를 호출해 외부 AI 호출 전 데이터 품질, 원천 추적 가능성, 서버 scope별 실제 현장/스모크 준비도를 확인한다. `AI 정답셋`의 `사례·원천 구성` 창은 후보를 포함 근거로 선택하고 실제 source ID·선택적 version ID·제외 사유·설명을 제외 근거로 입력한다. 첫 등록 사례는 비활성으로 남고 다른 사용자가 2차 승인해야 활성화된다. 승인 사례는 dataset version으로 묶어 작성자·검토자·두 승인자를 분리하고, 승인 snapshot에 결합한 평가 run을 실행·비교한다. 합성/시험 회귀와 실제 현장 준비도는 별도 계열로 유지한다.

실제 익명 현장 dataset의 24칸 독립 표본 검토와 불일치 제3 합의는 FastAPI, 서버 DB와 WPF에 구현되어 있다. `AI 정답셋`에서 승인된 `FIELD_READINESS` dataset과 그 dataset을 통과한 평가 run을 함께 선택하면 `24칸 독립 검토`가 활성화된다. 화면은 서버가 고정한 표본 계획과 기대·실제·제외 근거 trace를 보여주며, 첫 판정은 두 번째 제출 전까지 숨긴다. 두 판정이 다르면 앞선 두 사람과 다른 제3 사용자에게 불일치 case만 열어 합의를 받는다.

`AI 운영` 화면은 `/api/v1/ai-operations`를 통해 승인, 프롬프트, 전역/현장 운영 정책과 질의 감사 메타데이터를 조회·변경한다. provider 자격증명·질의 원문·응답 원문은 표시하지 않으며 provider 자격증명은 설정 여부만 표시한다. 감사 CSV는 현장 정책에서 내보내기를 허용한 경우에만 저장할 수 있다. 서버는 설정된 주기로 만료 보존을 자동 처리하며, 화면의 실행 버튼은 다음 주기를 기다리지 않고 같은 일괄 처리를 즉시 요청한다. 감사·보존 탭은 선택 질의의 고객/현장, hold 상태, 두 보존 예정 시각, 전체 hold/감사 이력을 read-back한다. 단일 만료와 hold 설정·해제는 사유·근거 번호, 이중 확인, 최신 상태 태그와 안정 operation key를 사용하며 응답 유실은 같은 요청으로 한 번 재시도한다. 성공 뒤 query/hold/audit를 서버에서 다시 읽기 전에는 완료로 표시하지 않는다.

`작업내역` 화면의 서버 동기화 큐는 완료, 보존 구 형식, 선행 조건 대기, 수동 조치 필요, 재시도 가능을 별도 운영 상태로 표시한다. 요약에는 `SYNCED`가 아닌 큐 깊이, 최장 대기 시간, 최근 1시간 처리량과 실패 분포가 나온다. 인증 만료나 서버 연결 실패·시간 초과는 현재 재시도 묶음을 중단하며, 개별 항목의 검증·파일 오류는 해당 항목을 실패로 남기고 다음 독립 항목을 계속 처리한다. 모든 경우 로컬 원천과 큐는 유지한다.

## 후속 제품 방향

- 채널/인수인계 화면의 운영 UX 고도화와 현장별 권한 세분화
- 인수인계 등록 작성 화면과 템플릿 보강
- 채널 메시지와 인수인계를 문서, FieldComment, 작업순서, 작업내역, 보고서 근거로 더 쉽게 연결하는 운영 흐름
- 백그라운드 알림 정책과 현장별 polling 운영 UX 검증

초기 알림 전달 방식은 사내망 REST API 전경 polling으로 구현·확정되어 있다. WPF는 기본 15초 간격으로 먼저 sync manifest를 확인한 뒤 `/api/v1/notifications?afterId={cursor}`를 조회하고 연결 실패 시 최대 120초까지 backoff한다. 서버 scope와 사용자 ID별 cursor 및 처리한 `message_id`를 로컬 SQLite에 보존하고, 응답 처리가 끝난 뒤 같은 트랜잭션에서만 cursor를 전진시킨다. 서버 URL·instance·epoch 변경 또는 cursor 역행은 자동 초기화하지 않고 polling을 중지하며, 복구 경계에서는 단독 `알림 위치 초기화`도 차단한다. 관리자가 `서버 재결합`의 모든 판정을 사유와 함께 승인한 뒤에만 cursor를 0으로 재추적하며 기존 처리 `message_id`는 재조회 멱등 근거로 보존한다. 상세 정책은 [WPF 사용자별 알림 cursor 보존 정책](./docs/notification-cursor.md)을 따른다. 외부 push나 WebSocket은 초기 구현의 대안이 아니라 현장 네트워크 정책과 백그라운드 알림 요구가 확인될 때 검토하는 확장 선택지다.

이 기능은 개인 메신저나 사내 메신저 전체 대체가 아니라, 현장 기록과 관리자 검토 흐름을 이어주는 업무 채널 기능이다.

## 프로젝트 구조

```text
apps/windows/
  docs/                         Windows 앱 구현 문서
  src/FlowNote.Windows.App/     WPF UI
  src/FlowNote.Windows.Core/    로컬 DB, 서비스, 정책, 서버 API 클라이언트
  src/FlowNote.Windows.Core.Tests/  서버 알림 cursor 등 Core 단위 테스트
  src/FlowNote.Windows.SmokeTests/  콘솔 스모크 테스트
  src/FlowNote.Windows.SyncConvergenceTests/  서버 권위 mutation과 재실행 멱등 수렴 검증
  src/FlowNote.Windows.SyncMigrationTool/  보존 FAILED 큐 진단·승인 전환 CLI
```

## 로컬 데이터

기본 DB 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다.

- `FLOWNOTE_LOCAL_DATA_DIR`: 로컬 데이터 폴더 override
- `FLOWNOTE_LOCAL_DATABASE_PATH`: SQLite 파일 경로 override
- `FLOWNOTE_API_BASE_URL`: FastAPI 서버 URL

업로드 파일과 FieldComment 첨부는 로컬 데이터 폴더의 `Files/` 아래 보존한다.

## 권한 요약

- 문서 등록/작업순서 편집: 관리자 계열, 반장, 조장
- 보고서 작성: 관리자/문서관리/부서관리 계열
- 파일 감시: 관리자 계열만
- 사용자 관리: `admin`, `system-admin`
- 승인 단말 관리: 서버 로그인 `admin`, `system-admin`
- 외부 AI 운영 관리: 서버 로그인 `system-admin`
- 채널 관리/인수인계 확인 현황: 문서 등록 권한과 같은 관리자/반장/조장 계열
- 다운로드 허용: 관리자 계열 중 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`
- FieldComment 작성: 모든 기본 현장 role

`RolePermissionPolicy` 정합성 검증 기준:

- `CanRegisterDocuments`: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`
- `CanWriteFieldComments`: 모든 기본 role
- `CanWriteReports`, `CanDownloadDocuments`: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`
- `CanReadAccessLogs`, `CanManageUsers`: `admin`, `system-admin`

서버 URL이 설정된 상태에서는 서버가 401 또는 403을 반환하거나 인증서·주소·방화벽·시간 초과로 연결에 실패해도 로컬 계정으로 자동 우회하지 않는다. 로그인 화면은 인증서와 PC 시간, 현재 서버 주소, 방화벽을 순서대로 확인하도록 안내한다. 서버 URL이 없는 승인된 로컬 운영 PC에서만 로컬 계정 로그인을 사용한다.
서버 로그인 성공 시에는 같은 로그인 ID의 로컬 role과 다르더라도 서버 응답 role이 화면 버튼과 정책 결과의 기준이다.
임시 비밀번호 서버 로그인은 메인 화면보다 비밀번호 변경 창을 먼저 표시하며, 변경 성공 후 새 비밀번호 재로그인을 요구한다. 서버 계정 화면의 401은 재로그인, 403은 권한 부족으로 안내하고 작업 버튼을 비활성화한다. 서버 연결이 끊겨도 열린 서버 계정 화면을 로컬 계정 화면으로 자동 전환하지 않는다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

스모크 테스트는 `FLOWNOTE_API_BASE_URL`이 없으면 `http://127.0.0.1:5184`의 로컬 FastAPI 서버를 자동 확인한다. 해당 서버가 실행 중이면 서버 로그인, 문서 등록, 버전, 공개 조회까지 서버 연동 블록을 검증하고, 실행 중이 아니면 기존 로컬 SQLite 검증만 계속한다.

표준 통합 실행은 저장소 루트의 `scripts/verify-preserved-tests.ps1`을 사용한다. 스크립트가 새 `FLOWNOTE_SMOKE_RUN_ID`와 증거 폴더를 주입하고 비어 있는 `5184` 포트에 누적 Windows 스모크 FastAPI를 직접 시작한다. 이미 건강한 서버가 있으면 그 설정을 추정해 재사용하지 않고 환경 실패로 중단한다. AI 보존 검증에 필요한 `system-admin` 계정은 일반 관리자 API로 만들지 않는다. 스크립트가 `FLOWNOTE_ENVIRONMENT=test`와 `FLOWNOTE_SMOKE_SERVER_DATABASE_PATH`를 설정하고, 파일명이 `flownote.windows-smoke.sqlite3`인 기존 시험 DB에서만 전용 계정을 준비한다. 환경, 경로 또는 파일 조건이 하나라도 맞지 않으면 계정을 만들지 않고 즉시 중단한다. 구 FAILED 큐 dry-run·승인 재실행 멱등성, 서버 viewer 비밀번호 변경·Windows/승인 Android 세션·비활성화 차단, AI ground-truth 평가와 provider 차단, AI 보존 설정→재조회→일괄 만료 차단→해제→단일 만료→감사 조회, cursor 재시작 복구, SQLite 무결성·매핑/idempotency 중복을 같은 실행 ID로 검증한다.

WPF smoke는 시작·종료 시 주요 로컬 테이블 건수를 읽고 오늘 사진/인수인계 문서 2건과 기존 과거 문서의 신규 버전을 SQL로 다시 확인한다. 결과는 `wpf-smoke-database-evidence.json`에 문서 ID, 이전·신규 버전, 무결성 값과 함께 보존하며 표준 스크립트의 단계별 로그·WPF Core TRX·최종 요약과 한 run ID를 공유한다.

별도 PC 복구 리허설에서는 `scripts/verify-pilot-restore.py`의 `wpf` 대상을 사용해 앱이 종료된 WPF DB와 `Files`의 복구 전후 증거를 수집·비교한다. 도구는 수집 중 DB·파일 불변과 checkpoint되지 않은 WAL 부재도 검사하며 같은 실행 경로의 기존 증거를 덮어쓰지 않는다. server와 wpf 비교를 마친 뒤 `compare-set`으로 두 대상의 `backup-set-id`·`restore-approval-id`가 서로도 같은지 확인한다. 이 도구의 통과는 실제 별도 PC 복구 절차 자체를 대신하지 않는다.

서버 전용 `controlled_copy_grants`가 WPF 공통 DB에 잘못 생성되어 `document_versions.version_id` FK mismatch가 나는 경우 DB나 원천 파일을 삭제하지 않는다. 앱과 서버를 멈춘 뒤 `python scripts/repair-wpf-controlled-copy-schema.py --database data/local/flownote.local.sqlite --run-id <새-run-id>`를 저장소 루트에서 실행한다. 도구는 `data/local/wpf-schema-repair/<run-id>/`에 원본 SQLite backup, 전후 row 수·DDL·FK·hash와 요약을 먼저 보존하고 grant row를 보존 테이블로 옮긴 뒤 무결성을 재검사한다. 실제 공통 DB 복구 run `WPF-P0-20260720-0840`은 문서 버전 3,384행 hash를 유지하며 `quick_check=ok`, FK 위반 0건으로 끝났다. FastAPI도 WPF 로컬 schema를 서버 DB URL로 받으면 테이블 생성 전에 거부한다.

현재 코드와 표준 스크립트 guard는 FastAPI 154건·WPF Core 76건·Android 20건을 기준으로 한다. 이번 macOS 검증에서 WPF Core 수집·고유·TRX 76/76이 일치했다. Windows 수집 목록과 원시 TRX의 `total/passed=76/76`, 누적 공통 DB 스모크와 Android build를 같은 clean 소스 커밋에서 새 run ID로 2회 완료해 각각 `partial_run=false`, `verification-summary.json=PASSED`가 나오기 전까지 통합 기준선 재확립은 `대기`다.

스모크 테스트는 공통 SQLite에 기록을 누적한다. 테스트 DB와 파일 산출물은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.

파일 유형별 미리보기 샘플과 실패 안내 기준은 [문서 미리보기 안정화 기준](./docs/document-preview-stability.md)을 따른다.
보존 FAILED 큐의 dry-run, 승인 전환과 무손실 검증 기준은 [보존 동기화 실패 무손실 전환](./docs/legacy-sync-migration.md)을 따른다.
