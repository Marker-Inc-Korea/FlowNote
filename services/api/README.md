# API Service

FlowNote Python FastAPI 서버 영역이다.

## 예상 책임

- 문서 등록, 조회, 다운로드
- 문서 버전 관리와 변경 사유 기록
- 현장 단말기용 최신 문서 제공
- 관리자 파일 변경 감지 결과 수신
- 권한, 이력, 접근 로그 관리
- 현장 코멘트와 정형 문구 관리
- 작업내역과 보고서 관리
- AI 검색과 작업 조언 API 제공
- SQLite 우선 메타데이터 저장
- 필요 시 PostgreSQL 전환
- 서버 PC 로컬 `storage/` 폴더 기반 파일 저장

API 초안은 [docs/api.md](../../docs/api.md)를 기준으로 한다.

## 로컬 개발

새 개발 방향의 백엔드는 Python을 기준으로 한다.

로컬 테스트 DB는 SQLite 파일을 우선 사용한다.

Python 서버 스캐폴딩을 추가할 때 기준은 다음과 같다.

```text
Language: Python FastAPI
API base path: /api/v1
Metadata DB: SQLite first, PostgreSQL later if needed
File storage: local storage folder on the server PC
File upload: multipart/form-data
Config: local .env, committed secrets 금지
```

## 디렉터리

- `app/`: Python API 애플리케이션
- `app/api/v1/`: `/api/v1` 라우트
- `app/core/`: 설정과 공통 인프라
- `data/`: 로컬 SQLite DB 생성 위치. 실제 DB 파일은 커밋하지 않음
- `storage/`: 서버 로컬 파일 저장 위치. 실제 업로드 파일은 커밋하지 않음
- `db/`: 향후 SQLite 마이그레이션 또는 스키마 메모 위치
- `tests/`: Python API 테스트

## 실행 후보

의존성을 설치한 환경에서는 다음 형태로 로컬 FastAPI 서버를 실행한다.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

현재 Python 스캐폴딩에 포함된 API:

- `GET /`
- `GET /api/v1/health`

개발용 계정과 비밀번호는 실제 구현 시 로컬 시드 데이터 또는 개발 전용 설정으로만 관리한다. 실제 사용자 계정, 비밀번호, 토큰, API 키, DB 접속 정보는 커밋하지 않는다.
