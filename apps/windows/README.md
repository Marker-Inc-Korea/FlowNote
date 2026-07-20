# Windows App

`apps/windows/`는 FlowNote Windows WPF 클라이언트 영역이다. 현장/관리자 PC에 설치해 사용하는 네이티브 앱을 기준으로 한다.

현재 프로젝트는 WPF UI `net10.0-windows`, Core와 스모크 테스트 `net10.0`을 대상으로 한다. 현재 기능 목록은 `FlowNote.Windows.App`, `FlowNote.Windows.Core`, `FlowNote.Windows.SmokeTests` 코드에 실제 연결된 범위만 포함한다.

이 문서는 2026-07-20 현재 코드 기준이다. 운영 설치나 현장 검증이 남은 내용은 현재 구현과 분리해 후속 제품 방향에만 둔다.

## 현재 구현

- 로그인 화면과 메인 탐색기 화면
- 로컬 SQLite 초기화와 기본 계정/그룹/폴더 시드
- 사용자 관리: 서버 로그인 시 서버 계정 생성, 이름/역할/상태 변경, 임시 비밀번호 재설정, 활성 세션 조회/폐기. 서버 미연결 로컬 로그인 시 로컬 계정 관리
- 승인 단말 관리: 서버 단말 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체
- 폴더 트리와 문서 목록. 기본 폴더는 `문서`, `인수인계`, `작업순서`, `사진`이다.
- 새 폴더 생성
- 샘플 문서 등록, 파일 업로드, Drag & Drop 등록
- 문서 상태 변경과 공개 버전 지정
- 문서 태그 저장과 표시
- TXT, PDF, XLSX, 이미지 미리보기
- 문서 열람 시작/종료 로그
- viewer 자동 닫힘과 다운로드 차단 로그
- 허용 role의 서버 1회성 controlled copy 저장과 SHA-256 검증, 비허용 role의 기존 차단 안내·이력
- FieldComment 작성과 첨부 저장, 원천 불변 검증, 단계형 관리자 검토, 담당자·기한 지정, 다중 선택 일괄 변경, 감사·품질 작업함
- 알림, 전체 이력
- 관리자 파일 감시 후보 처리
- 작업순서 관리자 화면과 TV 화면
- 보고서 초안 생성 보조, 문서 저장, 서버 보고서 저장 시도
- 채널함: 서버 내 채널, 채널 메시지/알림, 인수인계 조회, 읽음/수신 확인, 원천 링크 복사, 후속 FieldComment 생성
- 채널 관리: 서버 채널 생성, 멤버 추가/제외
- 인수인계 확인 현황: 수신자별 receipt 상태 변경, 후속 FieldComment 생성
- FastAPI 서버 인증과 승인 단말/문서/controlled copy/FieldComment/첨부/접근 로그/보고서/작업순서/채널·인수인계/AI 검색 근거·회귀 평가/외부 AI 운영 API 클라이언트
- AI 근거 후보 운영 점검: 서버 후보 재생성, 품질 지표, 제외 사유, 후보 목록, 원천 추적값 복사
- `system-admin` 전용 `AI 운영` 화면: 전송 승인 생성·철회, 프롬프트 검토·승인·활성화·폐기, 전역/현재 현장 kill switch와 호출·비용·보존 정책, 정제 감사 조회/CSV 내보내기, 서버 자동 보존과 별개인 만료 보존 작업 즉시 실행
- 서버 동기화 큐: 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장. 문서 버전·첨부 idempotency key 전달과 큐 깊이·최장 대기·최근 처리량·실패 분포·row별 운영 상태 표시 포함
- 보존 동기화 실패 전환 CLI: FAILED 큐를 읽기 전용 dry-run으로 분류하고, plan hash와 row별 운영자 승인을 받은 구 `create`/FieldNote 항목만 현재 action의 별도 큐로 무손실 전환

WPF에는 `/api/v1/ai/queries`를 호출하는 실제 외부 AI 질의 실행 화면이나 운영 provider client가 없다. AI 화면은 외부 호출 없는 근거 후보 운영 점검 화면과 `system-admin` 전용 운영 제어 화면으로 분리되어 있다.

AI 검색 근거 후보는 현재 FastAPI 서버 API, WPF 서버 클라이언트, `AI 근거 후보 운영 점검` 화면에 구현되어 있다. 이 화면은 `/api/v1/ai-search/candidates/rebuild`, `/api/v1/ai-search/quality`, `/api/v1/ai-search/candidates`를 호출해 외부 AI 호출 전 데이터 품질과 원천 추적 가능성을 확인한다. WPF 서버 클라이언트는 `/api/v1/ai-search/evaluations` 계약도 구현하며, 스모크 테스트가 기대 근거·제외 근거와 재생성 전후 candidate ID/content hash/순위 안정성을 검증한다. 회귀 평가를 직접 구성·실행하는 WPF 운영 UI는 아직 없다.

