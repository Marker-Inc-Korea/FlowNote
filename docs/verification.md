# 검증 자동화

이 문서는 테스트 DB와 산출물 보존 규칙을 지키면서 FlowNote의 현재 검증 순서를 한 번에 실행하는 기준이다. 실패하더라도 SQLite DB, 로그, 테스트 입력 파일, 출력 파일, 렌더링 결과, 스모크 테스트 산출물은 삭제하지 않는다.

## 2026-07-22 작업 102 AI 보존 WPF 구현 문서 재대조

작업 시작 시 `main...origin/main`은 동기화되어 있었고 미커밋 변경은 없었다. 직전 코드에서 WPF `AI 운영` 화면에 고객·현장 질의 상세, 단일 즉시 만료와 legal hold 설정·해제가 구현되었지만 일부 상위 문서에는 서버 API 전용 또는 WPF 미구현으로 남아 있던 설명을 현재 코드 기준으로 바로잡았다. WPF의 사유·근거 번호 검사, 이중 확인, 최신 `stateTag`, 조작별 operation key 재시도와 완료 후 query/hold/audit read-back 계약도 제품·시스템·배포 문서에 일치시켰다.

현재 표준 스크립트의 FastAPI guard는 149건이다. `services/api/.venv/bin/python -m pytest -q`는 `149 passed`, WPF Core는 `43 passed`로 통과했고 WPF 앱 빌드는 경고·오류 0이었다. 이어서 실행한 `python -m ruff check app tests`도 통과했다. Android와 Windows 누적 공통 DB 스모크는 새로 실행하지 않았다. 기존 SQLite, 로그, 테스트 파일과 산출물은 삭제하거나 초기화하지 않았다.

## 2026-07-22 작업 102 현재 코드·문서 재확인

작업 시작 시 `main...origin/main`은 동기화되어 있었고 반영할 미커밋 코드 변경은 없었다. 현재 API·구현 범위와 정량 기준을 코드에 대조했으며, 2026-07-22 검증 기준을 이미 반영한 상위 문서의 기준일만 오래된 표기로 남아 있어 현재 날짜로 맞췄다.

`services/api/.venv/bin/python -m pytest -q`는 `144 passed`로 통과했고, 이어서 실행한 `python -m ruff check app tests`도 통과했다. 이번 직접 실행은 FastAPI 회귀와 정적 검사만 대상이며 WPF·Android·공통 SQLite 스모크를 포함한 Windows x64 무생략 통합 기준선은 아니다. 기존 SQLite, 로그, 테스트 파일과 산출물은 삭제하거나 초기화하지 않았다.

## 2026-07-22 FastAPI 144건 기준선 guard 복구와 보조 실행

`scripts/verify-preserved-tests.ps1`의 FastAPI 수집/JUnit 기대값을 131건에서 144건으로 갱신했다. 수집 총수·고유 node ID 수·JUnit 실행 수를 직접 대조하고, `verification-summary.json`의 `fastapi` 항목에 `expected`, `collected`, `unique_node_ids`, `passed`, failure/error/skipped와 `collection_matches_junit`을 기록하도록 보강했다. 실행 전후 `git-status`, `git-ls-files`, staged 파일 목록도 각각 독립 파일로 보존하며 신규 금지 추적 산출물과 staged 금지 산출물·개인 경로 수를 요약에 기록한다.

macOS ARM64 보조 run `p0-baseline-144-macos-precheck-20260722-002`에서 FastAPI는 `collected=144`, `unique=144`, JUnit `144 passed`, failure/error/skipped 0으로 일치했고 실행 전후 신규 추적 파일과 staged 파일은 0건이었다. 첫 시도 `p0-baseline-144-macos-precheck-20260722-001`은 잘못 지정한 가상환경 Python 경로로 테스트 시작 전에 실패했으며 해당 로그와 실패 요약도 삭제하지 않고 보존했다.

이 호스트에는 Windows x64 PowerShell/.NET Desktop과 JDK/Android SDK가 없으므로 WPF Core·앱 build·공통 DB 스모크·스모크 전후 DB 무결성·Android 단위/debug build는 `NOT_RUN`이다. 따라서 `p0-baseline-144-macos-precheck-20260722-002`의 요약은 `partial_run=true`, `status=FAILED_ENVIRONMENT`이며 Windows 무생략 통합 기준선이 아니다. Windows x64 표준 환경에서 새 실행 ID로 `.\scripts\verify-preserved-tests.ps1 -RunId <승인된-run-id>`를 옵션 생략 실행해 `partial_run=false`, `status=PASSED`를 확보하기 전까지 최신 통합 기준선 판정은 `대기`다. 기존 DB·로그·테스트 산출물은 삭제하거나 초기화하지 않았다.

## 2026-07-21 작업 102 AI 보존·현장 준비도 문서 갱신

현재 작업 트리의 코드를 기준으로 AI 질의 감사·보존 API를 고객·현장 scope에 고정하고, 단일 즉시 만료와 `ACTIVE`/`RELEASED` legal hold 계약을 API·데이터 모델·보안·설계 결정 문서에 반영했다. 정기 스케줄러와 `system-admin` 수동 보존 작업은 활성 hold를 건너뛰고, 해제 이력은 원래 row를 삭제하지 않는다. 실제 현장 준비도 검증기는 승인된 `FIELD_READINESS` dataset과 고객·현장·선택적 라인·DB fingerprint를 결합하고, 외부 호출 없이 동일 snapshot을 두 번 평가한다.

현재 정량 기준은 루트 `GET /`를 포함한 OpenAPI 125개 method/path 조합, SQLAlchemy ORM 58개 테이블, `Settings` 36개 항목, 중복 없는 pytest node ID 144개다. `services/api/README.md`의 API 표는 OpenAPI와 누락·초과 0건이다. 변경 Python·테스트·검증기의 Ruff 검사와 AI 운영·DB 집중 회귀 6건은 통과했다. 실제 현장 dataset·검증 계정·비밀번호가 없어 `verify-ai-field-readiness.py`는 실행하지 않았다. 기존 SQLite, 로그, 테스트 파일과 산출물은 삭제하지 않았다.

## 2026-07-21 작업 102 파일럿 판정 schema 2 문서 갱신

현재 작업 트리의 코드 변경을 우선해 파일럿 실행 문서를 다시 맞췄다. `manage-pilot-run.py`는 `pilot-run.json` schema version 2와 네 개의 원시 측정 CSV를 만들고, 기존 실행·CSV는 기본적으로 덮어쓰지 않는다. 필수 게이트에는 Android 보안 저장/뷰어, 전달/복구, MDM kiosk 재시작이 추가됐으며 역할별 최대 시간·재시도·도움 요청, 8개 Android 전달 시나리오, 보안 실기 8개 항목, 단말 재접속 차단/교체 이력, UX 관찰의 개발 항목 전환을 증거 파일과 함께 판정한다.

`verify-android-release.sh`의 신규 `android-delivery.csv`도 동일한 8개 condition과 `elapsed_seconds`·`allowed_seconds` 열을 사용하도록 배포 문서와 Android README를 갱신했다. 정상·Doze는 30초, 5분 단절은 `30 + page_seconds`를 강제하고, 누락·서버 receipt 중복은 0건, crash 경계 표시 중복은 최대 1건만 허용한다. 이번 요청은 문서 갱신이므로 실제 고객 유사망 파일럿, APK 설치/rollback, 전체 테스트·빌드는 실행하지 않았고 기존 테스트 DB·로그·산출물은 삭제하지 않았다.

## 2026-07-21 작업 207 전체 Markdown 현재 코드 재대조

Git 추적 Markdown 42개를 목록화하고 작업 정책 원문 `AGENTS.md`를 제외한 제품·구현 문서 41개를 FastAPI, WPF, Android와 운영 스크립트에 대조했다. 가상환경·빌드 캐시·`data/local`·`tmp`의 Markdown은 외부 의존 또는 누적 테스트 증거이므로 수정하지 않았다. 과거 일일 기록은 당시 작업 맥락을 유지하되 “현재 코드 기준” 절에 서버 권위 revision·도메인별 mutation receipt·instance/epoch manifest와 관리자 승인형 reconciliation을 반영했다.

이번 재대조까지 반영한 값은 OpenAPI 125개 method/path 조합, SQLAlchemy ORM 58개 테이블, `Settings` 36개 항목, 중복 없는 pytest node ID 144개다. 새 서버 구현인 고객·현장 scope별 AI 질의/보존 감사, 단일 즉시 만료, `ACTIVE`/`RELEASED` legal hold와 실제 현장 준비도 검증기를 제품·시스템·MVP·보안·배포·데이터·API·서버·클라이언트 문서에 반영했다. 당시 WPF는 AI 보존 일괄 실행까지만 지원했고 단일 만료·hold 조작 UI는 없다는 구현 경계를 분리했다. 보고서 동기화는 WPF가 응답 source-set hash를 다시 검증한 뒤 report revision·content hash·source-set hash를 로컬에 보존하는 당시 코드로 과거 API 설명을 교정했다. `services/api/README.md`의 API 표는 OpenAPI와 누락·초과 0건이며, ORM 테이블 목록과 설정 목록도 코드 누락 0건, 로컬 Markdown 링크도 누락 0건이다. 이 절 작성 당시에는 pytest 수집만 다시 확인했고 전체 pytest·WPF·Android 빌드와 통합 스모크는 실행하지 않았다. 이후 결과는 이 문서 최상단의 최신 절을 따른다.

## 2026-07-21 작업 102 현재 코드 문서 재대조

당시 작업 시작 시 Git 작업 트리와 `main...origin/main`은 깨끗해 반영할 미커밋 코드는 없었다. 서버 복구 manifest/reconciliation, WPF 재결합 경계와 관련 상위 문서는 그 시점 코드와 일치했다. 다만 `services/api/README.md`의 FastAPI 수집 기준만 서버 복구 회귀 6건이 추가되기 전인 137건에 머물러 있어 당시 수집값 143건으로 갱신했다.

그 재대조에서 `.venv/bin/python -m pytest --collect-only -q`는 중복 없는 143건을 수집했다. 당시 OpenAPI는 루트 `GET /`를 포함한 122개 method/path 조합이고 SQLAlchemy ORM은 57개 테이블이었다. 전체 테스트·WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았으며 기존 SQLite, 로그와 테스트 산출물은 삭제하지 않았다. 이 수치는 이후 AI 보존 변경 전 기록이며 현재 기준은 이 문서 상단의 125개 API·58개 테이블·144개 테스트를 따른다.

## 2026-07-21 작업 102 서버 복구 reconciliation 문서 갱신

당시 구현 코드의 FastAPI server identity/epoch manifest와 reconciliation API, WPF URL별 binding·자동 전송/polling 차단, 관리자 `서버 재결합` 승인 적용을 개발 문서에 반영했다. 기존 문서에 목표 계약으로 남아 있던 `/sync/reconcile`, `/sync/mutations/{idempotency_key}`, sync header 계약은 현재 코드의 `/sync/reconciliation-runs` 계열과 manifest body 계약으로 바로잡았다. `DIVERGED/CONFLICT`의 실제 로컬 종결 상태가 `DISCARDED`이고 `RECONCILIATION_DIVERGED` 감사를 보존하는 점도 코드 기준으로 명시했다.

당시 OpenAPI는 루트 `GET /`를 포함한 122개 method/path 조합이고 ORM은 `server_identity`, `reconciliation_runs`, `reconciliation_items`를 포함한 57개 테이블이었다. `services/api/README.md` API 표와 OpenAPI 집합은 누락·초과 0건으로 일치했다. FastAPI는 중복 없는 143건을 수집했고 `tests/test_sync_reconciliation_api.py` 집중 테스트 6건은 instance ID 안정성·명시적 epoch 증가, `CONFIRMED/ABSENT/DIVERGED` 판정, 승인 뒤 divergence 감사 보존, 네 장애 유형별 독립 run 생성을 검증했다. 2026-07-21 전체 FastAPI 143건과 Ruff 정적 검사는 통과했다. WPF Core는 36건이 통과해 instance/epoch·cursor·URL 차단과 큐 보존을 확인했다. Windows 대상 WPF 앱은 macOS에서 `EnableWindowsTargeting=true`로 빌드해 경고·오류 0건으로 통과했다. 실제 WPF 2대와 서버 프로세스를 사용하는 통합 장애 주입 스모크는 Windows 현장 환경 검증 범위다. 이 수치는 AI 보존 변경 전 역사적 결과이며 현재 기준은 문서 상단을 따른다. 기존 SQLite와 테스트 산출물은 삭제하지 않았다.

## 2026-07-21 작업 207 전체 문서 갱신과 작업순서 서버 권위 대조

Git 추적 Markdown 42개를 전부 목록화했다. 작업 정책 원문 `AGENTS.md`는 제품 설명 갱신 대상에서 제외하고, 나머지 제품·구현 Markdown 41개를 FastAPI, Windows WPF, Android와 운영 스크립트에 다시 대조했다. 가상환경·빌드 캐시·`data/local`·`tmp`의 Markdown은 제품 문서가 아니며 누적 테스트 증거이므로 수정하지 않았다. 과거 일일 기록과 검증 절의 당시 수치·실패 결과도 증거로 보존하고, 현재 사양처럼 읽히는 문장만 최신 코드로 갱신했다.

이 절을 처음 작성한 시점의 OpenAPI는 루트 `GET /`를 포함한 116개 method/path 조합이었고 ORM은 FieldComment 검토·보고서·작업순서 mutation receipt를 포함한 54개 테이블이었다. 이후 서버 복구 reconciliation 시점에는 122개 API와 57개 테이블이었다. 당시에도 작업순서는 `board_revision`과 mutation receipt를 쓰는 FastAPI 권위 aggregate였고, FieldComment 검토는 `review_revision`, 보고서는 `report_revision`과 내용/source 집합 hash를 권위값으로 사용했다. WPF는 작업순서 서버 snapshot을 직접 읽고, 검토·첨부·보고서 재시도에는 base revision·mutation key·파일/source hash를 전달해 응답 read-back을 로컬에 보존했다.

이 절 작성 당시 `.venv/bin/python -m pytest --collect-only -q`는 중복 없는 137건을 수집했다. 새 3건은 FieldComment 검토 동시성/receipt 재생, 첨부 응답 유실 재시도, 보고서 선정 뒤 source 변경 409 차단이었다. 전체 pytest는 당시 문서 갱신 중 새로 실행하지 않았으며, 직전 134 passed는 새 3건 추가 전의 역사적 결과로 보존한다. 당시 macOS에서 실행 가능한 WPF Core 테스트는 작업순서 서버 권위 정책 5건을 포함해 33 passed, failed/skipped 0이었고 Android `testDebugUnitTest`는 Java Runtime 부재로 테스트 시작 전 환경 실패였다. WPF 앱 build·누적 스모크·Android build도 Windows 표준 기준선으로 새로 실행하지 않았다. 이후 143건 통과 기록도 역사적 결과이며 현재 수집 기준은 문서 상단의 144건이다.

이 절 작성 당시 `scripts/verify-preserved-tests.ps1`의 `$expectedFastApiTestCount`는 131이었다. 2026-07-22에 guard는 144건으로 복구됐지만 새 Windows x64 무생략 `PASSED` 기준선은 아직 확보하지 못했다. 기존 `baseline-131-macos-precheck-20260721-001`은 당시 결과로 보존하지만 현재 코드 기준선으로 승격하지 않는다. 기존 실패 run, SQLite, 로그, 파일은 삭제하거나 초기화하지 않았다.

## 2026-07-20 작업 207 전체 문서 재대조

현재 FastAPI 코드에서 다시 산출한 결과 OpenAPI는 루트 `GET /`를 포함한 116개 method/path 조합, ORM은 51개 테이블, `Settings`는 36개 항목이다. 서버 API README의 116개 표 항목은 OpenAPI와 누락·초과 없이 일치한다. DB 개요와 초기 스키마 문서에는 `ai_search_ground_truth_provenance`, `ai_ground_truth_dataset_versions`, `ai_ground_truth_dataset_cases`, `ai_evaluation_dataset_bindings`를 포함한 51개 ORM 테이블을 반영했다.

