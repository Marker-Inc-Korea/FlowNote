# Windows App

Windows 영역은 FlowNote의 유일한 활성 클라이언트 개발 위치이다. 클라이언트 앱은 Windows WPF 기반 설치형 앱으로 제작한다.

## 목표 책임

- 관리자 로그인
- 문서 조회와 미리보기
- 로컬 파일 선택과 Drag & Drop 등록
- FieldNote와 사진/파일 첨부 로컬 저장
- 문서 열람 로그와 전체 이력 저장
- 작업순서판 관리자 편집 화면과 현장 TV 화면
- FastAPI 서버 URL이 있을 때 문서, FieldNote, 첨부, 접근 로그, 작업순서판 동기화 후보 전송
- 후속 구현: 지정 파일 또는 폴더 감시
- 후속 구현: 변경 감지 파일을 새 버전 업로드 후보로 표시
- 후속 구현: 변경 사유와 버전명을 입력한 뒤 업로드 확정

현장 사용자용 뷰어 전용 단말기에는 파일 감시 기능을 넣지 않는다.

## 기술 기준

- UI 프레임워크: WPF
- UI 표시: 네이티브 앱 화면
- 현재 로컬 기능: 파일 선택, Drag & Drop, 파일 복사, 미리보기
- 후속 로컬 기능: WPF 네이티브 파일 감시
- 현재 서버 API 클라이언트: Python FastAPI 서버의 로그인, `/auth/me`, Bearer 인증 헤더 기반 문서 등록/목록/버전 조회, FieldNote 등록, FieldNote 첨부 등록/조회, 문서 접근 로그, 작업순서판 REST API 호출

## 디렉터리

- `src/FlowNote.Windows.App/`: Windows WPF 앱 진입점
- `src/FlowNote.Windows.Core/`: 파일 감시, API 클라이언트, 로컬 보안 제어 같은 공통 로직
- `docs/`: Windows 앱 구현 메모와 파일 감시 정책

## 현재 구현 상태

현재 `src/FlowNote.Windows.App/`에는 WPF 기반 탐색기형 셸 화면이 있다.

- 상단: 앱 이름과 기본 작업 버튼 영역
- 좌측: 문서 구조 탐색용 트리 영역
- 오른쪽 작업 영역: 검색 입력, 파일 목록, Drag & Drop 파일 업로드
- 상단 작업 버튼: 알림함, 새 폴더, 문서 등록, 파일 업로드
- 하단: 현재 셸 상태 표시 영역
- 시작 화면: 로그인 창. 로그인 성공 후에만 탐색기 화면을 연다.

`src/FlowNote.Windows.Core/Explorer/`에는 화면 바인딩을 위한 임시 탐색기 모델이 있다.

- `ExplorerFolder`: 좌측 트리용 폴더 모델
- `ExplorerDocument`: 중앙 문서 목록용 문서 모델
- `UploadCandidate`: 파일 선택과 Drag & Drop 입력 정보를 담는 임시 파일 정보 모델
- `ExplorerWorkspace`: WPF 화면에 표시할 탐색기 작업 공간 상태

`src/FlowNote.Windows.Core/Storage/`에는 로컬 SQLite 초기화와 서비스 묶음이 있다.

- 로컬 DB 경로: 개발 실행 시 저장소 루트의 `data/local/flownote.local.sqlite`, 배포 실행 시 앱 실행 폴더의 `Data\flownote.local.sqlite`
- 로컬 데이터 위치 override: `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`
- 기본 계정: `admin`
- 기본 비밀번호: `1234`
- 개발/스모크 테스트 계정: 관리자 그룹과 반장 3명 기준 작업조 계정. 모든 비밀번호는 `1234`
- 기본 루트 폴더: `Root`
- 루트 아래 기본 폴더: `문서`, `인수인계`, `작업순서`, `사진`
- 기본 폴더 정책: 네 개 기본 폴더는 시스템 폴더로 처리하며 삭제할 수 없다.
- 문서 열람 감사 로그: 문서 보기 창 열림 시 `document_view_logs`에 열람 시작을 저장하고 닫힘 시각과 닫힘 사유를 같은 행에 갱신한다.
- 전체 이력: 상단 `이력` 메뉴는 사용자별 알림과 별개로 `activity_history`에 저장된 전체 변경/감사 이력을 최신순으로 표시한다. 이력에는 누가 수행했는지, 대상 문서/폴더, 작업 유형, 내용을 남긴다.
- 문서 태그: 문서 등록/파일 업로드 시 태그 입력값, 폴더명, 문서 유형, 확장자 태그를 로컬 SQLite `tag_definitions`, `document_tags`에 저장하고 문서 목록에 표시한다.
- `문서` 하위 기본 분류 폴더: `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서`
- 문서 분류 정책: `문서` 폴더에 파일을 등록하면 파일명과 제목 기준으로 위 분류 폴더 중 하나에 자동 배치한다.
- 폴더별 등록 규칙: `인수인계`와 `사진`은 파일 등록 시 `yyyy-MM-dd` 형식의 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- 폴더별 등록 규칙: `작업순서`는 파일명에서 확장자를 제외한 값을 작업 제목으로 자동 생성한다.

