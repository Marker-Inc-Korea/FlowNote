# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 현재 구현, 데이터 모델, API, 보안, 배포 기준을 관리한다. 문서는 2026-08-03 현재 개발된 코드 기준을 우선하며 아직 구현되지 않은 기능은 후속 범위로 분리한다.

전체 문서 갱신 범위는 Git이 추적하는 제품·구현 Markdown이다. `AGENTS.md`는 작업 정책 원문이고 `현장정리문서/`는 현장 의견 원문이므로 제품 코드 설명과 분리한다. 가상환경·빌드 캐시·테스트 산출물 안의 Markdown도 생성·보존 기록이므로 갱신 대상에서 제외한다.

## 읽는 순서

1. [제품 개요](./product-overview.md)
2. [시스템 맵](./system-map.md)
3. [데이터 모델](./data-model.md)
4. [FieldComment 검토·분석·선정 운영](./field-comment-review-workflow.md)
5. [AI 준비 ground-truth와 48건 회귀 기준](./ai-ground-truth.md)
6. [API](./api.md)
7. [MVP 범위](./mvp-scope.md)
8. [구현 로드맵](./implementation-roadmap.md)
9. [보안](./security.md)
10. [배포](./deployment.md)
11. [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)
12. [역할별 업무 UX와 접근성 공통 기준](./ux-accessibility.md)
13. [설계 결정](./decisions.md)
14. [검증 기록과 현재 검증 제한](./verification.md)

## 현재 코드 기준