Git이 추적하는 Markdown 42개를 현재 서버·Windows·Android 코드와 대조했다. 과거 일일 기록과 검증 실행의 당시 수치는 역사적 증거로 유지하고, 현재 상태처럼 읽히는 오래된 날짜·기능·테이블·테스트 기준만 갱신했다. `pytest --collect-only -q`는 중복 없는 131건을 수집했고 전체 `pytest -q`도 131건 모두 통과했다. 표준 스크립트는 아직 128건을 강제하므로 Windows 무생략 통합 기준선은 재확립되지 않았다. WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-20 현재 코드 기반 문서 갱신

현재 HEAD의 AI ground-truth 사례 운영·승인 경계 코드를 상위 개발 문서와 대조했다. WPF 사례·원천 구성 화면, `includePending` 사례 조회, 사례 등록·2차 승인 role, dataset 승인 role 분리, 대체본 scope 조건, dataset ID 기반 변경·전이의 scope 재검사와 DB 승인자 분리 제약을 문서에 반영했다. 최상위·Windows·FastAPI README의 구현 요약과 API 설명도 같은 기준으로 갱신했다. 이번 요청은 문서 갱신이므로 코드 테스트·빌드·스모크는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-20 파일럿 실행 준비 게이트

`scripts/manage-pilot-run.py`를 추가해 실제 파일럿 증거 구조 생성과 완료 판정을 분리했다. `PILOT-20260720-1500-LOCAL-001`로 초기 판정표 생성과 누락 게이트 검출을 시험했으며 예상대로 종료 코드 1과 `FAIL` 판정이 나왔다. 잘못된 `PILOT-bad` 실행 ID는 종료 코드 2로 거부됐다. 결과와 로그는 Git 제외 경로 `data/local/pilot-evidence/PILOT-20260720-1500-LOCAL-001/`에 보존했다. Python compile, 저장소 FastAPI 가상환경의 Ruff check와 `git diff --check`는 통과했다. 이 실행은 고객 유사망·Windows·Android·별도 PC 복구가 없는 로컬 준비 점검이므로 실제 파일럿 통과 증거가 아니며 모든 실기 게이트는 계속 `대기`다.

## 표준 실행

Windows 배포 준비·통합 검증 PC의 표준 도구 기준은 다음과 같다. `verify-preserved-tests.ps1`은 실행 시작 단계에서 이 기준을 검사하고 실제 버전을 실행 ID 폴더의 `environment.json`에 남긴다.

| 도구 | 표준 기준 |
| --- | --- |
| 운영체제 | Windows 10/11 또는 동등한 Windows Server x64 |
| PowerShell | Windows PowerShell 5.1 이상. PowerShell 7.4 LTS 이상 권장 |
| .NET | SDK 10.x와 `Microsoft.WindowsDesktop.App` Runtime 10.x |
| Python | `services/api/.venv/Scripts/python.exe`, Python 3.11 이상 |
| Android Java | x64 JDK 17. `JAVA_HOME`과 `java`가 같은 설치를 가리켜야 함 |
| Android SDK | `ANDROID_SDK_ROOT` 또는 `ANDROID_HOME`, Platform 35, Build Tools 35.0.0, Platform Tools |
| Android 빌드 | 저장소 Gradle Wrapper 8.10.2, Android Gradle Plugin 8.7.3 |
| Git | 검증 PC PATH에서 실행 가능한 Git |

JDK 21 등 다른 Java 버전에서 우연히 빌드되는 결과는 표준 기준선으로 확정하지 않는다. WPF framework-dependent 배포 대상 PC도 Desktop Runtime 10.x를 사용하며, 런타임 설치를 통제할 수 없는 대상에는 별도의 self-contained MSI 검증 기준을 적용한다.

저장소 루트에서 다음 명령을 실행한다.

```powershell
.\scripts\verify-preserved-tests.ps1
```

스크립트는 기본 `integrated-smoke-yyyyMMdd-HHmmss` 실행 ID를 만들며 `-RunId <값>`으로 현장 실행 ID를 지정할 수 있다. 단계별 로그, JUnit/TRX, 관리형 FastAPI 로그, WPF DB 증거, Android 결과, 환경 정보와 `verification-summary.json`은 Git 제외 경로 `data/local/integrated-smoke/<run-id>/`에 보존한다. 실패하면 즉시 종료하되 실패 단계까지의 DB·로그·산출물을 삭제하거나 초기화하지 않으며, 요약 파일에 실패 단계와 원인을 남긴다. 스크립트는 다음 순서로 실행한다.

1. Windows, PowerShell, .NET Desktop, Python, JDK, Android SDK와 Git 버전을 점검하고 `environment.json`을 쓴다.
2. `.gitignore`가 알려진 테스트/빌드 산출물 경로를 제외하는지 점검한다.
3. 실행 전 `git status --porcelain=v1 --untracked-files=all`과 `git ls-files`에서 테스트 산출물, 빌드 결과, 개인 로컬 경로가 잡히지 않는지 점검한다.
4. `services/api`에서 FastAPI pytest node ID 149개를 수집하고 중복 node ID가 0개인지 확인한다. 수집 목록은 `fastapi-collected-tests.txt`로 보존한다.
5. FastAPI pytest를 실행하고 실행 ID별 JUnit을 보존한다. 수집 총수·고유 node ID 수·JUnit 실행 수가 모두 149인지 직접 대조한다.
6. WPF Core 테스트를 실행하고 TRX를 보존한다.
7. WPF 앱을 빌드한다.
8. WPF 공통 DB의 스모크 전 `quick_check`와 `foreign_key_check`를 별도 JSON 증거로 확인한다.
9. `5184` 포트에 서버가 없으면 누적 `flownote.windows-smoke.sqlite3`와 `storage/windows-smoke`를 쓰는 FastAPI를 시작하고, 같은 실행 ID로 WPF 통합 스모크를 실행한다.
10. WPF 공통 DB의 스모크 후 무결성을 다시 확인한다.
11. Android `testDebugUnitTest`와 `assembleDebug`를 실행하고 JUnit XML을 실행 ID 폴더에도 복사해 보존한다.
12. `-RunAndroidDeviceSmoke`를 지정하면 연결된 승인 실단말이 정확히 1대인지 확인하고 `connectedDebugAndroidTest`를 실행한다.
13. 실행 후 `git status --short --untracked-files=all`, `git ls-files`, staged 파일 목록을 다시 점검하고 전후 증거 파일과 신규 금지 추적 산출물 수를 보존한다.

개별 명령은 다음과 같다.

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest
cd ..\..
dotnet test .\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
cd apps\android
.\gradlew.bat testDebugUnitTest assembleDebug
cd ..\..
git status --short
```

WPF 통합 스모크는 같은 실행 ID로 반장·조장·조원·문서관리자·system-admin·viewer와 승인 Android 단말을 추적한다. 오늘 사진/인수인계 문서의 날짜 폴더 생성·등록·목록 조회, 기존 과거 날짜 사진/인수인계 문서 중 무작위 1건의 버전 증가, FieldComment 검토 상태와 보고서 source, 채널 알림·receipt, 사용자별 cursor 재시작 복구를 연결한다. 과거 날짜 폴더나 문서는 새로 만들지 않으며 기존 과거 문서가 하나도 없으면 환경 준비 누락으로 실패한다. 또한 이번 실행에서 만든 구 `create` FAILED 큐를 dry-run하고 plan hash로 승인한 뒤 같은 row를 다시 승인해 target 큐·감사 중복이 생기지 않는지 확인한다. 서버 viewer는 임시 비밀번호 변경 후 Windows/승인 Android 세션을 만들고 `DISABLED` 전환 직후 access/refresh가 모두 차단되는지 확인한다. AI ground-truth 평가는 계속 통과하면서 외부 provider 호출은 `AI_EXTERNAL_CALL_DISABLED`로 차단되는지를 같은 흐름에서 검증한다.

FieldComment 정제 스모크의 기존 6개 슬롯은 범주마다 `NORMAL-01/02`, `EXCLUSION-01/02`, `CONFLICT-01/02`로 고정한다. 아래 8범주에 각각 6건을 배분해 48건을 구성하며, 각 행은 `case_key`, category, scenario type, 생성 또는 재사용한 source/version/trace ID, 기대 포함/제외 근거, 실제 결과, 원천 hash 전후를 증거 JSON에 남긴다.

| 시나리오 | 허용 근거 | 반드시 제외할 근거 |
| --- | --- | --- |
| `SAFETY` 안전 | 현재 공개 안전 문서, 선정 FieldComment, 관련 작업순서 이력 | 비공개 안전 초안, 권한 밖 채널 기록 |
| `QUALITY` 품질 | 공개 검사 기준, 선정 품질 FieldComment | 상충 미해결 기록, 제외 판정 기록 |
| `EQUIPMENT_ANOMALY` 설비 이상 | 공개 점검 기준, 설비 태그 FieldComment | 오래된 비공개 버전, 다른 설비의 동명이력 |
| `WORK_HOLD` 작업 보류 | 보류 사유 FieldComment, 인수인계 또는 작업순서 이력 | 사유 없는 보류, 담당 채널 밖 기록 |
| `REWORK` 재작업 | 재작업 전후 기록과 현재 검사 기준 | 원문 없는 요약, `EXCLUDED` 오입력 |
| `HANDOVER` 인수인계 | 인수인계 문서, 수신 확인, 선정 후속 FieldComment | 미수신 개인 메모, 공개되지 않은 초안 |
| `LATEST_PUBLISHED_DOCUMENT` 최신 공개 문서 | 현재 공개 version과 연결 기록 | 삭제·비공개·과거 version |
| `CONFLICTING_RECORDS` 상충 기록 | 서로 다른 source type의 고정 원천과 상충 표시 | 한쪽 원천 은폐, orphan/허위 인용 |

재실행은 `smoke48-v1`의 같은 case key와 업무 idempotency key를 사용해 기존 원천·보고서·작업순서를 재사용하고 새 중복 row나 알림을 만들지 않는다. 상태는 `ANALYZED 8`, `REVIEWED 8`, `SELECTED 16`, `EXCLUDED 16`으로 수렴하며 담당자, 기한, 전이 사유와 source hash 전후 동일성을 감사에서 확인한다. 실행별 증거 파일은 덮어쓰거나 삭제하지 않는다. 오늘 사진/인수인계 등록과 기존 과거 문서 무작위 버전 증가는 이 배분과 별도로 계속 필수다.

검증 순서는 시드, `scripts/sql/verify-ai-ground-truth-48.sql`, 동일 snapshot 2회 평가, `GET /api/v1/ai-search/readiness`, 외부 provider 비활성 질의다. SQL은 총 건수뿐 아니라 24칸×2건, 상태와 source type 분포, 16개 보고서의 2종 이상 source 연결, 고정 version/hash/trace, 태그 축 커버리지, orphan·멱등키 중복을 검사한다. 평가는 top-k 포함·인용 trace·의미 일치·상충 표시 `1.0`, 제외 노출·권한 누출·허위 인용 `0`을 강제한다. readiness에서 `SMOKE_REGRESSION`은 `smoke_regression_readiness`에만 나타나야 하고 최상위 `ground_truth_count` 및 provider 착수 판정은 `FIELD_READINESS`와 같아야 한다. `AI_EXTERNAL_CALL_DISABLED`가 아니거나 `provider_start_ready=true`이면 실패다.

마지막 로컬 SQLite 검사는 `quick_check=ok`, `foreign_key_check=0`, `server_sync_queue.idempotency_key` 중복 0, `server_id_mappings(entity_type, local_id, local_version_no)` 중복 0을 강제한다. `wpf-smoke-database-evidence.json`에는 주요 테이블 실행 전후 통계, 오늘 문서 ID, 과거 기존 문서의 이전·신규 버전과 무결성 결과가 저장된다. 통제된 기준선은 실행마다 설정이 식별되는 관리형 FastAPI를 사용하므로 시작 전에 `5184` 포트를 비워야 한다. 해당 포트에 이미 건강한 서버가 있으면 환경 실패로 중단하고 외부 프로세스는 종료하지 않는다.

한 run ID의 `verification-summary.json`이 `partial_run=false`, `status=PASSED`이고 모든 필수 단계가 `PASSED`일 때만 최신 Windows 통합 기준선으로 확정한다. 현재 FastAPI 수집/JUnit guard와 목표는 149건이며 failure/error/skipped와 중복 node ID는 모두 0이어야 한다. WPF TRX와 Android JUnit도 failure/error 0, WPF·Android build 로그도 build error 0이어야 하며 DB 증거의 네 무결성 값이 모두 위 기준과 일치해야 한다. 단계 생략 스위치를 사용한 실행이나 Windows가 아닌 환경의 부분 실행은 기준선 확정 근거가 아니다.

Windows 통합 `PASSED`는 실제 운영 배포의 선행 조건이지 최종 완료 판정이 아니다. 이후 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)에 따라 깨끗한 PC의 설치·업그레이드·제거, HTTPS 인증서 갱신, 단말 교체, 고객 유사망 장애, 별도 PC 복구와 역할별 업무를 새 파일럿 `run_id`로 검증한다.

## 2026-07-20 작업 102 현재 코드 문서 갱신

작업 시작 시 Git 작업 트리는 깨끗해 미커밋 변경은 없었다. 최근 구현을 다시 대조해 FastAPI ground-truth 첫 승인, 서로 다른 사용자의 2차 승인, 고정 원천 snapshot/provenance, 실제 현장/스모크 준비도 분리를 제품 개요·MVP·로드맵·서버 API 목록에 반영했다. 합성/시험 48건 회귀는 실제 현장 준비도와 운영 provider 승인을 대신하지 않는다는 경계도 명시했다.

현재 앱의 OpenAPI schema에서 다시 산출한 값은 루트 `GET /`를 포함한 109개 method/path 조합이고 ORM은 48개 테이블이다. 기존 서버 API README의 108개 총계와 누락된 `POST /api/v1/ai-search/ground-truth-cases/{ground_truth_case_id}/second-approval` 항목을 현재 코드에 맞게 수정했으며, README 표와 OpenAPI의 109개 조합이 누락·초과 없이 일치함을 확인했다. `pytest --collect-only -q`는 130건을 수집했다. 이번 요청은 문서 갱신이므로 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-20 작업 102 보고서 근거 코드 재대조

작업 시작 시 Git 작업 트리는 깨끗해 반영할 미커밋 변경은 없었다. 최근 구현된 보고서 근거 계약을 FastAPI, WPF와 상위 문서에 다시 대조했다. 현재 WPF 후보는 `SELECTED` FieldComment, 현재 공개 문서, 작업순서 항목/이력으로 제한되며, 이전 문서에 남아 있던 `REVIEWED`·`ANALYZED` FieldComment 후보 설명을 제거했다. 보고서 초안과 최종 저장은 서로 다른 source type 2종 이상, source별 고정 version, type/ID/version 중복 금지를 적용한다. 각 source의 독립 trace ID와 저장 시점 SHA-256을 보존하고 최종 문서 저장 전에 같은 version의 현재 원천 hash를 다시 검사한다.

현재 코드에서 다시 산출한 정량 기준은 전역 OpenAPI 108개 method/path 조합, ORM 47개 테이블, `Settings` 36개 항목이다. `services/api/.venv/bin/python -m pytest --collect-only -q`는 중복 없는 130건을 수집했고 전체 `pytest -q`도 130건 모두 통과했다. 최근 보고서 근거 회귀 2건이 추가됐지만 `scripts/verify-preserved-tests.ps1`은 아직 128건을 강제하므로 표준 Windows 검증은 현재 수집 단계에서 실패한다. 이번 요청은 문서 갱신이므로 스크립트 코드는 변경하지 않았고 WPF·Android 빌드와 통합 스모크도 새로 실행하지 않았다. 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-20 후보 4 AI 준비 데이터셋과 48건 승인 기초

`smoke48-v1` 비민감 시험 세트를 공용 FastAPI 테스트 SQLite에 누적했다. 8범주×3유형×2건의 48건은 모두 중복 없는 case key, source/version/trace ID, content hash, 포함·제외 근거, `as_of`, 허용 순위, `TEST/SMOKE_REGRESSION` provenance와 서로 다른 두 승인자를 가진다. 민감정보 형태, 합성 고객 식별자, 로컬 경로, 권한 밖 채널, 삭제/비공개 문서, `EXCLUDED`/`ARCHIVED` 원천을 부정 사례로 포함한다. 실제 현장 준비도에는 합산하지 않는다.

`scripts/sql/verify-ai-ground-truth-48.sql` 결과는 case 48, 매트릭스 빈 칸·case key 중복·승인 위반·provenance 위반·snapshot/reference hash 위반·근거 누락·원천 orphan이 모두 0이었다. 제외 원천의 현재 content hash도 평가 시 snapshot과 다시 비교한다. 같은 snapshot의 두 평가 run `aiseval_1041239657ce4f639940120dec0e3a78`, `aiseval_a3ff5b191d684c0a880f5566544dec5c`는 각각 48/48 `PASSED`였다. 두 run 모두 candidate ID/content hash와 순위가 안정됐고 top-k 포함, 인용 trace, 의미 일치, 상충 표시가 100%였으며 권한 누출, 존재하지 않는 인용, 제외 원천 노출은 0건이었다.

후보 4 반영 후 전역 OpenAPI는 108개 method/path 조합, ORM은 48개 테이블이다. 최종 `ruff check`는 통과했고 FastAPI 전체 회귀는 130건 모두 통과했다. 최종 로그는 `services/api/data/local/integration-logs/fastapi-ai-ground-truth-48-20260720-final.log`에 보존했다. 기존 SQLite, 평가 run/case, 로그와 테스트 산출물은 삭제하지 않았다. Windows/Android 통합 스모크는 이번 작업에서 실행하지 않았으며 오늘 사진/인수인계와 기존 과거 문서 버전 증가 규칙은 기존 통합 스모크 책임으로 유지한다.

## 2026-07-20 작업 102 현재 코드 문서 재대조

작업 시작 시 Git 작업 트리는 깨끗해 반영할 미커밋 코드 변경은 없었다. 최근 2026-07-20 구현 변경은 FastAPI 초기화의 WPF 로컬 SQLite 오접속 차단, 보존형 controlled copy 스키마 복구 도구, 표준 검증의 FastAPI 128건 기준 정렬이며, 상세 계약은 이미 서버·데이터 모델·배포·Windows SQLite 문서에 반영되어 있었다. 이번 재대조에서는 최상위 README와 서비스 개요에 남아 있던 2026-07-16 코드 기준일을 현재 기준으로 맞추고, 두 구현 목록에 서버/WPF SQLite 스키마 경계 검사를 명시했다.

현재 코드에서 다시 산출한 정량 기준은 전역 OpenAPI 108개 method/path 조합, ORM 47개 테이블, `Settings` 36개 항목이다. `services/api/.venv/bin/python -m pytest --collect-only -q`도 중복 없는 128건 수집을 확인했다. 문서 갱신 요청이므로 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-20 WPF 공통 DB P0 무결성 복구

`controlled_copy_grants`는 FastAPI `Base.metadata.create_all()`이 WPF 공통 DB를 서버 DB URL로 잘못 받은 실행에서 유입된 서버 전용 schema였다. 서버 FK는 `document_versions.version_id`를 참조하지만 WPF 로컬 테이블은 `id` PK와 `(document_id, version_no)` 의미 키를 사용하고 `version_id` 열이 없으므로, 테이블 생성 직후부터 SQLite `foreign key mismatch`가 발생하는 구조였다. FastAPI 초기화는 이제 WPF 로컬 `documents`/`document_versions` 형태를 먼저 판별해 서버 테이블 생성 전에 중단한다.

보존 migration `scripts/repair-wpf-controlled-copy-schema.py`는 원본 SQLite 일관 backup, 전체 테이블 row 수·DDL·FK, DB SHA-256, `document_versions`·controlled copy·접근 감사 row hash를 먼저 저장한다. 서버 전용 grant row는 FK 없는 `preserved_server_controlled_copy_grants`에 원래 열 값과 run ID를 보존하고 `local_schema_migration_audit`에 원래 DDL과 보호 대상 hash를 남긴 뒤 충돌하는 활성 테이블만 제거한다. 실제 공통 DB run `WPF-P0-20260720-0840`은 원래 grant 0행, 문서 버전 3,384행, 접근 감사 0행을 보존했고 `quick_check=ok`, FK 검사 오류 없음, 위반 0건으로 끝났다. 별도 비영(非零) TOOLTEST는 소비 완료 grant 1행과 접근 감사 1행의 값·hash 보존을 확인했다. 원본 DB backup과 전후 JSON은 `data/local/wpf-schema-repair/<run-id>/`에 남아 있으며 Git 제외 대상이다.

FastAPI 수집 목록은 128개 node ID, 중복 0개로 대조했고 macOS 보조 run `p0-recovery-macos-20260720-0850`에서 JUnit `128 passed`를 보존했다. 이 호스트에는 `dotnet`, JDK, Android SDK가 없어 WPF Core/TRX·WPF 앱 build·누적 스모크·Android 단위/debug build를 실행할 수 없었다. 따라서 이 보조 run은 Windows 표준 `PASSED` 기준선이 아니며, 128 기준으로 갱신된 `verify-preserved-tests.ps1`을 표준 Windows x64 환경에서 옵션 생략 없이 새 run ID로 실행하기 전까지 최신 통합 기준선 재확립 판정은 `대기`다.

## 2026-07-16 후보 6 AI ground-truth와 provider 착수 게이트

승인 세트의 시작 하한은 `8개 범주 × 3개 유형 × 각 2건 = 48건`이다. 범주는 `SAFETY`, `QUALITY`, `EQUIPMENT_ANOMALY`, `WORK_HOLD`, `REWORK`, `HANDOVER`, `LATEST_PUBLISHED_DOCUMENT`, `CONFLICTING_RECORDS`, 유형은 `NORMAL`, `EXCLUSION`, `CONFLICT`다. 총 48건을 채워도 한 조합이 2건 미만이면 통과하지 않는다. 개발용 복제·랜덤 row는 승인 수량에 넣지 않고, 실제 익명 현장 표본이 확보되면 기존 이력을 비활성화하거나 삭제하지 않은 채 새 승인 version으로 교체·확장한다.

각 case는 질문, 기대 결과, 기대 포함 근거, 반드시 제외할 근거와 제외 사유, 허용 순위, `as_of`, 고객·현장·선택적 라인·DB scope, 승인자와 승인 시각을 기록한다. 포함 근거는 승인 시점의 candidate/source/version/trace ID와 content hash, 승인자 권한, `as_of` 이전 생성 여부를 확인한다. 제외 근거도 실제 원천 row가 있어야 한다. `CONFLICT`는 최소 두 개의 기대 근거를 요구한다. 원천이나 권한으로 역추적할 수 없는 case는 승인 저장 자체를 실패시킨다.

릴리스 게이트 임계값은 candidate ID/content hash 안정성 100%, 동일 snapshot ranking 안정성 100%, 허용 top-k 포함률 100%, citation trace 존재율 100%, citation 의미 일치율 100%, 상충 표시율 100%다. 제외 근거 노출, 권한 누출, 존재하지 않는 인용은 각각 0건이어야 한다. 네 원천 유형을 모두 포함하고 전체 case가 통과해야 한다. 임계값 변경은 평가 결과를 덮어쓰지 않고 결정 기록과 새 run으로 남긴다.

검증은 외부 호출 없이 fake/recording adapter와 로컬 candidate ranking으로 먼저 반복한다. prompt version, policy 또는 검색 구현을 바꾸기 전후에 같은 승인 case ID를 평가하고 `previous_run_delta`의 candidate 추가/제거, content hash와 순위 변경을 비교한다. 실패 run과 case row, fake payload, 로그는 삭제하지 않는다. 사람이 뽑은 표본 응답은 두 검토자가 근거 적합성, 누락, 과장, 상충 표시, `참고 요약` 표현과 자동 조치로 오인될 문구가 없는지를 각각 확인한다. 두 판단이 다르면 `PENDING`으로 두고 합의 근거를 새 검토 기록으로 남긴다.

실제 현장 승인본은 `scripts/verify-ai-field-readiness.py`에 dataset version과 고정 고객·현장·라인·DB scope를 주어 검증한다. 이 도구의 SQL 단계는 48건/24칸, dataset 네 actor와 case 두 승인자 분리, `ANONYMOUS_FIELD`/`PILOT` provenance, 중복·orphan·hash·제외 이유를 검사한다. 이어 같은 승인 snapshot을 두 번 평가하고 두 번째 run의 `previous_run_delta`와 100%/0건 임계값을 비교한다. 비밀번호는 `FLOWNOTE_FIELD_READINESS_VERIFY_PASSWORD`에만 두며 검증기 설정은 `FAKE` adapter와 `ai_external_call_enabled=false`를 강제한다.

사람 표본 검토는 자동 평가와 별개로 두 명이 같은 run/dataset snapshot에서 독립 수행한다. 각 검토자는 근거 적합성, 누락, 과장, 상충 표시, `참고 요약` 표현을 판정하고 reviewer ID·시각·근거를 남긴다. 불일치는 자동 합격으로 병합하지 않고 `PENDING`으로 유지한 채 제3의 합의 기록 또는 새 dataset version으로 종결한다.

provider 심사는 계약, 데이터 보존, 학습 사용, 전송 지역, TLS, timeout, 429, 5xx, 비용 한도, kill switch, 법무 승인, 고객 승인 12개 항목과 기술·보안·법무·고객 네 영역을 기록한다. 전건 `PASS`와 네 영역 `APPROVED` 전에는 `provider_review_ready=false`다. 현재 실제 현장 승인 ground-truth와 provider별 계약 증거가 등록되지 않았으므로 운영 착수 판정은 명시적 `대기`이며, 구현된 fake/recording 회귀와 제한형 test adapter가 운영 provider 승인을 뜻하지 않는다. 통과 후 첫 범위도 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`의 근거 검색과 `참고 요약`으로 제한한다.

