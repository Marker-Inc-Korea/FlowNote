# 2026-06-24 현재 작업 요약

이 문서는 2026-06-24 기준 작업 메모를 현재 코드 기준으로 정리한 기록이다.

## 서버

- FastAPI 서버는 SQLite 기반 MVP로 동작한다.
- 인증은 사용자 로그인, Access Token, Refresh Token, 로그아웃 세션 폐기를 포함한다.
- 문서는 등록, 목록, 상세, 버전, 상태, 공개 버전, 태그 기능을 제공한다.
- FieldComment는 문서와 분리된 현장 원천 기록으로 관리한다.
- 작업순서 보드와 항목, 변경 이력, 알림 후보를 관리한다.
- 보고서는 FieldComment와 문서 데이터를 바탕으로 초안 생성 보조와 저장 기능을 제공한다.

## Windows 앱

- Windows WPF 앱은 로컬 SQLite를 사용한다.
- 문서 등록, 문서 열람, FieldComment, 작업순서, 알림, 보고서, 사용자 관리 기능이 구현되어 있다.
- 기본 DB는 저장소 루트의 `data/local/flownote.local.sqlite`이다.
- `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 있으면 해당 위치를 우선한다.

## 현재 문서 기준

- 최신 구조는 `docs/product-overview.md`, `docs/system-map.md`, `docs/data-model.md`, `docs/api.md`를 기준으로 한다.
- 이 파일은 작업 기록이며, 현재 동작 기준을 판단할 때는 상위 문서를 우선한다.
