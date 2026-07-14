# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 현재 구현, 데이터 모델, API, 보안, 배포 기준을 관리한다. 문서는 2026-07-14 현재 개발된 코드 기준을 우선하며, 아직 구현되지 않은 기능은 후속 범위로 분리한다.

전체 문서 갱신 범위는 Git이 추적하는 제품·구현 Markdown이다. `AGENTS.md`는 작업 정책 원문이므로 제품 코드 설명과 분리하고, 가상환경·빌드 캐시·테스트 산출물 안의 Markdown은 생성·보존 기록이므로 갱신 대상에서 제외한다.

## 읽는 순서

1. [제품 개요](./product-overview.md)
2. [시스템 맵](./system-map.md)
3. [데이터 모델](./data-model.md)
4. [API](./api.md)
5. [MVP 범위](./mvp-scope.md)
6. [구현 로드맵](./implementation-roadmap.md)
7. [보안](./security.md)
8. [배포](./deployment.md)
9. [설계 결정](./decisions.md)
10. [검증 기록과 현재 검증 제한](./verification.md)

## 현재 코드 기준

- Windows WPF 앱은 로컬 SQLite를 기본 저장소로 사용한다.
- Android 현장 단말 앱은 Java/Android 네이티브 View 기반 최소 앱으로 구현되어 있다. 승인 단말 `deviceId` 로그인, 공개 문서 목록·상세 메타데이터 조회, FieldComment, 사진 첨부 outbox, 신호등식 기록, 전경 채널 알림 polling/읽음, 인수인계 확인을 제공한다. 문서 파일 본문 다운로드·미리보기는 아직 없다.
- Windows에는 `admin`, `system-admin`용 승인 단말 관리 화면이 구현되어 있다. FastAPI 단말 API를 통해 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체를 수행한다.
- Windows 사용자 관리는 로그인 저장소에 따라 분리된다. 서버 로그인한 `admin`, `system-admin`은 서버 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기를 수행하고, 로컬 로그인은 로컬 SQLite 계정 화면만 사용한다. 임시 비밀번호 계정은 메인 화면 전에 비밀번호 변경을 강제하고 변경 후 재로그인을 요구한다.
- Windows에는 채널함, 채널 관리, 인수인계 확인 현황 화면이 구현되어 있고 FastAPI 채널/인수인계 API를 직접 호출한다. 서버 미연결 시 로컬 데이터와 동기화 큐를 삭제하지 않고 서버 설정 확인 문구를 표시한다.
- FastAPI 서버는 `/api/v1` REST API와 SQLite, 로컬 `storage/` 파일 저장소를 사용한다.
- FastAPI 서버에는 공통 채널, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음, 인수인계 수신 확인 API가 있다.
- WPF와 스모크 테스트는 기본적으로 `data/local/flownote.local.sqlite`를 함께 사용한다.
- 테스트와 개발 SQLite는 누적 검증 기록으로 로컬에 보존하지만 Git으로 추적하거나 커밋하지 않는다.
- 문서 등록은 즉시 공개가 아니다. 등록된 문서는 `WORKING` 상태와 최신 버전으로 저장되고, 공개 버전은 별도 publish 절차로 지정한다.
- WPF 다운로드 허용 role의 파일 저장은 로컬 원본 복사가 아니라 서버의 세션 바인딩 1회성 controlled copy와 저장 후 SHA-256 검증을 사용한다.
- FieldComment는 문서 버전이 아니라 현장 원천 기록이다.
- WPF 서버 동기화 큐는 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장을 대상으로 한다.
- Windows 보존 동기화 전환 CLI는 FAILED 큐를 읽기 전용 dry-run으로 분류하고 plan hash와 row별 승인을 요구한다. 승인된 구 `create`/FieldNote 항목은 기존 원천·큐·파일을 수정하지 않고 현재 action의 신규 큐와 감사 이력으로 연결한다.
- WPF에는 AI 근거 후보 운영 점검 화면이 있으며, 서버의 `ai_search_candidates` 재생성/품질/목록 API를 직접 조회한다. WPF 서버 클라이언트와 스모크 테스트는 오프라인 ground-truth 회귀 평가 API도 호출해 후보 ID·내용 hash·순위·원천 커버의 재현성을 검증한다.
- 외부 AI 질의·요약은 `/api/v1/ai/queries` 생성·조회, 호출 로그 모델, 기능 플래그·승인·목적·원천 권한·민감정보·최소 payload·근거 snapshot 게이트까지 구현되었다. 운영 provider client와 네트워크 호출은 아직 없으며 기본값은 비활성이다.
- 고객·현장별 AI 금칙어와 고객 식별자는 `ai_sensitive_data_policies`에 버전별로 저장하고 활성 정책을 provider 직전 필터에 적용한다. 이를 관리하는 운영 API/UI는 아직 없다.
- WPF MSI 패키징과 FastAPI 작업 스케줄러 등록/관리는 `scripts/`의 PowerShell 스크립트로 문서화되어 있다.
- 사용자 역할은 코드와 DB에서 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`, `viewer`를 사용한다.
- AI 자동 조언과 운영 provider 연동은 후속 계층이다. 현재 서버는 `ai_search_candidates` 운영 점검, `ai_search_evaluation_runs`/`ai_search_evaluation_cases` 오프라인 회귀 평가, 외부 호출 전 원천 권한·민감정보·최소 payload·근거 snapshot·인용 검증과 감사 게이트를 다룬다. provider 호출 지점은 테스트용 주입 경계까지만 있으며 운영 네트워크 client는 없고, WPF UI는 근거 후보 운영 점검 화면까지만 제공한다.
- MES/ERP 연동은 후속 계층이다. 서버 계정 관리 API와 Windows 운영 UI, 강제 비밀번호 변경, 세션 폐기는 현재 구현 범위다.
- Windows와 Android의 업무 채널 알림과 인수인계 알림은 개인 메신저가 아니라 현장 기록 축적 흐름으로 다룬다.
- FastAPI 코드는 2026-07-14 현재 pytest 96건이 수집되며 `scripts/verify-preserved-tests.ps1`도 같은 96건을 기준선으로 사용한다. AI 근거 검색·provider 경계, controlled copy, 서버 계정 수명주기·권한·세션·감사 회귀가 포함된다.

## 일일 기록

`docs/daily/`의 파일은 특정 날짜의 작업 맥락과 당시 검증 결과를 보존하는 기록이다. 과거 실행 횟수와 누적 DB 수치는 당시 사실이므로 최신 수치로 덮어쓰지 않으며, 현재 기능 판단은 이 폴더보다 상위 문서와 코드를 우선한다.

## 검증 자동화

FastAPI pytest, WPF build, WPF smoke를 테스트 DB와 산출물 보존 규칙에 맞춰 실행하는 표준 순서는 [verification.md](./verification.md)를 따른다.
