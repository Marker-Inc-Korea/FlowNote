# FlowNote 문서 안내

## 현재 기준

- 문서 기준일: 2026-08-13
- 제품 단계: 공개 가능한 현재 기준선을 정리한 연구개발 프로토타입
- UX 기준: 현재 Windows·Android 메뉴와 화면. 현장 관찰 뒤 변경 가능

이 폴더는 제품 방향, 설계 계약, 역할별 매뉴얼, 운영 기준과 검증 기록을 관리한다. 처음 읽는 사람은 모든 문서를 순서대로 읽을 필요가 없다. 아래에서 역할에 맞는 경로를 선택한다.

## 독자별 읽는 순서

### 연구 책임자·검토자

1. [GitHub README](../README.md)
2. [연구 결과 정리](./research-summary.md)
3. [제품 개요](./product-overview.md)
4. [구현 로드맵](./implementation-roadmap.md)
5. [검증 기록과 현재 제한](./verification.md)
6. [오픈소스 공개 기준](./open-source-release.md)

### 제품·아키텍처 검토자

1. [제품 개요](./product-overview.md)
2. [시스템 맵](./system-map.md)
3. [데이터 모델](./data-model.md)
4. [API 계약](./api.md)
5. [중요 설계 결정](./decisions.md)

### 설치·운영 담당자

1. [역할별 매뉴얼 안내](./manuals/README.md)
2. [서버 설치·운영 매뉴얼](./manuals/server-operations.md)
3. [배포 기준](./deployment.md)
4. [보안 기준](./security.md)
5. [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)
6. [공통 장애 대응](./manuals/troubleshooting.md)

### Windows 사용자·관리자

1. [Windows 사용 매뉴얼](./manuals/windows-user-guide.md)
2. [FieldComment 검토·분석·선정 운영](./field-comment-review-workflow.md)
3. [역할별 업무 UX와 접근성](./ux-accessibility.md)
4. [Windows 구현 문서](../apps/windows/README.md)

### Android 현장 사용자·단말 관리자

1. [Android 현장 사용 매뉴얼](./manuals/android-field-guide.md)
2. [공통 장애 대응](./manuals/troubleshooting.md)
3. [Android 구현·빌드 문서](../apps/android/README.md)
4. [보안 기준](./security.md)

### 개발·검증 담당자

1. [시스템 맵](./system-map.md)
2. [데이터 모델](./data-model.md)
3. [API 계약](./api.md)
4. [검증 자동화와 실행 기록](./verification.md)
5. [AI ground-truth와 회귀 기준](./ai-ground-truth.md)
6. [중요 설계 결정](./decisions.md)

## 문서 역할

| 문서 | 주된 책임 | 변경 시점 |
| --- | --- | --- |
| [연구 결과 정리](./research-summary.md) | 연구 목적·방법·구현·검증·한계 요약 | 연구 기준선 또는 결론 변경 |
| [제품 개요](./product-overview.md) | 제품 목적·원칙·배포 방향 | 제품 범위 변경 |
| [시스템 맵](./system-map.md) | 구성요소와 도메인 관계 | 실행·데이터 흐름 변경 |
| [데이터 모델](./data-model.md) | 엔티티·상태·역할·저장 경계 | schema·상태 계약 변경 |
| [API](./api.md) | 경로·요청·응답 계약 | 외부 API 계약 변경 |
| [보안](./security.md) | 계정·단말·열람·운영 통제 | 권한·보안 정책 변경 |
| [배포](./deployment.md) | 설치·패키지·환경·백업·복구 기준 | 배포 방식 변경 |
| [검증](./verification.md) | 실행 절차와 보존된 결과 | 검증 실행 또는 기준 변경 |
| [설계 결정](./decisions.md) | 중요한 선택과 이유 | 되돌리기 어려운 결정 발생 |
| [역할별 매뉴얼](./manuals/README.md) | 실제 화면과 운영 절차 | UX·메뉴·운영 절차 변경 |
| [오픈소스 공개 기준](./open-source-release.md) | 공개 포함·제외 범위와 공개 전 확인 | 공개 범위·법적 조건 변경 |

## 현재 구현 요약

