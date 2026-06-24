# API Service

FlowNote Python FastAPI 서버 영역이다.

## 현재 구현 상태

현재 서버는 SQLite MVP 초기 구현 단계이다. 제품 전체 범위 중 문서 등록, 문서 버전 등록, 서버 로컬 파일 저장, FieldNote 원천 이력 API의 최소 흐름을 검증한다.

구현된 API:

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

문서 등록 API는 `multipart/form-data`로 파일과 메타데이터를 받고, 파일을 서버 로컬 `storage/documents/{document_id}/v{version_no}/` 아래에 저장한다. SQLite에는 `documents`, `document_versions`, `file_objects`를 통해 문서 상태, 버전 번호, 변경 사유, 원본 파일명, 저장 키, 확장자, MIME, 파일 계열, 크기, SHA-256 해시를 기록한다.

FieldNote API는 문서 파일 개정 이력과 현장 코멘트 이력을 분리하기 위한 최소 구현이다. 문서 또는 문서 버전을 참조하는 원천 코멘트를 저장하고, 관리자 검토/분석 내용과 상태를 갱신할 수 있다.

현재 구현되지 않은 범위:

- 로그인/세션/권한 API
- 다운로드 차단과 문서 열람 감사 로그의 실제 적용
- WPF 로컬 FieldNote와 서버 FieldNote API 자동 동기화
- 파일 감시 결과 수신
- 보고서 생성, 작업순서판, AI 검색/조언 API
- MES/ERP 연동

상세 API 계약과 미래 API 초안은 [docs/api.md](../../docs/api.md)를 기준으로 한다.

## 로컬 개발

기준 스택:

```text
Language: Python FastAPI
API base path: /api/v1
Metadata DB: SQLite first, PostgreSQL later if needed
File storage: local storage folder on the server PC
File upload: multipart/form-data
Config: local .env, committed secrets 금지
```

로컬 실행 예:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

개발 DB 기본값:

- `FLOWNOTE_DATABASE_URL`: 기본 `sqlite:///./data/flownote.sqlite3`
- `FLOWNOTE_TEST_DATABASE_URL`: 기본 `sqlite:///./data/flownote.test.sqlite3`
- `FLOWNOTE_STORAGE_ROOT`: 기본 `./storage`

실제 사용자 계정, 비밀번호, 토큰, API 키, 운영 DB 접속 정보는 커밋하지 않는다.

## 디렉터리

- `app/`: Python API 애플리케이션
- `app/api/v1/`: `/api/v1` 라우트
- `app/core/`: 설정, 파일 저장, 공통 인프라
- `app/db/`: SQLAlchemy 모델, 세션, 초기화
- `data/`: 로컬 SQLite DB와 테스트 산출물 위치. 실제 DB 파일은 커밋하지 않는다.
- `storage/`: 서버 로컬 파일 저장 위치. 실제 업로드 파일은 커밋하지 않는다.
- `db/`: 스키마 메모와 마이그레이션 기록
- `tests/`: Python API 테스트

## 검증

```powershell
cd services\api
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m pytest
```

최근 검증 결과는 [docs/daily/2026-06-24-current-work-summary.md](../../docs/daily/2026-06-24-current-work-summary.md)와 개별 작업 기록을 기준으로 한다.

## 보존 대상

테스트 SQLite DB, 테스트 로그, 테스트 업로드 파일, 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.

대표 보존 경로:

- `data/flownote.test.sqlite3`
- `data/test-artifacts/`
- `storage/document-registration-tests/`
- `storage/field-note-tests/`
