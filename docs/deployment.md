# FlowNote 배포

## 기준

FlowNote의 기본 배포 형태는 사내 단일 서버 PC 운영과 Windows WPF 설치형 클라이언트 배포이다. 클라우드, 외부 접근, 일반 브라우저 직접 사용은 초기 기준이 아니며 별도 협의가 필요한 후속 선택지다.

```text
Server PC
  -> FastAPI server
  -> SQLite DB
  -> local storage/ folder

Client PCs
  -> Windows WPF installed app
  -> local SQLite DB and local Files/ folder
  -> API connection to Server PC when FLOWNOTE_API_BASE_URL is set
```

WPF 앱은 로컬 SQLite에 먼저 기록하고 서버 URL이 설정되어 있으면 서버 동기화를 시도한다. 서버 호출 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다.

## 운영 설치 경로

운영 설치 시 경로는 고객사 서버 PC에서 명시적으로 만든 고정 폴더를 사용한다. 아래 경로는 기준 예시이며, 실제 현장에서는 드라이브만 바꿔도 같은 구조를 유지한다.

```text
C:\FlowNote\
  Server\
    api\                  FastAPI 서버 코드와 실행 환경
    data\                 서버 SQLite
      flownote.sqlite3
    storage\              서버 문서 파일, 첨부, 보고서 파일
    logs\                 서버 실행 로그
    .env                  서버 운영 환경 변수, Git 제외
  Client\
    FlowNote.Windows.App\ WPF 앱 설치 폴더
  LocalData\
    flownote.local.sqlite WPF 공통 SQLite
    Files\                WPF 로컬 파일 복사본과 첨부
```

서버 PC에 WPF 앱도 함께 설치해 관리자 작업을 수행하는 경우 `C:\FlowNote\LocalData`를 공통 로컬 데이터 폴더로 사용한다. 현장 클라이언트 PC는 각 PC의 로컬 데이터 폴더를 사용하되, 서버 동기화가 필요한 경우 `FLOWNOTE_API_BASE_URL`만 서버 주소로 맞춘다.

## 운영 환경 변수

운영에서는 상대 경로보다 절대 경로를 사용한다. 환경 변수는 Windows 시스템 환경 변수, 서비스 계정 환경 변수, 또는 Git에 포함하지 않는 `.env`에 둔다.

| 구분 | 변수 | 운영 기준 |
| --- | --- | --- |
| 서버 | `FLOWNOTE_DATABASE_URL` | `sqlite:///C:/FlowNote/Server/data/flownote.sqlite3` |
| 서버 | `FLOWNOTE_STORAGE_ROOT` | `C:\FlowNote\Server\storage` |
| 서버 | `FLOWNOTE_ACCESS_TOKEN_SECRET` | 현장별 긴 비밀값. 기본값 사용 금지 |
| 서버 | `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES` | 기본 480분. 현장 보안 정책에 따라 조정 |
| 서버 | `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS` | 기본 14일. 현장 보안 정책에 따라 조정 |
| 서버 | `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES` | 기본 20971520 바이트 |
| WPF | `FLOWNOTE_LOCAL_DATA_DIR` | `C:\FlowNote\LocalData`처럼 DB와 `Files\`를 함께 둘 폴더 |
| WPF | `FLOWNOTE_LOCAL_DATABASE_PATH` | 특정 DB 파일을 직접 지정할 때만 사용. 지정 시 `FLOWNOTE_LOCAL_DATA_DIR`보다 DB 경로 우선 |
| WPF | `FLOWNOTE_API_BASE_URL` | 서버 PC 주소. 예: `http://192.168.0.10:5184` |
| WPF | `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` | 문서 뷰어 자동 닫힘 시간. 5초-3600초로 정규화 |

`FLOWNOTE_LOCAL_DATABASE_PATH`를 지정하면 WPF DB 파일 위치가 그 값으로 고정된다. 다만 로컬 파일 저장 위치는 `FLOWNOTE_LOCAL_DATA_DIR` 기준으로 관리하는 편이 운영자가 백업 대상을 이해하기 쉽다. 운영에서는 특별한 이유가 없으면 `FLOWNOTE_LOCAL_DATA_DIR`만 지정한다.

## 테스트 환경 변수

테스트와 스모크 테스트는 운영 데이터와 분리하되, 생성된 테스트 기록은 삭제하지 않는다.

| 구분 | 변수 | 테스트 기준 |
| --- | --- | --- |
| FastAPI pytest | `FLOWNOTE_TEST_DATABASE_URL` | 테스트 코드의 전용 SQLite URL. 기본값은 `sqlite:///./data/flownote.test.sqlite3` |
| FastAPI pytest | `FLOWNOTE_DATABASE_URL` | 일반 개발 실행 기본값은 `sqlite:///./data/flownote.sqlite3` |
| FastAPI pytest | `FLOWNOTE_STORAGE_ROOT` | 일반 개발 실행 기본값은 `./storage`; 테스트별 하위 폴더 사용 |
| WPF 개발/스모크 | `FLOWNOTE_LOCAL_DATA_DIR` | 지정하지 않으면 저장소 루트 `data/local` 자동 사용 |
| WPF 개발/스모크 | `FLOWNOTE_LOCAL_DATABASE_PATH` | 지정하지 않으면 `data/local/flownote.local.sqlite` 자동 사용 |
| WPF 서버 연동 스모크 | `FLOWNOTE_API_BASE_URL` | 서버 연동 블록을 검증할 때만 설정 |

Windows 앱과 Windows 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 함께 사용한다. 매 테스트마다 임시 SQLite를 새로 만들지 않고 누적된 로컬 DB를 기능 검증의 근거로 사용한다.

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

## 서버 실행 체크리스트

