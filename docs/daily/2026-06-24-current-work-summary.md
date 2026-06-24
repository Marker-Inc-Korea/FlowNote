# 2026-06-24 현재 작업 종합 정리

## 목적

이 문서는 2026-06-23부터 2026-06-24 현재까지 구현과 문서화가 진행된 내용을 한 곳에서 확인하기 위한 요약이다. 상세 설계는 `docs/`의 주 문서를 기준으로 하고, 날짜별 검증 결과는 같은 `docs/daily/` 폴더의 개별 작업 기록을 기준으로 한다.

## 현재 구현 기준

현재 동작 구현은 두 축으로 나뉜다.

- Windows WPF 로컬 SQLite 프로토타입: 현장/관리자 클라이언트 화면과 로컬 문서 등록, 미리보기, 현장 코멘트 입력 흐름을 검증한다.
- Python FastAPI SQLite MVP: 서버 측 문서 등록, 버전 등록, 파일 저장 참조, 현장 코멘트 원천 이력 API의 최소 계약을 검증한다.

아직 전체 제품 수준의 인증/권한, 다운로드 차단, 뷰어 자동 닫힘, 파일 감시, 보고서 생성, AI 검색/조언, MES/ERP 연동은 구현 완료 기능이 아니다.

## Windows WPF 작업 결과

WPF 앱은 `apps/windows/` 아래에 위치한다.

- 로그인 창에서 `admin / 1234` 기본 계정으로 로그인한 뒤 탐색기형 화면을 연다.
- 기본 폴더 `문서`, `인수인계`, `작업순서`, `사진`을 생성하고 시스템 폴더로 보호한다.
- `문서` 아래에 `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서` 분류 폴더를 자동 생성한다.
- 파일 업로드 버튼과 Drag & Drop으로 선택 파일을 `Data\Files\Uploads\yyyy-MM-dd\` 아래에 복사하고 SQLite 문서 원본 버전으로 등록한다.
- TXT, PDF, Excel, 이미지 문서 미리보기를 지원한다. PDF는 WebView2 표시를 우선하고 실패 시 텍스트 추출 fallback을 사용한다.
- Excel은 첫 번째 시트를 행/열 그리드로 표시한다.
- 파일 등록 위치는 선택 폴더 기준으로 배치한다. `인수인계`와 `사진`은 날짜 하위 폴더를 만들고, `작업순서`는 파일명을 작업 제목으로 사용한다.
- 서버 문서 API 연동 후보로 `FlowNoteServerDocumentClient`를 추가했다. 환경 변수 `FLOWNOTE_API_BASE_URL`이 있을 때 Windows smoke test에서 서버 등록/목록/버전 조회를 추가 검증한다.

## WPF FieldNote 분리 결과

기존에는 문서 보기 창의 코멘트가 `document_versions.comment`에 누적되어 문서 버전 증가와 섞였다. 현재 흐름은 신규 코멘트를 `field_notes`에 원천 이력으로 저장하도록 분리했다.

- 신규 코멘트 저장은 `FieldNoteService.AddDocumentNote`를 사용한다.
- `field_notes`에는 문서 ID, 당시 문서 버전 번호, 입력 방식, 원문, 작성자, 위치/단말기 후보, 상태, 동기화 후보 시간을 저장한다.
- 신규 FieldNote는 문서 파일 버전을 증가시키지 않는다.
- 문서 목록용 요약을 위해 `documents.latest_comment`와 `documents.updated_at`만 갱신한다.
- 기존 로컬 DB의 `document_versions.comment` 데이터는 앱 초기화 시 `field_notes`로 백필한다.
- 과거 호환용 `DocumentService.AddCommentVersion` 경로는 남아 있지만 신규 문서 보기 코멘트의 기본 경로는 FieldNote이다.

## FastAPI 서버 작업 결과

FastAPI 서버는 `services/api/` 아래에 위치한다.

- 앱 시작 시 SQLite DB를 초기화하고 `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다.
- 기본 상태 확인 API는 `GET /`, `GET /api/v1/health`, `GET /api/v1/health/db`이다.
- 문서 등록 API는 파일을 서버 로컬 `storage/documents/{document_id}/v{version_no}/` 아래에 저장하고, SQLite에 문서, 버전, 파일 참조, SHA-256, 크기, MIME, 파일 계열을 기록한다.
- 새 문서 버전 등록 시 변경 사유를 필수로 받고 기존 최신 버전은 `SUPERSEDED`로 바꾼다.
- 현장 코멘트 API는 문서/문서버전과 분리된 `field_notes` 원천 이력으로 등록, 목록, 상세, 검토/분석 갱신을 제공한다.
- 현재 서버 API는 인증/권한 적용 전 단계이다. 알 수 없는 사용자 참조나 존재하지 않는 문서 참조는 검증한다.

