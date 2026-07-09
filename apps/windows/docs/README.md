# Windows App Notes

이 폴더는 Windows WPF 클라이언트의 현재 구현 메모를 둔다.

## 문서

- [탐색기형 메인 화면](./explorer-shell.md)
- [로컬 SQLite 기본 구조](./local-sqlite-basics.md)
- [문서 미리보기 안정화 기준](./document-preview-stability.md)
- [서버 동기화 실패와 재시도 UX](./server-sync-ux.md)

## 현재 기준

Windows 앱은 로컬 SQLite 저장을 기본으로 하고, `FLOWNOTE_API_BASE_URL`이 설정되면 FastAPI 서버 API 호출을 시도한다. 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 서버 저장 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다. AI 근거 후보 운영 점검 화면은 서버의 `/api/v1/ai-search` API를 직접 조회하며 로컬 동기화 큐 대상은 아니다.