구현 검증은 `services/api/.venv/bin/python -m ruff check services/api/app services/api/tests` 통과 후 AI 검색·운영·질의 집중 회귀 22건과 FastAPI 전체 회귀 128건을 실행해 모두 통과했다. 테스트 SQLite와 adapter 기록은 삭제하거나 초기화하지 않았다. 이번 개발 DB의 누적 테스트 case와 provider review는 실제 고객/법무 승인 세트로 승격하지 않는다.

## 2026-07-16 작업 207 전체 Markdown 코드 정합성 갱신

작업 정책 원문 `AGENTS.md`를 제외한 Git 추적 제품·구현 Markdown 40개를 현재 FastAPI, Windows WPF, Android와 운영 스크립트에 다시 대조했다. 시작 시 존재하던 문서 4개의 사용자 변경은 되돌리지 않고 함께 보존했다. 현재 정량 기준은 루트 `GET /`와 문서별 보조 router를 포함한 API 108개 method/path 조합, 서버 ORM 47개 테이블, `Settings` 36개 항목, FastAPI 테스트 수집 128건이다. API 전체 표는 `services/api/README.md`와 실제 route 집합이 일치하고 설정 항목은 API·서버·배포 문서에 모두 반영되어 있다.

코드보다 오래된 Android 데이터 모델의 “사진 URI” 설명은 현재 Keystore AES-GCM 암호문 payload와 앱 내부 암호화 첨부 참조, 구 persist URI 읽기 호환 계약으로 갱신했다. 최상위·제품·서비스·Windows 문서에는 구현된 `verify-pilot-restore.py`의 서버 DB+`storage` 및 WPF DB+`Files` 복구 전후 증거 비교 범위를 보강했다. 과거 일일 기록과 검증 이력의 당시 수치·실패 결과는 현재 상태로 덮어쓰지 않고 시점 기록으로 유지했다.

이번 작업에서는 `services/api/.venv/bin/python -m pytest --collect-only -q`로 128건 수집을 확인했다. 전체 pytest, WPF·Android 빌드와 통합 스모크는 문서 갱신 범위에서 새로 실행하지 않았다. `scripts/verify-preserved-tests.ps1`의 고정 기준은 여전히 120건이므로 현재 코드와 불일치하며, 이를 고치기 전 표준 통합 실행은 유효한 `PASSED` 기준선이 아니다. 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-16 후보 5 FieldComment 정제 검증

- FastAPI 전체 `128 passed`, Ruff 통과. 원천 hash 전후 일치, 단계별 감사, 작업함 6종 필터·우선순위, report source 역추적, 미선정·비공개·현재 공개본이 아닌 버전·권한 밖 채널 제외를 자동 검증했다.
- WPF Core 테스트 `21 passed`, Core·WPF 앱·스모크 프로젝트 빌드는 경고 0/오류 0이었다.
- 통합 스모크 run `candidate5-20260716-final`, `-final2`, `-final3`의 DB·파일은 삭제하지 않았다. 세 실행 모두 오늘 사진/인수인계 등록과 기존 과거 사진 또는 인수인계 문서 무작위 버전 증가를 완료했다. 첫 실행은 구 단말 모드 `field` 계약 불일치로 중단되어 `viewer`로 바로잡았고, 이후 실행은 계정·승인 단말까지 통과했다.
- 최종 실행은 누적 큐 985건 가운데 구 형식 653건, 선행 문서 미동기화 260건 등 과거 backlog가 남은 상태에서 이번 run 전용 row만 모두 동기화됐다고 가정한 기존 검증 블록에서 중단됐다. 과거 큐를 삭제·재분류하지 않았으며 통합 전체 `PASSED` 증거로 승격하지 않는다.
- 13:26 KST 이후 공통 SQLite의 FieldComment 상태는 `NEW 2026`, `ANALYZED 255`, `REVIEWED 246`, `SELECTED 246`, `EXCLUDED 23`, `ARCHIVED 20`이다. 로컬 report source 표기는 현행 대문자 기준 `FIELD_COMMENT 354`, `DOCUMENT 212`, `WORK_SEQUENCE_HISTORY 120`, `WORK_SEQUENCE_ITEM 20`이며 구 소문자 호환 row도 그대로 보존했다.

## 2026-07-16 작업 102 현재 코드 문서 갱신

깨끗한 `main` 작업 트리에서 최근 Android 보안 문서 열람, 문서 revision 충돌, 채널 알림·동기화, FieldComment 검토 역추적, AI 검색 readiness와 복구 증거 수집/비교 CLI 구현을 개발 문서와 다시 대조했다. 전역 OpenAPI는 루트 `GET /`를 포함한 108개 method/path 조합이고 `docs/api.md`와 `services/api/README.md`의 API 표는 누락·초과 없이 같은 집합을 설명한다. 두 문서에 107개로 남아 있던 총계를 108개로 바로잡았다. 상위 문서에는 `verify-pilot-restore.py`가 서버 DB+`storage`와 WPF DB+`Files`의 전후 무결성 증거를 비교하는 현재 구현임을 반영했다.

서버 ORM은 47개 테이블을 생성한다. DB 개요의 46개 총계를 47개로 수정하고, 상위 데이터 모델 표에 `ai_operational_policies`, `ai_operation_audit_events`, `ai_retention_audits`를, 초기 스키마 설명에 `android_document_view_grants`를 보강했다. `Settings` 36개 항목은 API·서버 설정 문서에 모두 반영되어 있다.

`services/api/.venv/bin/python -m pytest --collect-only -q`로 FastAPI 128건 수집을 확인했다. 120건 기준과 일치한다고 남아 있던 `services/api/tests/README.md`는 실제 코드와 표준 스크립트의 불일치를 설명하도록 수정했다. 이번 요청은 문서 갱신이므로 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았다. 스크립트의 FastAPI 고정 기준은 여전히 120건이므로 현재 128건 코드와 일치하지 않는다. 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-16 작업 102 초기 코드·문서 재대조 기록

