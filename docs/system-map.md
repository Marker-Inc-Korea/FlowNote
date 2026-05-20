# FlowNote 상관관계 정리

## 1. 전체 기준

FlowNote는 생산현장 문서를 중심으로 문서 버전, 현장 단말기, 관리자 파일 감시, 현장 코멘트, 작업내역, AI 검색을 연결하는 독립형 문서·현장지식 관리 서버이다.

제품 방향은 단순 문서관리 프로그램이나 순수 지식관리 시스템 중 하나로 고정하지 않는다. 문서관리 기능은 신뢰 가능한 문서 상태, 공개 버전, 변경 이력을 만들고, 현장지식 기능은 문서와 작업 맥락에 연결된 코멘트와 문제점을 축적한다. 오랜 운영으로 쌓인 연결 데이터는 추후 AI 검색, 작업 조언, 의사결정 보조의 기반이 된다.

현장 코멘트는 원천 이력 데이터로 보존한다. 이 데이터는 관리자급 사용자의 분석과 결합되어 보고서 형태의 정제 문서로 연결될 때 실제 활용성이 높아진다. FlowNote는 난잡한 원천 코멘트와 정제된 보고서를 모두 유지하여, 이력 추적과 문서화된 판단 근거를 동시에 확보한다.

현재 단계에서 AI는 검색과 조언을 중심으로 둔다. 과거 생산 데이터로 새로운 작업을 설계하는 기능은 장기 가능성으로 남기며, 초기 구조에서는 현장의 소리와 문서 이력을 안정적으로 기록하는 것을 우선한다.

개발은 Web UI와 API를 기준으로 진행하지만, 고객 생산공장 운영에서는 일반 브라우저 직접 접근을 기본 사용 방식으로 두지 않는다. 현장 사용자는 승인된 Android/Windows 클라이언트 앱의 WebView를 통해 접근한다.

FlowNote는 MES/ERP를 대체하지 않는다. 초기 작업지시는 MES 연동 데이터가 아니라 관리자가 직접 입력한 업무 구조로 관리한다. 문서 정리 구조는 프로그램이 강제하지 않고 고객이 결정한다. 기존 MES/ERP가 있으면 후속 단계에서 정형 생산 데이터를 연동하고, FlowNote는 문서, 현장 코멘트, 작업내역, 관리자 보고서를 연결해 AI 활용 데이터를 보강한다.

기본 기술 기준은 다음과 같다.

| 영역 | 기준 |
| --- | --- |
| Web UI | TypeScript + React + Vite |
| Android | Kotlin + WebView |
| Windows | WPF + WebView2 |
| Metadata DB | MySQL |
| 배포 | 고객 데이터 주권 기반 독립 인스턴스 |

단말기는 서버가 아니라 클라이언트이다. 서버는 고객이 승인한 위치에 구축하고, 현장 규모와 보안 정책에 따라 내부망 서버, 대용량 서버, 미니PC, 고객 사내 서버, 전용 클라우드 등으로 운영할 수 있다.

## 2. 핵심 도메인 관계

```text
Document
  -> DocumentVersion
      -> FileObject

Document
  -> DocumentPermission
  -> DocumentHistory
  -> DocumentAccessLog
  -> Notification

DocumentStructure
  -> DocumentStructureItem
      -> DocumentStructureItemDocument
          -> Document
          -> DocumentVersion

TerminalDevice
  -> viewer
      -> Published document view
      -> ViewerSession timeout (client app phase)
      -> FieldNote create
      -> Download control (client app phase)
  -> admin_support
      -> WatchedFile
      -> FileChangeCandidate
      -> DocumentVersion upload assist
      -> Admin download policy

FieldNote
  -> Document
  -> DocumentVersion
  -> OperatorProfile / UserAccount
  -> CommentTemplate
  -> ReportSource
      -> Report
          -> Document

WorkRecord
  -> WorkRecordVersion
  -> WorkRecordDocument
      -> Document
      -> DocumentVersion

SearchIndexItem
  -> DocumentVersion
  -> FieldNote
  -> Report
  -> WorkRecordVersion

AiAdviceLog
  -> WorkRecord
  -> Document
  -> source_refs

ExternalSystem
  -> IntegrationMapping
  -> DocumentStructure / WorkRecord / FieldNote

OperatorProfile / UserAccount
  -> DocumentHistory
  -> DocumentAccessLog
  -> FieldNote
  -> WorkRecordParticipant
```

## 3. 문서와 파일

문서는 메타데이터이고, 파일은 저장소에 보관되는 바이너리이다.

- `Document`: 문서의 대표 정보
- `DocumentVersion`: 문서의 개정 단위
- `FileObject`: 실제 파일 참조 정보

동일 문서가 수정되면 기존 파일을 덮어쓰지 않고 `DocumentVersion`을 추가한다. 업로드된 문서가 항상 최신 확정본이라고 가정하지 않는다. 가장 최근 등록 버전과 현장 공개 버전은 분리해서 관리한다.