`src/FlowNote.Windows.Core/Auth/`, `Documents/`, `FieldNotes/`, `Folders/`, `Notifications/`, `ServerApi/`, `Sync/`, `Tags/`, `WorkSequences/`에는 로그인, 문서 등록, 현장 코멘트 원천 이력, FieldNote 첨부, 폴더 관리, 알림함, 문서 태그, 작업순서판, 서버 문서/FieldNote/첨부/접근 로그/작업순서판 API 클라이언트, 로컬 서버 동기화 큐 서비스가 있다.

파일 내용 보기는 목록을 더블 클릭했을 때 별도 보기 창으로 연다. 보기 창에서는 텍스트, PDF, Excel, 사진 파일을 미리 볼 수 있고, 저장된 문서에는 코멘트를 남길 수 있다. PDF는 WebView2 기반 PDF 뷰어로 원본 레이아웃을 표시하고, Excel은 첫 번째 시트를 행/열 그리드로 표시한다. PDF 뷰어 표시가 실패할 때만 PdfPig 기반 텍스트 파싱을 보조 fallback으로 사용한다. 새 코멘트는 `field_notes`에 원천 이력으로 저장하고 문서 파일 버전은 증가시키지 않는다. 문서 목록에서 빠르게 확인할 수 있도록 `documents.latest_comment`와 `documents.updated_at`만 갱신한다.

새 FieldNote가 저장되면 문서 작성자에게 알림을 남긴다. 과거 호환용 `DocumentService.AddCommentVersion` 경로는 남아 있으며, 이 경로를 사용할 때는 v2는 v1 작성자에게, v3는 v2 작성자에게 보내는 방식으로 직전 버전 작성자에게 알림을 보낸다.

`DocumentViewWindow`의 새 코멘트와 첨부 저장 흐름은 로컬 `field_notes`와 `field_note_attachments` 저장 직후 `server_sync_queue`에 서버 등록 후보를 남기고, `FLOWNOTE_API_BASE_URL`과 Bearer token이 있는 `FlowNoteServerDocumentClient`가 만들어진 경우 즉시 재시도를 수행한다. 서버 URL이 없거나 전송이 실패해도 로컬 저장은 성공으로 유지하고, 실패 사유는 `server_sync_queue.last_error`와 `activity_history`의 `server_sync.failed` 이력에 남긴다.

