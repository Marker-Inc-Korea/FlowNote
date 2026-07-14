# Windows App Notes

이 폴더는 Windows WPF 클라이언트의 현재 구현 메모를 둔다.

문서 내용은 2026-07-14 현재 `FlowNote.Windows.App`, `FlowNote.Windows.Core`, 스모크·Core 테스트 코드 기준이다.

## 문서

- [탐색기형 메인 화면](./explorer-shell.md)
- [로컬 SQLite 기본 구조](./local-sqlite-basics.md)
- [문서 미리보기 안정화 기준](./document-preview-stability.md)
- [서버 동기화 실패와 재시도 UX](./server-sync-ux.md)
- [WPF 사용자별 알림 cursor 보존 정책](./notification-cursor.md)
- [보존 동기화 실패 무손실 전환](./legacy-sync-migration.md)

## 현재 기준

Windows 앱은 로컬 SQLite 저장을 기본으로 하고, `FLOWNOTE_API_BASE_URL`이 설정되면 FastAPI 서버 API 호출을 시도한다. 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 서버 저장 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다. 보존 FAILED 큐는 일반 재시도와 분리된 CLI에서 먼저 읽기 전용으로 진단하며, 승인한 항목만 기존 큐를 그대로 둔 채 현재 action의 새 큐로 전환한다. 채널함, 채널 관리, 인수인계 확인 현황, AI 근거 후보 운영 점검과 controlled copy는 서버 API를 직접 사용하며 로컬 동기화 큐 대상은 아니다.
