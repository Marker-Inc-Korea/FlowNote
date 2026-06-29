# Windows App Notes

이 폴더는 Windows WPF 클라이언트의 구현 메모를 보관한다.

## 문서

- [탐색기형 셸 화면](./explorer-shell.md)
- [로컬 SQLite 기본 구조](./local-sqlite-basics.md)

## 현재 코드 기준 요약

Windows 앱은 현재 FlowNote의 유일한 활성 클라이언트이다. 로컬 SQLite를 기본 저장소로 사용하고, `FLOWNOTE_API_BASE_URL`이 설정된 경우 FastAPI 서버 로그인과 문서/FieldNote/첨부/접근 로그 동기화를 시도한다. 서버가 없거나 전송이 실패해도 로컬 저장은 유지하고, 실패는 `server_sync_queue`와 `activity_history`에 남긴다.
