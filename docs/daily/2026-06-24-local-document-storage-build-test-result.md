# 2026-06-24 로컬 문서 저장 빌드 테스트 기록

이 문서는 로컬 문서 저장 관련 작업 기록을 현재 코드 기준으로 정리한 것이다.

## 현재 저장 구조

- 서버 API는 업로드 파일을 서버 로컬 `storage/` 폴더에 저장한다.
- Windows 앱은 앱 관리 저장소와 공통 SQLite를 사용한다.
- Windows 기본 SQLite는 `data/local/flownote.local.sqlite`이다.
- `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`로 로컬 DB 위치를 지정할 수 있다.

## 기록되는 정보

- 문서 제목, 설명, 상태, 작성자, 폴더, 태그
- 문서 버전, 변경 사유, 파일명, 저장 경로, 파일 크기, 해시
- 문서 열람 이력
- FieldComment와 첨부
- 작업순서, 알림, 보고서, 활동 이력

## 검증 산출물 정책

테스트 파일, 렌더링 결과, 스모크 테스트 출력, SQLite DB, 로그는 보존한다. 새 산출물 경로가 생기면 Git 제외 규칙을 먼저 확인한다.
