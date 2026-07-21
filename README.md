# FlowNote

FlowNote는 생산공장 현장의 문서와 현장 지식을 함께 관리하는 사내 서버형 문서/현장지식 관리 시스템이다. 문서 파일, 문서 메타데이터, 버전, 변경 사유, 현장 코멘트, 작업순서, 접근 로그를 함께 축적해 이후 AI 검색과 작업 조언의 근거 데이터로 사용할 수 있게 하는 것이 제품 방향이다.

이 README의 기능 목록은 2026-07-21 현재 저장소 코드 기준이다. 구현되지 않은 내용은 아래의 제외 범위와 각 문서의 후속 항목에서만 다룬다.

현재 코드는 Windows WPF 로컬 클라이언트, Android 현장 단말 최소 앱, Python FastAPI 서버가 함께 개발되어 있다. WPF 앱은 로컬 SQLite를 우선 저장소로 사용하고, `FLOWNOTE_API_BASE_URL`이 설정되어 있으면 FastAPI 서버와 인증 후 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 저장 전송을 시도한다. Android 앱은 승인 단말 `deviceId`로 서버 로그인 후 공개 문서 목록·상세, PDF/이미지/TXT 앱 내부 보안 열람, FieldComment, 사진 첨부, 신호등식 기록, 채널 알림, 인수인계 확인을 수행한다. WPF는 서버 전송 실패 시 로컬 원천과 재시도 큐를 유지하고, Android는 FieldComment와 사진 첨부 전송 실패 항목만 전용 SQLite outbox에 두되 업무 payload와 앱 내부 첨부 파일은 Keystore AES-GCM으로 보호한다.

## 현재 구현

- Windows WPF 로그인 화면과 탐색기형 메인 화면
- 공통 로컬 SQLite 기본 경로 `data/local/flownote.local.sqlite`
- 로컬 기본 계정과 그룹 시드, 기본 비밀번호 `1234`
- 사용자 관리 화면: 사용자 추가, 이름/역할/비밀번호 변경
- 서버 계정 관리 화면: 계정 생성, 이름/역할/상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기, 첫 로그인 비밀번호 변경 강제
- 기본 폴더: 문서, 인수인계, 작업순서, 사진
- 문서 하위 분류 폴더: 도면, 작업표준서, 점검표, 품질검사, 안전수칙, 보전작업, 일반문서
- 파일 업로드와 Drag & Drop 등록, 로컬 `Files/Uploads/yyyy-MM-dd/` 복사
- 문서 상태 `WORKING`, `IN_REVIEW`, `PUBLISHED`, `ARCHIVED`
- 최신 버전과 공개 버전 분리, 명시적 공개 처리
- 문서 태그 저장과 목록 표시
- TXT, PDF, XLSX, 이미지 미리보기
- 문서 열람 시작/종료, 자동 닫힘, 다운로드 차단 로그
- 허용 role의 공개 문서 버전 controlled copy: 서버 1회성 티켓, 세션 바인딩, SHA-256 검증
- FieldComment 원천 불변 기록과 첨부 파일 저장, 단계형 검토·담당/기한 지정·감사·품질 작업함. 검토 revision·mutation receipt와 첨부 부모/파일 hash 검증 포함
- 알림, 전체 이력, 보고서 초안 문서 저장과 서버 저장 시도. 보고서 revision·내용/source 집합 hash·mutation receipt와 source 변경 재검증 포함
- 작업순서 관리자/TV 화면과 서버 직접 운영: `board_revision`, mutation key, 멱등 receipt, stale revision 충돌 처리. 로컬 테이블은 읽기 캐시·초안으로만 보존
- Windows 채널함, 채널 관리, 인수인계 확인 현황 화면
- WPF 서버 scope·사용자별 알림 cursor와 처리 메시지 SQLite 보존, cursor 역행 차단과 관리자 초기화
- AI 근거 후보 운영 점검 화면: 후보 재생성, 품질 지표, 제외 사유, 원천 추적값 복사
- AI 정답셋 운영 화면: 사례·원천 구성, 독립 2인 사례 승인, 불변 dataset version 작성·검토·2단계 승인·평가 run 비교
- 시스템 관리자용 외부 AI 운영 화면: 전송 승인 생성·철회, 불변 프롬프트 검토·승인·활성화·폐기, 전역/현장 kill switch와 한도·보존 정책, 정제 감사 내보내기와 만료 보존 일괄 즉시 실행
- FastAPI AI 보존 제어: 고객·현장 scope별 질의 감사, 기본 1시간 간격 만료 처리, 단일 질의 즉시 만료, 근거 번호가 있는 legal hold 설정·해제. 활성 hold는 자동·수동·단일 만료보다 우선한다.
- FastAPI 서버 DB와 WPF 로컬 DB의 SQLite 스키마 경계 보호: 서버 초기화가 WPF 문서 테이블 구조를 감지하면 테이블 생성 전에 중단
- 관리자급 파일 감시 후보 등록과 버전 확정
- FastAPI 인증, 승인 단말, 문서, controlled copy, FieldComment, 첨부, 태그, 접근 로그, 작업순서, 채널/인수인계, 보고서, AI 검색 근거 후보·회귀 평가, 외부 AI 질의 안전장치·운영 제어 API
- Android 현장 단말 최소 앱: 승인 단말 로그인, 공개 문서 목록·상세, PDF/PNG/JPEG/WebP/UTF-8 TXT 앱 내부 보안 열람, FieldComment, 사진 첨부, 신호등식 기록, 알림/인수인계 조회와 확인, SQLite outbox 재전송
- FastAPI-WPF role 정책 정합성 검증: 문서 등록, FieldComment 작성, 보고서 작성, 접근 로그 조회, 사용자 관리, controlled copy 다운로드
- WPF 동기화 큐 대상: 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장
- 서버 복구 경계 보호와 관리자 재결합: instance/epoch/API contract manifest, URL·epoch·cursor 역행 감지, 큐 inventory 판정·승인, mapping/큐/binding 적용과 알림 cursor 재추적
- 누적 FAILED 큐의 읽기 전용 진단과 승인 기반 무손실 전환 CLI

