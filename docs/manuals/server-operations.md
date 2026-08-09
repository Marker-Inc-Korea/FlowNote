# FlowNote 서버 설치·운영 매뉴얼

## 1. 문서 목적

이 문서는 승인된 Windows 서버 또는 Windows Pro x64 PC에 FlowNote FastAPI 서버를 배치하고 운영 상태를 확인하는 순서를 정리한다. 실제 운영 설치는 현장 승인, HTTPS 인증서, DNS, 방화벽, 백업 위치와 책임자가 확정된 뒤 수행한다.

기준일은 2026-08-13이며, 상세 환경 변수와 파일럿 증거 계약은 [배포 기준](../deployment.md)과 [파일럿 기준](../pilot-rehearsal.md)을 우선한다.

## 2. 운영 전제조건

- 승인된 서버 PC와 관리자 권한
- Windows Server 또는 Windows Pro x64
- Python 3.11 이상
- 승인된 HTTPS reverse proxy, DNS 이름과 인증서
- 서버 DB·storage·환경 파일의 접근 통제된 백업 위치
- 설치 담당자, 운영 담당자, 보안 담당자와 복구 승인자
- 서버와 클라이언트의 시간 동기화

현재 클라이언트는 HTTPS만 허용한다. FastAPI 내부 포트를 클라이언트에 직접 노출하거나 HTTP 주소를 운영 우회 경로로 사용하지 않는다.

## 3. 운영 경로

| 경로 | 내용 |
| --- | --- |
| `C:\FlowNote\Server\api` | FastAPI 코드와 운영 가상환경 |
| `C:\FlowNote\Server\data` | 서버 SQLite |
| `C:\FlowNote\Server\storage` | 서버 문서 파일 |
| `C:\FlowNote\Server\logs` | 표준·오류 로그 |
| `C:\FlowNote\Server\.env` | 서버 환경 설정과 비밀값 |
| `C:\FlowNote\LocalData` | 같은 PC에 WPF를 설치할 때 사용하는 별도 WPF 로컬 데이터 |

서버 SQLite와 WPF SQLite에 같은 파일 경로를 지정하지 않는다.

## 4. 설치 전 승인 점검

- [ ] 설치 대상 OS·CPU·디스크 여유 공간을 기록했다.
- [ ] 운영 DNS 이름과 HTTPS 인증서의 SAN이 일치한다.
- [ ] 인증서 신뢰 체인, 폐기 확인과 시간 동기화를 확인했다.
- [ ] 서버 내부 포트와 reverse proxy 외부 포트를 확정했다.
- [ ] `customer_scope`와 `site_scope`를 현장 한 곳에 맞게 확정했다.
- [ ] DB, storage와 `.env`의 백업·복구 책임자를 정했다.
- [ ] 외부 AI 호출이 비활성이라는 사실을 확인했다.
- [ ] 운영 패키지 hash, signer와 승인 번호를 운영대장에 기록했다.
- [ ] 실제 고객 자료와 자격 증명이 Git에 포함되지 않았음을 확인했다.

## 5. 서버 파일 배치

관리자 PowerShell에서 운영 폴더를 준비한다.

```powershell
New-Item -ItemType Directory -Force C:\FlowNote\Server\api
New-Item -ItemType Directory -Force C:\FlowNote\Server\data
New-Item -ItemType Directory -Force C:\FlowNote\Server\storage
New-Item -ItemType Directory -Force C:\FlowNote\Server\logs
```

승인된 소스 또는 배포본에서 API 코드와 `pyproject.toml`을 복사한다.

```powershell
Copy-Item -Recurse .\services\api\app C:\FlowNote\Server\api\
Copy-Item .\services\api\pyproject.toml C:\FlowNote\Server\api\
```

운영 가상환경과 의존성을 설치한다.