이 구현은 파일 감시와 권한별 다운로드 제어를 포함하지 않는다. Drag & Drop과 파일 업로드 버튼은 선택한 파일을 공통 로컬 데이터 폴더의 `Files\Uploads\yyyy-MM-dd\` 아래로 복사하고 SQLite에 문서와 원본 버전 `v1`, 문서 태그를 즉시 저장한다. 이후 `server_sync_queue`에 `wpf:document:{localDocumentId}:v1` 형식의 idempotency key를 남기고 서버 등록을 시도한다. 성공하면 `documents.server_document_id`, `documents.server_version_id`, `documents.synced_at`, `document_versions.server_version_id`, `document_versions.synced_at`, `server_id_mappings`가 갱신된다. 문서 열람 감사 로그는 앱 실행 흐름에서 로컬 SQLite에 먼저 저장하고, 열람 시작/닫힘을 별도 큐 항목으로 남긴 뒤 서버 문서 ID와 버전 ID가 매핑되면 FastAPI `POST /api/v1/documents/{documentId}/access-logs`로 전송한다. 서버 접근 로그 성공 시 `document_view_logs.server_start_log_id`, `server_close_log_id`, `synced_at`를 기록한다. 업로드 원본 파일은 GitHub에 올리지 않고, SQLite DB의 문서 메타데이터와 상대 경로 기록은 추적 대상이다. `FlowNoteServerDocumentClient`는 FastAPI 문서 등록/목록/버전 조회, `POST /api/v1/field-notes` 등록, FieldNote 첨부 등록/조회, 문서 접근 로그 등록/조회, 작업순서판 API를 호출한다. `ServerFieldNoteCreateRequest.FromLocal`은 로컬 `FieldNoteRecord`의 문서 ID, 입력 방식, 신호등 값, 원문, 작성/전달 주체, 단말기/위치 정보를 서버 요청으로 변환하고, 서버 문서 버전 ID를 알고 있는 경우 `documentVersionId`로 함께 보낸다. FieldNote 성공 시 `field_notes.server_note_id`와 `field_notes.synced_at`을 기록하고, 첨부 성공 시 `field_note_attachments.server_attachment_id`와 `synced_at`을 기록한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

프로그램 테스트 기준:

- 문서 등록 테스트는 단일 계정이 아니라 여러 테스트 ID로 진행한다.
- 문서 등록 가능 기준은 조장 이상이다. 테스트에서는 관리자 그룹, 반장, 조장 계정이 문서 등록 후보이며 조원 계정은 문서 등록자가 아니라 코멘트 작성자로 검증한다.
- 코멘트 등록은 ID 기준 제한을 두지 않는다. 반장, 조장, 조원, 관리자 그룹 계정 모두 코멘트 등록 테스트 대상이 될 수 있다.
- 프로그램 테스트용 문서 파일의 파일명과 표시 내용은 한글, 숫자, 영문만 사용한다. 사용자가 직접 화면에서 확인할 때 표시 언어가 맞아야 하므로 `???`처럼 깨진 문자가 보이는 테스트 파일은 사용하지 않는다. 이 제한은 프로그램 테스트용 문서 파일에만 적용하며, 일반 문서 파일이나 MD 문서 작성 기준에는 적용하지 않는다.
- 서버 URL인 `FLOWNOTE_API_BASE_URL`이 없으면 스모크 테스트는 로컬 SQLite 기준으로 검증을 진행하되, 문서/FieldNote/접근 로그 서버 전송 실패 큐와 `server_sync.failed` 이력 생성을 확인한다. 서버 URL이 설정된 경우에는 같은 큐를 FastAPI로 재전송하고 서버 ID와 `synced_at` 기록까지 추가 검증한다.
- 스모크 테스트를 포함한 프로그램 테스트는 공통 SQLite인 `data/local/flownote.local.sqlite`를 계속 사용한다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 지정된 경우 해당 위치를 우선 사용한다. 테스트마다 임시 SQLite를 새로 만들지 않고, 누적된 데이터와 이력을 보존한 상태에서 추가 검증한다.
- 스모크 테스트는 사용자가 명시적으로 요청하지 않은 스모크/테스트 전용 업무 폴더를 앱 문서 구조에 만들지 않는다. 문서 등록은 현재 기본 폴더 체계인 `문서`, `인수인계`, `사진`, `작업순서`와 그 규칙에서 파생된 기존 분류/날짜 폴더 기준으로 진행한다.
- 알림 테스트는 공통 SQLite에 누적된 전체 알림 개수를 1건으로 제한하지 않는다. 특정 notify 이벤트가 발생했을 때 해당 문서와 수신자 기준으로 알림이 1건 생성되는지만 검증한다.
- 스모크 테스트는 항상 오늘 날짜 기준 문서 등록을 포함한다. 오늘 날짜의 `사진`과 `인수인계` 문서는 날짜 폴더 생성, 문서 등록, 목록 조회까지 필수로 검증한다.
- 스모크 테스트는 과거 특정 날짜를 매 실행마다 랜덤하게 골라 버전 증가를 검증한다. 과거 날짜 테스트는 이미 존재하는 `사진` 또는 `인수인계` 날짜 폴더와 그 안의 기존 문서를 대상으로 하며, 과거 날짜 폴더나 과거 날짜 문서를 새로 만들지 않는다.

스모크 테스트는 `admin / 1234` 로그인, 잘못된 비밀번호 거부, 개발/스모크 테스트 계정의 고정 `user_id`와 역할값, 관리자 그룹과 반장 3명 기준 작업조 구성, 기본 폴더 자동 생성, `문서` 하위 분류 폴더 자동 생성, 기본 폴더 삭제 차단, 기존 폴더 기준 문서 등록/목록, 문서 열람 감사 로그 생성과 닫힘 시각/사유 갱신, 전체 이력에 수행자와 작업 내용 기록, FieldNote 저장과 문서 버전 미증가, 최신 코멘트 요약 갱신, 과거 호환용 코멘트 버전 증가 경로, 직전 버전 작성자 알림 생성, 알림 읽음 처리, `문서` 파일의 분류 폴더 자동 배치, 오늘 날짜 `인수인계`와 `사진` 문서 등록/목록 조회, 기존 과거 날짜 문서의 랜덤 버전 증가, `작업순서`의 파일명 기반 작업 제목 생성, 업로드 파일의 로컬 경로 저장 흐름, 서버 미설정 상태의 동기화 실패 큐 생성을 확인한다. 스모크 테스트 SQLite DB는 앱 로컬 공통 DB를 사용하며 삭제하지 않고 실행 결과에 경로를 출력한다. `FLOWNOTE_API_BASE_URL`이 설정된 경우 FastAPI 로그인 API, 인증 헤더가 붙은 `/auth/me`, 문서 등록/목록/버전 조회, 보류 중인 문서/FieldNote/접근 로그 큐 재전송, 서버 ID 및 `synced_at` 기록, 이미 동기화된 항목의 중복 큐/중복 전송 방지도 함께 확인한다.

개발/스모크 테스트 계정은 모두 비밀번호 `1234`를 사용한다. 관리자 그룹은 `group-admin`이고, 현장 작업조는 `group-line-a`, `group-line-b`, `group-line-c`이다.

| group_id | user_id | login_id | 표시명 | role | supervisor_user_id |
| --- | --- | --- | --- | --- | --- |
| `group-admin` | `user-admin` | `admin` | `Administrator` | `system-admin` |  |
| `group-admin` | `user-deputy` | `deputy` | `차장` | `assistant-manager` |  |
| `group-admin` | `user-depthead` | `depthead` | `부장` | `department-manager` |  |
| `group-admin` | `user-manager` | `manager` | `관리자` | `document-admin` |  |
| `group-line-a` | `user-foreman-a` | `foreman-a` | `반장 A` | `line-foreman` |  |
| `group-line-a` | `user-lead-a1` | `lead-a1` | `조장 A-1` | `team-lead` | `user-foreman-a` |
| `group-line-a` | `user-member-a1` | `member-a1` | `조원 A-1` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a2` | `member-a2` | `조원 A-2` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a3` | `member-a3` | `조원 A-3` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a4` | `member-a4` | `조원 A-4` | `team-member` | `user-foreman-a` |
| `group-line-b` | `user-foreman-b` | `foreman-b` | `반장 B` | `line-foreman` |  |
| `group-line-b` | `user-lead-b1` | `lead-b1` | `조장 B-1` | `team-lead` | `user-foreman-b` |
| `group-line-b` | `user-lead-b2` | `lead-b2` | `조장 B-2` | `team-lead` | `user-foreman-b` |
| `group-line-b` | `user-member-b1` | `member-b1` | `조원 B-1` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b2` | `member-b2` | `조원 B-2` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b3` | `member-b3` | `조원 B-3` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b4` | `member-b4` | `조원 B-4` | `team-member` | `user-foreman-b` |
| `group-line-c` | `user-foreman-c` | `foreman-c` | `반장 C` | `line-foreman` |  |
| `group-line-c` | `user-lead-c1` | `lead-c1` | `조장 C-1` | `team-lead` | `user-foreman-c` |
| `group-line-c` | `user-member-c1` | `member-c1` | `조원 C-1` | `team-member` | `user-foreman-c` |
| `group-line-c` | `user-member-c2` | `member-c2` | `조원 C-2` | `team-member` | `user-foreman-c` |
| `group-line-c` | `user-member-c3` | `member-c3` | `조원 C-3` | `team-member` | `user-foreman-c` |
