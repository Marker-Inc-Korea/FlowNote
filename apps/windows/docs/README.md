# Windows App Notes

이 폴더는 Windows WPF 클라이언트의 현재 구현 메모를 둔다.

## 문서

- [탐색기형 메인 화면](./explorer-shell.md)
- [로컬 SQLite 기본 구조](./local-sqlite-basics.md)
- [서버 동기화 실패와 재시도 UX](./server-sync-ux.md)

## 현재 기준

Windows 앱은 로컬 SQLite 저장을 기본으로 하고, `FLOWNOTE_API_BASE_URL`이 설정되면 FastAPI 서버 API 호출을 시도한다. 서버 호출 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다.
