# 2026-06-24 문서 등록 로컬 저장 구축 결과

## 작업 범위

FastAPI 서버에 문서 메타데이터, 파일 저장, 문서 버전, 변경 사유를 로컬 SQLite와 서버 PC `storage/` 폴더에 저장하는 기본 API를 추가했다.

- `POST /api/v1/documents`: 문서와 최초 버전 등록
- `GET /api/v1/documents`: 문서 목록 조회
- `GET /api/v1/documents/{documentId}`: 문서 상세와 최신 버전 조회
- `GET /api/v1/documents/{documentId}/versions`: 버전 목록 조회
- `POST /api/v1/documents/{documentId}/versions`: 새 버전 업로드

파일 바이너리는 DB에 넣지 않고 로컬 저장소에 둔다. SQLite에는 `FileObject`, `Document`, `DocumentVersion`으로 저장 키, 원본 파일명, 파일 계열, 크기, SHA-256 해시, 버전 번호, 변경 사유를 기록한다.

## 구현 내용

- `services/api/app/core/storage.py`
  - 업로드 파일을 `storage/documents/{document_id}/v{version_no}/` 아래에 저장
  - SHA-256, 파일 크기, 확장자, 파일 계열 계산
  - PDF, Excel, 이미지, 텍스트, Office, 도면 계열 기본 분류
- `services/api/app/api/v1/documents.py`
  - 문서 등록, 목록, 상세, 버전 목록, 버전 등록 API 구현
  - `changeReason` 공백 입력 거부
  - 새 버전 등록 시 기존 최신 버전을 `SUPERSEDED`로 표시
- `services/api/pyproject.toml`
  - multipart 업로드 처리용 `python-multipart` 추가
  - 테스트 샘플 생성을 위한 `reportlab`, `pillow` dev 의존성 추가
- `services/api/tests/test_documents_api.py`
  - 제조업 현장 샘플 PDF, 기존 제조업 Excel 샘플, 현장 사진형 PNG를 사용한 실제 multipart 등록 테스트 추가
  - 저장 파일 존재, SQLite 기록, 버전 증가, 변경 사유, SHA-256, 파일 크기 검증

## 테스트 산출물 보존

사용자 요청에 따라 테스트 DB, 테스트 로그, 샘플 파일, 업로드 저장 파일은 삭제하지 않았다.

- 테스트 SQLite DB: `services/api/data/flownote.test.sqlite3`
- 테스트 샘플/로그: `services/api/data/test-artifacts/document-registration-2026-06-24/`
- 업로드 저장 파일: `services/api/storage/document-registration-tests/`
- 최근 등록 로그 예시: `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-110145/e5df64de/document-registration-log.txt`

2026-06-24 11:01 기준 확인:

| 항목 | 결과 |
| --- | --- |
| 테스트 DB 크기 | 266,240 bytes |
| 테스트 샘플/로그 파일 수 | 26 |
| 업로드 저장 파일 수 | 12 |
| SQLite `documents` 수 | 16 |
| SQLite `document_versions` 수 | 18 |
| SQLite `file_objects` 수 | 18 |

반복 테스트와 실패 테스트에서 생성된 산출물도 검증 기록으로 남겨 두었다.

## 검증 결과

작업 위치: `services/api`

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| 개발 의존성 설치 | `.\\.venv\\Scripts\\python -m pip install -e ".[dev]"` | 통과 |
| 정적 검사 | `.\\.venv\\Scripts\\python -m ruff check .` | 통과, `All checks passed!` |
| 컴파일 확인 | `.\\.venv\\Scripts\\python -m compileall app tests` | 통과 |
| 전체 테스트 | `.\\.venv\\Scripts\\python -m pytest -q` | 통과, `4 passed in 1.68s` |
| Windows 앱 빌드 | `dotnet build apps\\windows\\src\\FlowNote.Windows.App\\FlowNote.Windows.App.csproj` | 통과, 경고 1개 |
| Windows 스모크 테스트 | `dotnet run --project apps\\windows\\src\\FlowNote.Windows.SmokeTests\\FlowNote.Windows.SmokeTests.csproj` | 통과, `FlowNote Windows smoke tests passed.` |

초기 테스트에서 `ownerId`와 `createdBy`가 `user_accounts` 외래 키를 참조하는데 테스트 계정을 먼저 만들지 않아 SQLite FK 오류가 발생했다. 테스트 시작 시 `user-test-admin` 계정을 보장하도록 수정한 뒤 전체 테스트를 다시 통과시켰다.

Windows 빌드와 스모크 테스트를 처음 병렬로 실행했을 때 `FlowNote.Windows.Core.dll` 파일 잠금으로 스모크 테스트 빌드가 실패했다. 앱 빌드가 끝난 뒤 스모크 테스트를 단독 실행하니 통과했다. 병렬 빌드 충돌로 판단하며 코드 수정은 필요하지 않았다.

## 확인된 제한

- 인증/로그인 API는 아직 구현하지 않았다. 현재 문서 API는 테스트 계정 또는 이미 존재하는 사용자 ID를 전제로 한다.
- `tags`, `links`, 문서 권한, 다운로드 제한, 접근 로그 API는 아직 구현하지 않았다.
- Excel 샘플은 스프레드시트 전용 `@oai/artifact-tool` 런타임을 사용할 수 없어 새로 저작하지 않고, 기존 Windows 앱 샘플 `.xlsx`를 테스트 산출물로 복사해 등록 검증에 사용했다.
- PDF 생성은 ReportLab으로 수행했고 업로드/해시 검증까지 완료했다. 현재 셸에서 Poppler `pdftoppm`을 찾을 수 없어 PDF 렌더 이미지 검증은 수행하지 못했다.
