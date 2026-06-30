# FlowNote 상관관계 정리

## 0. 현재 코드 기준 상관관계

현재 실제 구현은 Windows WPF 앱이 로컬 SQLite DB를 직접 사용하는 프로토타입 구조이다.

```text
Windows WPF App
  -> FlowNoteLocalDatabase
      -> user_accounts
      -> document_folders
      -> documents
      -> document_versions
      -> field_notes
      -> work_sequence_boards / work_sequence_items
      -> work_sequence_change_history
      -> notifications

Windows WPF App
  -> data/local/flownote.local.sqlite
  -> data/local/Files/Uploads/yyyy-MM-dd

FastAPI Server
  -> GET /
  -> GET /api/v1/health
  -> POST /api/v1/auth/login
  -> documents / document_versions / file_objects
  -> field_notes
  -> work_sequence_boards / work_sequence_items
```

현재 코드에는 FastAPI 로그인 API, refresh token 회전, logout 세션 폐기, `/auth/me`, WPF 로그인 화면의 서버 로그인 우선 호출과 로컬 SQLite 폴백, 로그인 성공 후 Bearer 인증 헤더 적용, 문서 등록/버전 등록 API, 문서 상태와 공개 버전 API, 서버 `storage/` 저장소, 서버 `FieldNote` 등록/조회/검토 API, FieldNote 첨부 API, 서버 문서 접근 로그 API, 작업순서판 최소 API, WPF 로컬 `field_notes` 오프라인 저장 흐름, WPF 로컬 작업순서판 편집/TV 읽기 화면이 구현되어 있다. 로그인 API는 사용자명/비밀번호로 계정 활성 상태를 확인하고 사용자 정보, access token, refresh token, 만료 시각을 반환한다. 문서, 태그, FieldNote, 문서 접근 로그, 작업순서판 API는 인증 헤더가 없거나 token이 만료/대체/폐기되었으면 `401`을 반환한다. 문서 쓰기, 태그 쓰기, 작업순서판 쓰기, 접근 로그 조회는 role 기반 권한 검사를 수행한다. 작업순서판은 기존 `작업순서` 폴더 파일 등록과 분리된 운영 보드이며, 항목 순서 변경과 상태 변경을 별도 이력과 알림 이벤트 후보로 남긴다. WPF는 문서, FieldNote, 첨부, 접근 로그 전송 후보를 `server_sync_queue`에 남기고 서버 URL이 있으면 재시도한다. `WorkRecord`, `Report`, `SearchIndexItem`, `AiAdviceLog`, MES/ERP 연동 모델은 아직 구현되어 있지 않다. 아래 상관관계는 제품 목표와 서버 확장 기준이며, 미래 기능은 현재 코드와의 구현 비교 대상이 아니다.

## 1. 전체 기준

FlowNote는 생산현장 문서를 중심으로 문서 버전, 현장 단말기, 관리자 파일 감시, 현장 코멘트, 작업내역, 후속 AI 활용 기반을 연결하는 독립형 문서·현장지식 관리 서버이다.

제품 방향은 단순 문서관리 프로그램이나 순수 지식관리 시스템 중 하나로 고정하지 않는다. 문서관리 기능은 신뢰 가능한 문서 상태, 공개 버전, 변경 이력을 만들고, 현장지식 기능은 문서와 작업 맥락에 연결된 코멘트와 문제점을 축적한다. 오랜 운영으로 쌓인 연결 데이터는 추후 AI 검색, 작업 조언, 의사결정 보조의 기반이 된다.

현장 코멘트는 원천 이력 데이터로 보존한다. 이 데이터는 관리자급 사용자의 분석과 결합되어 보고서 형태의 정제 문서로 연결될 때 실제 활용성이 높아진다. FlowNote는 난잡한 원천 코멘트와 정제된 보고서를 모두 유지하여, 이력 추적과 문서화된 판단 근거를 동시에 확보한다.

현재 단계에서는 현장의 소리와 문서 이력을 안정적으로 기록하는 것을 우선한다. AI 검색과 조언은 축적된 데이터의 후속 활용 계층으로 두고, 과거 생산 데이터로 새로운 작업을 설계하는 기능은 장기 가능성으로 남긴다.

개발은 Python FastAPI 서버와 Windows WPF 클라이언트를 기준으로 진행한다. 고객 생산공장 운영에서는 일반 브라우저 직접 접근을 기본 사용 방식으로 두지 않는다. 현장 사용자는 승인된 설치형 클라이언트 앱을 통해 접근한다.

