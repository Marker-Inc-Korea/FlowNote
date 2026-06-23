# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 도메인 관계, 데이터 모델, API, 설계 결정을 관리한다.

## 읽는 순서

1. [FlowNote 소개서](./00-introduction/flow-note-introduction.md)
2. [제품 개요](./product-overview.md)
3. [상관관계 정리](./system-map.md)
4. [아키텍처](./architecture.md)
5. [데이터 모델](./data-model.md)
6. [API 초안](./api.md)
7. [보안 정책](./security.md)
8. [배포 기준](./deployment.md)
9. [MVP 범위](./mvp-scope.md)
10. [구현 로드맵](./implementation-roadmap.md)
11. [결정 기록](./decisions)

## 핵심 관계 요약

상세 관계는 [상관관계 정리](./system-map.md)를 기준으로 한다.

```text
Document
  -> DocumentVersion
  -> FileObject

DocumentStructure
  -> DocumentStructureItem
  -> DocumentStructureItemDocument
  -> Document / DocumentVersion

TerminalDevice
  -> viewer: 현장 사용자 문서 열람
  -> admin_support: 관리자 파일 변경 감지와 업로드 보조

Client App
  -> Windows WPF
  -> Local App Function: 로컬 제어와 파일 감시

Backend
  -> Python FastAPI Server
  -> SQLite first
  -> Local server storage folder

Deployment
  -> Server PC
  -> SQLite metadata DB
  -> Local storage folder
  -> Client installer

FieldNote
  -> Document / DocumentVersion
  -> DocumentStructureItem
  -> FieldNoteAttachment / FileObject
  -> OperatorProfile / UserAccount
  -> CommentTemplate
  -> Report

WorkRecord
  -> WorkRecordVersion
  -> WorkRecordParticipant
  -> WorkInstruction Document
  -> WorkSequenceBoard / WorkSequenceItem
  -> AI Advice

SearchIndexItem
  -> DocumentVersion / FieldNote / Report / WorkRecordVersion

ExternalSystem
  -> IntegrationMapping
  -> MES/ERP 정형 데이터와 FlowNote 엔티티 연결
```

## 결정 기록

- [0001. 초기 제품 범위와 도메인 분리](./decisions/0001-initial-product-scope.md)
- [0002. 생산공장 문서 버전 관리와 단말기 알림](./decisions/0002-factory-document-versioning-and-terminal-notification.md)
- [0003. 문서 연결형 현장 코멘트와 정형 문구](./decisions/0003-document-linked-field-comments.md)
- [0004. AI 검색과 작업 조언](./decisions/0004-ai-search-and-work-advice.md)
- [0005. 문서 형식과 단말기 파일 감시 역할 분리](./decisions/0005-document-formats-and-terminal-file-watch.md)
- [0008. 회원 인증과 클라이언트 단계 보안 정책](./decisions/0008-auth-viewer-timeout-download-policy.md)
- [0010. 고객 정의 문서 구조와 외부 작업 구조 연결](./decisions/0010-document-tree-bom-work-structure.md)
- [0011. 문서관리와 현장지식관리의 균형](./decisions/0011-document-and-field-knowledge-balance.md)
- [0012. 운영 클라이언트 접근과 단계적 현장 입력](./decisions/0012-production-client-access-and-staged-field-input.md)
- [0013. MES/ERP 보완 연동 전략](./decisions/0013-mes-erp-complementary-integration.md)
- [0014. 관리자 입력 기반 작업지시 우선](./decisions/0014-manual-work-order-first.md)
- [0015. 태그, 문서 상태, 클라이언트 보안 범위](./decisions/0015-tags-status-and-client-security-scope.md)
- [0016. 현장 코멘트 분석, 보고서화, 작업자 추적](./decisions/0016-field-note-analysis-report-traceability.md)
- [0017. 고객 데이터 주권 기반 배포](./decisions/0017-customer-data-sovereignty-deployment.md)
- [0018. 현장 체감 우선 기능: 검색, 사진 기록, 작업순서판](./decisions/0018-field-first-search-sequence-and-photo-records.md)
- [0020. 사내 서버형 FastAPI와 Windows WPF 클라이언트 전환](./decisions/0020-internal-server-fastapi-native-client.md)
- [0022. Windows 단일 클라이언트와 Python 백엔드 고정](./decisions/0022-windows-only-client-python-backend.md)

## 작성 원칙

- 문서 관리, 현장 단말기, 현장 코멘트, 작업내역, AI 기능의 경계를 명확히 유지한다.
- FlowNote가 단순 문서관리 프로그램이나 순수 지식관리 시스템으로 치우치지 않도록 문서와 현장지식의 연결 관계를 유지한다.
- 도메인 간 관계가 바뀌면 `system-map.md`를 먼저 갱신한다.
- 중복 설명은 각 문서의 책임에 맞게 한 곳에만 상세히 둔다.
- 구현 스택보다 도메인 구조와 API 경계를 우선 정리한다.