이 기록은 같은 날 후보 5 FieldComment 정제 변경 전의 재대조 결과다. 당시 깨끗한 작업 트리의 구현을 제품·시스템·데이터 모델·API·보안·배포·클라이언트·서버 개발 문서와 대조했다. 코드가 문서보다 우선한다는 기준으로 전역 FastAPI OpenAPI 105개 method/path 조합, ORM 46개 테이블, `Settings` 36개 항목을 확인했다. 서버 API 목록에서 빠진 문서 soft delete를 보강하고, Android 보안 본문 열람·Keystore 보호 outbox·로그인 세션 foreground service 알림 복구가 메타데이터 조회와 전경 Activity polling으로 남아 있던 당시 상태 요약·MVP·파일럿 문구를 구현에 맞게 바로잡았다. 그 시점의 FastAPI 수집값 126건과 표준 스크립트 고정값 120건의 불일치도 활성 검증·배포 문서에 명시했다. 후속 후보 5 변경 이후의 현재 기준은 위 절의 `128 passed` 기록을 따른다.

`services/api/.venv/bin/python`으로 당시 OpenAPI 105개 조합, ORM 46개 테이블, `Settings` 36개 항목을 확인했다. `pytest --collect-only -q`로 당시 FastAPI 테스트 126건 수집도 확인했다. 문서 정합성 작업이므로 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았고, 기존 SQLite·로그·캐시·테스트 산출물은 삭제하지 않았다.

## 2026-07-15 작업 207 전체 Markdown 코드 정합성 갱신

작업 정책 원문 `AGENTS.md`를 제외한 Git 추적 제품·구현 Markdown 40개를 FastAPI, Windows WPF, Android 현재 코드와 다시 대조했다. 기존 작업 트리의 문서 8개 변경은 되돌리지 않고 함께 보존했다. FieldComment 원천 불변·단계형 검토, 담당자·기한, WPF 다중 선택 개별 동기화와 FastAPI 최대 200건 트랜잭션 일괄 검토, 원천 hash 감사·품질 작업함을 상위 제품/시스템/클라이언트/서버/과거 요약 문서에 반영했다. 제한형 generic 네트워크 adapter가 구현되어 있는데도 네트워크 client가 없다고 남아 있던 초기 스키마 설명을 test scope 전용 구현과 provider별 운영 client 미구현으로 바로잡고, 운영 배포 표에는 현재 AI readiness·adapter·timeout·재시도·응답 크기 설정을 보강했다.

전역 FastAPI 앱의 루트 `GET /`를 포함한 102개 method/path 조합을 `docs/api.md`와 `services/api/README.md`의 API 표와 집합 비교해 누락·초과 0건을 확인했다. ORM 45개 테이블은 세 데이터베이스 문서에 모두 존재하고 `Settings` 31개 항목은 API 문서와 서버 README에 모두 반영되어 있다. 제품·구현 Markdown 40개의 상대 파일 링크는 깨진 링크 0건이며 `git diff --check`와 Ruff도 통과했다. `pytest --collect-only -q`로 116건 수집을 확인했으며 문서 갱신 범위이므로 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았다. 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-15 실제 배포 리허설과 제한 파일럿 준비

Windows 서버/WPF 설치, .NET/self-contained/WebView2, EXE·MSI hash와 서명, 작업 스케줄러 재부팅, HTTPS·방화벽·주소·시간, Android 서명/배포/단말 수명주기/outbox 보호, 서버·WPF 별도 PC 복구, 역할별 업무와 권한 역검증, 단절·알림 복구, 제한형 AI, UX 관찰, 중단/rollback을 하나의 실행 기준으로 정리했다. 실행 증거는 `PILOT-YYYYMMDD-HHMM-현장코드-일련번호` 형식의 `run_id`로 연결하고 DB 무결성, 원천별 전후 개수와 파일 SHA-256을 비교한다.

현재 macOS 개발 환경에서는 Windows MSI 설치, 코드 서명, 사내 CA, MDM, 승인 Android 실단말, 고객 유사 네트워크와 별도 복구 PC를 사용할 수 없어 실기 게이트는 모두 `대기`다. 문서만 변경했으므로 FastAPI/WPF/Android 테스트를 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물을 삭제하지 않았다.

## 2026-07-15 제한형 AI provider adapter와 응답 검증

provider 중립 `invoke(payload)` 계약, fake/recording/callable adapter와 명시적 test scope 전용 JSON 네트워크 adapter를 구현했다. provider payload는 정제 질의, 최소 발췌, 안정 ID/hash, prompt version과 허용 출력 형식으로 제한한다. 응답은 크기 제한 안의 완전한 JSON, 기존 citation ID, 중복 없는 claim 구조를 요구하며 숫자·핵심 토큰·부정 극성 규칙으로 claim과 summary를 근거에 대조한다. 낮은 의미 확신과 호출 중 승인·원천·권한 변경은 본문 없는 `INSUFFICIENT_EVIDENCE`로 보류한다.

fake adapter로 success, timeout, 429/5xx 재시도, 비재시도 차단, 잘못된 인용을 결정적으로 재현했다. 별도 단위 검증은 불완전 JSON, 과대 응답, prompt injection, 중복 인용, citation 숫자 변조를 차단한다. 통합 테스트는 provider 호출 중 FieldComment 상태를 변경해 응답 후 원천 재검사와 본문 전체 폐기를 확인하고, provider-bound payload에 주민번호·전화번호·이메일 canary와 제한 원천 원문이 0바이트임을 유지한다. 각 재시도는 같은 `query_id`의 `ai_call_attempts`로 이어진다.

`services/api/.venv/bin/python -m ruff check app tests`와 `pytest --collect-only -q`를 실행해 정적 검사 통과와 116건 수집을 확인했다. 전체 `pytest -q`는 116건 모두 통과했다. `scripts/verify-preserved-tests.ps1`의 수집/JUnit 기준도 116건으로 갱신했다. 이번 환경에서는 WPF·Android 빌드와 통합 스모크를 새로 실행하지 않았으며 기존 SQLite, 로그, 캐시와 테스트 산출물을 삭제하지 않았다.

## 2026-07-15 작업 102 문서 재갱신

현재 코드의 `Settings`와 FastAPI lifespan을 다시 대조해 기본 활성 만료 보존 스케줄러, 3600초 기본 간격과 60~86400초 제한, `system-admin` 즉시 실행 경로를 제품·시스템·데이터·API·보안·배포·로드맵·서버·WPF 문서에 반영했다. 추가 재대조에서는 루트 `GET /`를 포함한 OpenAPI 102개 method/path 조합, ORM 45개 테이블, `Settings` 31개 항목이 현재 핵심 문서에 빠짐없이 반영됐음을 확인했다. 다만 데이터 모델에 남아 있던 “실제 삭제 없음” 문구와 일부 현재 코드 요약의 수동 보존·provider 설명은 자동 만료 처리와 제한형 generic 네트워크 adapter 구현에 맞게 바로잡았다. 116건을 수집하는 현재 FastAPI 코드와 같은 116건을 요구하는 표준 스크립트의 기준선도 상위 문서에서 일치시켰다.

이번 문서 갱신에서 `.venv/bin/python -m pytest --collect-only -q`를 실행해 116건 수집을 확인했다. 전체 pytest, WPF·Android 빌드와 통합 스모크는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물을 삭제하지 않았다.

## 2026-07-15 작업 102 현재 코드 재대조

이 절은 외부 AI 응답 검증과 자동 보존 스케줄러가 추가되기 전 같은 날의 중간 재대조 기록이다. 현재 기준은 위의 116건 수집·통과 기록과 문서 상단의 표준 실행 절을 우선한다.

작업 시작 시 Git 작업 트리는 깨끗했으므로 미커밋 변경을 추정하지 않고 최근 FastAPI, Windows WPF, Android 구현과 현재 개발 문서를 다시 대조했다. FastAPI OpenAPI의 루트 `GET /`를 포함한 102개 method/path 조합과 `docs/api.md`, `services/api/README.md`의 각 102개 표 항목은 누락과 초과가 각각 0건이었다. 서버 ORM 45개 테이블도 `docs/data-model.md`, `services/api/db/README.md`, `services/api/db/migrations/0001_initial_mvp_schema.md`에 모두 반영했다.

당시 외부 AI 운영 제어 구현을 기준으로 제품·시스템·MVP·로드맵·보안·배포·서버·WPF 문서를 다시 대조했다. 서버에는 `system-admin` 전용 승인·프롬프트·운영 정책·감사·보존 API가, WPF에는 별도 `AI 운영` 화면이 구현되어 있어 “운영 승인 API/UI 없음”과 “WPF는 근거 후보 점검 화면만 제공”이라는 오래된 설명을 수정했다. 그 시점의 미구현 범위에는 자동 보존 스케줄러가 포함됐지만 현재 서버 lifespan에는 기본 1시간 간격 스케줄러가 구현되어 있다.

`services/api/.venv/bin/python -m pytest --collect-only -q`를 다시 실행한 결과 현재 코드는 106건을 수집했다. `scripts/verify-preserved-tests.ps1`과 기존 문서는 104건을 고정 기대하고 있어 표준 실행이 수집 단계에서 실패하는 불일치를 확인했다. 이번 요청은 문서 갱신이므로 스크립트 코드는 변경하지 않고 현재 상태와 후속 수정 필요를 문서에 남겼다. 전체 pytest, WPF 빌드·스모크와 Android 빌드·단위 테스트는 새로 실행하지 않았고 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

## 2026-07-15 Windows 통합 기준선 복구 준비

표준 스크립트에 Windows x64와 도구 버전 사전점검, WPF Core TRX, 단계별 로그와 실패 요약, FastAPI/Android JUnit 수치 검사, WPF 실행 전후 DB 통계 및 오늘/과거 날짜 SQL 증거 파일을 추가했다. 동일 run ID 경로에 기존 증거가 있으면 덮어쓰지 않고 새 run ID를 요구하며, `5184` 포트의 외부 서버도 임의로 재사용하거나 종료하지 않는다.

현재 macOS 작업 환경에서는 `baseline-recovery-macos-20260715`로 FastAPI 96건 수집과 96건 전체 통과를 다시 확인해 JUnit과 로그를 보존했다. 이 환경에는 PowerShell과 .NET SDK가 없고 Android 표준 JDK/SDK도 갖춰지지 않아 WPF Core/build/smoke와 Android unit/debug build는 실행하지 않았다. 따라서 이 기록은 서버 회귀의 부분 근거일 뿐 최신 Windows 통합 기준선 확정 기록은 아니다. Windows 배포 준비 PC에서 생략 스위치 없이 표준 스크립트를 실행해 단일 `PASSED` 요약이 생긴 뒤 이 절에 run ID, 실제 WPF/Android 테스트 수와 DB 증거 값을 추가해야 한다.

## 2026-07-14 작업 207 전체 Markdown 코드 정합성 갱신

Git이 추적하는 제품·구현 Markdown 38개를 FastAPI, Windows WPF, Android 현재 코드와 다시 대조했다. 작업 정책 원문인 `AGENTS.md`와 가상환경·빌드 캐시·테스트 산출물 안의 생성 Markdown은 갱신 대상에서 제외했다. 기존 작업 트리에 있던 `docs/verification.md`, `services/api/db/README.md`, `services/api/db/migrations/0001_initial_mvp_schema.md` 변경은 되돌리지 않고 현재 문서 갱신에 합쳤다.

오래된 서버 계정 결정에서 WPF 연동과 첫 로그인 강제 변경을 후속으로 읽을 수 있던 문장을 현재 서버 계정 수명주기 API와 WPF 구현으로 대체했다. Android 배포 설명은 문서 파일 본문 뷰어가 아니라 공개 문서 메타데이터 조회임을 명확히 하고, outbox 범위를 FieldComment와 사진 첨부로 제한했다. 외부 AI 질의 role은 실제 보고서 작성 role 여섯 개로 바로잡고 `ai_sensitive_data_policies`를 상위 데이터 모델, API DB 개요, 초기 스키마와 과거 스키마 요약에 모두 반영했다. 미구현 질의 재생성 경로는 현재 API 표에서 빼고 후속 예외로 분리했다.

FastAPI OpenAPI의 현재 79개 method/path 조합과 `docs/api.md`, `services/api/README.md`의 각 79개 표 항목을 비교해 누락과 초과가 각각 0건임을 확인했다. 서버 ORM 41개 테이블도 `docs/data-model.md`, API DB 개요, 초기 스키마 설명에 모두 포함된다. Git 추적 제품 Markdown 38개의 상대 파일 링크를 검사해 깨진 링크 0건을 확인했고 `git diff --check`도 통과했다. macOS 실행 가능한 `services/api/.venv/bin/python`으로 `pytest --collect-only -q`를 실행해 96건 수집을 확인했다. 문서만 변경했으므로 전체 pytest, WPF/Android 빌드와 스모크 테스트는 새로 실행하지 않았고 기존 SQLite, 캐시, 로그와 테스트 산출물은 삭제하지 않았다.

## 2026-07-14 작업 6 통합 사람형 스모크 기준선

실행 ID `integrated-smoke-20260714-agent6`으로 이 macOS 환경에서 FastAPI pytest를 최종 재실행해 96건 전체 통과를 확인했다. 정상 JUnit과 로그는 `data/local/integrated-smoke/integrated-smoke-20260714-agent6/`에 보존했다. 앞선 두 번의 로그 경로 계산 실패도 삭제하지 않았다. 그중 첫 JUnit은 저장소 한 단계 위의 로컬 `data/local`에, 두 번째 JUnit은 정상 실행 ID 폴더에 남아 있으며 최종 판정은 `fastapi-pytest-final.xml`과 `fastapi-pytest-final.log`를 기준으로 한다.

공통 WPF SQLite, FastAPI 테스트 SQLite, FastAPI Windows 스모크 SQLite는 모두 `quick_check=ok`, `foreign_key_check=0`이었다. 공통 WPF SQLite의 idempotency 중복과 서버 ID 매핑 중복은 각각 0건이었다. Git 상태에는 코드·문서 변경만 표시됐고 추적 중인 금지 산출물은 0건이었다.

현재 머신에는 `dotnet`, 실제 Java runtime, Android SDK/`adb`, Windows 설치 PC와 승인 Android 실단말이 없다. 따라서 새 WPF 통합 코드의 build/smoke와 Android unit/build/실단말은 이 실행에서 통과 판정을 내리지 않는다. WPF 빌드 시도는 `command not found: dotnet`, Android 시도는 `Unable to locate a Java Runtime`으로 종료됐으며 로그를 실행 ID 폴더에 보존했다.

| 영역 | 이번 실행 증거 완료도 | 판정 | 남은 필수 근거 |
| --- | ---: | --- | --- |
| FastAPI 기준선 | 96/96 (100%) | 조건부 가능 | 운영 서버 PC의 HTTPS·인증서·백업/복구 리허설 |
| WPF 최신 build + 통합 스모크 | 0/2 (0%) | 대기 | Windows에서 build와 관리형 FastAPI 연동 스모크 통과 |
| Android unit + build + 실단말 | 0/3 (0%) | 대기 | JDK/SDK 환경의 unit/build와 승인 실단말 시나리오 |
| SQLite·매핑·idempotency·Git | 4/4 (100%) | 가능 | Windows/Android 통합 실행 뒤 같은 검사 재확인 |
| 설치 PC·실단말 교차 검증 | 0/6 (0%) | 대기 | HTTPS, 인증서, 카메라, outbox 재시도, controlled copy, 전경 polling |

전체 운영 배포 판정은 **대기**다. 서버 API 코드 기준선과 현재 누적 DB 무결성은 통과했지만, 완료 기준의 독립 환경 3개 중 FastAPI만 최신 실행 증거가 있고 WPF·Android 및 실제 설치/단말 교차 근거가 없다. Windows와 Android 각 환경의 자동 검증이 통과하면 `조건부 가능`, 설치 PC와 승인 실단말의 6개 교차 항목까지 실행 ID로 대조되면 `가능`으로 올린다.

2026-07-14 현재 FastAPI 코드는 96건이 수집된다. 서버 계정 수명주기 회귀에 AI provider 직전 권한·민감정보·최소 payload 게이트 회귀 4건을 추가한 결과다. 표준 PowerShell 스크립트도 같은 96건을 요구한다.

## 2026-07-14 WPF 사용자별 알림 cursor 영구 보존