```powershell
cd C:\FlowNote\Server\api
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

## 6. 환경 설정

`C:\FlowNote\Server\.env`는 저장소 밖에서 만들고 서버 운영자만 읽을 수 있게 제한한다. 최소한 다음 범주를 확정한다.

| 범주 | 주요 변수 | 기준 |
| --- | --- | --- |
| 실행 | `FLOWNOTE_ENV`, `FLOWNOTE_API_HOST`, `FLOWNOTE_API_PORT` | `production`, reverse proxy 내부 바인딩 |
| 데이터 | `FLOWNOTE_DATABASE_URL`, `FLOWNOTE_STORAGE_ROOT` | 서버 전용 절대경로 |
| 초기 계정 | `FLOWNOTE_INITIAL_ADMIN_PASSWORD` | 빈 DB 첫 실행에만 주입하고 즉시 교체·제거 |
| 인증 | `FLOWNOTE_ACCESS_TOKEN_SECRET` | 현장별 긴 난수, 기본값 금지 |
| scope | `FLOWNOTE_CUSTOMER_SCOPE`, `FLOWNOTE_SITE_SCOPE` | 서버 한 대의 고객·현장 경계 |
| 문서 승인 | `FLOWNOTE_DOCUMENT_APPROVAL_*` | 현장 역할 분리 정책을 명시 |
| AI | `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED` | 현재 `false` 유지 |

다음 설정은 현재 운영 기준에서 활성화하지 않는다.

```text
FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false
FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=DISABLED
FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED=false
```

실제 비밀값, 고객명, 서버 주소와 인증서 경로를 이 문서나 커밋에 추가하지 않는다.

## 7. 자동 시작 등록

저장소의 설치 스크립트를 관리자 PowerShell에서 실행한다.

```powershell
.\scripts\install-flownote-server-task.ps1 `
  -ServerRoot C:\FlowNote\Server `
  -StartNow
```

스크립트는 `\FlowNote\FlowNoteApi` 작업을 `SYSTEM` 최고 권한과 부팅 트리거로 등록하고, 실행 래퍼를 `C:\FlowNote\Server\scripts`에 복사한다.

상태와 수명주기 명령은 다음과 같다.

```powershell
.\scripts\manage-flownote-server-task.ps1 -Action status
.\scripts\manage-flownote-server-task.ps1 -Action start
.\scripts\manage-flownote-server-task.ps1 -Action stop
.\scripts\manage-flownote-server-task.ps1 -Action restart
```

`unregister`는 작업 스케줄러 등록을 제거하므로 승인된 제거·재설치 절차에서만 사용한다. DB, storage와 로그는 별도 보존 대상이다.

## 8. 설치 직후 점검

### 8.1 작업과 로그

```powershell
.\scripts\manage-flownote-server-task.ps1 -Action status
Get-Content C:\FlowNote\Server\logs\flownote-api.err.log -Tail 100
```

로그에 비밀번호, 토큰과 실제 고객 문서 내용이 남지 않는지 함께 확인한다.

### 8.2 서버 내부 health

서버 PC 내부 reverse proxy 연결을 확인할 때만 loopback HTTP를 사용한다.

```powershell
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health/db
```

### 8.3 클라이언트 HTTPS

클라이언트 PC에서는 승인된 실제 HTTPS 주소로 확인한다.

```powershell
Invoke-RestMethod https://<승인된 서버 DNS 이름>/api/v1/health
Invoke-RestMethod https://<승인된 서버 DNS 이름>/api/v1/health/db
```

실패하면 서버 프로세스 → reverse proxy → 인증서 → DNS → 방화벽 → 클라이언트 시간 순서로 확인한다.

## 9. 최초 관리자와 계정 운영

빈 서버 DB를 처음 실행하기 전에 `FLOWNOTE_INITIAL_ADMIN_PASSWORD`에 8자 이상의 임시 비밀번호를 주입한다. 값이 없으면 첫 `admin` 생성을 거부한다. 초기화가 끝나면 설정에서 이 값을 제거하고, 운영 로그인 전에 서버 PC에서 비밀번호를 다시 변경한다. 비밀번호는 명령줄 인자로 전달하지 않고 대화식 프롬프트에 입력한다.

```powershell
cd C:\FlowNote\Server\api
.\.venv\Scripts\python.exe -m app.ops.server_accounts `
  reset-password --username admin
```

일반 계정은 서버 로그인한 `admin` 또는 `system-admin`이 Windows 앱의 `계정 · 단말 > 사용자 관리`에서 발급한다. 임시 비밀번호 계정은 첫 로그인에서 비밀번호 변경 후 다시 로그인해야 한다.

비상 상황에서만 서버 운영 CLI를 사용한다.

```powershell
# 상태 변경
.\.venv\Scripts\python.exe -m app.ops.server_accounts `
  set-status --username <사용자 ID> --status LOCKED

# 비밀번호 재설정
.\.venv\Scripts\python.exe -m app.ops.server_accounts `
  reset-password --username <사용자 ID>
```

