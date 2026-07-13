# 2026-06-24 현재 작업 요약

이 문서는 2026-06-24 기준 작업 메모를 현재 코드 기준으로 정리한 기록이다.

## 서버

- FastAPI 서버는 SQLite 기반 MVP로 동작한다.
- 인증은 사용자 로그인, Access Token, Refresh Token, 로그아웃 세션 폐기를 포함한다.
- 승인 단말 등록·조회·상태 변경·교체와 Android 로그인 승인을 관리한다.
- 문서는 등록, 목록, 상세, 버전, 상태, 공개 버전, 태그 기능을 제공한다.
- 허용 role은 현재 공개 버전을 1회성 controlled copy로 저장할 수 있고 서버와 WPF가 SHA-256을 검증한다.
- FieldComment는 문서와 분리된 현장 원천 기록으로 관리한다.
- 작업순서 보드와 항목, 변경 이력, 알림 후보를 관리한다.
- 공통 채널, 채널 메시지, 사용자별 알림 읽음, 인수인계 수신 확인을 관리한다.
- 보고서는 FieldComment와 문서 데이터를 바탕으로 초안 생성 보조와 저장 기능을 제공한다.
- AI 검색 전 단계의 근거 후보 재생성, 목록 조회, 품질 점검 API를 제공한다.
- AI ground-truth 회귀 평가와 외부 AI 질의의 기본 비활성·승인·근거 snapshot·인용 감사 골격을 제공하며 운영 provider client는 없다.

## Windows 앱

- Windows WPF 앱은 로컬 SQLite를 사용한다.
- 문서 등록, 문서 열람, FieldComment, 작업순서, 알림, 채널함, 채널 관리, 인수인계 확인 현황, 보고서, 사용자 관리 기능이 구현되어 있다.
- 서버 연결 시 AI 근거 후보 운영 점검 화면에서 후보 재생성, 품질 지표, 제외 사유, 원천 추적값을 확인할 수 있다.
- 기본 DB는 저장소 루트의 `data/local/flownote.local.sqlite`이다.
- `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 있으면 해당 위치를 우선한다.

## 현재 문서 기준

- 최신 구조는 `docs/product-overview.md`, `docs/system-map.md`, `docs/data-model.md`, `docs/api.md`를 기준으로 한다.
- 이 파일은 작업 기록이며, 현재 동작 기준을 판단할 때는 상위 문서를 우선한다.
- Android 현재 구현은 승인 단말 로그인, 공개 문서 목록·상세 메타데이터 조회, FieldComment/사진 outbox, 채널 알림과 인수인계 확인까지다. 문서 파일 본문 뷰어는 없다.
