# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 현재 구현, 데이터 모델, API, 보안, 배포 기준을 관리한다. 문서는 2026-07-13 현재 개발된 코드 기준을 우선하며, 아직 구현되지 않은 기능은 후속 범위로 분리한다.

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
- Android 현장 단말 앱은 Java/Android 네이티브 View 기반 최소 앱으로 구현되어 있다. 승인 단말 `deviceId` 로그인, 공개 문서 조회/상세, FieldComment, 사진 첨부 outbox, 신호등식 기록, 전경 채널 알림 polling/읽음, 인수인계 확인을 제공한다.
- Windows에는 `admin`, `system-admin`용 승인 단말 관리 화면이 구현되어 있다. FastAPI 단말 API를 통해 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체를 수행한다.
- Windows에는 채널함, 채널 관리, 인수인계 확인 현황 화면이 구현되어 있고 FastAPI 채널/인수인계 API를 직접 호출한다. 서버 미연결 시 로컬 데이터와 동기화 큐를 삭제하지 않고 서버 설정 확인 문구를 표시한다.
- FastAPI 서버는 `/api/v1` REST API와 SQLite, 로컬 `storage/` 파일 저장소를 사용한다.
- FastAPI 서버에는 공통 채널, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음, 인수인계 수신 확인 API가 있다.
- WPF와 스모크 테스트는 기본적으로 `data/local/flownote.local.sqlite`를 함께 사용한다.
- 테스트와 개발 SQLite는 누적 검증 기록으로 로컬에 보존하지만 Git으로 추적하거나 커밋하지 않는다.
- 문서 등록은 즉시 공개가 아니다. 등록된 문서는 `WORKING` 상태와 최신 버전으로 저장되고, 공개 버전은 별도 publish 절차로 지정한다.
- FieldComment는 문서 버전이 아니라 현장 원천 기록이다.
- WPF 서버 동기화 큐는 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장을 대상으로 한다.
- WPF에는 AI 근거 후보 운영 점검 화면이 있으며, 서버의 `ai_search_candidates` 재생성/품질/목록 API를 직접 조회한다.
- 외부 AI 질의·요약은 `/api/v1/ai/queries` 생성·조회, 호출 로그 모델, 기능 플래그·승인·목적·근거 snapshot 차단 골격까지 구현되었다. 운영 provider client와 네트워크 호출은 아직 없으며 기본값은 비활성이다.
- WPF MSI 패키징과 FastAPI 작업 스케줄러 등록/관리는 `scripts/`의 PowerShell 스크립트로 문서화되어 있다.
- 사용자 역할은 코드와 DB에서 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`, `viewer`를 사용한다.
- AI 자동 조언과 운영 provider 연동은 후속 계층이다. 현재 서버는 `ai_search_candidates` 운영 점검과 외부 호출 전 안전장치·감사 골격을 다루고, WPF는 근거 후보 운영 점검 화면까지만 제공한다.
- MES/ERP 연동과 서버 계정 관리 UI는 후속 계층이다.
- Windows와 Android의 업무 채널 알림과 인수인계 알림은 개인 메신저가 아니라 현장 기록 축적 흐름으로 다룬다.
- FastAPI 테스트 수집 기준은 2026-07-13 현재 68개이며, 표준 PowerShell 검증 스크립트도 같은 기준선을 사용한다. FastAPI 전체 pytest 68건은 통과했으며 WPF 빌드와 WPF 스모크를 포함한 전체 표준 검증 결과는 별도로 남긴다.

## 일일 기록

`docs/daily/`의 파일은 특정 날짜의 작업 맥락과 당시 검증 결과를 보존하는 기록이다. 과거 실행 횟수와 누적 DB 수치는 당시 사실이므로 최신 수치로 덮어쓰지 않으며, 현재 기능 판단은 이 폴더보다 상위 문서와 코드를 우선한다.

## 검증 자동화

FastAPI pytest, WPF build, WPF smoke를 테스트 DB와 산출물 보존 규칙에 맞춰 실행하는 표준 순서는 [verification.md](./verification.md)를 따른다.
