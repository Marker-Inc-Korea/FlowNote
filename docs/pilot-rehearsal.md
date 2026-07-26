# FlowNote 실제 배포 리허설과 제한 현장 파일럿

이 문서는 FlowNote를 개발 PC가 아닌 고객 유사 환경에 설치하고 제한된 현장 파일럿을 시작하기 위한 실행 기준이다. 코드와 자동 테스트가 통과해도 이 문서의 필수 시나리오와 운영 승인이 끝나기 전에는 제품 배포 완료로 판정하지 않는다.

2026-07-22 현재 저장소에는 리허설·파일럿 증거 생성과 판정을 보조하는 스크립트가 있지만, 현장별 서명·인증서·MDM·고객 유사망·별도 PC 복구를 완료했다는 실기 증거는 없다. 따라서 이 문서는 구현 완료 목록이 아니라 현재 코드와 운영 보조 도구에 적용할 후속 실기 절차다.

## 범위와 원칙

- 대상은 깨끗한 Windows 서버 PC 1대, 깨끗한 Windows 클라이언트 PC 1대 이상, 승인된 Android 현장 단말 1대 이상이다.
- 네트워크는 고객과 같은 방화벽, 사내 DNS 또는 고정 주소, 사내 CA, 프록시, 시간 동기화 정책을 적용한 별도 검증 구간을 사용한다.
- 파일럿 데이터는 비민감 시험 데이터 또는 고객이 서면 승인한 제한 범위만 사용한다. 실제 고객 데이터는 Git, 일반 메신저, 개인 저장소와 개발용 AI provider에 전송하지 않는다.
- 제한형 AI 결과는 자동 조치, 작업 지시 또는 품질 판정이 아니라 근거 인용이 붙은 `참고 요약`으로만 표시한다. 비민감 시험 scope 밖의 provider 호출은 비활성으로 유지한다.
- 각 실행은 하나의 `run_id`로 설치 파일, 설정 점검, 화면 캡처, 서버·클라이언트 로그, DB 무결성, 관찰 결과를 연결한다. 실패 산출물도 삭제하지 않고 접근이 통제된 증거 저장소에 보존한다.
- 현장별 요구는 공통 제품 결함, 설정/운영 절차, 현장 전용 요구로 분류한다. 공통 제품에 반영할 때는 두 곳 이상에서 재현되거나 보안·데이터 손실·핵심 업무 차단에 해당하는지를 우선 판단한다.

## 착수 전 승인표

아래 항목의 담당자, 대행자, 승인자와 연락 수단이 비어 있으면 리허설을 시작하지 않는다.

| 책임 영역 | 담당자가 승인할 내용 |
| --- | --- |
| 서버 운영 | 서버 설치, 작업 스케줄러, 방화벽, 주소 변경, 로그 수집, 재부팅 |
| 인증서 | 사내 HTTPS 인증서 발급, 개인키 보관, 클라이언트/Android 신뢰 배포, 갱신, 폐기 |
| Windows 배포 | EXE/MSI 코드 서명, hash 배포, 설치·업그레이드·제거, WebView2/.NET 정책 |
| Android 운영 | 운영 서명키, APK 또는 AAB 선택, MDM/승인 배포, `deviceId` 수명주기, 분실 대응 |
| 데이터 보호 | 서버와 WPF 백업 저장소, 복구 승인, 보존 기간, 개인정보·고객정보 처리 |
| 현장 운영 | 참여 사용자와 역할, 단말 거치 위치, 시험 시간, 생산 영향, 중단 판단 |
| 지원 | 1차·2차 연락처, 대응 시간, 원격/현장 지원 허용 범위, 장애 인계 |
| AI 승인 | 시험 고객·현장·원천·provider·model·만료일, 금지 데이터, kill switch 담당자 |

착수 전에는 파일럿 시작·종료 일시, 허용 사용자와 단말, 허용 문서 범위, 성공 기준, 중단 기준, rollback 목표 시점, 증거 저장 위치, 개인정보/고객정보 삭제·반환 기준을 서면으로 확정한다.

### 우선순위 5 사전 승인 계약

Windows/서버 고객 유사망 리허설은 `windows_server_rehearsal` 프로필로 실행한다. Android·AI 실기 게이트는 이 실행의 완료 조건이 아니지만, 두 영역을 포함한 8개 책임 영역은 이번 리허설에서 무엇을 시험하고 무엇을 하지 않는지 담당자와 독립 승인자가 미리 승인해야 한다. 담당자와 승인자의 대소문자·앞뒤 공백을 제외한 식별자가 같으면 자기 승인으로 판정해 시작하지 않는다.

실제 사람 이름, 연락처, 장비명, 고객명, IP와 공유 경로는 Git 문서에 적지 않는다. 접근 통제되고 Git에서 제외된 `<증거 저장소>/<run_id>/pilot-run.json`과 `approvals/` 원시에 실제 값을 기록한다. 저장소 문서에는 익명 역할/장비 식별자와 증거 상대경로만 남긴다. 2026-07-26 현재 실제 책임자·시험 장비·운영 인증서·이전 승인 서버/WPF 버전과 hash/signer·RTO/RPO·rollback 결정권자·비상 연락 흐름은 제공되지 않았다. 임의 값으로 채우지 않으며, 해당 값과 서명 원시 증거가 들어오기 전 상태는 `LOCALCHECK FAIL / 리허설 착수 금지`다.

schema version 4의 각 `responsibilities.<area>`에는 `owner`, `approver`, `test_scope`, `stop_criteria`, `evidence_repository`, `approval_evidence`를 모두 기록한다. 통합 `authorization`에는 다음 값을 기록한다.

| 필드 | 현장 확정 기준 | 현재 판정 |
| --- | --- | --- |
| `decision`, `approved_at` | 실행 전 승인 `PASS`, 시간대가 포함된 승인 시각 | 미확정 |
| `run_scope` | 서버/WPF 신규 설치·수명주기, HTTPS·망 변경, 장기 단절, 디스크 부족, rollback의 포함·제외 범위 | 미확정 |
| `stop_criteria` | 데이터 손실, 권한 우회, 미승인 유출, DB 무결성 실패, rollback/핵심 업무 재개 실패를 포함한 5개 이상 | 미확정 |
| `evidence_repository`, `retention_until` | 접근 통제 저장소 식별자와 `YYYY-MM-DD` 보존 기한 | 미확정 |
| `equipment.server_ids` | 초기화 또는 승인 snapshot 상태의 익명 서버 ID 1개 이상 | 미확정 |
| `equipment.windows_client_ids` | 초기화 또는 승인 snapshot 상태의 익명 Windows ID 1개 이상 | 미확정 |
| `previous_approved_versions.server`, `.wpf` | 실제 복귀 가능한 패키지/백업 세트의 승인 버전 식별자 | 미확정 |
| `previous_approved_packages.server`, `.wpf` | 이전 승인 버전, 패키지 SHA-256, signer 인증서 SHA-256 | 미확정 |
| `recovery_objectives.server_restore`, `.wpf_restore`, `.rollback` | 각각 0보다 큰 승인 RTO/RPO(초) | 미확정 |
| `rollback_decision_authority` | rollback을 최종 결정하는 익명 역할 ID | 미확정 |
| `emergency_contact_flow` | 접근 통제 연락망의 승인 흐름 ID | 미확정 |
| `evidence` | 같은 `run_id`의 통합 사전 승인 원시 파일 상대경로 | 미확정 |

