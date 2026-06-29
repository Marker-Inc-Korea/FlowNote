# 로컬 SQLite 기본 구조

## 목적

Windows WPF 클라이언트가 서버 연동 전에도 로그인, 폴더 관리, 문서 등록의 기본 흐름을 검증할 수 있도록 로컬 SQLite 저장소를 둔다.

이 저장소는 최종 서버 데이터베이스를 대체하지 않는다. 현재 단계에서는 클라이언트 화면 흐름과 기본 서비스 경계를 확인하기 위한 로컬 구조이다.

## 기본 설정

- DB 경로: 개발 실행 시 저장소 루트의 `data/local/flownote.local.sqlite`, 배포 실행 시 앱 실행 폴더의 `Data\flownote.local.sqlite`
- DB 위치 override: `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`
- 기본 로그인 ID: `admin`
- 기본 비밀번호: `1234`
- 기본 역할: `system-admin`
- 앱 시작 방식: 로그인 창이 먼저 열리고, 로그인 성공 후에만 탐색기 화면을 사용할 수 있다.
- 기본 루트 폴더: `Root`
- 루트 아래 기본 폴더: `문서`, `인수인계`, `작업순서`, `사진`
- `문서` 하위 기본 분류 폴더: `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서`

## 테이블

현재 로컬 DB는 다음 테이블을 만든다.

- `user_accounts`: 로그인 계정
- `document_folders`: 문서 폴더
- `documents`: 문서 등록 기본 정보
- `document_versions`: 원본 등록과 문서 파일/과거 코멘트 버전 이력
- `field_notes`: 문서 파일 버전과 분리된 현장 코멘트 원천 이력
- `notifications`: FieldNote 또는 과거 코멘트 버전 경로에 따른 사용자 알림
- `server_sync_queue`: 문서, FieldNote, 접근 로그 서버 전송 후보와 실패 사유, 재시도 상태
- `server_id_mappings`: 로컬 원천 ID와 서버 `document_id`, `version_id`, `note_id`, `log_id` 매핑

## 서비스 위치

- `FlowNoteLocalDatabase`: SQLite 파일 생성, 스키마 생성, 기본 데이터 시드
- `FlowNoteLocalServices`: Auth, Folders, Documents, FieldNotes, Notifications, ServerSync 서비스 묶음
- `AuthService`: 로그인 검증
- `FolderService`: 폴더 생성, 목록, 삭제
- `DocumentService`: 문서 등록, 목록
- `FieldNoteService`: 현장 코멘트 원천 이력 저장과 문서별 조회
- `NotificationService`: 알림 목록, 읽지 않은 알림 수, 모두 읽음 처리
- `ServerSyncService`: 로컬 저장 후 서버 전송 큐 등록, 실패 이력 기록, 서버 재연결 시 보류 항목 재시도
- `DocumentPlacementService`: 기본 폴더별 문서 배치와 제목 생성 규칙

## 현재 동작