WPF 로컬 SQLite에 `server_notification_cursors`, `server_notification_messages`를 추가하고 서버 scope·사용자별 마지막 성공 cursor와 처리한 `message_id`를 한 트랜잭션으로 보존하도록 구현했다. FastAPI `/api/v1/notifications`는 서버 DB 복구에 따른 cursor 역행을 감지할 수 있도록 `X-FlowNote-Notification-Cursor` high-water 헤더를 반환한다. WPF는 역행 시 `RESET_REQUIRED`로 polling을 멈추며 Core 서비스가 `admin`, `system-admin` role을 다시 검사한 한글 확인 동작만 현재 scope·사용자 cursor를 초기화한다. 초기화해도 기존 처리 `message_id`는 삭제하지 않는다.

`FlowNote.Windows.Core.Tests` 5건은 두 사용자·두 서버 URL 격리, 처리 예외 rollback과 재처리 멱등성, 서비스 재생성에 따른 앱 재시작, 로그아웃/재로그인 보존, 로컬 DB 복구 row 부재, 서버 cursor 역행, 일반 사용자 초기화 거부, 관리자 초기화 뒤 기존 `message_id` 멱등 보존, HTTP 401 cursor 불변을 검증해 모두 통과했다. FastAPI 채널 API 테스트 3건은 여러 page에서 high-water 헤더가 안정적으로 유지되는 조건까지 통과했고 WPF 앱과 스모크 프로젝트 빌드에 성공했다.

서버 없이 실행한 WPF 전체 스모크는 통과했다. 테스트 FastAPI를 연결한 실행에서는 cursor/읽음/receipt 대조 구간을 통과했으며 로컬 row는 `server_scope = http://127.0.0.1:5184/`, `user_id = user-admin`, `last_success_cursor = observed_server_cursor = 149`, 처리 메시지는 `chmsg_0b7e7c166b744a7cbf7ded4d2879dbd4`였다. 같은 메시지가 서버 `notification_channel_members.last_read_message_id`에 저장되었고 인수인계 receipt `hreceipt_6a97fe1a089e4160912780f0701914a2`는 `FOLLOW_UP_REQUIRED` 및 읽음·확인·후속 필요 시각을 보존했다. 이후 기존 AI `REPORT_SOURCE` 후보 스모크가 누적 후보 500건 제한으로 이번 실행 row를 찾지 못해 전체 프로세스는 종료 코드 134로 끝났다. 이 후반 실패는 알림 cursor 대조 이후 발생했으며 테스트 DB와 모든 산출물은 삭제하지 않고 보존했다.

## 2026-07-14 작업 102 현재 코드 재대조

작업 시작 시 Git 작업 트리는 깨끗했으므로 미커밋 변경을 추정 반영하지 않고 현재 FastAPI, Windows WPF, Android 코드와 상위 제품 문서의 구현 범위를 다시 대조했다. Android 문서 본문 뷰어 미구현, WPF controlled copy 저장·SHA-256 검증, AI 근거 평가와 외부 호출 전 안전장치 골격 등 기존 구현 설명은 코드와 일치한다. 최신 Windows 코드의 보존 FAILED 큐 전환 기능은 독립 운영 문서와 데이터 모델·결정 기록에는 있었지만 Windows 문서 색인, 구현 목록, 로컬 SQLite 설명, 시스템 맵과 로드맵 연결이 부족해 해당 문서를 보강했다.

이후 서버 계정 수명주기 API와 WPF 운영 화면, 강제 비밀번호 변경, 세션 폐기 코드가 추가되어 상위 제품·시스템·보안·배포·로드맵 문서를 다시 갱신했다. 그 중간 시점에는 `services/api`의 `pytest --collect-only -q`와 `scripts/verify-preserved-tests.ps1` 기준선이 92건이었다. 같은 날 AI provider 직전 권한·민감정보·최소 payload 게이트 회귀가 추가된 현재 기준선은 이 문서 상단에 적은 96건이다. 아래 2026-07-13의 75건 수집·통과 문장도 당시 실행 기록으로 보존한다. 이 중간 문서 갱신에서는 전체 pytest, WPF 빌드·스모크와 Android 빌드·단위 테스트를 새로 실행하지 않았고 기존 테스트 데이터와 산출물은 삭제하지 않았다.

이번 재대조에서는 현재 코드의 설정 모델과 `.env.example`에 있는 `FLOWNOTE_AI_PROVIDER_EXCERPT_MAX_CHARS`, `FLOWNOTE_AI_PROVIDER_MAX_SOURCES`를 API 설정 목록에 반영했다. 이미 구현된 서버 계정·세션 운영 UI는 MVP 후속 후보에서 현재 구현 범위로 옮기고, 후속 항목은 실제 현장 권한·발급 절차 검증으로 좁혔다. `services/api`에서 `pytest --collect-only -q`를 다시 실행해 96건 수집을 확인했으며 전체 pytest, WPF/Android 빌드와 스모크 테스트는 새로 실행하지 않았다. 기존 SQLite, 로그, 캐시와 테스트 산출물은 삭제하지 않았다.

추가 대조에서 서버 ORM의 `ai_sensitive_data_policies`가 상위 데이터 모델에는 반영되어 있으나 API DB 개요와 초기 스키마 설명의 테이블 목록에는 빠진 것을 확인해 두 문서를 코드 기준으로 보완했다. 이 테이블은 고객·현장별 금칙어와 고객 식별자 정책 버전 및 활성 상태를 보존하고 provider payload 생성 전 필터에 적용한다. 현재 ORM 테이블은 `docs/data-model.md`, `services/api/db/README.md`, `services/api/db/migrations/0001_initial_mvp_schema.md` 세 곳에 모두 명시되어 있다.

## 2026-07-14 외부 AI provider 직전 게이트 검증

FastAPI fake provider/spy 경계로 실제 네트워크 없이 다음을 검증한다.

- 문서 공개 버전, 검토 완료 FieldComment, 작업순서 변경 이력, report source가 함께 필요한 질문에서 네 source type이 모두 최소 발췌와 candidate/source/version/trace ID, content hash, rank, prompt version을 갖는다.
- 같은 질문과 후보를 반복하면 질의 trace ID를 제외한 source 배열과 순위가 동일하다.
- 권한 없는 채널, 비공개·삭제 문서, 보관/미검토 FieldComment, 보관 보고서·유효하지 않은 보고서 원천은 `SOURCE_FORBIDDEN` 또는 `INSUFFICIENT_EVIDENCE`이며 provider spy에 후보 ID와 내용이 0바이트다.
- 주민등록번호·전화번호·이메일, 계정/token/경로/고객 식별자와 현장별 금칙어가 든 원천은 후보 생성 단계에서 제외되어 candidate ID와 원문이 provider payload에 0바이트다. 사용자 질의의 주민등록번호·전화번호·이메일만 대체 표식으로 마스킹하며 일반 오류와 호출 감사에는 검출 원문을 남기지 않는다.
- 승인 철회 직후 신규 질의는 `APPROVAL_REVOKED`로 차단되고 호출 횟수는 증가하지 않는다. 같은 DB의 `/api/v1/ai-search/quality`와 ground-truth 평가는 계속 동작한다.
- scope readiness가 미달이면 외부 호출 기능과 승인이 켜져 있어도 `AI_READINESS_NOT_MET`이고 provider spy 호출은 0회다. readiness 응답에서 네 원천별 부족 수, 승인 질문 48건과 범주×유형별 2건 부족 수, 품질 임계값, provider 심사 대기를 대조한다.
- 승인 사례 실행은 허용 순위와 `asOf`를 적용하고 run별 precision@k, recall@k, excluded-source violation, citation trace 성공률을 누적 비교한다. 임의 표본은 `trace_table`, `trace_id`, `trace_version_id`로 원문 화면과 DB row까지 역추적한다.

사람형 표본 검토는 테스트용 고객/현장 scope와 운영 scope를 섞지 않는다. 한 현장·한 라인에서 `line + equipment` 또는 `process + error_type`처럼 태그 두 축으로 표본을 고르고, `ANALYZED`/`REVIEWED`/`SELECTED` FieldComment만 원문 품질과 관리자 분석의 일치 여부를 확인한다. 운영 원문은 테스트 DB나 fake provider payload에 복제하지 않고 candidate/source ID와 정제된 점검 결과만 기록한다.

## 2026-07-13 전체 Markdown 코드 정합성 갱신

Git으로 추적하는 Markdown 문서 전체를 현재 FastAPI, Windows WPF, Android 코드와 다시 대조했다. 저장소 작업 규칙인 `AGENTS.md`는 제품 문서가 아니므로 내용 수정 대상에서 제외했고, 날짜별 작업·검증 수치는 당시 이력으로 보존하면서 현재 기능을 설명하는 문장만 최신 코드에 맞췄다.

주요 정정은 Android의 문서 기능을 파일 본문 열람으로 과장하지 않고 공개 문서 목록·상세 메타데이터 조회와 FieldComment 문서/버전 연결 범위로 명시한 것, 서버 DB 문서에 외부 AI 질의·근거 snapshot·인용·호출 감사·전송 승인 및 `controlled_copy_grants` 테이블을 추가한 것, WPF controlled copy가 로컬 원본 복사나 동기화 큐가 아니라 서버의 사용자·세션 바인딩 1회성 스트리밍과 저장 후 SHA-256 검증임을 반영한 것이다.

FastAPI OpenAPI의 루트 `GET /`를 포함한 전체 method/path 71개가 `docs/api.md` 또는 `services/api/README.md`에 모두 존재하고, 서버 ORM의 모든 `__tablename__`이 DB 스키마 문서 3곳에 빠짐없이 명시된 것도 확인했다. 추적 Markdown의 상대 파일 링크와 `git diff --check`도 통과했다.

`services/api`에서 `pytest --collect-only -q`로 75건을 확인한 뒤 전체 pytest를 실행해 75건이 모두 통과했다. 이번 작업은 문서와 예제 환경 변수 갱신이므로 WPF 빌드·스모크와 Android 빌드·단위 테스트는 새로 실행하지 않았다. 기존 SQLite, 로그, pytest cache와 테스트 산출물은 삭제하지 않았다.

## 2026-07-13 AI 근거 검색 회귀 평가 반영

문서 갱신 과정에서 추가된 `test_ai_search_ground_truth_evaluation_is_reproducible_and_persisted`는 안정 candidate ID와 content hash, 재생성 전후 순위, 네 원천 커버, 제외 근거, `INSUFFICIENT_EVIDENCE`, 평가 실행·케이스 SQLite 누적을 검증한다.

controlled copy 구현 후 `services/api`의 `pytest --collect-only -q`와 전체 pytest에서 75건 수집·통과를 확인했다. 이 환경에는 `dotnet` 명령이 없어 WPF 빌드와 WPF 스모크는 실행하지 못했다. 기존 DB, 로그, 테스트 산출물과 pytest cache는 삭제하지 않았다.

## 2026-07-13 외부 AI 질의 안전장치 검증

`scripts/verify-preserved-tests.ps1`의 FastAPI 수집 기대값을 58개에서 68개로 갱신했다. `services/api`에서 테스트를 다시 수집해 68개를 확인했고 전체 pytest 68건이 통과했다. 추가 기준에는 AI 근거 검색 2개와 외부 AI 질의의 비활성 기본값, 금지 목적, 전송 승인, 근거 snapshot, 응답 미저장, 권한, 프롬프트 불변성 검증 8개가 포함된다. 이번 실행에서는 WPF 빌드와 WPF 스모크를 실행하지 않았고 기존 DB, 로그, 파일과 실패 흔적은 삭제하지 않았다.

## 2026-07-13 표준 보존형 검증 기준 갱신

`scripts/verify-preserved-tests.ps1`의 FastAPI 수집 기대값을 53개에서 58개로 갱신했다. 테스트 파일의 최상위 `test_*` 함수를 파일별로 확인한 결과 합계는 58개였고, 기존 기준선 이후 추가된 테스트는 다음 5개다.

- `tests/test_auth_api.py`: 승인된 Android 단말 로그인과 미승인·비활성 단말 로그인 거부 2개
- `tests/test_terminal_devices_api.py`: 관리자 단말 등록·조회·변경·비활성화, 단말 교체·폐기 상태 불변식, 비관리자 접근 거부 3개

이번에는 테스트 수집 개수와 보존 상태만 점검했으므로 전체 회귀 통과 기록으로 판정하지 않는다. 표준 검증이 가능한 환경에서 `.\scripts\verify-preserved-tests.ps1`의 시작부터 Git 사후 점검까지 통과한 결과를 추가로 남겨야 한다.

실행 가능한 보존 점검에서는 공통 SQLite `data/local/flownote.local.sqlite`의 `PRAGMA quick_check`가 `ok`, `PRAGMA foreign_key_check` 결과가 0건이었다. `data/local/flownote.local.sqlite`, `data/local/Files/`, WPF `bin/`과 `obj/` probe 경로에 Git 제외 규칙이 적용됨을 확인했다. `git status --short --untracked-files=all`에는 이번 문서와 표준 스크립트 변경만 표시되었고, `git diff --cached --name-only`는 비어 있었다. 기존 DB, 로그, 파일과 실패 흔적은 삭제하지 않았다.

## 2026-07-10 코드-문서 정합성 재점검

현재 FastAPI 테스트를 다시 수집한 결과 58개가 정상 수집되었다. 이번 문서 갱신에서는 전체 pytest, WPF 빌드, WPF 스모크를 새로 실행하지 않았으며 기존 DB와 테스트 산출물도 삭제하거나 초기화하지 않았다.

현재 코드의 라우터, 서버 ORM 모델, Windows 서버 API 클라이언트와 Android 최소 앱을 상위 문서와 대조했다. 승인 단말 관리, 채널/인수인계, Android outbox, AI 근거 후보 read model은 구현 범위로 유지한다. `/api/v1/ai/queries` 생성·조회, `ai_queries` 계열 모델, 기능 플래그·목적·외부 전송 승인·근거 snapshot 검사는 안전장치 골격으로 검증한다. 운영 provider client, 네트워크 호출과 질의 재생성은 아직 검증 범위가 아니다.

## WPF 스모크 필수 조건

WPF 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 사용한다. 표준 스크립트는 실행 중 `FLOWNOTE_LOCAL_DATA_DIR`와 `FLOWNOTE_LOCAL_DATABASE_PATH`를 비워 임시 SQLite가 아니라 공통 SQLite에 누적 기록되도록 한다.

현재 스모크 테스트는 다음 항목을 필수로 검증한다.

- 오늘 날짜의 인수인계 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 오늘 날짜의 사진 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 기존 인수인계 또는 사진 날짜 폴더 중 과거 날짜 폴더를 랜덤 선택하고, 그 안의 기존 문서에 버전 코멘트를 추가해 버전 번호가 1 증가했는지 확인한다.
- 과거 날짜 검증은 기존 날짜 폴더와 기존 문서만 대상으로 하며, 과거 날짜 폴더나 과거 날짜 문서를 새로 만들지 않는다.
- TXT/PDF/XLSX/이미지 미리보기 샘플 기준을 확인하고, 각 유형별 열람 종료, 자동 닫힘, 다운로드 차단 로그를 공통 SQLite에 누적한다.
- 실행 출력의 `Preview audit smoke` 줄에 파일 유형, 샘플 파일 경로, 로그 ID가 남는다.
- `FLOWNOTE_API_BASE_URL`이 없더라도 `http://127.0.0.1:5184` 로컬 FastAPI 서버가 실행 중이면 서버 로그인, 문서 등록, 버전, 공개 조회를 검증한다.
- 서버 URL이 없으면 WPF 로컬 계정 fallback이 허용되는지 확인한다.
- 서버 로그인 응답이 401 또는 403이면 같은 로그인 ID의 WPF 로컬 계정으로 우회하지 않는지 확인한다.

controlled copy API 회귀는 `tests/test_controlled_copy_api.py`에서 전체 기본 role의 허용·거부, 정확한 공개 버전, SHA-256 일치, 만료·재사용·다른 사용자/세션·문서/버전 불일치·Range·경로 순회·전송 전 파일 변경을 검증한다. WPF 수동 확인에서는 허용 role의 서버 저장과 해시 검증 안내, 비허용 role의 기존 차단 안내를 확인하고 `document_access_logs`와 `activity_history`의 사용자·단말·버전·사유를 대조한다.

과거 날짜 후보가 하나도 없으면 스모크 테스트는 실패한다. 이 경우 DB를 삭제하지 말고 누적 데이터 상태를 확인해 다음 분석에 사용한다.