실행 후 `rollback.server.previous_approved_version`과 `rollback.wpf.previous_approved_version`은 사전 승인에 적은 버전과 정확히 같아야 한다. 실행 중 다른 복귀본으로 바꾸려면 현재 run을 중단하고 변경 승인을 보존한 뒤 새 `run_id`로 다시 시작한다.

책임 승인과 실제 값이 준비되면 새 실행 폴더를 다음 명령으로 만든다. 기존 LOCALCHECK와 실패 증거는 수정·삭제·재사용하지 않는다.

```powershell
py -3 scripts\manage-pilot-run.py prepare `
  --profile windows_server_rehearsal `
  --run-id PILOT-YYYYMMDD-HHMM-SITE-001 `
  --evidence-root D:\FlowNotePilotEvidence
```

## 실행 ID와 증거 구조

`run_id`는 `PILOT-YYYYMMDD-HHMM-현장코드-일련번호` 형식을 권장한다. 실제 고객명, 사용자명, 서버명, IP 주소는 파일명에 넣지 않고 접근 통제된 별도 대응표에서 관리한다.

```text
pilot-evidence/<run_id>/
  manifest.md
  pilot-run.json
  approvals/
  packages/
  install/
  network-and-certificate/
  server-logs/
  windows-logs/
  android-logs/
  backup-restore/
  scenario-results/
  observations/
  integrity/
  incident-and-rollback/