문서관리 영역은 파일 저장, 문서 상태, 버전, 권한, 이력, 보존 정책을 책임진다. 현장 코멘트나 작업 문제점은 문서 테이블에 직접 섞지 않고 별도 현장지식 데이터로 관리한다.

문서 상태 예시는 다음과 같다.

- `WORKING`: 작업중
- `IN_REVIEW`: 검토중
- `PUBLISHED`: 현장 공개
- `ARCHIVED`: 보관

## 4. 고객 정의 문서 구조와 업무 구조

생산현장의 문서 정리 방식은 고객마다 다르다. FlowNote는 문서 자체와 문서 정리 구조를 분리하고, 고객이 이미 사용하는 구조를 흡수한다.

- `DocumentStructure`: 고객이 정한 문서 구조의 루트
- `DocumentStructureItem`: 구조 안의 항목. 트리 노드, 폴더, 작업 단계, 현장 분류 등으로 사용할 수 있음
- `DocumentStructureItemDocument`: 구조 항목과 문서 또는 문서 버전의 연결

트리 구조는 구현 가능한 표현 방식 중 하나일 뿐 기본 강제 구조가 아니다. 현장에서 말하는 BOM 문서는 MES BOM을 차용한다는 뜻이 아니라 문서를 계층적으로 정리해 부르는 현장 용어의 예시이다.

관리자는 고객의 기존 정리 방식에 맞춰 구조를 만들고 문서를 연결한다. 추후 MES/ERP 연동 시에도 FlowNote가 구조를 강제하지 않고 외부 데이터와 고객 구조를 매핑한다.

## 4.1 태그 기반 보완 관계

고객 정의 문서 구조에 모두 흡수되지 않는 관계는 태그로 보완한다. 라인, 공정, 설비, 품목 같은 MES 계열 개념은 생산현장 맥락을 표현하기 위한 기준 후보로 차용하되, 고객별 용어와 운영 방식에 맞게 선택적으로 사용한다.

- 태그 유형: 설비, 품목, 공정, 오류 유형, 라인, 위치, 사용자 정의
- 문서 태그: 문서가 관련된 설비, 품목, 공정 등을 표시
- 현장 코멘트 태그: 문제점이나 경험이 발생한 설비, 품목, 공정, 오류 유형을 표시

같은 태그를 공유하는 문서와 현장 코멘트는 검색, 보고서, AI 조언에서 서로 연결될 수 있어야 한다.

## 4.2 MES/ERP와의 관계

MES/ERP는 FlowNote의 대체 대상이 아니라 연동 대상이다.

- MES/ERP: 작업지시, 생산실적, 설비, 품목, 공정 같은 정형 데이터의 원천
- FlowNote: 문서, 버전, 고객 정의 문서 구조, 현장 코멘트, 작업 문제점, 관리자 보고서, AI 검색/조언 데이터의 연결 계층
- 연동 어댑터: 현장별 MES/ERP API, DB, 파일 연동 차이를 흡수하는 계층

현재 단계의 작업지시는 FlowNote 내부에서 관리자가 입력한 `manual` 데이터로 본다. MES/ERP 연동이 추가되면 외부 원본 ID를 고객 정의 문서 구조에 매핑하고 자동 수신으로 확장한다.

AI는 MES/ERP의 정형 데이터만 보지 않고, FlowNote에 쌓인 현장 노하우와 문서 근거를 함께 참조해야 한다.

## 5. 단말기 역할

| 모드 | 대상 | 역할 |
| --- | --- | --- |
| `viewer` | 현장 사용자 단말기 | 현장 공개 문서 열람, 알림 확인, 현장 코멘트 등록 |
| `admin_support` | 관리자 단말기 | 파일 감시, 변경 후보 생성, 새 버전 업로드 보조, 관리자 다운로드 |

현장 사용자 단말기는 파일을 감시하지 않고 문서 파일 다운로드도 제공하지 않는다. 관리자 단말기도 자동 업로드를 하지 않고, 변경 후보를 만든 뒤 관리자가 변경 사유를 입력하여 업로드를 확정한다.

## 6. 회원관리와 열람 보안

FlowNote는 회원 로그인 기반 권한을 전제로 한다.

```text
UserAccount
  -> UserRole
  -> Role
  -> DocumentPermission
```

현장 사용자는 문서 열람과 코멘트 등록 중심으로 사용한다. 관리자급 권한이 없는 사용자 다운로드 차단은 클라이언트 앱 단계에서 구현한다.

문서 뷰어 자동 닫힘은 클라이언트 앱 단계에서 구현한다. 이는 클라이언트가 켜져 있어도 사용자가 자리를 비운 상황에서 문서가 계속 노출되는 현실 보안 문제를 줄이기 위한 정책이다.

