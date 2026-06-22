# Agent Instructions

## GitHub Push Policy

- Do not push to GitHub unless the user explicitly asks for a push.
- Changing files, running checks, staging, or creating a local commit does not imply permission to push.
- If a change should be shared remotely, wait for a direct user instruction to push.
- Before any push, confirm the target remote and branch if they are not already clear from the current task.

## Project

FlowNote는 생산공장 현장의 문서와 현장 지식을 함께 관리하는 독립형 서버이다.

주요 범위는 문서 파일 저장, 문서 메타데이터, 문서 버전, 변경 사유, 회원 로그인, 권한, 현장 단말기 뷰어, 관리자 파일 변경 감지, 현장 코멘트, 작업내역, 보고서 생성 보조, AI 검색과 작업 조언이다.

제품 방향은 단순 문서관리 프로그램이나 순수 지식관리 시스템 중 한쪽으로 치우치지 않는다. 초기에는 완성형 DMS/KMS보다 문서 버전, 현장 코멘트, 작업 문제점, 생산보고서, 작업내역을 오래 축적해 향후 AI가 검색, 조언, 의사결정 보조에 활용할 수 있는 근거 데이터를 쌓는 것을 1차 목표로 둔다.

FlowNote는 MES나 ERP를 대체하지 않는다. 작업지시 구조는 초기에는 관리자가 직접 입력하고 고객이 이미 사용하는 문서 정리 구조에 연결한다. 추후 MES/ERP가 있는 현장에서는 현장별 API 어댑터로 자동 수신할 수 있게 확장한다. 제품의 핵심은 정형 생산 데이터만으로 부족한 현장 노하우와 관리자 보고서를 함께 모아 AI 활용 데이터로 발전시키는 것이다.

배포 기준은 사내 서버형 운영이다. 생산현장 문서는 클라우드 사용을 꺼리는 경우가 많으므로 우선 고객 현장 또는 사내 서버 PC 1대에 서버를 설치하고, 현장 PC에는 네이티브 클라이언트 설치파일을 배포한다. 외부 접근이나 클라우드는 초기 기준이 아니라 별도 협의가 필요한 후속 선택지로 둔다.

현장 사용자의 경험은 관리 대상 데이터이다. 현장의 소리를 기록으로 남겨 특정 담당자에게 지식이 묶이지 않고, 누가 작업하더라도 과거 경험을 활용하고 발전시킬 수 있는 구조를 유지한다.

현장 코멘트는 원천 이력이며, 관리자급 검토와 분석을 통해 보고서 형태의 정제 문서로 연결되어야 한다. 난잡한 원천 데이터와 정제된 보고서가 함께 있어야 추적성과 의사결정 근거가 동시에 확보된다.

현장 사용자는 로그인 기반 권한으로 문서를 열람한다. 파일 다운로드 차단과 뷰어 자동 닫힘은 중요 보안 요구이며, Python FastAPI 서버와 Windows WPF 클라이언트 앱의 권한, 감사 로그, 로컬 제어 정책을 함께 사용해 구현한다.

## Repository Layout

- `docs/`: 제품, 아키텍처, 데이터 모델, API, 결정 기록
- `services/api/`: Python FastAPI 기반 FlowNote API 서버
- `apps/windows/`: Windows WPF 기반 현장/관리자 클라이언트
- `apps/web/`: 신규 개발 대상이 아닌 과거 웹 UI 자리. 새 기능을 추가하지 않는다.
- `packages/shared/`: 공통 도메인 모델, API 계약, 검증 규칙
- `packages/ui/`: 공통 UI 자원 또는 디자인 토큰
- `assets/`: 공통 정적 자원
- `scripts/`: 개발, 빌드, 운영 보조 스크립트

## Working Rules

- 문서 변경은 `docs/`의 역할 구분을 유지한다.
- 제품 방향은 `docs/product-overview.md`를 기준으로 맞춘다.
- 전체 도메인 관계는 `docs/system-map.md`를 기준으로 맞춘다.
- 도메인 관계와 처리 흐름은 `docs/architecture.md`에 둔다.
- 엔티티와 상태 값은 `docs/data-model.md`에 둔다.
- API 경로와 요청/응답 초안은 `docs/api.md`에 둔다.
- 중요한 설계 결정은 `docs/decisions/`에 ADR로 남긴다.
- Backend는 Python FastAPI를 기준으로 한다.
- Client는 Windows WPF 기반 네이티브 앱을 기준으로 한다.
- 클라이언트 앱은 Windows용 하나만 제작한다.
- Android, macOS, Linux 클라이언트는 현재 제품 개발 대상이 아니다.
- 독립 Web UI는 개발하지 않는다.
- Database는 SQLite를 우선 사용하고, 필요하면 PostgreSQL로 확장한다.
- 파일은 서버 PC의 로컬 `storage/` 폴더에 저장한다.
- 배포는 서버 PC 1대와 클라이언트 설치파일 배포를 기준으로 한다.
- MES/ERP는 대체 대상이 아니라 후속 연동 대상이며, 초기 작업지시는 관리자 입력 기준으로 설계한다.
- 문서 구조는 고객이 결정한다. 트리/BOM 문서 구조는 예시일 뿐 기본 강제 구조로 설계하지 않는다.
- BOM 문서 구조라는 표현은 현장 용어 예시일 뿐이며, MES BOM 차용이나 기본 구조 강제를 뜻하지 않는다.
- 문서와 현장 코멘트는 설비, 품목, 공정, 오류 유형 등 태그로 보완 연결할 수 있어야 한다.
- 문서 수정자, 열람자, 코멘트 등록자, 실제 전달자 또는 작업자 정보를 남겨야 한다.
- 현장 코멘트는 관리자 분석과 AI 보조 보고서 초안 생성을 통해 정제 문서로 연결될 수 있어야 한다.
- 문서 상태는 작업중/검토중/공개/보관 등을 구분하고, 업로드 문서를 무조건 최신 확정본으로 가정하지 않는다.
- Windows WPF 클라이언트 앱은 네이티브 UI를 우선하고, 파일 감시 같은 로컬 기능은 클라이언트 네이티브 기능으로 처리한다.
- 고객 생산공장 운영에서는 일반 브라우저 직접 접근이 아니라 승인된 설치형 클라이언트 앱 접근을 기본으로 한다.
- 제품 설계 시 DMS 기능만 남기거나 KMS 기능만 과도하게 확장하지 않고, 문서와 현장 지식의 연결 관계를 유지한다.
- AI는 장기적으로 의사결정 조언까지 확장하되, 현재 제품 문서에서는 검색과 작업 조언을 우선 기능으로 둔다.
- 현장 입력은 신호등식 기록, 기본 정형 문구, 짧은 메모, 관리자 대리 입력에서 시작하고 MES 연동은 후속 단계로 둔다.
- 프레임워크 스캐폴딩은 실제 구현 요청이 있을 때 추가한다.
- 빌드 결과, 의존성 폴더, 비밀값, 로컬 설정, 임시 파일은 커밋하지 않는다.

## Before Committing

- `git status`로 변경 파일을 확인한다.
- 변경한 문서 링크가 깨지지 않았는지 확인한다.
- 코드가 추가된 경우에만 관련 빌드 또는 테스트를 실행한다.