```

`manifest.md`에는 실행 시각과 시간대, 익명화한 장비 ID, OS·.NET·WebView2·앱 버전, 서버 API/DB schema 버전, Android build와 서명 인증서 지문, 담당자 역할, 단계별 시작·종료 시각, 최종 판정을 기록한다. 비밀번호, token, API key, 인증서 개인키, 실제 고객 문서 내용은 증거에 남기지 않는다.

패키지 증거에는 다음 값을 보존한다.

- framework-dependent MSI, self-contained MSI, 내부 배포용 WebView2 설치 파일, Android APK/AAB의 파일명·바이트 크기·SHA-256
- WPF EXE/MSI의 `signtool verify /pa` 결과와 서명 인증서 주체·일련번호·유효기간·타임스탬프
- Android의 release 서명 인증서 SHA-256 지문과 설치 후 package/versionCode/versionName
- 서버 배포 코드 또는 패키지의 버전 식별자와 파일 목록. `.env`, 비밀값과 고객 데이터는 패키지에 포함하지 않는다.

실행을 시작할 때 다음 명령으로 단일 `run_id`의 증거 폴더와 기계 판정표를 만든다. 생성된 `pilot-run.json`은 모두 `PENDING`이므로 실제 담당자, 현장 측정값과 증거 상대경로를 채우기 전에는 통과할 수 없다. 기존 실행은 기본적으로 덮어쓰지 않는다.

```powershell
py -3 scripts\manage-pilot-run.py prepare --run-id PILOT-YYYYMMDD-HHMM-SITE-001 --evidence-root D:\FlowNotePilotEvidence
```

준비 명령은 `scenario-results/android-delivery.csv`, `scenario-results/role-metrics.csv`, `scenario-results/restore-fault-injections.csv`, `observations/role-observations.csv`, `observations/development-items.csv`도 기존 파일을 덮어쓰지 않고 만든다. 익명 참여자 ID만 사용해 원시 관찰값을 적고, 집계한 분모·성공·중앙값·최대 시간·재시도·도움 요청은 `pilot-run.json` schema version 4에 옮긴다. 최종 검증은 요약값을 신뢰하지 않고 역할 원시 행에서 다시 계산해 일치 여부를 확인한다. Android 전달 항목은 `full_pilot` 프로필에서 정상, Doze, 5분 단절, 재부팅, 서버 주소 변경, access token 만료, refresh 거부, 강제 중지 뒤 kiosk 재실행을 각각 전건 성공과 허용 시간 이내로 기록해야 한다. 정상·Doze의 `allowed_seconds`는 30, 5분 단절의 값은 `30 + page_seconds`로 고정하며 임의 완화할 수 없다. 나머지 시나리오도 사전 승인한 양수 허용 시간과 측정 최대 시간을 반드시 기록한다.

`windows_server_rehearsal` 준비 과정에서는 원시 판정표 7개를 함께 만든다.

- `packages/windows-server-packages.csv`
- `install/windows-lifecycle.csv`
- `install/windows-runtime-matrix.csv`
- `scenario-results/windows-server-fault-injections.csv`
- `scenario-results/recovery-objectives.csv`
- `scenario-results/rollback-workflows.csv`
- `approvals/package-promotion-and-rollback.csv`

패키지 표에는 후보 서버 패키지·WPF MSI·WPF EXE와 이전 승인 서버 패키지·WPF MSI가 각각 정확히 한 행 있어야 한다. hash와 signer는 승인값과 같고 서명·chain·timestamp가 PASS이며 비밀·SQLite·고객 파일 혼입 수가 모두 0이어야 한다. 설치 표에는 서버 신규 설치와 WPF 신규 설치·업그레이드·제거·재설치를, runtime 표에는 .NET Desktop Runtime과 WebView2의 설치/미설치 조건을 각각 기록한다.

장애 주입 표에는 작업 스케줄러, 재부팅 자동 시작, 인증서 갱신·폐기·만료·미신뢰, 방화벽 포트 차단, DNS·고정 주소 변경, 시간 오차, 서버 재부팅 중 전송, 업그레이드 중단, 잘못된 패키지 서명이 각각 정확히 한 행 있어야 한다. 각 행은 장애 감지, 미승인 클라이언트 차단, 승인 클라이언트 재연결, 정상 업무 재개, 변경 승인 ID와 재개 시각을 모두 가져야 한다.

## 1. Windows 서버와 WPF 배포 리허설

다음 순서 전체를 같은 `run_id`로 수행한다.

1. 깨끗한 서버 PC에 FastAPI를 설치하고 `\FlowNote\FlowNoteApi` 작업을 등록한다. 서버 재부팅 후 사용자 로그인 없이 작업이 시작되고 health와 DB health가 정상인지 확인한다.
2. 깨끗한 클라이언트 PC에 framework-dependent MSI를 설치한다. .NET Windows Desktop Runtime이 없는 조건의 실패 안내와 필요한 런타임 설치 후 실행을 기록한다.
3. 같은 기준의 별도 깨끗한 PC 또는 원복 snapshot에 self-contained MSI를 설치해 .NET Runtime 없이 앱이 실행되는지 확인한다. WebView2 Runtime은 별도 필수 조건임을 유지한다.
4. WebView2 미설치 조건에서 한글 안내가 표시되고, 설치 후 같은 PDF를 열람할 수 있으며 다운로드·인쇄·외부 창 차단이 유지되는지 확인한다.
5. 동일 버전 복구 설치, 이전 승인 버전에서 신규 버전 업그레이드, 제거, 재설치를 수행한다. 업그레이드와 제거가 `C:\FlowNote\LocalData`의 DB·`Files`를 임의 삭제하지 않는지 확인한다.
6. 잘못된 서명, hash 불일치 또는 승인 목록 밖 버전은 설치 중단 처리한다. 승인된 EXE와 MSI는 모두 서명 검증을 통과해야 한다.
7. 서버 재부팅, 비정상 프로세스 종료 후 작업 스케줄러 재시작, 로그 순환 또는 디스크 부족 경고 절차를 확인한다.

필수 증거는 설치/제거 로그, 작업 스케줄러 상태와 최근 실행 결과, 앱 버전 화면, health 응답, MSI·EXE hash/서명, .NET/WebView2 버전, 설치 전후 데이터 경로 파일 목록이다.

## 2. HTTPS, 방화벽, 주소와 시간 리허설

운영 API URL은 사내 HTTPS 이름을 기준으로 하고 IP 주소 직접 사용은 긴급 진단용으로만 허용한다. FastAPI에 직접 TLS를 적용할지 승인된 사내 reverse proxy/TLS terminator를 둘지 먼저 확정하고, 어느 방식이든 클라이언트에서 서버까지 평문으로 노출되는 비승인 구간이 없어야 한다.

1. 서버 인증서의 SAN이 운영 DNS 이름과 일치하는지, 서버와 승인 클라이언트의 전체 체인이 신뢰되는지 확인한다.
2. 인증서 개인키는 서버의 제한된 계정만 읽게 하고 PFX, 암호, 개인키를 증거 폴더나 Git에 복사하지 않는다.
3. Windows WPF와 Android에서 같은 HTTPS health와 로그인을 확인한다. 인증서 오류를 무시하거나 HTTP로 자동 강등해서는 안 된다.
4. 방화벽은 승인된 현장 구간에서 FlowNote 포트로 들어오는 연결만 허용하고, 비승인 PC와 다른 VLAN의 연결 거부를 기록한다.
5. 서버 주소 변경 시 DNS 또는 설정 변경, WPF `FLOWNOTE_API_BASE_URL`, Android 서버 URL, 인증서 SAN, 방화벽, 알림 cursor의 서버 scope 분리를 순서대로 점검한다.
6. 서버·Windows·Android 시간을 표준 시간과 동기화하고, 허용 오차를 현장 정책으로 정한다. 인증서 유효성, token 만료, 로그 순서, 인수인계 시각이 같은 시간대를 사용하는지 확인한다.
7. 만료 전 갱신 인증서를 시험 설치하고 구·신 인증서 겹침 기간, rollback, 구 인증서 폐기, 모든 클라이언트 재접속을 확인한다.

인증서 갱신, 서버 주소 변경, 방화벽 변경은 변경 요청 번호, 작업자, 승인자, 적용·rollback 시각과 영향 단말 목록을 남긴다.

## 3. Android 운영 배포와 단말 수명주기

현장 착수 전에 다음 정책을 `결정`, `대기`, `해당 없음` 중 하나로 표시하고 `대기` 사유와 완료 기한을 기록한다.

| 항목 | 확정할 기준 |
| --- | --- |
| 산출물 | `결정`: MDM/사내 배포는 조직 키 서명 APK. 관리형 스토어를 실제 채택할 때만 AAB로 변경한다. |
| 서명키 | `결정`: 조직 소유, 최소 2인 승인, 오프라인/HSM 또는 승인 비밀 저장소, 빌드 시 환경 주입. 키 분실·유출은 보안 사고 절차를 따른다. |
| 배포 | `결정`: MDM allowlist, 동일 인증서 업그레이드/rollback, 이전 승인 APK 보존. 수동 sideload는 격리 리허설만 허용한다. |
| `deviceId` | `결정`: MDM 자산과 1:1 임의 발급, 사용자/하드웨어 식별자와 분리, 교체 시 새 ID, 기존 ID `RETIRED`. |
| 분실 | `결정`: 즉시 `INACTIVE`, 세션 폐기 확인, MDM 격리·잠금·초기화, 마지막 접속/사고 `run_id` 보존. |
| 비활성화 | `결정`: 수리는 `INACTIVE`, 교체·폐기는 `RETIRED`; 담당 관리자가 WPF/API와 MDM을 함께 처리한다. |
| outbox | `결정`: token·본문·새 첨부는 Keystore AES-GCM. 전체 암호화·화면 잠금·USB/backup 차단도 MDM 필수다. |

MDM 정책 보고서에서 단말 전체 암호화, 6자리 이상 화면 잠금, 개발자 옵션·USB 디버깅·USB 파일 전송·ADB backup 차단, 알 수 없는 출처 차단, 앱 allowlist, 원격 잠금·초기화와 kiosk 재실행을 확인한다. 하나라도 적용할 수 없으면 운영 데이터를 사용하지 않는다.

단말 교체 시험은 기존 단말 비활성화, 활성 세션 폐기, 새 `deviceId` 등록, 새 단말 로그인, 기존 단말 재로그인 거부, 미전송 outbox 처리 결정을 모두 포함한다. 미전송 항목을 새 단말로 임의 복사하지 않으며 전송·폐기·증거 보존 책임자가 판단한다.

착수 승인에는 개인 이름 대신 먼저 `Android 운영 책임자`, `MDM 책임자`, `인증서 책임자`, `서버 운영 책임자`, `정보보호 책임자`, `현장 운영 책임자`를 지정한다. 실제 담당자는 접근 통제된 대응표에 연결하고, 아래 항목마다 승인자·승인 시각·근거 문서·재검토 기한을 남긴다. 조직 소유 운영 서명키 보관/복구, APK 배포·allowlist·kiosk, 사내 CA trust 배포/갱신, `deviceId` 발급·`INACTIVE`·`RETIRED`·교체, 분실 원격 격리·잠금·초기화, 미전송 outbox의 전송/보존/폐기 판단 중 하나라도 책임자가 비어 있으면 실단말 시험을 시작하지 않는다.

문서 열람은 다음 매트릭스를 승인 실단말에서 모두 수행한다. `대용량`은 서버 계약의 byte/page 상한 바로 아래 정상 파일과 상한을 넘는 거부 파일을 각각 뜻한다.

| 시나리오 ID | 입력·상태 | 필수 동작 | 통과 기준 |
| --- | --- | --- | --- |
| `AND-DOC-PDF-*` | 정상·손상·대용량 PDF | 열기, page 이동, 홈 전환, 자동 닫힘 | 정상만 내부 렌더링, 손상·초과는 한글 실패 UX, 부분 파일 0건 |
| `AND-DOC-IMAGE-*` | 정상·손상·대용량 PNG/JPEG/WebP | 열기, 홈 전환, 자동 닫힘 | 원본명 미노출, 외부 앱/공유 없음, 종료 후 cache 0건 |
| `AND-DOC-TXT-*` | 정상·손상·대용량 UTF-8 TXT | 열기, 스크롤, 홈 전환, 자동 닫힘 | 정상 UTF-8만 표시, 오류 원문·원본명 미노출, cache 0건 |
| `AND-DOC-OFFLINE-*` | 다운로드 전·중 네트워크 단절 | 재시도, 홈 전환, 앱 재시작 | 부분 파일 즉시 제거, 소비 grant 재사용 없음, 복구 안내 표시 |
| `AND-DOC-LIFECYCLE-*` | 뒤로가기·홈·자동 닫힘·로그아웃·process 종료·재시작 | 파일 앱, 최근 화면, 앱 cache 검사 | `FLAG_SECURE` 캡처 차단, 최근 화면 본문 없음, cache/외부 파일/공유 target 0건 |

각 행은 성공 화면만 확인하지 않는다. `run-as` 또는 MDM 승인 진단으로 `cacheDir/secure-document-viewer/`, 외부/공용 저장소, 파일 앱 최근 항목을 검사하고, `dumpsys package`의 exported component와 intent resolver에서 본문 공유·외부 열기 경로가 없음을 남긴다. 화면 캡처·최근 화면 검사는 고객 원문 대신 승인된 비민감 파일로 수행한다.

### Android 알림·절전·보안 실단말 시나리오

각 시나리오는 앱이 만든 `ANDROID-DELIVERY-{uuid}`를 파일럿 `run_id` manifest에 연결하고 서버 메시지 `created_at`, Android `displayed_at`, 사용자 읽음/receipt 서버 처리 시각을 UTC와 현장 시간대로 함께 비교한다. 정상 연결과 Doze의 목표는 생성 후 30초, 5분 이상 단절·서버 주소 변경·재부팅 복구는 연결/부팅/설정 완료 후 30초+page 전송 시간이다.

1. 새 설치 로그인 후 초기 과거 알림이 시스템 새 알림으로 표시되지 않고 cursor만 따라잡는지 확인한다.
2. 화면 off와 `adb shell dumpsys deviceidle force-idle`에서 새 알림을 만들고 30초 이내 표시, 시스템 알림 ID와 `message_id` 일치를 기록한다.
3. Wi-Fi/사내망을 5분 이상 끊은 동안 3건을 만들고 연결 복구 뒤 순서·누락·중복을 확인한다. 시각 중복 허용은 crash 경계 최대 1건, 서버 receipt row 중복은 0건이다.
4. 단말 재부팅 뒤 사용자 앱 실행 전 foreground service 상태와 알림 복구를 확인한다. Android 강제 중지는 OS 예외로 분리해 MDM kiosk가 앱을 재실행하는 시각부터 목표를 측정한다.
5. DNS/서버 URL을 바꾸고 새 scope가 이전 cursor를 공유하지 않는지, 사내 인증서 오류에서 HTTP 강등하지 않는지 확인한다.
6. 단말을 `INACTIVE`, 사용자를 비활성화한 직후 기존 access API와 refresh가 401, 재로그인이 403인지 각각 확인한다. 분실 시 MDM 잠금/초기화 보고서를 연결한다.
7. 로그인 token과 outbox 본문/새 첨부를 `run-as` 또는 MDM 승인 저장소 검사로 확인해 평문 검색 결과 0건, backup 불가, Keystore key 비반출을 기록한다. 키 무효화 모의 후 단말 격리·미전송 판정 절차를 수행한다.
8. 서명 APK 신규 설치, 같은 키 업그레이드, 승인 이전 APK rollback을 수행하고 `apksigner` 인증서 SHA-256, APK SHA-256, package/versionCode/versionName과 설치 로그를 보존한다.

알림 계측 CSV는 최소 `scenario_id`, `condition`, `delivery_run_id`, `message_id`, `created_at_utc`, `recovery_ready_at_utc`, `displayed_at_utc`, `receipt_at_utc`, `page_seconds`, `elapsed_seconds`, `allowed_seconds`, `result`, `evidence`를 가진다. schema version 4 `full_pilot`의 기계 판정 대상 condition은 `normal`, `doze`, `disconnect_5m`, `reboot`, `address_change`, `access_token_expiry`, `refresh_rejected`, `force_stop_kiosk_restart`다. 각 condition은 원시 CSV에 1개 이상의 시도 행이 있어야 하고 모든 행이 `ANDROID-DELIVERY-*` ID, 수치형 측정/허용 시간, `PASS`, 같은 실행 폴더의 실제 증거를 가져야 한다. 정상·Doze는 `displayed_at-created_at <= 30초`, 5분 단절은 `displayed_at-recovery_ready_at <= 30초+page_seconds`로 계산하고 나머지는 사전 승인한 허용 시간과 비교한다. Logcat의 각 `page_ok`에 대해 `cursor_before`, `cursor_after`, `received`, `advanced`, `stale_or_duplicate`를 서버 응답/감사 로그와 대조한다. full page가 연속되는 101건 이상 backlog도 만들어 마지막 `message_id`까지 도달해야 하며, 누락 메시지·서버 receipt 중복 row는 각각 0건이어야 한다.

누락·서버 receipt 중복·crash 경계 표시 중복 집계는 `scenario-results/android-delivery-integrity.csv`, 보안 8개 항목은 `integrity/android-security.csv`, 발급·비활성화·분실·교체는 `scenario-results/android-device-lifecycle.csv`, 후보/이전 승인 패키지는 `packages/android-release-approval.csv`에 기록한다. `pilot-run.json`의 요약값과 게이트만 PASS로 바꿔서는 통과하지 않으며 원시 집계가 요약과 일치하고 각 원시 행의 PASS와 같은 `run_id` 안의 증거 파일이 모두 존재해야 한다. 단위/instrumentation 결과는 `android-logs/test-*`, 실단말·MDM 결과는 `android-logs/device-*`와 `mdm-*`로 분리하고 서로 대체하지 않는다.

실단말 업무 묶음은 같은 `run_id`에서 공개 문서 열람, FieldComment, 새 사진 첨부, 정상/Doze 알림, 인수인계 읽음·확인을 순서대로 수행한다. 네트워크 단절 중 FieldComment/사진 outbox를 만든 뒤 복구하고 서버 원천·첨부가 idempotency key별 1건인지 확인한다. 단말 교체 때는 기존 단말의 outbox 건별 `서버 반영 확인 후 폐기`, `기존 단말 재연결 후 전송`, `정보보호 승인 보존` 중 하나를 기록하고 새 단말로 암호문·Keystore key를 복사하지 않는다.

현장 관찰은 장갑 착용/미착용을 분리해 성공률·오입력·소요 시간·도움 요청을 기록하고, 배터리는 충전 상태, 화면 on/off, Doze, foreground service 실행 시간과 시험 전후 잔량/전류 근거를 함께 남긴다. 결함은 `공통 제품`, `MDM/단말 설정`, `현장 배치·교육` 중 하나로 분류하며 보안·손실·핵심 업무 차단은 현장 설정으로 축소 판정하지 않는다.

`scripts/verify-android-release.sh`의 결과, MDM 정책 PDF/JSON, `adb bugreport` 또는 제한된 logcat, 서버 감사 조회와 시각 비교표를 `pilot-evidence/<run_id>/android-logs`, `packages`, `scenario-results`, `integrity`에 보존한다. token, keystore, 암호와 고객 원문은 증거에서 제외한다.

## 4. 백업과 별도 PC 복구 훈련

배포 문서의 백업 세트를 사용하되 복구는 원본 서버가 아닌 별도 PC 또는 격리된 복구 구간에서 수행한다.

1. 서버 쓰기를 중지하고 SQLite checkpoint 또는 앱 중지 상태를 확인한 뒤 서버 DB, 같은 시점의 `storage`, 운영 설정과 로그를 하나의 백업 세트로 만든다.
2. WPF 앱을 종료하고 로컬 DB와 같은 시점의 `Files`를 PC별 백업 세트로 만든다.
3. 백업 전에 DB `PRAGMA quick_check`, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, 대상 파일 SHA-256 목록, 업무 원천별 개수를 기록하고 익명 백업 세트·복구 승인 ID를 부여한다.
4. 별도 PC에 서버 DB+`storage`를 함께 복원하고 health, DB health, 로그인, 문서 열람을 확인한다.
5. 별도 클라이언트 PC에 WPF DB+`Files`를 함께 복원하고 로컬 로그인/서버 로그인, 목록, 파일 열람, 미전송 큐와 알림 cursor 상태를 확인한다.
6. 복구 후 같은 SQL과 파일 hash 목록을 생성하고 원본과 다른 익명 복구 장비 ID를 기록해 전후 값을 비교한다. 불일치는 누락, 추가, 변경, 예상된 런타임 생성 파일로 분류한다.

전후 비교의 최소 원천은 문서, 문서 버전, FieldComment, FieldComment 첨부, 보고서, 보고서 source다. 해당 모델이 존재하는 경우 채널 메시지, 인수인계, 인수인계 receipt, 알림 읽음 위치와 활동/접근 이력도 포함한다. 전후 백업 세트·복구 승인 ID가 다르거나 원본과 복구 장비 ID가 같거나, DB quick check·integrity check가 `ok`가 아니거나 foreign key 위반이 1건이라도 있거나, 테이블별 row 수 또는 파일 상대경로·크기·SHA-256이 다르면 복구는 실패다.

## 5. 역할별 핵심 업무 시나리오

모든 사용자는 본인 계정으로 수행하고 성공 여부, 시작·종료 시각, 재시도 수, 도움 요청, 오류 메시지를 기록한다. 대리 입력은 실제 전달자 또는 작업자와 대리 입력자를 함께 남긴다.

| 역할 | 필수 시나리오 | 성공 기준 |
| --- | --- | --- |
| 관리자 | 계정·단말 운영, 문서 등록·버전·상태·공개, FieldComment 원천 불변 확인·담당/기한·단계형/일괄 검토·감사/품질 작업함, 보고서 source 선정·저장, 장애 로그 확인 | 승인된 기능만 보이고 모든 변경 주체와 사유가 추적됨 |
| 반장(`line-foreman`) | 공개 문서 열람, 현장 상태 확인, FieldComment/사진 검토 연결, 인수인계 확인과 후속 조치 | 작업 흐름을 중단하는 우회 입력 없이 완료 |
| 조장(`team-lead`) | 작업 전 문서 확인, 신호등식 기록, FieldComment/사진, 채널 알림, 인수인계 확인·후속 필요 표시 | 단말에서 핵심 입력과 수신 확인이 보존됨 |
| 작업자(`team-member`) | 공개 문서 목록·상세와 PDF/이미지/TXT 보안 열람, 짧은 FieldComment/사진, 기본 정형 문구, 알림·인수인계 확인 | 비허용 문서·관리 기능 접근 없이 승인 앱 내부에서 열람과 최소 입력을 완료 |

권한 역검증으로 각 역할이 허용되지 않은 문서, 다른 채널, 관리자 화면, controlled copy, AI 운영 화면에 접근할 수 없는지도 확인한다. 계정 비활성화·퇴사·부서 이동 후 기존 access/refresh session과 승인 단말 조합이 재사용되지 않아야 한다.

알림 복구는 네트워크 단절 중 발생한 메시지를 연결 복구 후 cursor 다음부터 중복 없이 수신하고, 읽음/인수인계 receipt가 서버에 보존되는지 확인한다. Android outbox 대상인 FieldComment/사진은 단절 중 입력, 앱 재시작, 재연결 후 멱등 전송을 확인하며 채널·인수인계가 outbox 대상인 것처럼 오인하지 않는다.

## 6. 장애, 중단과 rollback 시나리오

필수 장애 주입은 서버 재부팅, 서버 프로세스 종료, 네트워크 5분 이상 단절과 복구, DNS/서버 주소 변경, 인증서 갱신, Android 단말 교체, WPF 업그레이드 실패, 서버 및 WPF 백업 복구다.

다음 중 하나가 발생하면 신규 입력과 배포 확대를 즉시 중단한다.

- 데이터 손실, DB 무결성 실패, 원본 파일 hash의 승인되지 않은 변경
- 권한 우회, 비활성 계정·단말의 재접속, 미승인 파일·비밀·개인정보 유출
- 인증서 검증 우회 또는 HTTP 강등
- 핵심 역할이 문서 확인, 현장 기록, 인수인계 중 하나를 완료하지 못함
- 제한형 AI가 승인 scope 밖 데이터를 전송하거나 자동 조치로 오인될 수 있게 표시됨

중단 시 AI kill switch와 외부 호출 플래그를 끄고, 영향 계정 세션과 단말을 비활성화하며, 서버/WPF 쓰기를 통제한 뒤 로그·DB·파일을 보존한다. rollback은 승인된 이전 MSI/APK와 같은 시점의 서버 DB+`storage`, WPF DB+`Files` 세트로 수행한다. 원인 분석을 위해 실패 상태를 먼저 보존하고 운영 데이터를 임의 삭제하거나 덮어쓰지 않는다.

## 7. 현장 관찰과 UX 개발 항목 변환

관찰자는 작업을 방해하지 않는 위치에서 다음을 기록한다.

- 작업 시작부터 필요한 화면까지의 이동 수와 잘못 들어간 화면
- 버튼·라벨·상태·오류 문구를 이해하지 못한 지점과 도움 요청
- 장갑 착용 상태의 터치 실패, 사진 촬영, 키보드 입력과 스크롤 부담
- 단말 거치 위치, 시야각, 조명, 오염·소음, 한 손 사용 여부
- 작업 중 입력 가능한 순간, 입력 때문에 작업을 멈춘 시간, 나중 입력과 관리자 대리 입력
- 네트워크 단절을 사용자가 알아차린 시점, 저장됐다고 기대한 항목, 복구 후 신뢰 여부

사용자의 실명 대신 역할과 익명 참여자 ID를 기록한다. 화면 녹화·사진·음성은 현장 승인 범위와 개인정보 처리 절차를 따르고 승인받지 않은 작업자 얼굴, 고객 문서, 설비 비밀정보를 촬영하지 않는다.

관찰 결과는 다음 필드를 가진 개발 항목으로 변환한다.

| 필드 | 값 |
| --- | --- |
| 재현 맥락 | 역할, 작업, 단말, 위치, 네트워크, 장갑 여부 |
| 문제 유형 | 보안/데이터 손실/업무 차단/오입력/시간 지연/문구/선호 |
| 공통성 | 공통 제품, 설정·교육, 현장 전용 |
| 근거 | `run_id`, 시나리오 ID, 익명 관찰 번호, 로그/화면 시각 |
| 영향 | 실패 사용자 수, 성공률, 중앙값·최대 소요 시간, 재시도 수 |
| 우선순위 | P0 보안·손실, P1 핵심 업무 차단, P2 반복 지연·오입력, P3 선호·미관 |
| 완료 조건 | 수정 후 같은 맥락에서 측정할 수 있는 값 |

## 완료 판정

다음 조건을 모두 만족해야 제한 파일럿을 `통과`로 판정한다.

- 신규 설치, 업그레이드, 제거·재설치, 서버 재부팅과 자동 시작, 네트워크 단절·복구, 인증서 갱신, 단말 교체, 서버와 WPF 백업·별도 PC 복구가 통과했다.
- DB 무결성 위반, 데이터 손실, 권한 우회, 미승인 파일·비밀·개인정보 유출이 각각 0건이다.
- 관리자·반장·조장·작업자별 필수 시나리오의 분모·성공 건수·성공률과 중앙값·최대 소요 시간이 기록됐고 치명적 UX blocker가 0건이다.
- 파일럿 중단/rollback, 1차·2차 지원 연락, 로그 수집, 개인정보·고객정보 처리와 반환·삭제 절차가 책임자에게 승인됐다.
- 제한형 AI를 사용했다면 비민감 시험 scope, 전송 승인, kill switch, 근거 인용, `참고 요약` 표시, 사람 검토가 모두 확인됐다. 사용하지 않았다면 외부 호출 비활성 증거가 있다.
- 모든 필수 증거가 같은 `run_id`로 연결되고 승인자가 최종 판정과 남은 제한 사항에 서명했다.

하나라도 만족하지 않으면 결과는 `조건부 통과`가 아니라 `대기` 또는 `실패`다. 범위를 줄여 다시 시도할 때는 새 `run_id`를 발급하고 이전 실패 증거와 연결한다.

운영·보안·현장 서명 후에는 다음 명령을 실행한다. 도구는 필수 책임 영역, 고객 유사 장비 수, 모든 필수 게이트, 증거 파일 존재, 역할별 승인 성공률/중앙 시간, 0건 지표, 서버/WPF/Android rollback과 정상 업무 재개, 남은 항목의 책임자·기한·중단 영향, 3자 최종 승인을 같은 `run_id` 안에서 확인한다. 종료 코드 0과 `pilot-verification.json`의 `PASS`가 함께 있어야 하며, 이 결과는 서명 내용과 원천 증거의 사람 교차 검토를 대체하지 않는다.

schema version 4의 `full_pilot` 판정은 역할별 최대 시간·재시도·도움 요청, 평문 token/outbox·외부 공유·잔존 secure cache 0건, Android 알림 누락·서버 receipt 중복 0건, crash 경계 표시 중복 최대 1건, 분실·비활성 단말 재접속 차단과 교체 이력 보존도 별도로 강제한다. 서버/WPF comparison은 서로 다른 익명 장비 ID, 동일 백업 세트·복구 승인 ID, DB `quick_check`·`integrity_check`·FK, 테이블별 row 수, 파일 상대경로·크기·SHA-256 불일치 0건이어야 한다. 부분 복원·오래된 DB와 새 파일·누락 파일·잘못된 epoch 장애 주입은 자동 전송과 polling을 모두 차단하고 관리자 승인 재결합 뒤 정상화되어야 한다. Keystore token, outbox, 암호화 사진, 잘못된 키 복호화 실패, 종료 후 cache 정리, `FLAG_SECURE`, 공유 경로 부재와 backup 차단은 각각 확인해야 한다. 조치 가능한 UX 관찰은 전건 정확히 하나의 개발 항목으로 변환하고 P0~P3 합계와 `common_product`·`device_or_mdm_setting`·`site_layout_or_training` 분류 합계가 변환 건수와 일치해야 한다. 게이트·역할·Android 전달/보안/단말 수명주기·UX 변환·rollback·최종 승인의 증거 목록에는 같은 실행 폴더 안에 실제 존재하는 상대경로만 넣는다. `windows_server_rehearsal` 판정은 Android·역할별 UX 실기를 제외하고 서버/WPF/HTTPS·망·시간·권한·장기 단절·디스크 부족·별도 PC 복구·rollback 게이트와 해당 0건 지표를 강제한다. 추가로 패키지 5개 원시 행의 hash/signer 불일치와 혼입이 0건이고, 13개 장애 주입이 모두 복구되며, 서버 복구·WPF 복구·rollback의 실측 RTO/RPO가 승인값 이내이고, rollback 뒤 6개 핵심 업무가 같은 `run_id`에서 PASS여야 한다.

```powershell
py -3 scripts\manage-pilot-run.py verify --run-id PILOT-YYYYMMDD-HHMM-SITE-001 --evidence-root D:\FlowNotePilotEvidence
```

## 실행 결과표

실행 전 `run_id`, 시험 현장/라인 코드, 시작·종료 시각, 증거 저장소, 보존 만료일을 표 위에 기록한다. `상태`는 `미실행/실행중/완료`, `판정`은 `대기/통과/실패`만 사용한다. 담당자는 개인 이름 대신 먼저 책임 역할을 지정하고 승인된 증거 저장소의 대응표에서 실제 담당자와 연결한다. 아래 초기값은 2026-07-16 저장소 점검 결과이며 실기 완료 증거가 아니므로 모두 `대기`다.

| 게이트 | 상태 | 증거 | 담당자 | 후속 기한 | 판정 |
| --- | --- | --- | --- | --- | --- |
| Windows 서버 신규 설치·재부팅·자동 시작 | 미실행 | `<run_id>/install/server-*` | 서버 운영 책임자 | 파일럿 시작 전 | 대기 |
| WPF framework-dependent/self-contained 설치 | 미실행 | `<run_id>/install/wpf-fd-*`, `wpf-sc-*` | Windows 배포 책임자 | 파일럿 시작 전 | 대기 |
| WPF 업그레이드·제거·rollback | 미실행 | `<run_id>/install/wpf-lifecycle-*` | Windows 배포 책임자 | 파일럿 시작 전 | 대기 |
| EXE/MSI hash·서명과 WebView2 | 미실행 | `<run_id>/packages/*`, `<run_id>/install/webview2-*` | Windows 배포 책임자 | 파일럿 시작 전 | 대기 |
| HTTPS·방화벽·주소 변경·시간 동기화 | 미실행 | `<run_id>/network-and-certificate/network-*` | 서버 운영 책임자 | 현장 연결 전 | 대기 |
| 인증서 발급·배포·갱신·폐기 | 미실행 | `<run_id>/network-and-certificate/certificate-*` | 인증서 책임자 | 현장 연결 전 | 대기 |
| Android 서명·MDM/승인 배포 정책 | 미실행 | `<run_id>/packages/android-*`, `<run_id>/android-logs/mdm-*` | Android 운영 책임자 | 운영 로그인 발급 전 | 대기 |
| `deviceId` 발급·교체·분실·비활성화 | 미실행 | `<run_id>/scenario-results/device-lifecycle-*` | Android 운영 책임자 | 운영 로그인 발급 전 | 대기 |
| Android outbox 보호 정책 | 미실행 | `<run_id>/integrity/android-outbox-*` | Android 운영·정보보호 책임자 | 운영 로그인 발급 전 | 대기 |
| 서버 DB+`storage` 별도 PC 복구 | 미실행 | `<run_id>/backup-restore/server-*.json` | 데이터 보호 책임자 | 파일럿 시작 전 | 대기 |
| WPF DB+`Files` 별도 PC 복구 | 미실행 | `<run_id>/backup-restore/wpf-*.json` | 데이터 보호 책임자 | 파일럿 시작 전 | 대기 |
| 역할별 업무·권한 역검증 | 미실행 | `<run_id>/scenario-results/role-metrics.*` | 현장 운영 책임자 | 확대 판정 전 | 대기 |
| 네트워크 단절·알림/outbox 복구 | 미실행 | `<run_id>/scenario-results/disconnect-*` | 서버·Android 운영 책임자 | 확대 판정 전 | 대기 |
| 제한형 AI 또는 비활성 증거 | 미실행 | `<run_id>/integrity/ai-scope-or-disabled-*` | AI 승인·정보보호 책임자 | 최초 시나리오 전 | 대기 |
| UX 관찰과 개발 항목 변환 | 미실행 | `<run_id>/observations/observation-*`, `development-items.*` | 현장 관찰 책임자 | 확대 판정 전 | 대기 |
| 중단·rollback·지원·정보처리 승인 | 미실행 | `<run_id>/approvals/operations-approval.*` | 파일럿 책임자 | 리허설 착수 전 | 대기 |

### 역할별 측정 결과

성공률은 `성공 건수 / 필수 시나리오 분모 × 100`으로 계산한다. 중앙값과 최대 시간은 성공·실패를 포함한 모든 시도에서 따로 계산하지 않고, 원시 시도 행을 보존한 뒤 `전체 시도` 기준으로 산출한다. 재시도와 도움 요청은 성공 처리에서 숨기지 않고 별도 합계로 남긴다.

필수 `scenario_id`는 관리자 `ADMIN-DOCUMENT`, `ADMIN-FIELD-COMMENT-PHOTO`, `ADMIN-WORK-SEQUENCE`, `ADMIN-HANDOVER`, `ADMIN-REVIEW-REPORT`; 반장·조장·작업자는 각각 역할 접두사 `LINE-FOREMAN`, `TEAM-LEAD`, `TEAM-MEMBER`와 `DOCUMENT`, `FIELD-COMMENT-PHOTO`, `WORK-SEQUENCE`, `HANDOVER` 조합을 사용한다. 각 ID에 `required=TRUE`인 시도가 하나 이상 있어야 한다.

| 역할 | 참여자 수 | 필수 시나리오 분모 | 성공 | 성공률 | 중앙값 | 최대 | 재시도 | 도움 요청 | 치명적 blocker | 판정 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 관리자 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 대기 |
| 반장 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 대기 |
| 조장 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 대기 |
| 작업자 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 | 대기 |

### 손실·무결성·유출 결과

| 금지 사건 | 결과 | 증거 | 판정 |
| --- | ---: | --- | --- |
| 데이터 손실 | 미측정 | `<run_id>/integrity/data-loss-*` | 대기 |
| DB 무결성 실패 | 미측정 | `<run_id>/backup-restore/*-comparison.json` | 대기 |
| 권한 우회 | 미측정 | `<run_id>/scenario-results/permission-negative-*` | 대기 |
| 미승인 파일·비밀·개인정보 유출 | 미측정 | `<run_id>/integrity/disclosure-*` | 대기 |

복구 전후 증거는 쓰기가 중지되고 SQLite checkpoint 또는 앱 종료가 확인된 상태에서 다음처럼 수집한다. `capture`는 DB `quick_check`·`integrity_check`, foreign key 위반, 모든 업무 테이블의 원천 개수, DB 본파일과 파일 상대경로·크기·SHA-256을 JSON으로 남긴다. 전후에는 같은 `--backup-set-id`와 `--restore-approval-id`를 쓰고 서로 다른 익명 `--machine-id`를 기록한다. `compare`는 같은 `run_id`와 대상의 전후 값이 다르거나 별도 PC가 아니거나 복구 DB 무결성이 실패하면 종료 코드 1을 반환한다. 경로와 ID에는 실제 고객명, 서버명, IP를 넣지 않는다.

```powershell
py -3 scripts\verify-pilot-restore.py capture --run-id <run_id> --target server --phase before --machine-id SOURCE-SRV-01 --backup-set-id BACKUP-001 --restore-approval-id APPROVAL-001 --database C:\FlowNote\Server\data\flownote.sqlite3 --files C:\FlowNote\Server\storage --evidence-root D:\FlowNotePilotEvidence
py -3 scripts\verify-pilot-restore.py capture --run-id <run_id> --target server --phase after --machine-id RESTORE-SRV-02 --backup-set-id BACKUP-001 --restore-approval-id APPROVAL-001 --database D:\FlowNoteRestore\Server\data\flownote.sqlite3 --files D:\FlowNoteRestore\Server\storage --evidence-root D:\FlowNotePilotEvidence
py -3 scripts\verify-pilot-restore.py compare --before D:\FlowNotePilotEvidence\<run_id>\backup-restore\server-before.json --after D:\FlowNotePilotEvidence\<run_id>\backup-restore\server-after.json
```

WPF도 같은 명령에서 `--target wpf`, 로컬 DB, `Files` 경로와 서로 다른 원본/복구 PC ID로 전후를 수집한다. DB 본파일 크기와 SHA-256은 물리 복사 추적용 참고값으로 남기고, 논리 복구 PASS는 DB 검사·테이블별 row 수와 `storage`/`Files` manifest로 판정한다. 비교 JSON의 `table_count_mismatch_count`와 `file_mismatch_counts.missing/extra/size/sha256`은 모두 0이어야 한다.

장애 주입 결과는 `scenario-results/restore-fault-injections.csv`에 `partial_restore`, `old_database_new_files`, `missing_file`, `wrong_server_epoch`를 정확히 한 행씩 기록한다. 각 행은 `automatic_send_blocked`, `polling_blocked`, `reconciliation_required`, `admin_approved_rebind`, `normal_operation_resumed`가 모두 `TRUE`, `result=PASS`, 같은 실행 폴더의 화면·WPF 로그·서버 reconciliation 감사 증거가 있어야 한다. 실패 상태와 승인 전 로그는 정상화 결과로 덮어쓰지 않는다.

현장 관찰은 각 역할에 최소 한 행이 필요하며 `network`는 `CONNECTED/DISCONNECTED`, `gloves`는 `ON/OFF`, boolean 필드는 `TRUE/FALSE`로 기록한다. 전체 실행에는 장갑 착용과 네트워크 단절 관찰이 각각 하나 이상 있어야 한다. `actionable=TRUE`인 관찰은 `development-items.csv`의 고유 항목 하나와만 연결하고 `owner`, P0~P3, 세 분류 중 하나, 측정 가능한 `acceptance_criteria`, `due_date`, 증거를 모두 채운다.

### 2026-07-16 준비 점검

`PILOT-20260716-TOOLTEST-001`은 복구 증거 도구의 동작 확인용 `TOOLTEST`이며 실제 설치·복구 또는 현장 파일럿 run이 아니다. 이 실행을 완료 판정의 분자나 통과 증거로 사용하지 않는다. 증거는 Git 제외 로컬 경로 `data/local/pilot-evidence/PILOT-20260716-TOOLTEST-001/backup-restore/`에 보존했다.

| 점검 대상 | 결과 | 근거 | 후속 개발 항목 |
| --- | --- | --- | --- |
| 서버 개발 DB와 `storage` 동일 원천 전후 비교 | 도구 시험 통과 | `server-before.json`, `server-after.json`, `server-comparison.json`; `quick_check=ok`, foreign key 위반 0건, 파일 6,498건 | 실제 별도 PC 복구본으로 새 `PILOT` run 재검증 |
| WPF 공통 DB와 `Files` 동일 원천 전후 비교 | 도구 시험 실패 | `wpf-before.json`, `wpf-after.json`, `wpf-comparison.json`; `quick_check=ok`, 파일 920건, `foreign key mismatch - "controlled_copy_grants" referencing "document_versions"` | P0 데이터 무결성: 누적 DB를 삭제하지 않고 서버용 `controlled_copy_grants`가 WPF 로컬 `document_versions` schema와 충돌한 유입 경로를 규명하고 보존 migration 후 재검증 |

WPF 실패는 복구 실패를 모의한 결과가 아니라 현재 누적 공통 SQLite의 schema 무결성 차단을 발견한 준비 점검이다. 원천 DB와 파일을 수정하거나 삭제하지 않았으며, 이 항목이 해결되어도 별도 PC 복구와 나머지 실기 게이트는 계속 `대기`다.

### 2026-07-20 P0 후속 조치

위 `PILOT-20260716-TOOLTEST-001` 실패 증거는 당시 발견 기록으로 유지한다. 이후 FastAPI가 WPF 로컬 schema를 서버 DB로 초기화하는 경로를 `Base.metadata.create_all()` 전에 차단했고, `scripts/repair-wpf-controlled-copy-schema.py`로 원본 backup·DDL·FK·row hash를 보존한 뒤 서버 전용 grant 테이블을 격리했다. 공통 DB 복구 run `WPF-P0-20260720-0840`은 `document_versions` 3,384행의 hash를 유지하고 `quick_check=ok`, foreign key 위반 0건으로 끝났다.

따라서 “유입 경로 규명과 보존 migration” P0 개발 조치는 완료됐다. 다만 이 결과는 같은 원천 DB의 보존 복구 증거이며 별도 PC 복구 훈련이나 최신 Windows 무생략 통합 `PASSED`를 대신하지 않는다. WPF DB+`Files` 파일럿 게이트는 새 `PILOT` run에서 별도 PC 복구 전후를 비교할 때까지 계속 `대기`다.

현재 저장소와 개발 환경만으로는 위 실기 게이트를 통과 처리할 수 없다. 최초 통합 `PASSED` 실행 ID, Windows 배포 준비 PC, 고객 유사 네트워크, 운영 인증서/서명키 정책, 승인 Android 실단말과 현장 책임자가 준비된 뒤 실행한다.
