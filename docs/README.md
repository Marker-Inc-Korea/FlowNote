# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 현재 구현, 데이터 모델, API, 보안, 배포 기준을 관리한다. 문서는 현재 개발된 코드 기준을 우선하며, 아직 구현되지 않은 기능은 후속 범위로 분리한다.

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

## 현재 코드 기준

- Windows WPF 앱은 로컬 SQLite를 기본 저장소로 사용한다.
- Android 현장 단말 앱은 제품 방향에 포함되지만 아직 코드 구현 범위는 아니다. 역할은 현장 문서 열람, FieldComment, 사진 기록, 인수인계, 채널 알림이다.
- Windows의 채널 수신함, 채널 관리, 인수인계 확인 현황 UI는 제품 방향에 포함되지만 아직 클라이언트 코드 구현 범위는 아니다.
- FastAPI 서버는 `/api/v1` REST API와 SQLite, 로컬 `storage/` 파일 저장소를 사용한다.
- FastAPI 서버에는 공통 채널, 채널 메시지, 사용자별 알림 읽음, 인수인계 수신 확인 API가 있다.
- WPF와 스모크 테스트는 기본적으로 `data/local/flownote.local.sqlite`를 함께 사용한다.
- 문서 등록은 즉시 공개가 아니다. 등록된 문서는 `WORKING` 상태와 최신 버전으로 저장되고, 공개 버전은 별도 publish 절차로 지정한다.
- FieldComment는 문서 버전이 아니라 현장 원천 기록이다.
- WPF 서버 동기화 큐는 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장을 대상으로 한다.
- WPF에는 AI 근거 후보 운영 점검 화면이 있으며, 서버의 `ai_search_candidates` 재생성/품질/목록 API를 직접 조회한다.
- WPF MSI 패키징과 FastAPI 작업 스케줄러 등록/관리는 `scripts/`의 PowerShell 스크립트로 문서화되어 있다.
- 사용자 역할은 코드와 DB에서 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`, `viewer`를 사용한다.
- AI 자동 조언은 후속 계층이며, 현재 서버와 WPF는 근거 검색 후보 재생성/목록/품질 점검용 `ai_search_candidates` read model과 운영 점검 화면까지만 다룬다.
- MES/ERP 연동과 서버 계정 관리 UI는 후속 계층이다.
- Windows와 Android의 업무 채널 알림과 인수인계 알림은 개인 메신저가 아니라 현장 기록 축적 흐름으로 다룬다.

## 일일 기록

`docs/daily/`의 파일은 특정 날짜의 작업 기록이다. 최신 구현 판단은 이 폴더보다 상위 문서를 우선한다.

## 검증 자동화

FastAPI pytest, WPF build, WPF smoke를 테스트 DB와 산출물 보존 규칙에 맞춰 실행하는 표준 순서는 [verification.md](./verification.md)를 따른다.