## 7. WebView와 브릿지

Android와 Windows는 공통 Web UI를 WebView로 표시한다.

```text
Web UI
  -> Bridge Request
  -> Native App
  -> Local Function
  -> Bridge Response
```

브릿지는 웹이 직접 처리하기 어려운 로컬 기능만 제공한다.

- 파일 감시
- 로컬 파일 선택
- OS 알림
- 외부 뷰어 호출
- 단말기 정보 조회

브릿지는 문서 파일 자동 동기화 수단이 아니다.

## 8. 현장 코멘트와 보고서

현장 코멘트는 문서 파일이 아니라 문서, 문서 버전, 고객 정의 문서 구조 항목, 작업내역에 연결되는 현장지식 데이터이다. 현장 코멘트는 원천 이력으로 보존하며, 관리자 분석과 보고서 문서로 정제되는 흐름을 가진다.

- 초기 입력은 신호등식 기록, 기본 정형 문구, 짧은 메모, 관리자 대리 입력으로 시작한다.
- 설비, 품목, 공정, 오류 유형 같은 태그를 함께 달 수 있다.
- 현장 사용자는 직접 입력하거나 정형 문구를 선택한다.
- `raw_content`는 원문 보존용이다.
- `normalized_content`는 관리자 정리 문구이다.
- `analysis_content`는 관리자급 사용자의 분석과 판단을 남기는 정제 영역이다.
- 보고서는 `FieldNote`, `WorkRecord`, 관련 문서를 원천 데이터로 사용한다.
- 최종 보고서는 다시 `Document`로 저장한다.
- 보고서와 원천 코멘트는 `ReportSource`로 연결해 보고서 결론의 근거를 추적한다.

초기에는 현장 작업 흐름을 방해하지 않는 낮은 입력 부담을 우선한다. 실시간 직접 입력을 강제하지 않고, 말로 전달된 내용을 관리자가 대신 입력하는 경로도 허용한다. MES 연동과 자동 수집은 후속 단계에서 확장하되 데이터 모델은 처음부터 연결 관계를 유지한다.

이 구조의 목적은 현장 사용자의 경험이 개인에게만 남지 않도록 하는 것이다. 어느 작업자가 투입되더라도 과거 코멘트, 문제점, 조치 이력, 관련 문서를 함께 확인해 지식을 활용하고 발전시킬 수 있어야 한다.

## 8.1 작업자와 추적성

문서와 현장지식은 누가 작성, 수정, 열람, 전달했는지 남아야 실제 운영에서 신뢰할 수 있다.

- 문서 수정자는 `DocumentHistory.actor_id`로 기록한다.
- 문서 열람자는 `DocumentAccessLog.actor_id`로 기록한다.
- 현장 코멘트 입력자는 `FieldNote.author_id`로 기록한다.
- 실제 전달자 또는 작업자는 `FieldNote.reported_by`로 기록한다.
- 개인 작업자를 특정하기 어려운 경우 작업반, 조장, 관리자 대리 등록자, 라인 단위로 기록할 수 있어야 한다.

## 9. 작업내역과 AI

작업내역은 작업지시 문서와 현장 실행 결과를 연결한다.

- `WorkRecord`: 작업 단위
- `WorkRecordVersion`: 작업내역 개정 단위
- `WorkRecordDocument`: 작업과 관련 문서 연결

AI 검색과 조언은 원본 데이터를 대체하지 않는다. `SearchIndexItem`은 검색용 참조 데이터이고, `AiAdviceLog`는 AI 요청과 결과의 기록이다.

AI 답변은 가능한 경우 근거 문서, 문서 버전, 현장 코멘트, 작업내역을 함께 제공한다.

AI 기능은 문서와 현장지식 데이터를 활용하는 계층이다. 초기에는 자연어 검색, 관련 문서 탐색, 작업 전 주의 사항, 과거 문제점 기반 조언에 집중한다. 자동 의사결정이나 신규 작업 자동 설계는 충분한 운영 데이터가 쌓인 뒤 검토할 장기 과제이다.

## 10. 고객 데이터 주권 기반 배포

FlowNote는 고객 데이터 주권을 위해 고객 또는 현장별 독립 인스턴스를 기본으로 한다.

```text
Site Instance
  -> API Server
  -> MySQL
  -> File Storage
  -> Search Index
  -> Web UI
  -> Client Terminals
```

현장별로 데이터베이스, 파일 저장소, 인증 설정, 네트워크 보안 정책을 분리한다.

독립 인스턴스는 무조건 내부망 로컬 서버만을 뜻하지 않는다. 고객이 승인한 환경이라면 내부망, 고객 사내망, 전용 호스팅, 전용 클라우드, VPN 기반 외부 접근 구조를 선택할 수 있다. 중요한 기준은 데이터와 파일의 통제권이 고객에게 있고, 인가된 사용자만 접근하는 것이다.