## 2026-07-08 누적 스모크 기록

공통 SQLite `data/local/flownote.local.sqlite`에는 2026-07-08 15:25 KST 기준 `smoke-102-human-20260708-132307`, `smoke-102-20260708143141`, `102-20260708143304`, `smoke-102-human-20260708-152335` 실행 기록이 누적되어 있다. 이 기록은 삭제하지 않고 이후 회귀 검증의 기준 데이터로 사용한다.

- `smoke-102-human-20260708-132307` 실행에서는 오늘 날짜 폴더 기준으로 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달` 문서가 등록되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 라인A 계량기 사진은 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `사진/2026-06-29` 문서 `사진당일라인A20260629113103758`의 버전을 v4로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- `102-20260708143304` 실행에서는 오늘 날짜 기준 인수인계/사진 문서 12건과 보고서 문서 6건이 추가되었다. 이 중 3건은 v2가 `PUBLISHED`인 공개 문서, 9건은 `WORKING`, 보고서 6건은 `IN_REVIEW` 상태다.
- `102-20260708143304` 실행에서는 FieldComment 24건이 추가되었고 검토 상태는 `ANALYZED` 8건, `REVIEWED` 8건, `SELECTED` 8건으로 남았다. 신호등식 입력도 `green`, `yellow`, `red`가 각각 8건씩 누적되었다.
- `102 사람형 스모크 작업순서 20260708143304` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 작업순서 항목은 `COMPLETED` 1건, `HOLD` 1건으로 남았다. 변경 이력은 보드 생성 1건, 항목 추가 2건, 상태 변경 3건, 보류 사유 변경 1건이다.
- `102 AI 근거 축적 보고서 20260708143304-01`부터 `-06`까지 6개 보고서 문서는 각각 `report_sources` 4건을 보존한다. 전체 source 구성은 FieldComment 12건, 문서 6건, 작업순서 이력 6건이다.
- `smoke-102-human-20260708-152335` 실행은 2026-07-08 15:23 KST에 시작된 사람형 다중 actor 스모크다. 실행 전 누적은 `documents` 1574건, `document_versions` 2308건, `field_comments` 1409건, 검토 준비 FieldComment 226건, `reports` 61건, `report_sources` 237건, `document_view_logs` 2090건, `activity_history` 68415건, `work_sequence_change_history` 580건이었다.
- 같은 실행에서는 오늘 날짜 기준 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달`, `AI 근거 축적 보고서` 문서가 추가되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 사진 문서는 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-06` 문서 `doc-ba4f93c8dd0d46a19a57b53cd2f211a8`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- 같은 실행에서는 FieldComment 6건이 추가되었고 검토 준비 상태는 `ANALYZED` 2건, `REVIEWED` 2건, `SELECTED` 2건이다. 신호등식 입력은 `green` 3건, `yellow` 3건으로 남았다.
- `102 사람형 스모크 작업순서 20260708-152335` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 실행 전후 `work_sequence_change_history`가 580건에서 582건으로 증가했다.
- `smoke-102-human-20260708-152335 AI 근거 축적 보고서` 문서 `doc-e1500f91f8284e03a31c3e2f3c3e96d0`는 `report_sources` 9건을 보존한다.
- 2026-07-08 15:25 KST 기준 누적 테이블 수는 `documents` 1578건, `document_versions` 2315건, `field_comments` 1415건, `field_comment_attachments` 109건, `report_sources` 246건, `notifications` 1557건, `server_sync_queue` 771건, `work_sequence_boards` 116건, `work_sequence_items` 232건, `work_sequence_change_history` 582건, `work_sequence_notification_candidates` 237건이다.
- 2026-07-08 15:25 KST 기준 전체 FieldComment 상태는 `NEW` 1181건, `ANALYZED` 78건, `REVIEWED` 77건, `SELECTED` 77건, `EXCLUDED` 1건, `ARCHIVED` 1건이다. 신호등식 입력 누적은 `green` 302건, `yellow` 162건, `red` 70건이다.

## 2026-07-09 서버 동기화 스모크 기록

2026-07-09 KST에 FastAPI 서버를 `http://127.0.0.1:5184`로 실행한 상태에서 WPF 스모크 테스트를 실행했다. 스모크는 오늘 날짜 인수인계/사진 등록, 과거 날짜 기존 사진 문서 버전 증가, 문서 최초 등록 이후 버전/공개/상태/FieldComment/첨부/접근 로그/보고서 큐 순서 재시도, 서버 ID 매핑 복구, 보고서 중복 재전송 방지를 검증했다.

- 서버 연결 재시도 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 284건이다.
- 실패 큐는 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 20건으로 분류된다. 서버 URL 미설정 실패는 서버 연결 재시도 후 남아 있지 않다.
- `server_id_mappings`는 648건이며 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다.
- 누적 테이블 수는 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `notifications` 1576건, `server_sync_queue` 804건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `work_sequence_notification_candidates` 239건이다.

## 2026-07-09 사람형 AI 근거 스모크 기록

2026-07-09 08:55 KST에 `smoke-102-human-20260709-085509` 사람형 다중 actor 스모크를 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-085509` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-085509.out.log`와 `.err.log`에 남겼다.

- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 성공 이력을 `activity_history`에 남겼다.
- 실행 전 누적은 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `notifications` 1576건, `server_sync_queue` 804건이었다.
- 실행 후 누적은 `documents` 1619건, `document_versions` 2366건, `field_comments` 1461건, `field_comment_attachments` 114건, `report_sources` 278건, `document_view_logs` 2156건, `activity_history` 78943건, `work_sequence_boards` 118건, `work_sequence_items` 238건, `work_sequence_change_history` 592건, `notifications` 1586건, `server_sync_queue` 854건이다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 5건, 사진 5건이 되었다. 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 신호등식 기록은 `green` 8건, `yellow` 8건, `red` 8건으로 남겼다.
- `102 사람형 스모크 작업순서 20260709-085509` 보드 1건과 작업 항목 4건을 추가했다. 작업순서 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-7485b983de164d9b9aeb56a8385ee7dd`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- FastAPI pytest는 `services/api`에서 51개 테스트를 실행해 51개 모두 통과했다. 이 실행 환경에는 `dotnet` 명령이 없어 WPF C# 스모크 테스트는 실행하지 못했다.

## 2026-07-09 사람형 AI 근거 스모크 추가 기록

2026-07-09 09:41 KST에 `smoke-102-human-20260709-094127` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-094127` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-094127.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 166건, `documents` 1619건, `document_versions` 2366건, `field_comments` 1461건, `field_comment_attachments` 114건, `report_sources` 278건, `document_view_logs` 2156건, `activity_history` 78943건, `work_sequence_boards` 118건, `work_sequence_items` 238건, `work_sequence_change_history` 592건, `notifications` 1586건, `server_sync_queue` 854건이었다.
- 실행 후 누적은 `user_accounts` 174건, `documents` 1629건, `document_versions` 2377건, `field_comments` 1485건, `field_comment_attachments` 117건, `report_sources` 296건, `document_view_logs` 2168건, `activity_history` 79026건, `work_sequence_boards` 119건, `work_sequence_items` 242건, `work_sequence_change_history` 597건, `notifications` 1596건, `server_sync_queue` 904건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 9건, 사진 9건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 신호등식 기록은 `green` 8건, `yellow` 8건, `red` 8건으로 남겼다.
- `102 사람형 스모크 작업순서 20260709-094127` 보드 1건과 작업 항목 4건을 추가했다. 공통 SQLite에 직접 남은 항목 상태는 `TODO` 1건, `IN_PROGRESS` 1건, `HOLD` 1건, `COMPLETED` 1건이다. 단, 현재 FastAPI와 WPF 코드의 정식 작업순서 대기 상태는 `WAITING`이며 `TODO`는 새 API/화면에서 허용하는 상태가 아니다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-e95a9f4b10d347f588132370f663f3ae`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 2026-07-09 09:41 KST 실행 후 전체 FieldComment 상태는 `NEW` 1221건, `ANALYZED` 88건, `REVIEWED` 86건, `SELECTED` 86건, `EXCLUDED` 2건, `ARCHIVED` 2건이다. 신호등식 입력 누적은 `green` 323건, `yellow` 180건, `red` 87건이다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 284건, `PENDING` 100건이다. 실패 큐 분류는 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 10건, 구 FieldNote 첨부 큐 10건이다.

## 2026-07-09 사람형 AI 근거 스모크 11:34 기록

2026-07-09 11:34 KST에 `smoke-102-human-20260709-113417` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-113417` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-113417.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 184건, `documents` 1661건, `document_versions` 2416건, `field_comments` 1563건, `field_comment_attachments` 121건, `report_sources` 318건, `document_view_logs` 2229건, `activity_history` 79312건, `work_sequence_boards` 121건, `work_sequence_items` 248건, `work_sequence_change_history` 607건, `notifications` 1624건, `server_sync_queue` 963건이었다.
- 실행 후 누적은 `user_accounts` 192건, `documents` 1671건, `document_versions` 2427건, `field_comments` 1587건, `field_comment_attachments` 124건, `report_sources` 336건, `document_view_logs` 2241건, `activity_history` 79395건, `work_sequence_boards` 122건, `work_sequence_items` 252건, `work_sequence_change_history` 612건, `notifications` 1634건, `server_sync_queue` 1013건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 18건, 사진 18건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1294건, `ANALYZED` 97건, `REVIEWED` 95건, `SELECTED` 95건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 344건, `yellow` 198건, `red` 104건이다.
- `102 사람형 스모크 작업순서 20260709-113417` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-07` 문서 `doc-74cdbc614996469fb09542dcb50e10f5`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 200건이다.
- FastAPI pytest는 `services/api`에서 53개 테스트를 실행해 53개 모두 통과했다. 이 실행 환경에는 `dotnet` 명령이 없어 WPF C# 스모크 테스트는 실행하지 못했다.

## 2026-07-09 사람형 AI 근거 스모크 13:19 기록

2026-07-09 13:19 KST에 `smoke-102-human-20260709-131928` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-131928` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-131928.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 192건, `documents` 1671건, `document_versions` 2427건, `field_comments` 1587건, `field_comment_attachments` 124건, `report_sources` 336건, `document_view_logs` 2241건, `activity_history` 79395건, `work_sequence_boards` 122건, `work_sequence_items` 252건, `work_sequence_change_history` 612건, `notifications` 1634건, `server_sync_queue` 1013건이었다.
- 실행 후 누적은 `user_accounts` 200건, `documents` 1681건, `document_versions` 2438건, `field_comments` 1611건, `field_comment_attachments` 127건, `report_sources` 354건, `document_view_logs` 2253건, `activity_history` 79478건, `work_sequence_boards` 123건, `work_sequence_items` 256건, `work_sequence_change_history` 617건, `notifications` 1644건, `server_sync_queue` 1063건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 22건, 사진 22건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1306건, `ANALYZED` 101건, `REVIEWED` 99건, `SELECTED` 99건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 352건, `yellow` 206건, `red` 112건이다.
- `102 사람형 스모크 작업순서 20260709-131928` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-4fb6550f9d02455aacec9bd90fc9dd96`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 250건이다.
- 실행 로그의 마지막 결과는 `Smoke 102 human-like AI evidence run passed.`이며 `.err.log`는 비어 있다.

## 2026-07-09 사람형 AI 근거 스모크 14:28 기록

2026-07-09 14:28 KST에 `smoke-102-human-20260709-142853` 사람형 다중 actor 스모크를 추가 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-142853` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-142853.out.log`와 `.err.log`에 남겼다.

- 실행 전 누적은 `user_accounts` 200건, `documents` 1681건, `document_versions` 2438건, `field_comments` 1611건, `field_comment_attachments` 127건, `report_sources` 354건, `document_view_logs` 2253건, `activity_history` 79478건, `work_sequence_boards` 123건, `work_sequence_items` 256건, `work_sequence_change_history` 617건, `notifications` 1644건, `server_sync_queue` 1063건이었다.
- 실행 후 누적은 `user_accounts` 208건, `documents` 1691건, `document_versions` 2449건, `field_comments` 1635건, `field_comment_attachments` 130건, `report_sources` 372건, `document_view_logs` 2265건, `activity_history` 79561건, `work_sequence_boards` 124건, `work_sequence_items` 260건, `work_sequence_change_history` 622건, `notifications` 1654건, `server_sync_queue` 1113건이다.
- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 이력을 `activity_history`에 남겼다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 26건, 사진 26건이 되었다. 보고서 문서 2건도 `Report`, `IN_REVIEW` 상태로 추가되었다.
- 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다. 구성은 인수인계 TXT 4건, 사진 JPG 4건, 보고서 MD 2건, FieldComment 첨부 JPG 3건이다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 실행 후 전체 FieldComment 상태는 `NEW` 1318건, `ANALYZED` 105건, `REVIEWED` 103건, `SELECTED` 103건, `EXCLUDED` 3건, `ARCHIVED` 3건이다.
- 신호등식 입력 누적은 `green` 360건, `yellow` 214건, `red` 120건이다.
- `102 사람형 스모크 작업순서 20260709-142853` 보드 1건과 작업 항목 4건을 추가했다. 작업 항목 상태는 현재 정식 대기 상태인 `WAITING`과 `IN_PROGRESS`, `HOLD`, `COMPLETED`를 사용했고 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. 이번 실행의 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이며 각 보고서 문서는 source 9건을 보존한다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-687b7fd7ea144242be4345e5e7013d97`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 실행 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 300건이다. `server_id_mappings`는 648건이고 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다.
- 구 FieldNote 잔존 데이터는 `field_notes` 345건, `field_note_attachments` 20건이며, 새 작업 대상이 아닌 보존 테스트 기록으로 유지한다.
- 실행 로그의 마지막 결과는 `Smoke 102 human-like AI evidence run passed.`이며 `.err.log`는 비어 있다.

## 2026-07-10 서버-WPF 동기화 큐 정리 기록

공통 SQLite `data/local/flownote.local.sqlite`의 큐와 매핑을 삭제 없이 점검했다. 실행 전 상태는 `SYNCED` 520건, `FAILED` 293건, `PENDING` 300건이었다. 기존 실패 293건은 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 20건, 실제 서버/설정 오류 9건으로 분류했다. 실제 서버/설정 오류 9건은 현재 모두 서버 URL 미설정 사유다.

`PENDING` 300건은 모두 초기 로컬 큐의 `action = create` 형식이었다. 구성은 문서 60건, 문서 버전 6건, 문서 열람 로그 72건, FieldComment 144건, FieldComment 첨부 18건이다. 현재 서버 동기화 계약으로 임의 변환하지 않고 `FAILED`와 구 형식 별도 마이그레이션 보류 사유로 분류했다. 300행과 연결 로컬 데이터는 삭제하지 않았고 `attempt_count`는 전부 0을 유지했으며, `activity_history`에 `server_sync.legacy_queue_classified` 요약 이력을 추가했다.

정리 후 상태는 `SYNCED` 520건, `FAILED` 593건, `PENDING` 0건이다. `server_id_mappings`는 648건이고 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건을 유지했다. WPF 재시도 코드는 구 형식 `create` 큐와 선행 서버 ID가 없는 후행 큐를 서버 호출 및 시도 횟수 증가 전에 보류하도록 확인했다. 정식 재시도 순서는 문서 최초 등록, 버전, 공개, 상태, FieldComment, 검토 변경, 첨부, 접근 로그, 보고서다.

FastAPI 전체 pytest 55건이 모두 통과했다. WPF Core, 스모크, WPF 앱 빌드도 모두 경고·오류 0건을 확인했다. 스모크는 누적 사용자와 500행 목록 한도를 가정하던 검증을 전체 시드/전체 큐 기준으로 보강하고, 존재하지 않는 서버 operator/device ID를 보내던 AI 품질 입력을 정리한 뒤 로컬 FastAPI `http://127.0.0.1:5184`와 함께 최종 통과했다.

