# Windows App Notes

이 폴더는 Windows WPF 클라이언트의 현재 구현 메모를 둔다.

문서 내용은 2026-08-03 현재 `FlowNote.Windows.App`, `FlowNote.Windows.Core`, 스모크·Core·동기화 수렴 테스트 코드 기준이다.

## 문서

- [탐색기형 메인 화면](./explorer-shell.md)
- [로컬 SQLite 기본 구조](./local-sqlite-basics.md)
- [문서 미리보기 안정화 기준](./document-preview-stability.md)
- [서버 동기화 실패와 재시도 UX](./server-sync-ux.md)
- [WPF 사용자별 알림 cursor 보존 정책](./notification-cursor.md)
- [보존 동기화 실패 무손실 전환](./legacy-sync-migration.md)

## 현재 기준

Windows 앱은 로컬 SQLite 저장을 기본으로 하고, `FLOWNOTE_API_BASE_URL`이 설정되면 FastAPI 서버 API 호출을 시도한다. 메인 화면은 관리자·반장·조장·작업자의 첫 업무 3개를 로그인 직후 표시하고, 문서 검색·상태 필터를 폴더 이동과 목록 갱신 뒤에도 유지한다. 권한 없는 메뉴에는 필요한 역할과 현장 관리자 문의 방법을 표시하며, 동기화 미완료는 대기·실패·충돌·보류, 보존 여부와 다음 조치를 색상 없이도 알 수 있게 안내한다. WebView2 Runtime 누락과 서버 주소·인증서·연결 오류가 발생하면 누락 항목, 보존된 데이터, 담당자와 다음 조치를 구분해 보여주며 로컬 계정으로 자동 전환하지 않는다. 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, 문서 태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 서버 저장 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다. 태그는 마지막 서버 집합 대비 추가·제거 의도를 전송하며, 겹치지 않는 서버 변경만 자동 병합한다. 동기화 충돌 화면은 서버 값, 보존된 로컬 요청, 자동 병합 가능 항목과 사용자 선택 항목을 나눠 표시한다. 공개·상태·태그는 mutation receipt와 서버 read-back을 확인한 뒤에만 동기화를 끝낸다. FieldComment 검토 화면은 원천을 읽기 전용으로 유지하고 상태·담당자·기한·정리·분석·전이 사유를 별도 관리하며, 다중 선택 일괄 변경과 품질 작업함을 제공한다. 보존 FAILED 큐는 일반 재시도와 분리된 CLI에서 먼저 읽기 전용으로 진단하며, 승인한 항목만 기존 큐를 그대로 둔 채 현재 action의 새 큐로 전환한다. 작업순서 관리자·TV, 채널함, 채널 관리, 인수인계 확인 현황, AI 근거 후보 운영 점검, `AI 정답셋`, `system-admin` 전용 `AI 운영` 화면과 controlled copy는 서버 API를 직접 사용하며 로컬 동기화 큐 대상은 아니다. 작업순서는 권위 서버 snapshot을 읽지 못하면 로컬 row를 초안·읽기 캐시로만 표시하고 확정 변경을 차단한다.