- FastAPI 서버는 `/api/v1` REST API, 서버 전용 SQLite와 로컬 `storage/`를 사용한다.
- Windows WPF는 서버 계정 로그인, 문서 운영, 검토·공개, FieldComment 검토, 보고서, 작업판, 채널, 계정·단말과 운영 관리 화면을 제공한다.
- Android는 승인 단말 로그인, 공개 문서 보안 열람, 오늘의 작업순서, FieldComment·사진, 알림과 인수인계를 제공한다.
- WPF 로컬 SQLite와 Android 암호화 outbox는 연결 장애 때 업무 원천과 재시도 상태를 보존한다.
- 문서 등록은 공개가 아니며 정확한 version·revision·file hash 승인 뒤 공개한다.
- FieldComment 원천과 관리자 해석, 보고서 원천 snapshot을 분리해 보존한다.
- 실제 외부 AI provider 호출은 기본 비활성이고 운영 범위가 아니다.
- MES/ERP 연동은 후속 계층이다.

상세 구현 목록은 각 앱 문서와 [연구 결과 정리](./research-summary.md)에서 확인한다.

## 현재 검증 상태

2026-08-13 개발 PC 검증에서 FastAPI 209건, WPF Core 120건, Android 39건과 WPF·Android 개발 빌드·정적 검사가 통과했다. 운영 HTTPS 연동은 다시 실행하지 않았으며, 최신 통과 기록은 2026-08-09 스모크다.

다음 항목은 연구개발 기준선의 미완료 사항이 아니라 실제 운영 도입을 결정할 때 수행하는 별도 검증이다.

- Windows x64 무생략 통합 기준선 2회
- 실제 Windows UI와 승인 Android 실단말
- 코드 서명·MDM·현장 인증서
- 고객 유사망과 별도 PC 복구
- 역할별 현장 UX 전후 측정
- rollback과 운영·보안·현장 공동 승인

최신 수치와 실행 증거는 [검증 문서](./verification.md)를 기준으로 한다.

## 기록 문서와 현재 기준의 구분

`docs/daily/`는 특정 날짜의 작업 맥락과 당시 검증 결과를 보존한다. 과거 실행 횟수와 DB 수치는 당시 사실이므로 최신 값으로 덮어쓰지 않는다. 현재 기능 판단에는 README, 연구 결과, 제품·설계 문서와 코드를 우선한다.

`docs/현장정리문서/`는 현장 의견 원문이다. 원문을 제품 결론처럼 바꾸지 않으며, 수용·불수용·추가 검토 결정은 별도 설계·UX·검증 문서에 남긴다.

가상환경, 빌드 캐시, 테스트 산출물 안의 Markdown은 생성·보존 기록이므로 제품 문서 갱신 대상에서 제외한다.

## 문서 갱신 규칙

### 코드 기능이 바뀔 때

1. API·데이터·보안 계약 영향을 확인한다.
2. 해당 기준 문서를 먼저 갱신한다.
3. Windows·Android 메뉴와 버튼이 바뀌면 역할별 매뉴얼을 갱신한다.
4. README의 현재 상태와 연구 결과 요약에 영향을 주는지 확인한다.
5. 관련 검증을 실행하고 결과를 검증 문서에 보존한다.

### UX가 바뀔 때

1. 변경 전 역할, 시나리오, 조건과 측정값을 보존한다.
2. 메뉴·버튼·입력 필수값과 실패 안내를 코드와 매뉴얼에서 함께 바꾼다.
3. 보존 데이터와 다음 행동 안내가 축소되지 않았는지 확인한다.
4. 같은 역할·조건에서 변경 후 결과를 다시 측정한다.
5. 화면 캡처가 있다면 실제 고객 정보와 서버 주소를 제거하고 버전을 표시한다.

### 검증 결과를 기록할 때

- 실행하지 않은 검증을 통과로 표시하지 않는다.
- 실패 결과와 원시 증거를 삭제하지 않는다.
- 운영 서버 DB·storage·로그 사본은 개발 PC나 Git에 남기지 않는다.
- 단위 테스트 통과와 운영 배포 승인을 구분한다.

## 문서 정리 완료 기준

- 처음 보는 사람이 README와 연구 결과 문서로 목적·구조·현재 상태를 이해할 수 있다.
- 사용자와 운영자가 역할별 매뉴얼에서 실제 업무 순서를 찾을 수 있다.
- 메뉴, 버튼, 역할, 상태와 명령이 현재 코드와 일치한다.
- 현재 구현, 검증 중, 후속 범위가 섞이지 않는다.
- 링크가 유효하고 같은 목적의 문서가 중복되지 않는다.
- 비밀값, 실제 고객 정보와 운영 데이터가 포함되지 않는다.