- 기본 계정 `admin / 1234`를 자동 생성한다.
- 기본 루트 폴더 `Root`를 자동 생성한다.
- 루트 아래에 `문서`, `인수인계`, `작업순서`, `사진` 폴더를 자동 생성한다.
- 네 개 기본 폴더는 시스템 폴더로 표시하며 삭제할 수 없다.
- `문서` 아래에 `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서` 분류 폴더를 자동 생성한다.
- `문서` 하위 분류 폴더는 시스템 폴더로 표시하며 삭제할 수 없다.
- 기존 로컬 DB에 `문서` 바로 아래 문서가 있으면 초기화 과정에서 파일명과 제목 기준으로 분류 폴더로 이동한다.
- 기존 로컬 DB에 같은 이름의 기본 폴더가 있으면 초기화 과정에서 시스템 폴더로 보정한다.
- 새 폴더 버튼은 루트 아래에 폴더를 만든다.
- 문서 등록 버튼은 기본 폴더 `문서`를 기준으로 샘플 문서 메타데이터를 등록하고, 실제 저장 위치는 분류 규칙에 따라 `문서` 하위 폴더로 정한다.
- 파일 보기 창에서 새 코멘트를 저장하면 `field_notes`에 원천 이력으로 저장하고 `documents.version_no`는 올리지 않는다.
- `field_notes`에는 문서 ID, 당시 문서 버전 번호, 입력 방식, 원문, 작성자, 상태, 동기화 후보 시간을 저장한다.
- 화면에서는 문서 본문 아래에 FieldNote 목록을 누적 코멘트처럼 표시한다.
- 새 FieldNote가 저장되면 `documents.latest_comment`와 `documents.updated_at`를 갱신하고 문서 작성자에게 알림을 남긴다.
- `DocumentViewWindow`는 로컬 FieldNote 저장 직후 `server_sync_queue`에 서버 등록 후보를 남긴다. `FLOWNOTE_API_BASE_URL`이 없거나 전송 실패가 발생해도 로컬 저장 성공을 되돌리지 않으며, 실패 사유는 큐와 `activity_history`에 남긴다.
- 파일 업로드 문서, FieldNote, 문서 열람 시작/닫힘 로그는 서버 재연결 후 큐 순서대로 재시도한다. 성공하면 로컬 원천 레코드에 서버 ID와 `synced_at`을 기록한다.
- 기존 DB의 `document_versions.comment` 데이터는 앱 초기화 시 `field_notes`로 백필한다.
- 과거 호환용 `DocumentService.AddCommentVersion` 경로를 사용하면 `document_versions`에 새 버전을 추가하고 `documents.version_no`를 올린다. 이때 알림 수신자는 최초 작성자가 아니라 직전 버전 작성자이다. 예를 들어 v3 코멘트는 v2 작성자에게 알림을 보낸다.
- 파일 업로드 버튼과 Drag & Drop은 선택한 파일을 공통 로컬 데이터 폴더의 `Files\Uploads\yyyy-MM-dd\` 아래로 복사하고 SQLite에 문서와 원본 버전 `v1`을 즉시 저장한다.
- 업로드 원본 파일은 공개 저장소에 올리지 않지만, SQLite DB의 문서 메타데이터와 상대 경로 기록은 커밋 대상이다.
- PDF 업로드 파일은 저장된 로컬 경로를 기준으로 WebView2 PDF 뷰어에서 원본 레이아웃을 표시한다.
- Excel 업로드 파일은 저장된 로컬 경로를 기준으로 첫 번째 시트를 행/열 그리드로 표시한다.
- 사진 문서는 이미지 미리보기 아래에 누적 코멘트와 새 코멘트 입력 영역을 표시한다.
- `인수인계` 폴더에 파일을 등록하면 `yyyy-MM-dd` 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- `작업순서` 폴더에 파일을 등록하면 파일명에서 확장자를 제외한 값을 작업 제목으로 자동 생성한다.
- `사진` 폴더에 파일을 등록하면 `yyyy-MM-dd` 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- 문서가 들어 있는 폴더와 시스템 폴더는 삭제하지 않는다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

검증 내용:

- `admin / 1234` 로그인 성공
- 잘못된 비밀번호 로그인 실패
- 루트 폴더 자동 생성
- 기본 폴더 4개 자동 생성
- `문서` 하위 분류 폴더 7개 자동 생성
- 기본 폴더 삭제 차단
- 폴더 생성 후 목록 조회
- 문서 등록 후 목록 조회
- FieldNote 저장 후 문서 버전 미증가
- FieldNote 목록 조회
- FieldNote 저장 시 최신 코멘트 요약 갱신
- 과거 호환용 코멘트 버전 증가와 문서 버전 이력 조회
- 과거 호환용 코멘트 저장 시 직전 버전 작성자 알림 생성
- 알림 목록 조회와 모두 읽음 처리
- `문서` 파일 등록 시 분류 폴더 자동 배치
- `인수인계` 파일 등록 시 날짜 하위 폴더 생성
- `사진` 파일 등록 시 날짜 하위 폴더 생성
- `작업순서` 파일 등록 시 파일명 기반 작업 제목 생성
- 업로드 파일의 로컬 경로를 문서 등록 정보에 저장하는지 확인
- WPF 앱 빌드에서 PdfPig 기반 PDF 미리보기 코드 컴파일 확인
- 문서가 있는 폴더 삭제 차단
