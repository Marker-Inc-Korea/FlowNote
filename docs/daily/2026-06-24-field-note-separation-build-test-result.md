# 2026-06-24 FieldNote 분리 설계 및 검증 결과

## 작업 목적

현재 WPF 로컬 앱의 코멘트가 `document_versions.comment`에 누적되던 흐름을 FieldNote 원천 이력 구조로 분리할 준비를 했다. 목표는 문서 파일 개정 이력과 현장 코멘트 이력을 분리하고, 오프라인 WPF 입력을 먼저 로컬 SQLite에 안전하게 남긴 뒤 향후 FastAPI 서버 동기화로 확장할 수 있게 만드는 것이다.

## WPF 오프라인 최소 구현

WPF 로컬 SQLite에 `field_notes` 최소 테이블을 추가했다.

| 필드 그룹 | 내용 |
| --- | --- |
| 연결 대상 | `document_id`, `document_version_no` |
| 입력 원천 | `note_type`, `input_mode`, `signal_level`, `raw_content`, `entry_source` |
| 작성 주체 | `author_name`, `reported_by`, `operator_name`, `device_id`, `location_code` |
| 관리자 정리 후보 | `normalized_content`, `analysis_content`, `status` |
| 동기화 후보 | `note_id`, `created_at`, `synced_at` |

WPF 문서 보기 화면의 새 코멘트 저장은 `FieldNoteService.AddDocumentNote`를 사용한다. 이 흐름은 문서 버전을 증가시키지 않고 `field_notes`에 원천 코멘트를 저장한다. 문서 목록에서 빠르게 볼 수 있도록 `documents.latest_comment`와 `documents.updated_at`만 갱신한다.

기존 로컬 DB에 남아 있는 `document_versions.comment` 데이터는 앱 초기화 시 `field_notes`로 백필한다. 테스트 SQLite DB, 샘플 파일, 기존 테스트 기록을 삭제하지 않고 이어가기 위한 호환 경로이다.

## FastAPI 최소 구현

FastAPI에는 서버 FieldNote 최소 API를 추가했다.

| Method | Path | 역할 |
| --- | --- | --- |
| POST | `/api/v1/field-notes` | 현장 코멘트 원천 이력 등록 |
| GET | `/api/v1/field-notes` | 전체/문서별/상태별 목록 조회 |
| GET | `/api/v1/field-notes/{noteId}` | 단일 코멘트 조회 |
| PATCH | `/api/v1/field-notes/{noteId}` | 관리자 정리, 분석, 상태 갱신 |
| GET | `/api/v1/documents/{documentId}/field-notes` | 문서별 현장 코멘트 조회 |

현재 API는 인증/권한 적용 전 단계이다. `documentId`가 들어오면 서버의 `documents` 존재 여부를 확인하고, `documentVersionId`가 들어오면 기존 `document_versions.version_id`와의 연결을 확인한다.

## 확장 흐름

```text
WPF 오프라인 입력
  -> local SQLite field_notes
  -> documents.latest_comment 요약 갱신
  -> synced_at IS NULL 항목이 서버 동기화 후보

FastAPI 동기화 후보
  -> POST /api/v1/field-notes
  -> 서버 SQLite field_notes
  -> 관리자 검토 PATCH
  -> 후속 ReportSource / Report / AI 검색 근거로 확장
```

후속 작업은 WPF 로컬 `field_notes.synced_at` 기준 동기화 큐, 서버 note ID 매핑, 사진 첨부, 태그 연결, 충돌 처리, 권한/감사 로그이다.

## 변경 파일 요약

| 영역 | 파일 |
| --- | --- |
| WPF 로컬 DB | `apps/windows/src/FlowNote.Windows.Core/Storage/FlowNoteLocalDatabase.cs` |
| WPF FieldNote 서비스 | `apps/windows/src/FlowNote.Windows.Core/FieldNotes/FieldNoteRecord.cs`, `apps/windows/src/FlowNote.Windows.Core/FieldNotes/FieldNoteService.cs` |
| WPF 서비스 연결 | `apps/windows/src/FlowNote.Windows.Core/Storage/FlowNoteLocalServices.cs` |
| WPF 화면 흐름 | `apps/windows/src/FlowNote.Windows.App/DocumentViewWindow.xaml.cs`, `apps/windows/src/FlowNote.Windows.App/MainWindow.xaml.cs` |
| Windows 테스트 | `apps/windows/src/FlowNote.Windows.SmokeTests/Program.cs` |
| FastAPI API | `services/api/app/api/v1/field_notes.py`, `services/api/app/api/v1/router.py` |
| FastAPI 테스트 | `services/api/tests/test_field_notes_api.py` |
| 제품 문서 | `docs/data-model.md`, `docs/api.md`, `docs/system-map.md`, `docs/decisions.md` |

## 검증 결과

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| Windows Core 빌드 | `dotnet build apps\windows\src\FlowNote.Windows.Core\FlowNote.Windows.Core.csproj -p:UseSharedCompilation=false` | 통과, 경고 0개, 오류 0개 |
| Windows WPF 앱 빌드 | `dotnet build apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj -p:UseSharedCompilation=false` | 통과, 경고 0개, 오류 0개 |
| Windows smoke test | `dotnet run --project apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj -p:UseSharedCompilation=false` | 통과, `FlowNote Windows smoke tests passed.` |
| API 정적 검사 | `.venv\Scripts\python.exe -m ruff check .` | 통과, `All checks passed!` |
| API 컴파일 확인 | `.venv\Scripts\python.exe -m compileall app tests` | 통과 |
| FastAPI 전체 테스트 | `.venv\Scripts\python.exe -m pytest` | 통과, `9 passed in 1.37s` |

초기 병렬 빌드에서는 `VBCSCompiler`가 `FlowNote.Windows.Core.dll` 산출물을 잡아 WPF 앱 빌드가 한 차례 실패했다. 이후 공유 컴파일을 끈 순차 빌드로 재검증했고 통과했다. pytest도 처음에는 작업 디렉터리 기준 가상환경 경로를 잘못 지정해 전역 Python에서 `pytest`를 찾지 못했으나, `services/api/.venv/Scripts/python.exe`로 다시 실행해 통과했다.

## 보존한 산출물

요청에 따라 테스트 SQLite DB, 테스트 로그, 샘플 파일, 업로드 저장 파일은 삭제하지 않았다. 이번 테스트로 기존 `services/api/data/flownote.test.sqlite3`, `services/api/storage/document-registration-tests/`, `services/api/storage/field-note-tests/`, WPF 로컬 샘플/DB 파일은 보존된다.