현재 구현 API는 다음과 같다.

| Method | Path | 역할 |
| --- | --- | --- |
| GET | `/` | 서비스명과 실행 환경 |
| GET | `/api/v1/health` | 앱 상태 확인 |
| GET | `/api/v1/health/db` | DB 연결 확인 |
| POST | `/api/v1/documents` | 문서와 최초 버전 등록 |
| GET | `/api/v1/documents` | 문서 목록 조회 |
| GET | `/api/v1/documents/{documentId}` | 문서 상세 조회 |
| GET | `/api/v1/documents/{documentId}/versions` | 문서 버전 목록 조회 |
| POST | `/api/v1/documents/{documentId}/versions` | 새 문서 버전 등록 |
| POST | `/api/v1/field-notes` | 현장 코멘트 원천 이력 등록 |
| GET | `/api/v1/field-notes` | 현장 코멘트 목록 조회 |
| GET | `/api/v1/field-notes/{noteId}` | 현장 코멘트 상세 조회 |
| PATCH | `/api/v1/field-notes/{noteId}` | 관리자 검토/분석 내용 갱신 |
| GET | `/api/v1/documents/{documentId}/field-notes` | 문서별 현장 코멘트 조회 |

## 문서 갱신 결과

제품 방향과 실제 구현 상태가 섞이지 않도록 다음 기준으로 문서를 정리했다.

- `README.md`: 저장소 최상위 현재 구현 상태와 제품 방향 요약
- `docs/README.md`: 문서 읽는 순서와 날짜별 작업 기록 인덱스
- `docs/api.md`: 현재 구현 API와 미래 API 초안 구분
- `docs/data-model.md`: WPF 로컬 SQLite 모델과 FastAPI 서버 SQLite 초기 모델 구분
- `docs/system-map.md`: 문서, 버전, 파일, FieldNote, 보고서, 외부 시스템 관계 정리
- `docs/decisions.md`: 제품 방향, 클라이언트/서버/FieldNote 관련 결정 기록
- `apps/windows/README.md`: Windows 앱 현재 기능, 로컬 SQLite, 검증 명령
- `services/api/README.md`: FastAPI 현재 API, 실행, 테스트, 산출물 보존 기준

## 검증 기록

최근 작업에서 확인한 검증 결과는 다음과 같다.

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| Windows Core 빌드 | `dotnet build apps\windows\src\FlowNote.Windows.Core\FlowNote.Windows.Core.csproj -p:UseSharedCompilation=false` | 통과 |
| Windows WPF 앱 빌드 | `dotnet build apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj -p:UseSharedCompilation=false` | 통과 |
| Windows smoke test | `dotnet run --project apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj -p:UseSharedCompilation=false` | 통과 |
| API 정적 검사 | `.venv\Scripts\python.exe -m ruff check .` | 통과 |
| API 컴파일 확인 | `.venv\Scripts\python.exe -m compileall app tests` | 통과 |
| FastAPI 전체 테스트 | `.venv\Scripts\python.exe -m pytest` | 통과, `9 passed` |

## 보존 대상

요청 기준에 따라 테스트 SQLite DB, 테스트 로그, 샘플 파일, 테스트 업로드 저장소는 삭제하지 않았다. 특히 다음 경로는 검증 산출물로 남긴다.

- `apps/windows/src/FlowNote.Windows.App/Data/flownote.local.sqlite`
- `apps/windows/src/FlowNote.Windows.App/Data/Files/Samples/`
- `services/api/data/flownote.test.sqlite3`
- `services/api/data/test-artifacts/`
- `services/api/storage/document-registration-tests/`
- `services/api/storage/field-note-tests/`

## 후속 작업 후보

- 서버 인증/권한과 세션 API 추가
- WPF 로컬 FieldNote와 서버 FieldNote API 동기화
- FieldNote 사진 첨부와 태그 연결
- 문서 다운로드/열람 권한, 감사 로그, 뷰어 자동 닫힘 정책 구현
- 관리자 파일 감시와 새 버전 업로드 보조 흐름 구현
- 보고서 초안 생성과 ReportSource 연결
