# 2026-06-26 현재 작업 종합 정리

## 목적

이 문서는 2026-06-26 현재까지 FlowNote에 반영된 제품 방향, Windows WPF 클라이언트, FastAPI 서버, 스모크 테스트, 보존 대상 산출물을 한곳에서 확인하기 위한 종합 기록이다. 상세 계약은 `docs/api.md`, 도메인 관계는 `docs/system-map.md`, 구현 범위 판단은 `docs/mvp-scope.md`를 기준으로 한다.

## 현재 구현 기준

현재 실제 동작 범위는 Windows WPF 로컬 SQLite 프로토타입과 FastAPI SQLite MVP API가 병행되는 상태이다.

- Windows WPF 앱은 로컬 SQLite를 기본 저장소로 사용한다.
- `FLOWNOTE_API_BASE_URL`이 설정되면 서버 로그인, 문서 등록, FieldNote 등록, 문서 접근 로그 API 연동을 후보로 시도한다.
- 서버 연동 실패나 서버 URL 부재는 로컬 저장 성공을 취소하지 않는다.
- FastAPI 서버는 SQLite와 서버 로컬 `storage/` 폴더를 기준으로 문서, 버전, 태그, FieldNote, 문서 접근 로그의 최소 API를 제공한다.
- 인증은 MVP 로그인 API까지 구현되어 있으며, JWT 또는 세션 발급과 요청별 권한 검사는 아직 구현 완료 범위가 아니다.

## 제품 방향 정리

- FlowNote는 MES/ERP를 대체하지 않는 독립형 현장 문서/지식 관리 서버로 정리했다.
- 초기 배포 기준은 서버 PC 1대와 Windows WPF 설치형 클라이언트이다.
- 일반 브라우저 직접 접근은 기본 운영 방식이 아니며, 승인된 설치형 Windows 클라이언트 접근을 기준으로 한다.
- 단순 DMS나 순수 KMS 한쪽으로 치우치지 않고, 문서 버전, 현장 코멘트, 작업 문제점, 생산보고서, 작업내역을 함께 축적하는 방향을 유지한다.
- AI 검색과 작업 조언은 현재 MVP의 핵심 구현이 아니라, 축적된 데이터가 충분해진 뒤 붙이는 후속 계층으로 정리했다.

## Windows WPF 작업 결과

Windows 앱은 `apps/windows/` 아래에 위치한다.

- 로그인 창과 로그인 성공 후 탐색기형 메인 화면을 구성했다.
- 기본 계정 `admin / 1234`와 관리자 그룹, 반장, 조장, 조원 테스트 계정 체계를 로컬 SQLite에 생성한다.
- 기본 폴더 `문서`, `인수인계`, `작업순서`, `사진`을 시스템 폴더로 만들고 삭제하지 못하게 했다.
- `문서` 하위에는 `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서` 분류 폴더를 자동 생성한다.
- 파일 업로드 버튼과 Drag & Drop으로 파일을 `Data\Files\Uploads\yyyy-MM-dd\` 아래에 복사하고 SQLite에 문서와 원본 버전 `v1`을 등록한다.
- `인수인계`와 `사진`은 오늘 날짜 하위 폴더 기준으로 배치하고, `작업순서`는 파일명에서 작업 제목을 만든다.
- TXT, PDF, Excel, 이미지 미리보기를 지원한다. PDF는 WebView2 표시를 우선하고 실패 시 PdfPig 텍스트 추출을 보조로 사용한다.
- 문서 보기 창에서 작성한 새 코멘트는 문서 버전을 증가시키지 않고 `field_notes` 원천 이력으로 저장한다.
- FieldNote 저장 시 문서 작성자 알림을 만들고, 과거 호환용 코멘트 버전 증가 경로는 직전 버전 작성자에게 알림을 보낸다.
- 문서 보기 창 열림과 닫힘을 `document_view_logs`에 기록하고, 개발 검증용 자동 닫힘은 `auto_closed` 닫힘 사유로 저장한다.
- 전체 이력 창은 `activity_history`에 저장된 변경/감사 이력을 최신순으로 표시한다.
- 문서 등록과 파일 업로드 시 사용자가 입력한 태그, 폴더명, 문서 유형, 확장자 태그를 저장하고 문서 목록에 표시한다.
- 서버 API 클라이언트는 로그인, 문서 등록/목록/버전 조회, 서버 FieldNote 등록, 문서 접근 로그 등록/조회를 호출할 수 있다.

## FastAPI 서버 작업 결과

FastAPI 서버는 `services/api/` 아래에 위치한다.

- SQLite 기반 초기 스키마와 개발용 기본 관리자 계정 생성을 구성했다.
- 상태 확인 API `GET /`, `GET /api/v1/health`, `GET /api/v1/health/db`를 제공한다.
- MVP 로그인 API `POST /api/v1/auth/login`은 사용자명/비밀번호를 검증하고 사용자 정보를 반환한다.
- 문서 등록 API는 `multipart/form-data` 파일을 받아 서버 로컬 `storage/documents/{document_id}/v{version_no}/` 아래에 저장한다.
- SQLite에는 문서, 버전, 파일 참조, 원본 파일명, 저장 키, 확장자, MIME, 파일 계열, 크기, SHA-256 해시를 기록한다.
- 새 버전 등록 시 기존 최신 버전은 `SUPERSEDED`로 바꾸고 새 버전을 최신 버전으로 저장한다.
- 문서 태그 API와 문서 등록 시 태그 저장 흐름을 추가했다.
- FieldNote API는 문서/문서 버전에 연결된 현장 코멘트 원천 이력 등록, 목록/상세 조회, 관리자 검토/분석 갱신을 제공한다.
- 문서 접근 로그 API `POST /api/v1/documents/{documentId}/access-logs`, `GET /api/v1/documents/{documentId}/access-logs`를 추가했다.

## WPF와 서버 연동 기준

- WPF 로그인 화면은 `FLOWNOTE_API_BASE_URL`이 설정되어 있으면 서버 로그인 API를 먼저 호출한다.
- 서버 로그인 성공 시 `user_id`, `username`, `role`, `display_name`을 로그인 결과에 보관한다.
- 서버 URL이 없거나 서버 로그인 호출이 실패하면 기존 로컬 SQLite 로그인으로 폴백한다.
- WPF 로컬 문서 등록이 성공한 뒤 서버 URL이 있으면 같은 파일을 FastAPI `POST /api/v1/documents`로 등록 후보 시도한다.
- 문서 보기 창은 로컬 FieldNote 저장 직후 서버 FieldNote 등록을 후보로 시도한다.
- 문서 접근 로그는 로컬 SQLite에 먼저 저장하고, 서버 문서 ID와 버전 ID가 있는 연동 경로에서는 FastAPI 접근 로그 API로도 보낼 수 있다.
- 현재는 자동 재시도 큐, 충돌 해결, 완전 동기화 상태 관리가 없다.

## 검증 기록

최근 검증 기준은 다음과 같다.

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| FastAPI pytest | `.\.venv\Scripts\python.exe -m pytest` in `services/api` | 통과, `16 passed in 1.77s` |
| Windows App build | `dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj` | 통과 |
| Windows smoke build | `dotnet build .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj` | 통과 |
| Windows smoke test + FastAPI 연동 | `FLOWNOTE_API_BASE_URL=http://127.0.0.1:5185` 지정 후 smoke test 실행 | 통과 |
| Windows smoke test 로컬 폴백 | `FLOWNOTE_API_BASE_URL` 없이 smoke test 실행 | 통과 |