`AI 운영` 화면은 `/api/v1/ai-operations`를 통해 승인, 프롬프트, 전역/현장 운영 정책과 질의 감사 메타데이터를 조회·변경한다. provider 자격증명·질의 원문·응답 원문은 표시하지 않으며 provider 자격증명은 설정 여부만 표시한다. 감사 CSV는 현장 정책에서 내보내기를 허용한 경우에만 저장할 수 있다. 서버는 설정된 주기로 만료 보존을 자동 처리하며, 화면의 실행 버튼은 다음 주기를 기다리지 않고 같은 처리를 즉시 요청한다.

`작업내역` 화면의 서버 동기화 큐는 완료, 보존 구 형식, 선행 조건 대기, 수동 조치 필요, 재시도 가능을 별도 운영 상태로 표시한다. 요약에는 `SYNCED`가 아닌 큐 깊이, 최장 대기 시간, 최근 1시간 처리량과 실패 분포가 나온다. 인증 만료나 서버 연결 실패·시간 초과는 현재 재시도 묶음을 중단하며, 개별 항목의 검증·파일 오류는 해당 항목을 실패로 남기고 다음 독립 항목을 계속 처리한다. 모든 경우 로컬 원천과 큐는 유지한다.

## 후속 제품 방향

- 채널/인수인계 화면의 운영 UX 고도화와 현장별 권한 세분화
- 인수인계 등록 작성 화면과 템플릿 보강
- 채널 메시지와 인수인계를 문서, FieldComment, 작업순서, 작업내역, 보고서 근거로 더 쉽게 연결하는 운영 흐름
- 백그라운드 알림 정책과 현장별 polling 운영 UX 검증

초기 알림 전달 방식은 사내망 REST API 전경 polling으로 구현·확정되어 있다. WPF는 기본 15초 간격으로 `/api/v1/notifications?afterId={cursor}`를 조회하고 연결 실패 시 최대 120초까지 backoff한다. 서버 scope와 사용자 ID별 cursor 및 처리한 `message_id`를 로컬 SQLite에 보존하고, 응답 처리가 끝난 뒤 같은 트랜잭션에서만 cursor를 전진시킨다. 서버 cursor 역행은 자동 초기화하지 않고 polling을 중지하며 Core 서비스가 `admin`, `system-admin` role을 확인한 관리자 동작만 cursor를 초기화한다. 초기화해도 기존 처리 `message_id`는 재조회 멱등 근거로 보존한다. 상세 정책은 [WPF 사용자별 알림 cursor 보존 정책](./docs/notification-cursor.md)을 따른다. 외부 push나 WebSocket은 초기 구현의 대안이 아니라 현장 네트워크 정책과 백그라운드 알림 요구가 확인될 때 검토하는 확장 선택지다.

이 기능은 개인 메신저나 사내 메신저 전체 대체가 아니라, 현장 기록과 관리자 검토 흐름을 이어주는 업무 채널 기능이다.

## 프로젝트 구조

```text
apps/windows/
  docs/                         Windows 앱 구현 문서
  src/FlowNote.Windows.App/     WPF UI
  src/FlowNote.Windows.Core/    로컬 DB, 서비스, 정책, 서버 API 클라이언트
  src/FlowNote.Windows.Core.Tests/  서버 알림 cursor 등 Core 단위 테스트
  src/FlowNote.Windows.SmokeTests/  콘솔 스모크 테스트
  src/FlowNote.Windows.SyncMigrationTool/  보존 FAILED 큐 진단·승인 전환 CLI
```

## 로컬 데이터

기본 DB 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다.