최종 통과 실행은 오늘 `2026-07-10` 사진과 인수인계 문서를 등록·조회했고, 기존 `인수인계/2026-07-01` 문서를 새 폴더나 문서 생성 없이 v1에서 v2로 증가시켰다. 서버 재시도와 성공 이력도 `activity_history`에 누적됐다. 반복 검증 실행까지 포함한 최종 큐는 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이며, 실패는 구 형식 create 300건, 선행 문서/근거 미동기화 229건, 선행 FieldComment 미동기화 20건, 로컬 파일 누락 20건, 구 FieldNote 20건이다. `server_id_mappings`는 767건이고 중복 그룹은 0건이다. 공통 SQLite `PRAGMA quick_check`는 `ok`, 외래 키 위반은 0건이었으며 기존 SQLite와 테스트 산출물은 그대로 보존했다.

## 2026-07-10 사람형 AI 근거 스모크 14:33 기록

2026-07-10 14:33 KST에 `smoke-101-human-20260710-143343` 사람형 다중 actor 스모크를 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke101/2026-07-10/smoke-101-human-20260710-143343` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-101-20260710-143343.out.log`와 `.err.log`에 남겼다.

- 직전 `smoke-101-human-20260710-143325` 시도는 문서 등록 SQL 매개변수 수 불일치로 중단되었다. 중단 전에 생성된 계정 8건, 로그인 이력 8건, 입력 파일 1건과 오류 로그는 삭제하지 않고 실패 재현 기록으로 보존했다.
- 정상 실행 전 누적은 `user_accounts` 221건, `documents` 1798건, `document_versions` 2586건, `field_comments` 1745건, `field_comment_attachments` 136건, `report_sources` 408건, `document_view_logs` 2463건, `activity_history` 122030건, `work_sequence_boards` 128건, `work_sequence_items` 268건, `work_sequence_change_history` 642건, `notifications` 1728건이었다.
- 정상 실행 후 누적은 `user_accounts` 229건, `documents` 1808건, `document_versions` 2597건, `field_comments` 1769건, `field_comment_attachments` 139건, `report_sources` 426건, `document_view_logs` 2487건, `activity_history` 122120건, `work_sequence_boards` 129건, `work_sequence_items` 272건, `work_sequence_change_history` 646건, `notifications` 1752건이다.
- 정상 실행에서 승인 단말 로그인 계정 8건, 문서 10건, 문서 버전 11건, FieldComment 24건, 첨부 3건, 보고서 근거 18건, 문서 열람 로그 24건, 활동 이력 90건, 작업순서 보드 1건과 항목 4건, 작업순서 변경 이력 4건, FieldComment 알림 24건이 증가했다.
- 오늘 날짜 `2026-07-10` 기준 인수인계 문서 4건과 사진 문서 4건을 등록·조회했다. 정상 실행 후 오늘 날짜 폴더의 인수인계와 사진 문서는 각각 8건이다. 인수인계 2건은 `PUBLISHED`, 나머지 인수인계 2건과 사진 4건은 `WORKING` 상태로 남겼다.
- FieldComment 상태는 `NEW`, `ANALYZED`, `REVIEWED`, `SELECTED`가 각각 6건이며, 신호등식 입력은 `green` 12건, `yellow` 9건, `red` 3건이다. 24건의 문서 열람 로그는 모두 `window_closed` 종료 사유를 보존한다.
- `101 사람형 스모크 작업순서 20260710-143343` 보드는 `LINE-A`, `2026-07-10`, `ACTIVE` 기준으로 생성했다. 항목 상태는 `WAITING`, `IN_PROGRESS`, `HOLD`, `COMPLETED`가 각각 1건이며 변경 이력은 항목 추가 4건이다.
- `101 AI 근거 축적 보고서 20260710-143343-01`, `-02` 문서를 `Report`, `IN_REVIEW` 상태로 만들었다. 각 보고서는 FieldComment 4건, 문서 3건, 작업순서 이력 2건으로 source 9건을 보존하며, 전체 source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이다.
- 과거 날짜 무작위 검증은 기존 `사진/2026-07-07` 문서 `doc-0b1c18ed52b345bd98e331aebb50fefb`의 버전을 v1에서 v2로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- 이 실행은 서버 동기화 큐를 추가하거나 재시도하지 않았다. 실행 후 큐는 기존과 같은 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이고 `server_id_mappings`는 767건이다.
- 공통 SQLite `PRAGMA quick_check`는 `ok`, 외래 키 위반은 0건이다. 정상 실행 결과 JSON은 `.out.log`에 남았고 `.err.log`는 비어 있다.

## 산출물 보존과 Git 점검

테스트가 생성한 DB, 로그, 입력 파일, 출력 파일은 보존한다. 단, Git에는 다음 원칙을 적용한다.

- SQLite와 WAL/SHM 보조 파일은 테스트/개발 검증 기록으로 로컬에 보존하되 경로와 관계없이 Git으로 추적하거나 커밋하지 않는다.
- PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/`, `services/api/storage/`, `bin/`, `obj/` 하위 파일은 Git 제외 대상이다.
- 새 테스트 산출물 경로가 생기면 삭제하지 말고 먼저 `.gitignore` 제외 규칙을 추가한다.
- 이미 Git에 잡힌 테스트 산출물은 파일을 삭제하지 말고 `git rm --cached`로 추적만 해제한다.

표준 스크립트의 Git 점검은 금지 패턴이 `git status`나 추적 파일 목록에 잡히면 실패한다. 실패 메시지는 보존 대상 파일을 지우라는 뜻이 아니라 `.gitignore` 보강 또는 추적 해제가 필요하다는 뜻이다.

## WPF MSI 패키징 검증

WPF MSI는 Windows 배포 준비 PC에서 다음 순서로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.files.txt
git status --short --untracked-files=all
```

`.files.txt`에는 앱 실행 파일, `.deps.json`, `.runtimeconfig.json`, 앱 DLL, 의존 DLL, 네이티브 DLL만 있어야 한다. 다음 항목이 포함되면 `package-wpf-msi.ps1`가 실패해야 한다.

- 로컬 SQLite, WAL, SHM, DB 파일
- `Data\`, `Files\`, `storage\`, `logs\` 계열 경로
- `test`, `smoke`, `sample-registration`, `customer`가 들어간 파일
- PDF, Office, HWP, DWG, 이미지, 압축 파일, TXT/MD 같은 고객 파일 또는 테스트 산출물

self-contained 패키지가 필요한 PC는 별도 MSI로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.files.txt
```

설치 후에는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고 앱을 실행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

검증 기준은 다음과 같다.

- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에는 실행 파일과 의존 파일만 있다.
- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App` 아래에는 `flownote.local.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, `Files\`가 생기지 않는다.
- `C:\FlowNote\LocalData\flownote.local.sqlite`와 `C:\FlowNote\LocalData\Files`가 생성된다.
- .NET Windows Desktop Runtime이 없는 PC에서는 framework-dependent MSI 실행 실패를 기록하고, self-contained MSI 실행 결과를 별도로 기록한다.
- WebView2 Runtime이 없는 PC에서는 문서 뷰어 실패 안내가 표시되는지 확인하고, WebView2 Runtime 설치 후 같은 문서 열람이 성공하는지 기록한다.
- `git status`에서 `artifacts\wpf-msi`, publish 산출물, MSI 파일, `.wixpdb`가 추적 대상으로 잡히지 않는다.

설치 후 자동 점검은 다음 스크립트로 수행한다. 이 스크립트는 MSI 산출물 목록의 금지 패턴, 설치 폴더의 로컬 DB/`Files` 혼입 여부, `FLOWNOTE_LOCAL_DATA_DIR` 기준 로컬 데이터 생성 여부, .NET Windows Desktop Runtime, WebView2 Runtime, 선택적 서명 검증을 확인한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"
```

framework-dependent MSI 실패 양상은 .NET Windows Desktop Runtime이 없는 Windows PC에서 다음 기준으로 남긴다.

- MSI 설치 자체가 성공하더라도 앱 실행 시 .NET Desktop Runtime 요구 오류가 표시되는지 기록한다.
- `dotnet --list-runtimes` 결과에 `Microsoft.WindowsDesktop.App 10.`이 없는 상태임을 기록한다.
- 같은 PC에서 self-contained MSI 설치 후 앱 실행 성공 여부를 별도로 기록한다.

WebView2 Runtime 유무 검증은 같은 PDF 문서로 두 번 수행한다.

- WebView2 Runtime 미설치 또는 제거 상태에서 문서를 열어 `문서 뷰어를 시작할 수 없습니다.` 안내가 표시되는지 확인한다.
- Microsoft Edge WebView2 Runtime 설치 후 같은 문서가 WebView2 PDF 뷰어로 표시되고 저장/인쇄/외부 창 열기 차단이 유지되는지 확인한다.

코드 서명 검증은 서명 인증서가 준비된 배포 준비 PC에서 수행한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

서명 인증서가 준비된 PC에서는 같은 설치 후 점검에 `-CheckSignature`를 추가한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -CheckSignature
```

## Windows MSI 실기 검증 기록

2026-07-08 KST 기준 현재 이 저장소 작업 환경은 macOS이며 `pwsh`, `dotnet`, `wix`, `msiexec`, `signtool`이 없어 Windows MSI 실기 검증을 완료할 수 없다. 아래 기록은 Windows 배포 준비 PC와 설치 대상 PC에서 채운 뒤 운영 배포 확정 근거로 사용한다. 실제 실행 전까지 MSI 운영 배포 상태는 `대기`다.

### 실행 명령

배포 준비 PC에서 기본 MSI와 self-contained MSI를 모두 생성한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
```

설치 대상 PC에서는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고, 앱을 한 번 실행해 로컬 DB와 `Files\` 생성까지 확인한 뒤 자동 점검을 수행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
$env:FLOWNOTE_LOCAL_DATA_DIR = "C:\FlowNote\LocalData"
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

msiexec /x .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

git status --short --untracked-files=all
```

서명 인증서가 준비된 경우에는 `-Sign`으로 패키징하고 EXE와 MSI를 모두 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

### 결과 표

| 항목 | 상태 | 기록할 증거 |
| --- | --- | --- |
| 기본 MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| self-contained MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| 기본 MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| self-contained MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| 설치 폴더에 실행 파일과 의존 파일만 존재 | 대기 | `verify-wpf-msi-install.ps1` 출력 |
| 로컬 DB와 `Files\`가 `C:\FlowNote\LocalData`에만 생성 | 대기 | `verify-wpf-msi-install.ps1` 출력, 실제 경로 |
| .NET Windows Desktop Runtime 없는 PC의 framework-dependent 실행 실패 양상 | 대기 | `dotnet --list-runtimes` 결과, 오류 메시지 또는 스크린샷 설명 |
| 같은 PC의 self-contained MSI 실행 결과 | 대기 | 실행 성공/실패, 오류 메시지 |
| WebView2 Runtime 미설치 상태 PDF 열람 안내 | 대기 | 안내 문구, PC명, Windows 버전 |
| WebView2 Runtime 설치 후 같은 PDF 정상 열람 | 대기 | WebView2 버전, 열람 결과, 다운로드/인쇄/외부 창 차단 유지 여부 |
| 코드 서명 검증 | 선택 | 인증서 주체 또는 지문, `signtool verify /pa` 결과 |
| Git 산출물 제외 확인 | 대기 | `git status --short --untracked-files=all` 출력 |

### 배포 판정

다음 조건을 모두 만족하면 Windows WPF MSI 운영 배포 조건을 충족한 것으로 본다.

- 기본 MSI와 self-contained MSI가 모두 생성된다.
- MSI 포함 파일 목록에 SQLite, WAL/SHM, `Data\Files`, `storage`, `logs`, 테스트/샘플/고객 파일이 없다.
- 설치 폴더에는 실행 파일과 의존 파일만 있고, 로컬 DB와 `Files\`는 지정한 LocalData 경로에만 생성된다.
- framework-dependent MSI는 .NET Windows Desktop Runtime 필요 조건을 명확히 드러내고, 런타임 없는 PC에는 self-contained MSI를 배포 기준으로 선택할 수 있다.
- WebView2 Runtime 유무에 따른 안내와 설치 후 정상 PDF 열람이 확인된다.
- 서명 인증서가 준비된 배포에서는 EXE와 MSI가 모두 `signtool verify /pa`를 통과한다.
- Git 상태에 빌드/배포 산출물과 테스트 산출물이 추적 대상으로 잡히지 않는다.

## 현재 비Windows 환경 확인

2026-07-08 KST 기준 현재 macOS 개발 환경에서는 `wix`, `pwsh`, `dotnet`, `msiexec`, `signtool`이 없어 실제 MSI 생성과 설치 검증은 수행하지 못했다. 대신 다음 항목을 확인했다.

- `dotnet publish` framework-dependent: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet publish` self-contained: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet build` WPF 앱: 성공, 경고 0개
- `dotnet build` WPF 스모크 테스트: 성공, NuGet 취약성 데이터 조회 경고 2개
- `artifacts/wpf-msi` 하위 파일명 기준 금지 패턴 검사: 0건

위 항목은 이전 비Windows 사전 점검 기록이며, 운영 배포 확정 근거로는 부족하다. 남은 실기 검증은 Windows 배포 준비 PC 또는 현장 검증 PC에서 `package-wpf-msi.ps1` 기본 MSI와 `-SelfContained` MSI를 실제 생성하고, 위 설치 후 점검 스크립트와 수동 WebView2 열람 확인으로 완료한다.

## 2026-07-09 Windows MSI 실기 검증 시도 기록

2026-07-09 KST 기준 현재 작업 환경은 macOS `Darwin arm64`이며 `pwsh`, `dotnet`, `wix`, `msiexec`, `signtool` 명령이 모두 PATH에 없다. 따라서 이 환경에서는 `scripts/package-wpf-msi.ps1`, `scripts/verify-wpf-msi-install.ps1`, Windows 설치, .NET Windows Desktop Runtime 미설치 PC 실행, WebView2 Runtime 미설치/설치 후 PDF 열람, `signtool verify /pa`를 수행할 수 없다.

현재 로컬 `artifacts/wpf-msi`에는 2026-07-03 07:05 KST 생성 시각의 `FlowNote.Windows.App-0.1.0-win-x64.msi`, `FlowNote.Windows.App-0.1.0-win-x64.wixpdb`, `FlowNote.Windows.App.wxs`가 남아 있다. 이 산출물은 `.gitignore`의 `artifacts/`, `*.msi`, `*.wixpdb` 규칙으로 Git 추적 대상에서 제외된다. 다만 이 산출물에는 최신 스크립트가 생성하는 `.files.txt` manifest가 없고, self-contained MSI 파일도 없어 현재 완료 기준의 증거로 사용할 수 없다.

이번 환경 점검에서 확인한 사항은 다음과 같다.

- Windows 실기 검증 상태: `미완료`
- 배포 판정: `대기`
- 기본 MSI 기존 로컬 파일 SHA256: `d529b24993d3999d4b5224e107309995b2af701ec6d95476abb6b59d43f5d7fb`
- 기존 로컬 `wixpdb` SHA256: `c82b07e3f98d9d7ff95c7231135356d6ac3d840a991338a666f0e2c39406cc49`
- 기존 로컬 `.wxs` SHA256: `f4b2f28b0d5591b51fb96b05221811a18d2c22a7ba530b68e3422f1afc908d22`
- `artifacts/wpf-msi` 하위 배포 산출물은 현재 Git 추적 대상이 아니다.

Windows 배포 준비 PC에서 새로 검증할 때는 위 기존 로컬 산출물을 근거로 삼지 말고, 같은 작업일에 기본 MSI와 self-contained MSI를 다시 생성한 뒤 `Get-FileHash`, `.files.txt`, `verify-wpf-msi-install.ps1`, Runtime/WebView2 조건별 앱 실행 결과를 이 문서의 Windows MSI 실기 검증 기록 표에 반영한다.

## 2026-07-10 승인 단말 관리 API와 WPF 운영 화면 검증

FastAPI 승인 단말 관리 구현 후 `services/api/.venv/bin/python -m pytest -q`를 실행해 58건 전체 통과를 확인했다. 단말 전용 테스트는 다음 항목을 검증한다.

- `admin`, `system-admin`의 목록, 등록, 상세, 정보 변경, 상태 변경, 마지막 접속 조회 허용
- `viewer`의 단말 관리 API 403 거부
- 등록·정보 변경·비활성화와 교체 시 `activity_history`의 `terminal_device.*` 이벤트, actor, 변경 사유 기록
- 비활성화·폐기·교체 시 해당 단말의 기존 활성 인증 세션 `REVOKED` 처리
- 교체 시 기존 단말 `RETIRED`, 새 단말 `ACTIVE`, `replaced_device_id` 연결 및 폐기 단말 재활성화 409 거부
- 미등록, `INACTIVE`, `RETIRED` Android 단말 로그인 403
- 등록된 `ACTIVE` 단말의 반복 로그인 200, 로그인별 `auth_sessions.device_id` 2건 생성, 매 로그인 `last_seen_at` 유지·갱신

WPF는 `dotnet build apps/windows/src/FlowNote.Windows.App/FlowNote.Windows.App.csproj --no-restore -p:EnableWindowsTargeting=true`로 빌드했고 경고 0개, 오류 0개로 통과했다. 첫 실행은 `EnableWindowsTargeting` 미지정으로 `NETSDK1100`이 발생했으며, Windows 대상 빌드 속성을 명시한 재실행 결과를 통과 근거로 사용한다.

WPF 운영 화면의 소스·빌드 기준 확인 결과는 다음과 같다.

| 확인 항목 | 결과 | 근거 |
| --- | --- | --- |
| 관리자 메뉴 노출 | 통과 | `admin`, `system-admin`의 `CanManageUsers` 정책으로 `승인 단말` 버튼 표시 |
| 목록 필드 | 통과 | 단말명, device_id, 위치, 상태, 마지막 접속, 등록자, 변경자 컬럼 포함 |
| 운영 동작 연결 | 통과 | 등록, 정보 저장, 상태 적용, 교체 등록이 서버 전용 클라이언트에 연결 |
| 로컬 로그인 오등록 방지 | 통과 | 서버 URL·Bearer token이 없으면 서버 로그인 필요 안내만 표시 |
| Windows 실제 창 조작 | 대기 | 자동화 검증 범위에는 포함되지 않아 실기 확인 필요 |

Windows 실기 수동 검증에서는 서버 로그인 `admin`으로 `승인 단말` 창을 열고 신규 등록 → 목록/상세/등록자 확인 → Android 로그인 후 마지막 접속 새로고침 → 비활성화 후 로그인 403 → 교체 등록 후 기존 단말 폐기·새 단말 사용 상태를 순서대로 확인한다. 이 실기 결과는 Windows 검증 PC에서 실행한 시각, 사용자 ID, 대상 테스트 device_id와 함께 이 절에 추가한다. 기존 SQLite와 테스트 산출물은 삭제하지 않았다.

## 2026-07-10 삭제 문서의 AI 검색 근거 제외 검증

현재 코드와 문서의 정합성을 확인하면서 `services/api/.venv/bin/python -m pytest -q`를 실행했고 FastAPI 전체 58건이 5.13초에 통과했다. AI 검색 근거 테스트는 다음 조건을 함께 검증한다.

- 삭제되지 않은 공개 문서 버전은 `PUBLISHED_DOCUMENT_VERSION` 후보에 포함된다.
- `status = DELETED`이고 `deleted_at`이 설정된 문서는 직접 문서 후보에 포함되지 않는다.
- 삭제 문서를 원천으로 가리키는 `REPORT_SOURCE`는 보고서가 승인 상태로 남아 있어도 후보에 포함되지 않는다.
- 삭제 문서 원천과 실제로 존재하지 않는 원천은 `report_source_missing_origin` 제외 사유에 집계된다.
- 후보 재생성 응답과 품질 응답의 source별 후보 수, 제외 사유, 운영 안내가 일치한다.

이번 문서 정합성 검증에서는 기존 SQLite와 테스트 산출물을 삭제하지 않았다.

## 2026-07-10 Android 현장 단말 빌드·outbox·채널/인수인계 검증

Android Studio 내장 JBR 21과 Android SDK를 사용해 `apps/android`에서 `./gradlew testDebugUnitTest`와 `./gradlew assembleDebug`를 실행했고 모두 통과했다. JDK 21이 Java 8 source/target 지원 폐기 예정 경고를 출력했지만 테스트와 debug APK 생성에는 오류가 없었다. 생성 APK와 Gradle 로그는 `apps/android/app/build/` 아래에 보존되며 `.gitignore`의 `build/`, `*.apk` 규칙으로 Git에서 제외된다.

Android API 37.1 `Medium_Phone` AVD에 debug APK를 설치하고 로컬 FastAPI `http://10.0.2.2:5185` 및 보존 DB `services/api/data/flownote.android-verification.sqlite3`와 연결했다. 실행 식별자는 `20260710180354`이며, 승인 단말 `android-emulator-20260710180354` 로그인은 200, 미등록 단말과 `android-inactive-20260710180354` 로그인은 각각 403이었다. 비활성 단말은 앱 화면에서도 403을 확인했으며, 서버 영문 오류 본문이 노출되던 문제를 한글 현장 안내로 변환한 뒤 `요청이 거부되었습니다. 승인 단말 상태와 사용자 권한을 확인하세요. (HTTP 403)` 표시를 재확인했다.

