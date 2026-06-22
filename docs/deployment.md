# FlowNote 배포 기준

## 1. 배포 원칙

FlowNote는 초기 개발과 현장 테스트를 쉽게 하기 위해 사내 서버형 배포를 기본으로 한다.

생산현장의 기술문서, 도면, 생산규격, 보고서는 외부 클라우드 사용을 꺼리는 경우가 많다. 따라서 1차 배포는 서버 PC 1대에 Python FastAPI 서버, SQLite DB, 로컬 `storage/` 폴더를 두고, 현장/관리자 PC에는 Windows WPF 클라이언트 설치파일을 배포하는 구조로 잡는다.

FlowNote는 기존 MES/ERP를 대체하지 않는다. 현장에 MES나 ERP가 있으면 후속 단계에서 REST API 또는 현장별 어댑터로 연동한다.

## 2. 서버와 클라이언트

```text
Server PC
  -> Python FastAPI Server
  -> SQLite DB file
  -> Local storage/ folder
  -> Search index
  -> Integration adapter

Client PCs
  -> Windows WPF client installer
  -> REST API communication
```

독립 Web UI는 서버 배포 구성에 포함하지 않는다. 고객 생산공장 운영 환경에서 일반 사용자가 브라우저로 직접 접속하는 구조를 기본값으로 두지 않는다.

## 3. 기본 구성요소

- Python FastAPI server
- SQLite metadata DB
- Local server storage folder
- Windows WPF native client
- REST API
- Notification outbox
- Optional search index
- Optional MES/ERP integration adapter

## 4. 확장 기준

초기에는 SQLite를 사용한다. 다음 조건이 생기면 PostgreSQL 전환을 검토한다.

- 동시 사용자와 쓰기 요청이 SQLite 운영 한계를 넘는 경우
- 여러 서버 프로세스 또는 다중 서버 구성이 필요한 경우
- 고객 IT 정책상 중앙 DBMS 운영이 필요한 경우
- 고급 백업, 복제, 권한 관리가 필요한 경우

파일 저장은 초기에는 서버 PC의 로컬 `storage/` 폴더를 사용한다. NAS 또는 오브젝트 스토리지는 후속 확장으로 둔다.

## 5. 운영 설정

- FastAPI 바인딩 주소와 포트
- SQLite DB 파일 경로
- 서버 로컬 storage 경로
- 허용 확장자와 MIME 타입
- 최대 업로드 크기
- 인증 정책
- 관리자 역할
- 클라이언트 앱 허용 버전
- 일반 브라우저 직접 접근 허용 여부
- 앱 로컬 기능 허용 액션
- AI 검색 사용 여부
- 외부 시스템 연동 사용 여부
- MES/ERP API 연결 정보
- 백업 경로와 주기

## 6. 백업 대상

- SQLite DB 파일
- 서버 로컬 storage 폴더
- 운영 설정 파일
- 검색 인덱스 재생성 설정

검색 인덱스는 원본이 아니므로 필요 시 재생성할 수 있게 설계한다.
