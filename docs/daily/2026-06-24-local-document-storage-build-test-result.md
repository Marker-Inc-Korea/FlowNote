# 2026-06-24 문서 로컬 저장 빌드 및 테스트 결과

## 목적

FlowNote 핵심 기능인 문서 메타데이터, 실제 파일 저장, 문서 버전, 변경 사유가 로컬 SQLite와 서버 PC 로컬 storage에 저장되는지 확인했다.

이번 점검에서는 제조 현장에서 사용할 만한 샘플 문서 파일을 실제 multipart 업로드 대상으로 사용했다.

- PDF: 프레스 A 금형 교환 작업표준서, v2 변경본
- Excel: 프레스 A 설비점검표
- Image: 포장라인 라벨 검사 현장 이미지

테스트 중 생성된 SQLite DB, 테스트 로그, 샘플 파일, 업로드 저장 파일은 삭제하지 않았다.

## 확인한 구현 범위

- `services/api/app/core/storage.py`
  - 업로드 파일을 `storage/documents/{document_id}/v{version_no}/` 아래에 저장
  - 원본 파일명, 확장자, MIME 타입, 파일 계열, 크기, SHA-256 해시 계산
- `services/api/app/api/v1/documents.py`
  - `POST /api/v1/documents`
  - `GET /api/v1/documents`
  - `GET /api/v1/documents/{document_id}`
  - `GET /api/v1/documents/{document_id}/versions`
  - `POST /api/v1/documents/{document_id}/versions`
- `services/api/app/db/models.py`
  - `file_objects`, `documents`, `document_versions`에 메타데이터와 버전 이력 저장
  - 새 버전 등록 시 이전 최신 버전을 `SUPERSEDED`로 전환
  - `change_reason` 공백 입력 거부

## 테스트 산출물 보존 위치

- 테스트 SQLite DB: `services/api/data/flownote.test.sqlite3`
- 테스트 샘플 및 등록 로그: `services/api/data/test-artifacts/document-registration-2026-06-24/`
- API 업로드 저장 파일: `services/api/storage/document-registration-tests/`

이번 실행에서 확인한 대표 산출물:

- `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-120132/594868e1/document-registration-log.txt`
- `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-120132/594868e1/sample-files/작업표준서-프레스A-금형교환.pdf`
- `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-120132/594868e1/sample-files/작업표준서-프레스A-금형교환-v2.pdf`
- `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-120132/594868e1/sample-files/문서-설비점검표-프레스A.xlsx`
- `services/api/data/test-artifacts/document-registration-2026-06-24/20260624-120132/594868e1/sample-files/사진-포장라인-라벨검사.png`

## SQLite 확인 결과

`services/api/data/flownote.test.sqlite3` 기준:

| 항목 | 값 |
| --- | ---: |
| DB 크기 | 315,392 bytes |
| `documents` 행 수 | 54 |
| `document_versions` 행 수 | 63 |
| `file_objects` 행 수 | 63 |
| 업로드 저장 파일 수 | 50 |

행 수와 저장 파일 수에는 이전 테스트 실행에서 보존된 기록도 포함된다.

## 파일 점검 결과

| 파일 유형 | 점검 내용 | 결과 |
| --- | --- | --- |
| PDF | `%PDF-` 헤더, `%%EOF` 마커, API 등록, SHA-256/크기 비교 | 통과 |
| Excel | XLSX ZIP 필수 파트(`[Content_Types].xml`, `xl/workbook.xml`, `xl/worksheets/sheet1.xml`) 존재 | 통과 |
| Image | Pillow로 PNG 열기 및 `900x600` 크기 확인 | 통과 |

Poppler `pdftoppm`과 `pdfinfo`는 현재 PATH에서 찾지 못해 PDF 렌더 PNG 검증은 수행하지 못했다. PDF는 ReportLab 생성 파일의 구조 검증과 API 업로드 후 해시/크기 검증으로 확인했다.

## 실행한 검증

작업 위치: `services/api`

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| Python 정적 검사 | `.\\.venv\\Scripts\\python -m ruff check .` | 통과, `All checks passed!` |
| Python 컴파일 | `.\\.venv\\Scripts\\python -m compileall app tests` | 통과 |
| API 전체 테스트 | `.\\.venv\\Scripts\\python -m pytest -q` | 통과, `6 passed in 2.86s` |

작업 위치: 저장소 루트

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| Windows 앱 빌드 | `dotnet build apps\\windows\\src\\FlowNote.Windows.App\\FlowNote.Windows.App.csproj` | 통과, 경고 0개 / 오류 0개 |
| Windows 스모크 테스트 | `dotnet run --project apps\\windows\\src\\FlowNote.Windows.SmokeTests\\FlowNote.Windows.SmokeTests.csproj` | 통과, `FlowNote Windows smoke tests passed.` |

## 특이사항

처음 Windows 앱 빌드와 스모크 테스트를 동시에 실행했을 때 `VBCSCompiler`가 `FlowNote.Windows.Core.dll`을 잠가 빌드가 실패했다. `dotnet build-server shutdown`으로 빌드 서버를 정리한 뒤 빌드와 스모크 테스트를 단독 실행했으며 둘 다 통과했다.

이 문제는 병렬 실행 중 파일 잠금으로 판단되며, 코드 수정은 필요하지 않았다.
