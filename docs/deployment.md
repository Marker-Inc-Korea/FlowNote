# FlowNote 배포

## 기준

FlowNote의 기본 배포 형태는 사내 서버형 운영이다.

```text
Server PC
  -> FastAPI server
  -> SQLite DB
  -> local storage/ folder

Client PCs
  -> Windows WPF installed app
  -> optional API connection to Server PC
```

클라우드, 외부 접근, 일반 브라우저 직접 사용은 초기 기준이 아니며 별도 협의가 필요한 후속 선택지다.

## 현재 개발 실행

FastAPI:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

Windows WPF:

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
```

WPF에서 서버를 사용하려면 `FLOWNOTE_API_BASE_URL`을 설정한다.

## 주요 환경 변수

서버:

- `FLOWNOTE_DATABASE_URL`
- `FLOWNOTE_TEST_DATABASE_URL`
- `FLOWNOTE_STORAGE_ROOT`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`
- `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES`

WPF:

- `FLOWNOTE_LOCAL_DATA_DIR`
- `FLOWNOTE_LOCAL_DATABASE_PATH`
- `FLOWNOTE_API_BASE_URL`
- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`

## 데이터 보존

운영 백업 대상:

- FastAPI SQLite DB
- FastAPI `storage/` 폴더
- WPF 공통 로컬 SQLite
- WPF 로컬 `Files/` 폴더
- 운영 설정과 비밀값

테스트 산출물은 삭제하지 않는 것이 프로젝트 규칙이다. 테스트 파일과 로그는 운영 데이터가 아니지만 기능 검증 이력으로 보존한다.

## 후속 배포 과제

- Windows 설치파일 패키징
- 서버 서비스 등록 방식 정리
- 운영 DB/스토리지 백업 절차
- HTTPS 또는 사내망 접속 보호
- 운영 관리자 계정 발급과 최초 비밀번호 변경 절차
- PostgreSQL 전환 조건