outbox 실기 검증은 공개 문서 `doc_5fd2fb924dfd448aa48199bf2b2b73de`와 Android 파일 선택기로 고른 PNG 사진을 사용했다. 서버 포트를 연결 불가능한 값으로 바꾼 첫 전송에서는 outbox row가 `FAILED`, `attempt_count = 1`, `server_id = NULL`로 남고 사진 URI와 오류가 보존되었다. 15초 backoff 이후 정상 서버 주소로 재전송하자 같은 row가 `SYNCED`, `attempt_count = 2`, `server_id = comment_a65715b28fb749df932c8bf803233a8f`로 전환됐다. 서버 DB에는 다음 연결이 남았다.

- FieldComment: `comment_a65715b28fb749df932c8bf803233a8f`, `input_mode = signal`, `signal_level = yellow`, 승인 단말 ID와 Android idempotency key 기록
- 첨부: `att_2e804d51c3d949278118eecb3198d84c`, 위 comment ID 참조, `attachment_type = photo`, 파일 크기 8,460 bytes
- 보존 파일: `services/api/storage/android-verification/field-comments/comment_a65715b28fb749df932c8bf803233a8f/attachments/0e7916e07cf8416d8996df2aa4797362_field-photo.jpg`
- 실패/성공 outbox 스냅샷: `services/api/data/test-artifacts/android-verification-2026-07-10/20260710180354/`

채널 `channel_14090d18809d4668913f99fef315e743`의 Android 알림을 앱에서 읽음 처리한 뒤 `notification_channel_members.last_read_message_id`가 `chmsg_ad1b7d0deb0a47eea59f200f43bab271`로 저장된 것을 확인했다. 인수인계 `handover_97d53669291f4ec3a7d15471efeeafc3`의 receipt `hreceipt_e7e3ce69ab294532bae8376a6b9a330e`는 앱 버튼으로 `READ` → `ACKNOWLEDGED` → `FOLLOW_UP_REQUIRED`를 순서대로 변경했고, 각 단계 직후 서버 DB 상태를 대조했다. 최종 row에는 `read_at`, `acknowledged_at`, `follow_up_required_at`, `updated_by`가 모두 남았다.

재시도 단위 테스트는 최대 자동 시도 12회와 `15초 → 30초 → 60초 → ... → 최대 15분` 지수 backoff 값을 명시적으로 검증하도록 보강했다. 한글 오류 안내 테스트를 포함한 Android 단위 테스트와 debug 빌드를 다시 통과했으며, FastAPI 관련 회귀 테스트 `test_auth_api.py`, `test_terminal_devices_api.py`, `test_field_comments_api.py`, `test_channels_api.py`는 25건 모두 통과했다.

이번 결과는 에뮬레이터와 로컬 HTTP 서버를 사용한 개발 실기 검증이다. 운영 승인된 실제 태블릿 또는 러기드 단말의 카메라, 사내 Wi-Fi, HTTPS 인증서, MDM/운영 서명 APK 검증은 아직 대기 상태이며 운영 배포 확정 근거와 분리한다. SQLite, 업로드 사진, outbox 스냅샷, APK와 빌드 로그는 삭제하지 않았고 모두 Git 제외 경로에 보존했다.

## 2026-07-16 Android 보안 문서 본문 뷰어 검증

FastAPI에 Android 전용 grant/stream 권한·무결성 테스트를 추가했다. 현재 자동 검증은 승인된 활성 단말의 `viewer` 열람, `system-admin` 비허용 role, 단말 없는 세션과 비활성 단말 거부, grant 만료·재사용, 공개 해제, 발급 후 파일 변조, PDF/PNG/TXT 허용, 손상 PDF·미지원 형식·대용량 거부, 응답 SHA-256과 사용자·단말·문서 버전 감사 로그를 확인한다. 기존 WPF controlled copy 회귀 테스트도 함께 유지한다.

Android 단위 테스트에는 전용 API 경로와 SHA-256 hex 계약을 추가했고 계측 테스트에는 뷰어 Activity 비공개, `FLAG_SECURE`, 앱 내부 난수 캐시 시작 정리를 추가했다. 현재 Java Runtime을 찾을 수 없어 이번 변경 뒤 Gradle 단위/계측 빌드를 실행하지 못했다. 이 미실행 상태는 이전 2026-07-10 Android 빌드·에뮬레이터 통과 기록을 대체하지 않으며, JDK가 있는 검증 환경에서 `./gradlew testDebugUnitTest assembleDebug`와 승인 단말 계측을 다시 실행해야 한다.

현재 FastAPI 테스트는 120건이 수집되며 표준 검증 스크립트의 수집·JUnit 기준도 120건으로 갱신했다.

승인 실단말 수동 검증은 아직 대기 상태다. 다음을 같은 `run_id`로 기록한다.

- PDF, PNG/JPEG/WebP, UTF-8 TXT 정상 표시와 페이지/크기 한도 안내
- 손상 파일, 미지원 형식, 대용량, 수신 중 Wi-Fi 단절에서 뷰어 종료와 부분 캐시 제거
- 파일 앱, 다운로드, 최근 항목과 Android 공유 UI에 본문/원본 파일명이 나타나지 않는지 확인
- `cacheDir/secure-document-viewer/`가 열람 종료, 자동 닫힘, 홈 전환, 오류, 로그아웃, 앱 재시작 뒤 비어 있는지 확인
- 화면 캡처와 최근 앱 미리보기 차단, 외부 앱 열기/공유 진입점 부재 확인
- 공개 해제, 새 버전 공개, 사용자·단말 비활성화 직후 기존 grant 재사용 거부 확인
- 서버 원본 SHA-256, 수신 응답 `X-Content-SHA256`, 감사 로그 사용자·단말·문서 버전 대조

자동/수동 테스트 중 생성된 SQLite, 스트림 시험 파일, APK, JUnit XML과 로그는 기존 보존 규칙대로 삭제하지 않고 Git 제외 경로에 누적한다.

## 2026-07-16 문서 revision·상태·공개본 서버-WPF 동기화 검증

FastAPI 문서/DB 집중 테스트는 16건 모두 통과했다. 서로 같은 base revision을 읽은 두 작성자의 버전 등록, 공개본 교체 경쟁, 상태 변경을 교차해 한 요청만 revision을 증가시키고 다른 요청은 `STALE_BASE_VERSION`, `STALE_REVISION`, `PUBLISHED_VERSION_CHANGED` 중 해당 409로 남는지 확인했다. 같은 멱등키의 동일 파일은 기존 버전을 반환하고 다른 메타데이터·파일은 `IDEMPOTENCY_KEY_REUSED`, 선언 hash 불일치와 공개 직전 서버 파일 변조는 `FILE_HASH_MISMATCH`, 서버 soft delete 뒤 로컬 재전송은 `DOCUMENT_DELETED`로 분리됐다. FastAPI 앱을 닫고 같은 누적 DB로 다시 연 세 번의 lifecycle에서도 revision 1 → 2와 stale 409가 유지됐다.

WPF Core 테스트는 누적 `data/local/flownote.core-tests.sqlite`를 사용해 21건 모두 통과했다. 새 검증은 다음을 포함한다.

- 기존 DB 초기화가 `documents.server_revision`, 공개 버전 ID, 큐 conflict/resolution 열과 매핑 hash 열을 additive migration으로 추가하고 구 `field_notes` row를 보존한다.
- 구조화된 서버 409를 코드·expected/current revision·공개 버전 ID로 해석하고 요청 JSON에 `baseRevision`을 보낸다.
- 네트워크 503 중단 뒤 문서 큐가 `FAILED`로 남고 새 `ServerSyncService` 인스턴스에서 재연결하면 같은 idempotency key의 단일 큐와 문서/버전 매핑만 `SYNCED`가 된다.
- `CONFLICT`와 원 응답은 재시작 뒤 남고, 관리자 `KEEP_SERVER` 폐기는 사유·해결자·시각·`activity_history`와 함께 `DISCARDED`로 보존된다.
- 서버와 같은 문서 거버넌스 role만 WPF 상태/공개 버튼을 사용할 수 있다.

WPF Core와 앱은 macOS의 .NET SDK에서 각각 빌드했고, 앱은 `-p:EnableWindowsTargeting=true`를 사용해 경고 0개·오류 0개로 통과했다. 실제 Windows 창의 버튼 조작, 두 개의 실제 WPF 프로세스와 운영 유사 네트워크 장비를 사용한 동시 클릭은 Windows 검증 PC의 후속 실기 항목이며 자동 테스트의 두 클라이언트/재시작/503 주입 결과와 구분한다.

누적 SQLite SQL 대조 결과는 다음과 같다.

| 검사 | 결과 |
| --- | --- |
| 서버 `PRAGMA quick_check` / `foreign_key_check` | `ok` / 위반 0 |
| 공개 문서 포인터·버전 상태 불일치 | 0 |
| 문서별 복수 `is_published`, 복수 `is_latest` | 각각 0 |
| null 또는 1 미만 `documents.revision` | 0 |
| WPF Core DB `quick_check` / FK 위반 | `ok` / 0 |
| `server_id_mappings` 중복 그룹 | 0 |
| 공개 교체 경쟁 테스트의 DB hash와 실제 저장 파일 SHA-256 | 일치 |

첫 FastAPI 전체 회귀에서는 124건 중 AI 검색 ground-truth 평가 1건이 누적 suite 순서에서 실패했고 단독 재실행은 통과했다. 이후 공개 전 파일 변조 회귀를 추가한 최종 전체 재실행은 125건 모두 통과했다. 실패 실행과 재실행 캐시·DB 기록은 삭제하지 않았다.

## 서버 epoch 장애 주입과 자동 판정

각 시나리오(정상 DB 복구 후 epoch 증가, 이전 시점 복구, 빈 DB, 다른 instance/URL)를 별도 `run_id`로 실행하고 WPF 2대와 서버 DB에서 전후 JSON을 보존한다. JSON에는 instance/epoch, cursor, queue 상태별 count, mapping ID/revision/hash, 공개 version 포인터, report source-set hash를 포함한다.

SQLite 자동 판정의 최소 SQL은 다음과 같다.

```sql
PRAGMA quick_check;
PRAGMA foreign_key_check;
SELECT entity_type, local_id, local_version_no, COUNT(*) FROM server_id_mappings GROUP BY 1,2,3 HAVING COUNT(*) > 1;
SELECT idempotency_key, COUNT(*) FROM server_sync_queue GROUP BY idempotency_key HAVING COUNT(*) > 1;
SELECT COUNT(*) FROM server_sync_queue WHERE status NOT IN ('SYNCED', 'DISCARDED');
SELECT COUNT(*) FROM documents d LEFT JOIN server_id_mappings m ON m.entity_type='document' AND m.local_id=d.document_id WHERE d.server_document_id IS NOT NULL AND m.id IS NULL;
```

서버 DB에서는 `documents.latest_version_id/published_version_id`가 같은 문서의 version을 가리키는지, `document_versions.file_object_id`의 SHA-256과 저장 파일이 일치하는지, 보고서 `content_hash_sha256/source_set_hash_sha256`와 report source 집합이 일치하는지도 0건 기준으로 판정한다. 실패 run과 `DIVERGED` row가 적용 뒤에도 조회되는지 반드시 확인한다.