스모크 테스트는 서버 URL이 없으면 로컬 SQLite 기준으로 계속 진행하고, 서버 URL이 있으면 서버 로그인, 문서 등록/목록/버전 조회, 서버 FieldNote 등록, 문서 접근 로그 등록/조회까지 추가로 확인한다.

## 보존 대상 산출물

다음 파일과 디렉터리는 테스트 기록이며 삭제하지 않는다.

- `apps/windows/src/FlowNote.Windows.App/Data/flownote.local.sqlite`
- `services/api/data/flownote.test.sqlite3`
- `services/api/data/test-artifacts/`
- `services/api/storage/`
- `tmp/run-logs/`
- 사용자가 직접 테스트하거나 스모크 테스트가 생성한 문서 파일, 이미지, PDF, Excel, TXT, 렌더링 결과, 로그

SQLite DB는 누적 테스트 기록으로 사용할 수 있으므로 Git 추적 대상이 될 수 있다. SQLite 외 테스트 산출물과 실제 업로드 파일은 Git 제외 대상으로 유지한다.

## 아직 구현 완료가 아닌 범위

- JWT 또는 세션 토큰 발급
- 요청별 인증/권한 검사와 역할 기반 서버 권한 적용
- 운영용 다운로드 차단
- 운영 설정 기반 뷰어 자동 닫힘 시간 관리
- WPF와 서버의 재시도 큐, 충돌 처리, 완전 동기화
- 현장 코멘트 첨부 파일 API
- 작업순서판 실제 운영 모델
- 보고서 생성과 관리자 분석 보고서 확정 흐름
- AI 검색, 작업 조언, 의사결정 보조
- MES/ERP 현장별 어댑터
- 설치 패키징과 운영 서비스 등록

## 다음 작업 후보

- 서버 로그인 API를 JWT 또는 세션 기반 인증 흐름으로 확장한다.
- 문서 등록, FieldNote, 접근 로그 API에 사용자 권한 검사를 적용한다.
- WPF 서버 연동 실패 기록과 재시도 정책을 설계한다.
- FieldNote 첨부 파일과 사진 기록 API를 추가한다.
- 문서 상태 전환, 공개 버전, 보관 정책을 서버와 WPF 화면에 연결한다.
- 작업순서판과 현장 TV 화면의 최소 모델을 설계한다.
- 보고서 초안 생성 전 단계로 FieldNote 관리자 검토/분석 화면을 구체화한다.