FlowNote는 MES/ERP를 대체하지 않는다. 초기 작업지시는 MES 연동 데이터가 아니라 관리자가 직접 입력한 업무 구조로 관리한다. 문서 정리 구조는 프로그램이 강제하지 않고 고객이 결정한다. 기존 MES/ERP가 있으면 후속 단계에서 정형 생산 데이터를 연동하고, FlowNote는 문서, 현장 코멘트, 작업내역, 관리자 보고서를 연결해 AI 활용 데이터를 보강한다.

현장 사용자가 처음 체감해야 하는 기능은 AI보다 탐색기형 검색, 현장 공개 문서 뷰어, 사진 기록, 작업순서판과 현장 TV 화면이다. FlowNote는 문서관리와 현장지식의 구조를 유지하면서도, 현장에서 바로 찾고 보고 움직일 수 있는 운영 화면을 초기 우선순위로 둔다.

현장 소리는 제품 입력이지만 모두 구현 대상은 아니다. 사진 기록, 짧은 코멘트, 작업순서, 인수인계, 문서 보기 개선은 FlowNote의 핵심 흐름에 흡수하고, 메신저 전체 기능, 개인 메신저 수집, GPS 추적, 근태 관리, 전체 MES/ERP 대체 기능은 별도 시스템 영역으로 분리한다.

현장 관찰은 FlowNote 요구사항 분석의 일부이다. 작업자의 감각 판단, 공정 중간 보류, 재작업, 선별, 금형 또는 원재료 상태에 대한 경험은 MES 정량 결과 뒤에 숨어 있는 현장지식 데이터로 본다.

기본 기술 기준은 다음과 같다.

| 영역 | 기준 |
| --- | --- |
| Backend | Python FastAPI |
| Client | Windows WPF |
| Metadata DB | SQLite 우선, 필요 시 PostgreSQL |
| File Storage | 서버 PC 로컬 storage 폴더 |
| 배포 | 서버 PC 1대 + 클라이언트 설치파일 |

단말기는 서버가 아니라 클라이언트이다. 서버는 고객 현장 또는 사내 서버 PC 1대에 구축하고, 현장 PC에는 클라이언트 설치파일을 배포한다.

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
      -> Work sequence TV view
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
  -> FieldNoteAttachment
      -> FileObject
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
  -> WorkSequenceItem

SearchIndexItem
  -> DocumentVersion
  -> FieldNote
  -> Report
  -> WorkRecordVersion

WorkSequenceBoard
  -> WorkSequenceItem
      -> WorkRecord
      -> DocumentStructureItem
      -> WorkSequenceHistory
      -> WorkSequenceNotificationCandidate

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

압출, 소성, 재단, 조립 같은 공정명은 고정 모델이 아니라 현장 맥락을 설명하는 태그 후보로 본다. 고객별 용어와 실제 공정 경계가 다를 수 있으므로 태그와 작업내역으로 유연하게 연결한다.

기본 검색은 AI와 별개로 제공한다. 파일명, 문서명, 태그, 문서 구조, 작업지시 기준으로 윈도우 탐색기처럼 목록을 좁히고 바로 열람하는 경험을 우선한다.

사진 기록은 `FieldNoteAttachment`와 `FileObject`를 통해 문서 또는 작업 맥락에 연결한다. 작업일지나 종이 기록을 촬영한 사진도 현장 기록의 원천 데이터로 본다.

현장 관찰에서 확인한 입력 가능 순간과 단말기 위치는 `TerminalDevice`, `FieldNote`, `WorkRecord` 설계의 전제 조건이다. 단말기가 적재적소에 있다고 가정하지 않고, 실제 위치와 작업자 동선을 기준으로 사용성을 판단한다.

## 4.2 MES/ERP와의 관계

MES/ERP는 FlowNote의 대체 대상이 아니라 연동 대상이다.

- MES/ERP: 작업지시, 생산실적, 설비, 품목, 공정 같은 정형 데이터의 원천
- FlowNote: 문서, 버전, 고객 정의 문서 구조, 현장 코멘트, 작업 문제점, 관리자 보고서, AI 검색/조언 데이터의 연결 계층
- 연동 어댑터: 현장별 MES/ERP API, DB, 파일 연동 차이를 흡수하는 계층