- `C:\FlowNote\Server\data`, `C:\FlowNote\Server\storage`, `C:\FlowNote\Server\logs` 폴더를 만든다.
- 서버 실행 계정이 `data`, `storage`, `logs`에 읽기/쓰기 권한을 갖는지 확인한다.
- `FLOWNOTE_DATABASE_URL`, `FLOWNOTE_STORAGE_ROOT`, `FLOWNOTE_ACCESS_TOKEN_SECRET`을 운영값으로 설정한다.
- FastAPI 서버를 실행하고 `/api/v1/health`와 `/api/v1/health/db`를 확인한다.
- 최초 운영 계정의 기본 비밀번호를 현장 비밀번호로 변경한다.
- 서버 PC 방화벽에서 클라이언트 PC가 접근할 포트만 허용한다.

## WPF 실행 체크리스트

- WPF 앱 설치 폴더와 `C:\FlowNote\LocalData`를 준비한다.
- `FLOWNOTE_LOCAL_DATA_DIR`을 `C:\FlowNote\LocalData`로 설정한다.
- 서버 동기화가 필요한 PC에는 `FLOWNOTE_API_BASE_URL`을 서버 주소로 설정한다.
- 앱을 실행해 로그인, 문서 목록, 문서 열람, FieldComment 등록이 되는지 확인한다.
- 문서 열람 후 자동 닫힘과 다운로드 차단 로그가 남는지 확인한다.

## 백업 체크리스트

운영 백업은 서버 데이터와 로컬 앱 데이터를 분리해서 수행한다. 백업 전에는 가능하면 서버와 WPF 앱을 종료하거나 파일 잠금이 없는 시간대에 복사한다.

- 서버 SQLite: `C:\FlowNote\Server\data\flownote.sqlite3`
- 서버 SQLite 보조 파일: 같은 폴더의 `*.sqlite3-wal`, `*.sqlite3-shm`, `*.sqlite-wal`, `*.sqlite-shm`
- 서버 파일 저장소: `C:\FlowNote\Server\storage\`
- 서버 운영 설정: `.env` 또는 서비스 환경 변수 내역. 비밀값은 백업 저장소 접근권한을 제한한다.
- 서버 로그: `C:\FlowNote\Server\logs\`
- WPF 공통 SQLite: `C:\FlowNote\LocalData\flownote.local.sqlite`
- WPF SQLite 보조 파일: 같은 폴더의 `*.sqlite-wal`, `*.sqlite-shm`
- WPF 로컬 파일: `C:\FlowNote\LocalData\Files\`

## 복구 체크리스트

- 서버와 WPF 앱을 종료한다.
- 서버 `data`와 `storage`를 같은 시점의 백업본으로 복원한다.
- `.env` 또는 서비스 환경 변수를 복원하되, 새 서버 PC의 절대 경로가 다르면 경로 값을 수정한다.
- WPF 로컬 DB와 `Files\`를 같은 시점의 백업본으로 복원한다.
- 서버를 먼저 실행하고 `/api/v1/health/db`를 확인한다.
- WPF 앱을 실행해 로그인, 문서 목록, 최근 FieldComment, 문서 열람 로그를 확인한다.

서버 DB만 복원하고 `storage\`를 누락하면 문서 메타데이터는 있으나 파일을 열 수 없다. 반대로 `storage\`만 복원하고 DB를 누락하면 파일 소유 관계와 버전 이력을 추적할 수 없다. 두 대상은 같은 백업 세트로 관리한다.

## 장애 시 보존 파일

장애 분석 전에는 다음 파일과 폴더를 삭제하지 않는다.

- 서버 SQLite와 WAL/SHM 파일
- 서버 `storage\` 전체
- 서버 로그와 실행 콘솔 출력
- WPF `flownote.local.sqlite`와 WAL/SHM 파일
- WPF `Files\` 전체
- WPF WebView2/앱 로그가 생성된 경우 해당 로그
- 스모크 테스트 로그, 테스트 등록 메모, 렌더링 결과, 테스트 입력/출력 파일

## 커밋 제외와 보존 관계

Git 제외와 로컬 보존은 다른 기준이다. 실제 고객 문서, 운영 DB, 운영 파일 저장소, 비밀값, 개인 로컬 경로, 빌드/배포 산출물은 Git에 올리지 않는다. 그러나 테스트 SQLite, 테스트 파일, 테스트 로그, 스모크 테스트 산출물, 렌더링 결과는 기능 검증 이력이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 로컬에서 삭제하지 않는다.

현재 `.gitignore`는 빌드 산출물, 로그, 일반 SQLite, 운영/고객 파일, 로컬 파일 저장소를 제외하되 `data/local/**/*.sqlite`와 `services/api/data/**/*.sqlite`는 테스트와 개발 검증 DB로 추적될 수 있게 예외를 둔다. 커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 제외한 PDF, 이미지, Excel, TXT, 렌더링 결과, 테스트 로그, `data/local/Files/`, `Data/Files/` 하위 파일이 포함되지 않았는지 확인한다.

## 후속 배포 과제

- Windows 설치파일 패키징
- 서버 서비스 등록 방식 정리
- HTTPS 또는 사내망 접속 보호
- 운영 관리자 계정 발급과 최초 비밀번호 변경 절차
- PostgreSQL 전환 조건

## 검증 자동화

표준 검증 순서와 사후 Git 산출물 점검은 [검증 자동화 문서](./verification.md)를 따른다. 저장소 루트에서 `.\scripts\verify-preserved-tests.ps1`을 실행하면 FastAPI pytest 43개 수집/실행, WPF build, WPF smoke, `.gitignore` 산출물 제외 규칙, 실행 전후 `git status` 금지 패턴을 함께 확인한다.
