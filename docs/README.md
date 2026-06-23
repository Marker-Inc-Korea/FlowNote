# FlowNote 문서

이 폴더는 FlowNote의 제품 방향, 도메인 관계, 데이터 모델, API, 설계 결정을 관리한다.

현재 코드 기준으로 실제 구현된 범위는 Windows WPF 로컬 SQLite 프로토타입과 FastAPI 헬스체크 골격이다. 각 문서의 서버 API, 보고서, AI, MES/ERP, 배포 운영 항목은 제품 목표 또는 초안일 수 있으므로 현재 구현 완료 기능과 구분해서 읽는다.

## 읽는 순서

1. [제품 개요](./product-overview.md)
2. [상관관계 정리](./system-map.md)
3. [데이터 모델](./data-model.md)
4. [API 초안](./api.md)
5. [MVP 범위](./mvp-scope.md)
6. [구현 로드맵](./implementation-roadmap.md)
7. [보안 정책](./security.md)
8. [배포 기준](./deployment.md)
9. [설계 결정 요약](./decisions.md)

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

설계 결정은 [설계 결정 요약](./decisions.md)에 통합한다.

## 작성 원칙

- 문서 관리, 현장 단말기, 현장 코멘트, 작업내역, AI 기능의 경계를 명확히 유지한다.
- FlowNote가 단순 문서관리 프로그램이나 순수 지식관리 시스템으로 치우치지 않도록 문서와 현장지식의 연결 관계를 유지한다.
- 현장 의견과 현장 관찰 기준은 [제품 개요](./product-overview.md)와 [설계 결정 요약](./decisions.md)에 맞춘다.
- 도메인 간 관계가 바뀌면 `system-map.md`를 먼저 갱신한다.
- 중복 설명은 각 문서의 책임에 맞게 한 곳에만 상세히 둔다.
- 구현 스택보다 도메인 구조와 API 경계를 우선 정리한다.
