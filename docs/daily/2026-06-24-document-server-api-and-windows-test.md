# 2026-06-24 문서 서버 API 및 Windows 연동 검증

## 작업 범위

FlowNote 핵심 문서 처리 흐름을 FastAPI 서버 기준으로 보강했다.

- 문서 등록 API가 문서 메타데이터, 최초 파일 객체, 최초 버전, 변경 사유를 함께 저장한다.
- 문서 목록, 상세, 버전 목록, 새 버전 등록 API가 서버 SQLite와 로컬 `storage/` 파일 저장소를 기준으로 동작한다.
- `ownerId`, `createdBy`가 전달될 경우 실제 `user_accounts.user_id`인지 먼저 검증해 SQLite FK 오류 대신 422 응답을 반환한다.
- DB 저장 제약 오류가 발생하면 방금 저장한 업로드 파일을 정리해 `file_objects`와 `storage/`가 어긋나는 상황을 줄인다.
- 인증 API가 아직 없는 현재 단계에서는 `ownerId`, `createdBy`를 생략한 문서 등록을 허용한다.
- Windows Core에 FastAPI 문서 API 호출용 `FlowNoteServerDocumentClient`를 추가했다.
- Windows smoke test는 `FLOWNOTE_API_BASE_URL`이 있을 때 실제 FastAPI 서버에 파일을 업로드하고 목록/버전 조회까지 검증한다.

## 변경 파일

| 파일 | 내용 |
| --- | --- |
| `services/api/app/api/v1/documents.py` | 사용자 ID 검증, optional 입력 정리, DB 제약 오류 시 저장 파일 정리 |
| `services/api/tests/test_documents_api.py` | 사용자 생략 등록, 알 수 없는 사용자 참조 거절, storage 미저장 검증 추가 |
| `apps/windows/src/FlowNote.Windows.Core/ServerApi/FlowNoteServerDocumentClient.cs` | Windows Core에서 FastAPI 문서 등록/목록/버전 조회 호출 |
| `apps/windows/src/FlowNote.Windows.Core/ServerApi/ServerDocumentContracts.cs` | 서버 문서 API 응답 DTO |
| `apps/windows/src/FlowNote.Windows.SmokeTests/Program.cs` | FastAPI 서버 연동 smoke test 경로 추가 |

## 검증 결과

작업 위치는 저장소 루트와 API 폴더 `services/api`이다.

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| API 정적 검사 | `.\\.venv\\Scripts\\python.exe -m ruff check .` | 통과, `All checks passed!` |
| API 컴파일 확인 | `.\\.venv\\Scripts\\python.exe -m compileall app tests` | 통과 |
| API 전체 테스트 | `.\\.venv\\Scripts\\python.exe -m pytest` | 통과, `6 passed in 3.47s` |
| Windows 앱 빌드 | `dotnet build apps\\windows\\src\\FlowNote.Windows.App\\FlowNote.Windows.App.csproj` | 통과, 경고 0개, 오류 0개 |
| Windows 로컬 smoke test | `dotnet run --project apps\\windows\\src\\FlowNote.Windows.SmokeTests\\FlowNote.Windows.SmokeTests.csproj` | 통과, `FlowNote Windows smoke tests passed.` |
| FastAPI 실제 서버 + Windows 연동 smoke test | FastAPI를 `http://127.0.0.1:5185/`에 실행 후 `FLOWNOTE_API_BASE_URL` 지정 | 통과, `FlowNote Windows smoke tests passed.` |

실제 서버 연동 검증은 다음 조건으로 수행했다.

- `FLOWNOTE_ENVIRONMENT=integration`
- `FLOWNOTE_DATABASE_URL=sqlite:///./data/flownote.integration.sqlite3`
- `FLOWNOTE_STORAGE_ROOT=./storage/integration-tests`
- FastAPI 실행: `.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5185`
- Windows smoke test는 `sample-upload.txt`를 서버 `POST /api/v1/documents`로 업로드한 뒤 `GET /api/v1/documents`, `GET /api/v1/documents/{documentId}/versions`를 확인했다.

## 산출물 보존

요청에 따라 테스트 SQLite DB, 테스트 로그, 샘플 파일, 업로드 저장 파일은 삭제하지 않았다.

2026-06-24 11:29 기준 확인 수치:

| 위치 | 상태 |
| --- | --- |
| `services/api/data/flownote.test.sqlite3` | 307,200 bytes, `documents=42`, `document_versions=49`, `file_objects=49` |
| `services/api/data/flownote.integration.sqlite3` | 258,048 bytes, `documents=3`, `document_versions=3`, `file_objects=3` |
| `services/api/storage/document-registration-tests/` | 파일 38개 |
| `services/api/storage/integration-tests/` | 파일 3개 |
| `services/api/data/integration-logs/` | 로그 6개 |

마지막 실제 서버 검증 로그:

- `services/api/data/integration-logs/fastapi-20260624-112947.out.log`
- `services/api/data/integration-logs/fastapi-20260624-112947.err.log`

`fastapi-20260624-112947.err.log`에는 Uvicorn 시작 로그만 기록되었고 애플리케이션 예외는 확인되지 않았다.

## 남은 제한

- 서버 인증/세션 API는 아직 없다. 현재 문서 API는 인증 전 단계의 등록/목록/버전 저장 흐름 검증용이다.
- Windows WPF 화면은 아직 기본 로컬 SQLite 작업 공간을 사용한다. 이번 변경은 Windows Core에서 FastAPI 문서 API를 호출하고 smoke test로 검증하는 기반이다.
- 태그, 링크, 권한, 다운로드 차단, 접근 감사 로그 API는 후속 구현 범위이다.