현재 단계의 작업지시는 FlowNote 내부에서 관리자가 입력한 `manual` 데이터로 본다. MES/ERP 연동이 추가되면 외부 원본 ID를 고객 정의 문서 구조에 매핑하고 자동 수신으로 확장한다.

실증 현장에서 기존 MES 작업지시 또는 생산순서 정보가 이미 운영 중이면 작업순서판과 연결할 참조 데이터로 검토한다. 다만 근태, 전체 회원, ERP 양방향 동기화, 설비 감시는 FlowNote의 기본 책임으로 보지 않는다.

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
  -> role: 현재 MVP 권한 판단 기준
  -> UserRole / Role: 서버 스키마에는 있으나 현재 API 권한 판단의 주 경로는 아님
  -> DocumentPermission
```

현장 사용자는 문서 열람과 코멘트 등록 중심으로 사용한다. 관리자급 권한이 없는 사용자 다운로드 차단은 클라이언트 앱 단계에서 구현한다.

문서 뷰어 자동 닫힘은 클라이언트 앱 단계에서 구현한다. 이는 클라이언트가 켜져 있어도 사용자가 자리를 비운 상황에서 문서가 계속 노출되는 현실 보안 문제를 줄이기 위한 정책이다.

## 7. 앱 프론트엔드와 로컬 기능

Windows WPF 클라이언트는 앱 UI를 제공하고 Python FastAPI 서버와 통신한다.

```text
Client App UI
  -> REST API
  -> Python FastAPI Server
  -> SQLite / Local Storage Folder

Client App UI
  -> Local Action
  -> Native App Function
  -> Local Function
```

앱 로컬 기능은 서버가 직접 처리하기 어려운 단말기 기능만 제공한다.

- 파일 감시
- 로컬 파일 선택
- OS 알림
- 외부 뷰어 호출
- 단말기 정보 조회

로컬 기능은 문서 파일 자동 동기화 수단이 아니다.

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

## 9. 작업내역과 후속 AI 활용

작업내역은 작업지시 문서와 현장 실행 결과를 연결한다.

- `WorkRecord`: 작업 단위
- `WorkRecordVersion`: 작업내역 개정 단위
- `WorkRecordDocument`: 작업과 관련 문서 연결

작업순서판은 작업내역 또는 문서 구조 항목을 현장에서 처리할 순서로 배치한다.

- `WorkSequenceBoard`: 라인, 공정, 현장 구역별 작업순서판
- `WorkSequenceItem`: 표시 순서, 상태, 담당 작업반 또는 조장 정보
- `WorkSequenceHistory`: 순서 변경과 상태 변경 이력

작업순서판은 MES의 작업지시 원본을 대체하지 않는다. MES가 순서를 판단하지 못하거나 현장 판단이 필요한 경우 사무실, 관리자, 반장, 조장이 조정한 실행 순서를 현장 TV 화면으로 공유한다.

AI 검색과 조언은 원본 데이터를 대체하지 않는다. `SearchIndexItem`은 검색용 참조 데이터이고, `AiAdviceLog`는 AI 요청과 결과의 기록이다.

AI 답변은 가능한 경우 근거 문서, 문서 버전, 현장 코멘트, 작업내역을 함께 제공한다.

AI 기능은 문서와 현장지식 데이터를 활용하는 계층이다. 초기 구조에서는 문서 열람, 작업순서, 짧은 현장 기록을 안정적으로 남기는 것을 우선하고, 자연어 검색, 관련 문서 탐색, 작업 전 주의 사항, 과거 문제점 기반 조언은 데이터가 쌓인 뒤 활용성을 높이는 단계로 둔다. 자동 의사결정이나 신규 작업 자동 설계는 충분한 운영 데이터가 쌓인 뒤 검토할 장기 과제이다.

## 10. 사내 서버형 배포

FlowNote는 사내 서버형 단일 사이트 구성을 기본으로 한다.

```text
Server PC
  -> Python FastAPI Server
  -> SQLite
  -> Local Storage Folder
  -> Search Index
  -> Installed Native Client Apps
```

서버 PC에는 DB 파일, storage 폴더, 인증 설정, 운영 설정을 함께 둔다.

초기 기준은 서버 PC 1대와 클라이언트 설치파일 배포이다. PostgreSQL, NAS, 외부 접근, 클라우드 배포는 현장 테스트 이후 필요가 확인되면 확장한다.