- Windows WPF 앱은 로컬 SQLite를 기본 저장소로 사용한다.
- Android 현장 단말 앱은 Java/Android 네이티브 View 기반 최소 앱으로 구현되어 있다. 승인 단말 `deviceId` 로그인, 공개 문서 목록·상세, PDF/이미지/TXT 앱 내부 보안 열람, FieldComment, 사진 첨부·인수인계 outbox, 신호등식 기록, 전경 채널 알림 polling/읽음, 인수인계 작성·확인·보류와 같은 원천의 후속 FieldComment 작성을 제공한다. 확인·보류와 후속 코멘트는 전송 전에 암호화 outbox에 보존한다.
- Windows에는 `admin`, `system-admin`용 승인 단말 관리 화면이 구현되어 있다. FastAPI 단말 API를 통해 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체를 수행한다.
- Windows 사용자 관리는 로그인 저장소에 따라 분리된다. 서버 로그인한 `admin`, `system-admin`은 서버 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기를 수행하고, 로컬 로그인은 로컬 SQLite 계정 화면만 사용한다. 임시 비밀번호 계정은 메인 화면 전에 비밀번호 변경을 강제하고 변경 후 재로그인을 요구한다.
- Windows에는 채널함, 채널 관리, 인수인계 확인 현황 화면이 구현되어 있고 FastAPI 채널/인수인계 API를 직접 호출한다. 확인 현황은 운영 단위·채널별로 인수인계를 나누고 미확인·후속 조치 인원을 집계한다. 서버 미연결 시 로컬 데이터와 동기화 큐를 삭제하지 않고 서버 설정 확인 문구를 표시한다.
- FastAPI 서버는 `/api/v1` REST API와 SQLite, 로컬 `storage/` 파일 저장소를 사용한다.
- FastAPI의 파일 기반 SQLite 연결은 `WAL`, 30초 `busy_timeout`, `synchronous=NORMAL`, `foreign_keys=ON`을 공통 적용한다. 요청 session은 정상·예외 종료 때 남은 transaction을 rollback하고 연결을 닫는다. 자동 만료 보존 작업은 서버 시작 직후가 아니라 설정한 첫 주기가 지난 뒤 실행한다.
- 파일럿 서버 PC 1대는 고객 하나와 현장 하나의 경계로 운영한다. 보호 요청에 다른 고객·현장 scope가 들어오면 대상 존재 여부를 드러내지 않는 `404 SCOPE_NOT_FOUND`로 거부하고 감사 이력을 남긴다.
- FastAPI 서버 DB와 WPF 로컬 DB는 스키마 소유권이 다른 별도 SQLite 파일이다. FastAPI 초기화는 WPF `documents`/`document_versions` 형태를 감지하면 서버 테이블을 만들기 전에 중단한다.
- FastAPI 서버에는 공통 채널, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음, 인수인계 수신 확인 API가 있다.
- WPF와 스모크 테스트는 기본적으로 `data/local/flownote.local.sqlite`를 함께 사용한다.
- 테스트와 개발 SQLite는 누적 검증 기록으로 로컬에 보존하지만 Git으로 추적하거나 커밋하지 않는다.
- 문서 등록은 즉시 공개가 아니다. 등록된 문서는 `WORKING` 상태와 최신 버전으로 저장되고, 공개 버전은 별도 publish 절차로 지정한다.
- WPF 다운로드 허용 role의 파일 저장은 로컬 원본 복사가 아니라 서버의 세션 바인딩 1회성 controlled copy와 저장 후 SHA-256 검증을 사용한다.
- FieldComment는 문서 버전이 아니라 현장 원천 기록이다.
- FieldComment 원천 핵심 필드는 생성 후 수정·삭제하지 않고 관리자 해석은 담당자·기한·정리·분석·상태·전이 사유와 원천 hash 감사로 분리한다. `red` 신호 또는 상충 원천의 결정은 분석자와 다른 사용자가 맡는다. WPF에는 상세 필터와 저장된 보기, 다중 선택 검토 preview·품질 작업함·서버 역추적 화면이 있다. 검토 화면 상단은 서버 권위 현황과 실제 현장 AI 준비도를 함께 읽되 합성·시험 수치를 실제 현장 준비도에 더하지 않는다. FastAPI에는 요청당 최대 200건을 입력 순서대로 사전검증하고 항목별 revision·mutation receipt로 부분 성공 처리하는 일괄 검토, 원자형 호환 일괄 경로, 감사·품질·검토 대시보드 API, 보고서 source와 생성 최종 문서·버전을 잇는 통합 역추적 API가 구현되어 있다.
- 보고서 초안과 최종 저장은 서로 다른 source type 2종 이상을 요구한다. WPF 화면은 `SELECTED` FieldComment, 현재 공개 문서, 작업순서 이력을 후보로 제공한다. Core의 저장 전 검증은 작업순서 항목과 이력을 모두 받아 서버의 현재 항목·최신 변경 기록 또는 선택한 변경 기록과 대조한다. 최초 원천 검증에서 서버에 연결할 수 없거나 선택 뒤 기록이 달라졌으면 로컬 보고서와 전송 대기 기록을 만들지 않는다. 검증을 통과하면 서버가 source별 version, 독립 trace ID와 저장 시점 SHA-256을 고정하고 최종 문서 저장 직전에 원천을 다시 확인한다.
- WPF 서버 동기화 큐는 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, 문서 태그, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장을 대상으로 한다. FieldComment의 분석·검토 완료·보고서 선정은 각 상태 전이를 별도 큐 기록으로 보존한다. 보고서는 여러 문서의 근거를 묶더라도 나머지 전송 대기 항목을 먼저 처리한 뒤 시도한다. 공개·상태·태그는 안정된 mutation key와 서버 receipt를 사용하고 2xx 응답 뒤 서버 문서 상태를 다시 읽어야 `SYNCED`로 종결한다. 작업내역 화면에서는 큐 깊이·최장 대기·최근 처리량·실패 분포와 row별 운영 상태를 확인한다. 서버본 유지로 종결한 `DISCARDED`도 전체 보존 건수에는 포함하되 재시도 대상 큐 깊이에서는 제외한다.
- WPF 메인 화면은 관리자·반장·조장·작업자의 첫 업무 3개를 로그인 직후 보여준다. 빠른 업무는 기존 권한 검사와 창을 그대로 사용한다. 문서 검색과 상태 필터는 폴더 이동 뒤에도 유지되며, 권한이 없는 기능에는 필요한 역할과 문의 방법을 표시한다. 동기화 미완료 상태는 대기·실패/충돌·보류 건수, 로컬 원천 보존 여부와 다음 확인 위치를 함께 안내한다.
- 작업순서는 동기화 큐 대상이 아니다. WPF 관리자·TV 화면은 FastAPI snapshot을 권위 원천으로 읽고, 관리 화면은 `board_revision`, mutation key, `baseBoardRevision`으로 서버를 직접 변경한다. 서버 미연결·조회 실패에서는 로컬 row를 읽기 캐시·초안으로만 표시하고 확정 변경을 차단한다.
- Windows 보존 동기화 전환 CLI는 FAILED 큐를 읽기 전용 dry-run으로 분류하고 plan hash와 row별 승인을 요구한다. 승인된 구 `create`/FieldNote 항목은 기존 원천·큐·파일을 수정하지 않고 현재 action의 신규 큐와 감사 이력으로 연결한다.
- WPF에는 AI 근거 후보 운영 점검 화면과 `AI 정답셋` 화면이 있다. `AI 정답셋`의 `사례·원천 구성` 창은 서버 후보를 포함 근거로 선택하고 실제 원천 ID·제외 사유를 제외 근거로 입력해 사례를 첫 승인 상태로 등록하며, `includePending=true`로 조회한 미승인 사례를 다른 사용자가 2차 승인할 수 있게 한다. 이어서 승인 사례를 불변 dataset version으로 구성하고 작성·검토·독립 2단계 승인·평가 run 비교를 수행한다. FastAPI는 고객·현장·선택적 라인·DB fingerprint scope별 ground-truth를 저장하고 고정 원천 snapshot과 접근권한을 재검증한 뒤에만 활성화한다.
- AI provenance는 `ANONYMOUS_FIELD`/`PILOT`의 `FIELD_READINESS`와 `SYNTHETIC`/`TEST`의 `SMOKE_REGRESSION`을 분리해 보존한다. 다만 승인 `FIELD_READINESS` dataset과 provider 착수 48건에는 고객 승인을 받은 `ANONYMOUS_FIELD`만 포함하고 `PILOT`은 별도 기록으로 유지한다. 합성 48건 회귀 통과도 실제 현장 준비도나 운영 provider 착수 승인이 아니다.
- 실제 익명 현장 24칸 독립 표본 검토와 불일치 제3 합의는 FastAPI, 서버 DB와 WPF에 구현되어 있다. WPF `AI 정답셋`에서 승인된 `FIELD_READINESS` dataset과 통과한 평가 run을 선택하면 `24칸 독립 검토`를 열 수 있다. 첫 판정은 두 번째 제출 전까지 숨기고, 두 판정이 다르면 앞선 검토자가 아닌 제3 사용자에게 불일치 case만 표시한다.
- 서버와 WPF에는 `system-admin` 전용 외부 AI 운영 제어면이 구현되어 있다. 전송 승인 생성·철회, 프롬프트 불변 버전의 검토·승인·활성화·폐기, 고객·현장별 민감정보 정책의 작성·분리 검토·승인·활성·대체·철회·폐기, 전역/현장 kill switch와 요청·동시성·timeout·비용·보존 한도, 정제 감사 조회/CSV 내보내기, 만료 보존 일괄·단일 실행과 법무·감사 legal hold 설정/해제를 관리한다. WPF의 민감정보 정책과 단일 만료·hold 조작은 이중 확인, 낙관적 동시성 표식, 멱등 키와 서버 read-back을 사용한다. provider 비밀값과 민감정보 정책 원문은 반환하지 않는다.
- 외부 AI 질의·요약은 `/api/v1/ai/queries` 생성·조회, provider 중립 fake/recording adapter, 호출 로그 모델, 기능 플래그·승인·목적·원천 권한·민감정보·최소 payload·근거 snapshot·응답 의미 검증 게이트까지 구현되었다. generic 네트워크 adapter는 명시적 test scope로 제한되고 기본값은 비활성이다.
- 고객·현장별 AI 금칙어와 고객 식별자는 `ai_sensitive_data_policies`의 불변 버전으로 저장한다. 작성자·검토자·승인자를 분리한 운영 API와 WPF UI가 활성 정책을 관리하며, provider 호출 직전과 응답 직후에는 정책 ID·content hash·revision snapshot을 다시 확인한다.
- WPF MSI 패키징, FastAPI 작업 스케줄러 등록/관리와 Windows/서버 후보·이전 승인 패키지 hash/signer 검증은 `scripts/`의 PowerShell 스크립트로 문서화되어 있다. 패키지 검증 결과는 `verify-windows-server-packages.ps1`이 같은 파일럿 `run_id`의 원시 CSV와 signtool transcript로 보존한다.
- `scripts/verify-pilot-restore.py`는 서버 DB+`storage`와 WPF DB+`Files`의 복구 전후 증거를 수집·비교한다. 전후에 동일한 익명 백업 세트·복구 승인 ID와 서로 다른 원본/복구 장비 ID를 기록하고, DB `quick_check`·`integrity_check`, foreign key, 테이블별 row 수, 책임 원천 fingerprint, DB 참조 파일과 실제 파일의 상대경로·크기·SHA-256이 모두 통과해야 한다. DB 본파일 크기·SHA-256은 물리 복사 추적용 참고값이며, 이 도구는 실제 별도 PC 복구 리허설을 대신하지 않는다.
- `scripts/manage-pilot-run.py`는 실제 파일럿의 단일 `run_id` 증거 구조와 schema version 13 판정표를 만든다. `full_pilot`의 `prepare`는 승인 원시표와 역할·게이트·선행조건별 준비 화면만 만들고 담당자/독립 승인자·승인 시각·근거 참조, 시험 범위, 5개 이상 중단 기준, 증거 저장소, 보존 기한, 익명 장비, 이전 승인 패키지, RPO/RTO, rollback 권한, 비상 연락과 운영·보안·현장 서명을 `authorize`가 대조한 뒤에만 설치·복구·Android 운영 입력을 연다. 승인 철회와 중단은 원시를 보존한 채 입력을 다시 잠그며 재개는 사전 지정한 rollback 결정권자를 확인한다. `full_pilot`은 Android 전달 8개 조건, 누락·receipt·crash 경계 무결성, 보안 8개 항목, 단말 수명주기 4개 시나리오와 후보·이전 승인 패키지를 원시 CSV로 대조한다. 역할별 UX는 세 핵심 흐름의 BEFORE 2회, 측정 시각·재시도·원천 ID, 장갑·한 손·거치 위치·단절 조건과 모든 관찰의 수용/불수용/검토 결정을 원시 CSV로 대조한다. 전체 파일럿 판정과 별도로 승인 계약·BEFORE·개발 항목·운영/보안/현장 공동 검토의 `ux_before_baseline` 판정도 기록한다. 수용한 P0/P1은 같은 개발 주기의 동일 역할·참여자·시나리오·조건에서 서로 다른 UI build의 수정 전후를 각각 2회 이상 측정한다. AFTER는 전건 성공, 원천 보존/다음 행동 이해, 유실·중복·치명적 blocker 0건을 충족해야 한다. 중앙 완료 시간·화면 이동·도움 요청 중 하나 이상은 개선되고 이 세 지표와 중앙 재시도 수는 모두 악화되지 않아야 한다. `windows_server_rehearsal`은 서버와 두 WPF MSI 변형의 패키지 hash·signer·혼입, 두 MSI의 10개 수명주기 행과 runtime matrix, 시작 실패 UX 8회, 장애 주입 14개와 네트워크 fail-closed 3개, 별도 PC 복구, RPO/RTO, 서버 재부팅과 rollback 후 각각 6개씩 총 12개 핵심 업무를 원시 CSV/JSON으로 대조한다. 모든 PASS 행의 증거 파일은 같은 실행 폴더에 실제로 있어야 하며 요약 JSON만 수정하거나 실기 증거가 없으면 PASS를 만들지 않는다.
- 사용자 역할은 코드와 DB에서 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`, `viewer`를 사용한다.
- AI 자동 조언과 운영 provider 연동은 후속 계층이다. 현재 서버는 `ai_search_candidates` 운영 점검, `ai_search_evaluation_runs`/`ai_search_evaluation_cases` 오프라인 회귀 평가, 외부 호출 전후 원천 권한·민감정보·최소 payload·근거 snapshot·인용·의미 검증과 감사 게이트, `system-admin` 전용 승인·프롬프트·운영 정책·감사·보존 제어면을 다룬다. generic 네트워크 adapter는 명시적 test scope까지만 허용한다. WPF는 근거 후보 점검 화면과 별도의 `AI 운영` 화면을 제공하지만 실제 외부 AI 질의 실행 화면은 없다.
- MES/ERP 연동은 후속 계층이다. 서버 계정 관리 API와 Windows 운영 UI, 강제 비밀번호 변경, 세션 폐기는 현재 구현 범위다.
- Windows와 Android의 업무 채널 알림과 인수인계 알림은 개인 메신저가 아니라 현장 기록 축적 흐름으로 다룬다.
- 2026-08-03 현재 수집 결과는 FastAPI 182건·WPF Core 101건·Android 32건이다. 표준 스크립트 `scripts/verify-preserved-tests.ps1`의 guard는 FastAPI 181건·WPF Core 98건·Android 32건이므로 현재 코드와 일치하지 않는다. guard를 맞춘 뒤 Windows에서 FastAPI 수집/JUnit과 WPF Core 수집 목록·TRX를 다시 대조하고, 누적 공통 DB 스모크와 Git 전후 점검을 포함한 무생략 run을 같은 clean 소스 커밋에서 2회 연속 실행해야 한다. 두 실행 모두 `partial_run=false`, `verification-summary.json=PASSED`일 때 통합 기준선으로 인정한다.

## 일일 기록

`docs/daily/`의 파일은 특정 날짜의 작업 맥락과 당시 검증 결과를 보존하는 기록이다. 과거 실행 횟수와 누적 DB 수치는 당시 사실이므로 최신 수치로 덮어쓰지 않으며, 현재 기능 판단은 이 폴더보다 상위 문서와 코드를 우선한다.

## 검증 자동화

FastAPI pytest, WPF Core 테스트·앱 build·통합 smoke, Android 단위 테스트·debug build와 실행 전후 Git 산출물 점검을 하나의 실행 ID로 보존하는 표준 순서는 [verification.md](./verification.md)를 따른다. 표준 실행은 Windows x64 도구 기준을 먼저 검사하며 단계별 로그, JUnit/TRX, WPF SQLite 증거와 최종 요약이 모두 통과한 경우에만 통합 기준선으로 인정한다.
