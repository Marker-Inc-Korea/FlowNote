# FlowNote

FlowNote는 생산공장 현장의 문서와 현장 지식을 함께 관리하는 사내 서버형 문서/현장지식 관리 시스템이다. 문서 파일, 문서 메타데이터, 버전, 변경 사유, 현장 코멘트, 작업순서, 접근 로그를 함께 축적해 이후 AI 검색과 작업 조언의 근거 데이터로 사용할 수 있게 하는 것이 제품 방향이다.

현재 코드는 Windows WPF 로컬 클라이언트와 Python FastAPI 서버가 함께 개발되어 있다. WPF 앱은 로컬 SQLite를 우선 저장소로 사용하고, `FLOWNOTE_API_BASE_URL`이 설정되어 있으면 FastAPI 서버와 인증, 문서, FieldComment, 첨부, 접근 로그, 작업순서 일부를 동기화한다. 서버가 없거나 동기화가 실패해도 로컬 저장은 유지된다.

## 현재 구현

- Windows WPF 로그인 화면과 탐색기형 메인 화면
- 공통 로컬 SQLite 기본 경로 `data/local/flownote.local.sqlite`
- 로컬 기본 계정과 그룹 시드, 기본 비밀번호 `1234`
- 사용자 관리 화면: 사용자 추가, 이름/역할/비밀번호 변경
- 기본 폴더: 문서, 인수인계, 작업지시서, 사진
- 문서 하위 분류 폴더: 도면, 작업표준, 점검표, 품질검사, 안전수칙, 보전작업, 일반문서
- 파일 업로드와 Drag & Drop 등록, 로컬 `Files/Uploads/yyyy-MM-dd/` 복사
- 문서 상태 `WORKING`, `IN_REVIEW`, `PUBLISHED`, `ARCHIVED`
- 최신 버전과 공개 버전 분리, 명시적 공개 처리
- 문서 태그 저장과 목록 표시
- TXT, PDF, XLSX, 이미지 미리보기
- 문서 열람 시작/종료, 자동 닫힘, 다운로드 차단 로그
- FieldComment 원천 기록과 첨부 파일 저장
- 알림, 전체 이력, 보고서 초안 문서 저장, 작업순서 보드/항목/TV 화면
- 관리자급 파일 감시 후보 등록과 버전 확정
- FastAPI 인증, 문서, FieldComment, 첨부, 태그, 접근 로그, 작업순서, 보고서 API

아직 구현되지 않은 범위는 운영 설치 자동화, 고도화된 서버-WPF 양방향 동기화 정책, AI 검색/조언, MES/ERP 어댑터, 일반 브라우저 사용자 화면, 클라우드 운영이다.

## 저장소 구조

```text
FlowNote/
  apps/
    windows/       Windows WPF 클라이언트
  services/
    api/           Python FastAPI 서버
  docs/            제품, 시스템, 데이터, API, 보안, 배포 문서
  data/local/      WPF 공통 로컬 SQLite와 로컬 산출물
```

## 개발 기준

- Backend: Python FastAPI
- Client: Windows WPF 네이티브 앱
- Database: SQLite 우선, 필요 시 PostgreSQL 확장
- Server file storage: 서버 PC 로컬 `storage/`
- Client local storage: 저장소 루트 `data/local/`
- 배포 방향: 서버 PC 1대와 Windows 설치형 클라이언트

## 문서

문서 시작점은 [docs/README.md](./docs/README.md)이다. 현재 코드 기준의 핵심 문서는 [docs/product-overview.md](./docs/product-overview.md), [docs/system-map.md](./docs/system-map.md), [docs/data-model.md](./docs/data-model.md), [docs/api.md](./docs/api.md)를 기준으로 본다.