계정 잠금·비활성화, role 변경과 비밀번호 재설정은 활성 세션을 폐기한다. 자기 자신 비활성화, 마지막 활성 `system-admin` 제거와 권한 상승은 서버 정책을 따른다.

## 10. 일상 운영 점검

### 매일

- 작업 스케줄러 상태와 최근 종료 코드를 확인한다.
- `/health`, `/health/db`를 확인한다.
- 오류 로그의 반복 401·403·5xx·SQLite lock과 파일 오류를 확인한다.
- 디스크 여유 공간과 storage 증가량을 확인한다.
- WPF `현장 운영 > 운영 준비도`에서 동기화 지연과 조치 필요 항목을 확인한다.

### 매주

- 활성 계정, 잠금·비활성 계정과 승인 단말 상태를 검토한다.
- 장기 미확인 인수인계와 FieldComment 검토 지연을 확인한다.
- DB와 storage 백업 세트가 같은 시점·승인 ID로 묶였는지 확인한다.
- 백업 hash, 크기와 접근 권한을 확인한다.

### 변경 전후

- 소스 커밋, 패키지 hash, signer, DB schema와 rollback 후보를 기록한다.
- 대기 중인 WPF 동기화 큐와 Android outbox를 확인한다.
- 변경 뒤 health, 로그인, 문서 조회·열람, 기록·보고서 흐름을 다시 확인한다.

## 11. 백업

하나의 백업 세트에는 최소한 다음을 포함한다.

- 서버 SQLite 본파일과 관련 WAL 상태
- 서버 `storage/`
- 접근 통제된 `.env`와 작업 스케줄러 설정 기록
- 백업 시각, 서버 instance, 패키지 hash와 승인 ID

DB와 storage를 서로 다른 시점의 사본으로 섞지 않는다. 운영 DB와 storage를 개발 PC로 내려받지 않는다.

백업을 확인할 때 파일 존재만 보지 말고 다음을 기록한다.

- SQLite `quick_check`, `integrity_check`, foreign key 결과
- 테이블별 row 수
- DB가 참조하는 파일과 실제 storage 파일의 상대경로·크기·SHA-256
- 백업 세트 ID와 복구 승인자

## 12. 복구

복구는 승인된 별도 PC 또는 격리 환경에서 먼저 수행한다.

1. 새 서버 경로와 Python 환경을 준비한다.
2. 같은 백업 세트의 DB와 storage를 복원한다.
3. 새 절대경로에 맞게 `.env`를 확인한다.
4. 서버를 시작하고 DB·storage 무결성을 확인한다.
5. WPF의 자동 동기화와 Android polling을 바로 재개하지 않는다.
6. 서버 instance·epoch와 책임 원천 manifest를 대조한다.
7. Windows `현장 운영 > 변경 이력`의 서버 재결합 절차로 업무 재개를 승인한다.
8. 로그인, 문서 공개본, FieldComment, 작업순서, 인수인계와 보고서를 확인한다.

상세 RPO/RTO와 장애 주입 절차는 [배포 문서의 운영 복구 점검표](../deployment.md#운영-복구-점검표)를 따른다.

## 13. 서버 장애 시 금지 행동

- 운영 DB나 storage를 삭제하고 새로 시작하지 않는다.
- WPF 로컬 DB·Files 또는 Android outbox를 초기화하지 않는다.
- 클라이언트를 HTTP나 로컬 FastAPI로 우회 연결하지 않는다.
- 서로 다른 시점의 DB와 storage를 임의로 조합하지 않는다.
- 원인 확인 없이 같은 요청을 새 식별자로 반복 생성하지 않는다.
- 운영 DB·로그·고객 파일을 Git, 메신저 또는 개발 PC에 복사하지 않는다.

## 14. 인계할 운영 정보

실제 값은 접근 통제된 운영대장에 기록한다.

- 서버 자산 ID와 OS
- 승인 DNS 이름과 인증서 만료일
- 설치 소스 커밋, 패키지 hash와 signer
- 작업 스케줄러 이름과 실행 계정
- DB·storage·로그 경로
- 백업 위치, 주기, 보존 기간과 복구 승인자
- 계정·승인 단말 운영 책임자
- 장애 연락망과 중단·rollback 결정권자
- 마지막 성공 health·백업·복구·파일럿 실행 ID
