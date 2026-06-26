# 2026-06-26 Windows smoke server blocks

## 작업 범위

- Windows smoke test에 서버 로그인 API, 서버 FieldNote 등록, 서버 문서 접근 로그 등록/조회 검증 블록을 분리해 추가했다.
- `FLOWNOTE_API_BASE_URL`이 없거나 유효하지 않으면 서버 연동 블록을 건너뛰고 로컬 SQLite 검증은 계속 진행하는 기존 방식을 유지했다.
- FastAPI에 `POST /api/v1/documents/{documentId}/access-logs`, `GET /api/v1/documents/{documentId}/access-logs`를 추가했다.
- Windows Core 서버 문서 클라이언트에 문서 접근 로그 등록/조회 계약을 추가했다.
- API 문서, Windows README, MVP/제품 현재 구현 상태 문서를 갱신했다.

## 변경 파일

| 파일 | 내용 |
| --- | --- |
| `services/api/app/api/v1/document_access_logs.py` | 문서 접근 로그 등록/조회 API 추가 |
| `services/api/app/api/v1/router.py` | 문서 접근 로그 라우터 등록 |
| `services/api/tests/test_document_access_logs_api.py` | 접근 로그 생성/조회와 다른 문서 버전 거부 pytest 추가 |
| `apps/windows/src/FlowNote.Windows.Core/ServerApi/FlowNoteServerDocumentClient.cs` | 서버 접근 로그 등록/조회 메서드 추가 |
| `apps/windows/src/FlowNote.Windows.Core/ServerApi/ServerDocumentContracts.cs` | 서버 접근 로그 요청/응답 DTO 추가 |
| `apps/windows/src/FlowNote.Windows.SmokeTests/Program.cs` | 로그인 API, FieldNote 등록, 문서 접근 로그 서버 검증 블록 추가 |
| `docs/api.md` | 현재 구현 API와 문서 접근 로그 계약 갱신 |
| `apps/windows/README.md` | 서버 클라이언트와 smoke 검증 범위 갱신 |
| `docs/mvp-scope.md` | 현재 구현/미구현 범위 보정 |
| `docs/product-overview.md` | FastAPI 현재 구현 범위 보정 |

## 검증 결과

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| FastAPI pytest | `.\.venv\Scripts\python.exe -m pytest` in `services/api` | 통과, `16 passed in 1.77s` |
| Windows App build | `dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj` | 통과, 경고 0개, 오류 0개 |
| Windows smoke build | `dotnet build .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj` | 통과, 경고 0개, 오류 0개 |
| Windows smoke test + FastAPI 연동 | `FLOWNOTE_API_BASE_URL=http://127.0.0.1:5185` 지정 후 `dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj` | 통과, `FlowNote Windows smoke tests passed.` |
| Windows smoke test 로컬 폴백 | `FLOWNOTE_API_BASE_URL` 제거 후 `dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj` | 통과, 서버 연동 블록 skip 메시지 확인 후 `FlowNote Windows smoke tests passed.` |

## 서버 연동 검증 조건

- 기존 `5184` 포트는 사용 중이라 건드리지 않았다.
- 현재 코드 검증용 FastAPI 서버를 `127.0.0.1:5185`에서 임시 실행했다.
- smoke test 완료 후 이번 작업에서 띄운 `5185` 서버 프로세스만 종료했다.
- 서버 로그는 테스트 기록으로 보존한다.

## 보존 산출물

삭제하지 않은 산출물:

- Windows smoke SQLite DB: `apps/windows/src/FlowNote.Windows.App/Data/flownote.local.sqlite`
- Windows smoke 샘플 파일: 사용자별 임시 폴더 아래 `flownote-program-test-files\`
- FastAPI pytest DB: `services/api/data/flownote.test.sqlite3`
- FastAPI pytest storage: `services/api/storage/`
- FastAPI smoke 서버 로그: `services/api/data/test-artifacts/server-smoke-2026-06-26/uvicorn-5185-out.log`, `services/api/data/test-artifacts/server-smoke-2026-06-26/uvicorn-5185-err.log`

## 메모

- `document_access_logs.device_id`는 서버 DB의 `terminal_devices.device_id`를 참조한다. 현재 smoke test는 임의 단말 ID를 만들지 않으므로 `deviceId`를 보내지 않고 문서, 문서 버전, actor, action 중심으로 검증한다.
- 서버 접근 로그 API는 아직 JWT/세션 인증과 역할 기반 권한 검사를 적용하지 않는다. 현재 단계에서는 서버 연동 계약과 DB 저장 흐름 검증용이다.
