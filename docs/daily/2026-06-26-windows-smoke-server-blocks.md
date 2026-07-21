# 2026-06-26 Windows 스모크와 서버 블록 기록

이 문서는 Windows 스모크 테스트와 서버 연계 확인 기록을 현재 코드 기준으로 정리한 것이다.

## 스모크 테스트 기준

- Windows 앱과 Windows 스모크 테스트는 저장소 루트의 공통 SQLite `data/local/flownote.local.sqlite`를 사용한다.
- 환경 변수 `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 지정되면 해당 위치를 우선한다.
- 스모크 테스트는 임시 SQLite를 새로 만들지 않고 공통 DB에 기록을 누적한다.
- 테스트는 오늘 날짜 기준 문서 등록을 포함해야 하며, 사진과 인수인계 문서의 날짜 폴더 생성, 문서 등록, 목록 조회를 확인한다.
- 과거 날짜 테스트는 기존 날짜 폴더와 기존 문서를 대상으로 버전 증가를 검증한다. 과거 날짜 폴더나 문서를 새로 만들지 않는다.

## 서버 연계 확인 범위

- 서버 API는 인증, 승인 단말, 문서와 controlled copy, FieldComment 원천·검토·감사·품질, 접근 로그, 작업순서, 채널/인수인계, 보고서, AI 검색 근거 후보·회귀 평가와 외부 AI 질의 안전장치, sync manifest·관리자 승인형 reconciliation을 제공한다.
- Windows 앱은 로컬 SQLite를 우선 사용하며 서버 동기화 큐와 서버 ID 매핑 테이블을 가진다.
- 서버 연계 테스트에서 생성된 로그, DB, 입력 파일, 출력 파일은 보존한다.
- 2026-07-21 최신 코드는 FastAPI 143건을 수집하고, 표준 통합 스크립트의 수집/JUnit guard는 과거 기준 131건이다. macOS `baseline-131` 보조 run은 당시 FastAPI 131건만 통과했고 WPF/Android는 실행하지 못했다. guard를 143건으로 맞춘 뒤 WPF Core 테스트·앱 빌드·스모크, Android 단위 테스트·debug build와 Git 산출물 사후 점검을 같은 실행 ID로 묶은 Windows 무생략 `PASSED` run을 새로 확보해야 한다.

## 주의

스모크 테스트 산출물과 고객 문서 성격의 파일은 Git 커밋 대상이 아니다. 이미 Git에 잡힌 테스트 산출물은 파일을 삭제하지 않고 추적만 해제한다.