운영 배포 보조 스크립트는 현재 저장소에 포함되어 있다. WPF MSI 패키징은 `scripts/package-wpf-msi.ps1`, FastAPI 서버 작업 스케줄러 등록과 관리는 `scripts/install-flownote-server-task.ps1`, `scripts/manage-flownote-server-task.ps1`를 기준으로 한다. `scripts/verify-pilot-restore.py`는 파일럿 복구 전후의 서버 DB+`storage`와 WPF DB+`Files` 증거를 수집하고 무결성·테이블별 row 수·파일 상대경로/크기/SHA-256을 비교한다.

아직 구현되지 않은 범위는 현장별 설치 검증과 코드 서명 검증, 현장별 런타임 패키징 확정, 서버-WPF 동기화 정책 고도화, Android 보안 본문 뷰어의 승인 실단말 검증과 운영 배포 서명/MDM/인증서 확정, 운영 provider를 통한 실제 외부 AI 검색·요약/작업 조언, MES/ERP 어댑터, 일반 브라우저 사용자 화면, 클라우드 운영이다. 현재 서버에는 외부 호출 없이 DB 원천을 사용하는 `ai_search_candidates` 후보 재생성·목록·품질 점검, 독립 승인 ground-truth 사례와 불변 dataset version 기반 오프라인 회귀 평가, `/api/v1/ai/queries`의 기본 비활성 안전장치·감사 골격, `system-admin` 전용 `/api/v1/ai-operations` 승인·프롬프트·정책·감사·보존·legal hold API가 구현되어 있다. WPF에는 근거 후보 운영 점검, `AI 정답셋`, 별도의 `AI 운영` 화면이 있으나 단일 질의 만료와 legal hold 조작은 현재 서버 API 전용이다.

## 저장소 구조

```text
FlowNote/
  apps/
    windows/       Windows WPF 클라이언트
    android/       Android 현장 단말 클라이언트
  services/
    api/           Python FastAPI 서버
  docs/            제품, 시스템, 데이터, API, 보안, 배포 문서
  data/local/      WPF 공통 로컬 SQLite와 로컬 산출물
```

## 개발 기준

- Backend: Python FastAPI
- Client: Windows WPF 네이티브 앱, Android 네이티브 앱
- Database: SQLite 우선, 필요 시 PostgreSQL 확장
- Server file storage: 서버 PC 로컬 `storage/`
- Client local storage: WPF는 저장소 루트 `data/local/`, Android는 앱 전용 SQLite outbox와 Keystore 보호 payload·암호화 첨부 저장소
- 배포 방향: 서버 PC 1대, Windows 설치형 클라이언트, 승인된 Android 현장 단말

## 문서

문서 시작점은 [docs/README.md](./docs/README.md)이다. 현재 코드 기준의 핵심 문서는 [docs/product-overview.md](./docs/product-overview.md), [docs/system-map.md](./docs/system-map.md), [docs/data-model.md](./docs/data-model.md), [docs/api.md](./docs/api.md)를 기준으로 본다.