- `FLOWNOTE_LOCAL_DATA_DIR`: 로컬 데이터 폴더 override
- `FLOWNOTE_LOCAL_DATABASE_PATH`: SQLite 파일 경로 override
- `FLOWNOTE_API_BASE_URL`: FastAPI 서버 URL
- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`: 뷰어 자동 닫힘 시간

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

서버 URL이 설정된 상태에서 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.
서버 로그인 성공 시에는 같은 로그인 ID의 로컬 role과 다르더라도 서버 응답 role이 화면 버튼과 정책 결과의 기준이다.
임시 비밀번호 서버 로그인은 메인 화면보다 비밀번호 변경 창을 먼저 표시하며, 변경 성공 후 새 비밀번호 재로그인을 요구한다. 서버 계정 화면의 401은 재로그인, 403은 권한 부족으로 안내하고 작업 버튼을 비활성화한다. 서버 연결이 끊겨도 열린 서버 계정 화면을 로컬 계정 화면으로 자동 전환하지 않는다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

스모크 테스트는 `FLOWNOTE_API_BASE_URL`이 없으면 `http://127.0.0.1:5184`의 로컬 FastAPI 서버를 자동 확인한다. 해당 서버가 실행 중이면 서버 로그인, 문서 등록, 버전, 공개 조회까지 서버 연동 블록을 검증하고, 실행 중이 아니면 기존 로컬 SQLite 검증만 계속한다.

표준 통합 실행은 저장소 루트의 `scripts/verify-preserved-tests.ps1`을 사용한다. 스크립트가 새 `FLOWNOTE_SMOKE_RUN_ID`와 증거 폴더를 주입하고 비어 있는 `5184` 포트에 누적 Windows 스모크 FastAPI를 직접 시작한다. 이미 건강한 서버가 있으면 그 설정을 추정해 재사용하지 않고 환경 실패로 중단한다. 구 FAILED 큐 dry-run·승인 재실행 멱등성, 서버 viewer 비밀번호 변경·Windows/승인 Android 세션·비활성화 차단, AI ground-truth 평가와 provider 차단, cursor 재시작 복구, SQLite 무결성·매핑/idempotency 중복을 같은 실행 ID로 검증한다.

WPF smoke는 시작·종료 시 주요 로컬 테이블 건수를 읽고 오늘 사진/인수인계 문서 2건과 기존 과거 문서의 신규 버전을 SQL로 다시 확인한다. 결과는 `wpf-smoke-database-evidence.json`에 문서 ID, 이전·신규 버전, 무결성 값과 함께 보존하며 표준 스크립트의 단계별 로그·WPF Core TRX·최종 요약과 한 run ID를 공유한다.

별도 PC 복구 리허설에서는 `scripts/verify-pilot-restore.py`의 `wpf` 대상을 사용해 앱이 종료된 WPF DB와 `Files`의 복구 전후 증거를 수집·비교한다. 이 도구의 통과는 테이블별 row 수, 파일 상대경로·크기·SHA-256, DB `quick_check`와 foreign key 일치를 뜻하며 실제 별도 PC 복구 절차 자체를 대신하지 않는다.

서버 전용 `controlled_copy_grants`가 WPF 공통 DB에 잘못 생성되어 `document_versions.version_id` FK mismatch가 나는 경우 DB나 원천 파일을 삭제하지 않는다. 앱과 서버를 멈춘 뒤 `python scripts/repair-wpf-controlled-copy-schema.py --database data/local/flownote.local.sqlite --run-id <새-run-id>`를 저장소 루트에서 실행한다. 도구는 `data/local/wpf-schema-repair/<run-id>/`에 원본 SQLite backup, 전후 row 수·DDL·FK·hash와 요약을 먼저 보존하고 grant row를 보존 테이블로 옮긴 뒤 무결성을 재검사한다. 실제 공통 DB 복구 run `WPF-P0-20260720-0840`은 문서 버전 3,384행 hash를 유지하며 `quick_check=ok`, FK 위반 0건으로 끝났다. FastAPI도 WPF 로컬 schema를 서버 DB URL로 받으면 테이블 생성 전에 거부한다.

현재 FastAPI 코드는 130건을 수집·통과하지만 표준 스크립트는 128건을 강제해 불일치한다. 스크립트를 130건으로 갱신한 뒤에도 최신 개발 호스트에는 Windows/.NET/JDK/Android SDK가 없어 WPF Core·앱 build·누적 스모크·Android build를 한 run으로 완료할 수 없다. 새 Windows 무생략 `verification-summary.json=PASSED`가 나올 때까지 마지막 통합 기준선 재확립은 `대기`로 본다.

스모크 테스트는 공통 SQLite에 기록을 누적한다. 테스트 DB와 파일 산출물은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.

파일 유형별 미리보기 샘플과 실패 안내 기준은 [문서 미리보기 안정화 기준](./docs/document-preview-stability.md)을 따른다.
보존 FAILED 큐의 dry-run, 승인 전환과 무손실 검증 기준은 [보존 동기화 실패 무손실 전환](./docs/legacy-sync-migration.md)을 따른다.
