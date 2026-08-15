# Windows App

`apps/windows/`는 FlowNote Windows WPF 클라이언트 영역이다. 현장/관리자 PC에 설치해 사용하는 네이티브 앱을 기준으로 한다.

현재 프로젝트는 WPF UI `net10.0-windows`, Core와 스모크 테스트 `net10.0`을 대상으로 한다. 현재 기능 목록은 `FlowNote.Windows.App`, `FlowNote.Windows.Core`, `FlowNote.Windows.SmokeTests` 코드에 실제 연결된 범위만 포함한다.

이 문서는 2026-08-15 현재 코드 기준이다. 운영 설치나 현장 검증이 남은 내용은 현재 구현과 분리해 후속 제품 방향에만 둔다.

현재 화면의 역할별 사용 순서는 [Windows 사용 매뉴얼](../../docs/manuals/windows-user-guide.md), 설치·연결 장애는 [공통 장애 대응](../../docs/manuals/troubleshooting.md)을 따른다.

## 현재 완료된 비AI 구현

아래 목록은 현재 업무 기능으로 완료 판정한 Windows 범위다. AI 후보·정답셋·운영 안전장치 화면은 이 목록에서 제외하고 다음 절에 연구·시험 기반으로 구분한다.

- 로그인 화면과 메인 탐색기 화면. 로그인 역할에 맞춘 첫 업무 3개와 기존 업무 창 바로 가기, 파일명·제목·태그·사용자·최근 코멘트 검색, 문서 상태 필터, 권한 문의 안내, 동기화 미완료 건수·로컬 보존·다음 조치 표시를 포함한다.
- 로컬 SQLite 초기화와 기본 계정/그룹/폴더 시드
- 사용자 관리: 운영 HTTPS 서버 로그인 후 서버 계정 생성, 이름/역할/상태 변경, 임시 비밀번호 재설정, 활성 세션 조회/폐기. 로컬 계정 모델과 화면은 기존 데이터·단위 테스트 호환용이며 표준 로그인에서는 사용하지 않음
- 승인 단말 관리: 서버 단말 목록·상세·마지막 접속 조회, 등록, 정보/상태 변경, 교체
- 시작 실패 안내: 로컬 저장소, WebView2 Runtime, 서버 주소·인증서·연결 오류를 `실패 내용`, `누락 항목`, `보존된 로컬 상태`, `처리 담당자`, `가능한 다음 행동`으로 나누어 표시한다. 읽기 전용 스크롤 안내, 키보드 접근 키와 크기 조절 창을 제공하며 로컬 계정으로 자동 전환하지 않는다.
- 폴더 트리와 문서 목록. 기본 폴더는 `문서`, `인수인계`, `작업순서`, `사진`이다.
- 새 폴더 생성
- 샘플 문서 등록, 파일 업로드, Drag & Drop 등록
- 문서 상태 변경과 서버 승인 작업함. 최신 version·revision·file hash를 고정한 검토 요청, 지정 검토자의 승인·반려, 승인 버전 공개·취소와 append-only 상태 이력을 표시
- 문서 태그 저장과 표시
- TXT의 인코딩·긴 행, PDF의 암호·손상·큰 페이지, XLSX의 다중 시트·수식·병합 범위, 이미지의 회전·투명도·고해상도를 안전 한도 안에서 처리하는 앱 내부 미리보기와 구조화된 한글 실패 안내
- 문서 열람 시작/종료 로그
- viewer 수동 닫힘과 다운로드 차단 로그
- 허용 role의 서버 1회성 controlled copy 저장과 SHA-256 검증, 비허용 role의 기존 차단 안내·이력
- FieldComment 작성과 첨부 저장, 원천 불변 검증, 단계형 관리자 검토, 담당자·기한 지정, 다중 선택 일괄 변경, 감사·품질 작업함. 검토 화면은 서버 권위 대시보드에서 미검토·상충·안전/품질 위험·보고서 미연결·담당자 없음·기한 초과 수와 담당자·다음 조치를 표시한다. 담당 역할·신호등·채널·문서 버전·검토 기한으로 목록을 좁힐 수 있으며, 원천 연결 상세 창에서 본문·첨부·관찰 문서·작업순서·감사·보고서 근거를 함께 확인한다. AI 준비도는 후속 참고 영역으로 분리해 조회 실패가 작업함 운영을 막지 않으며, 합성·시험 자료는 실제 현장 준비도에 더하지 않는다.
- 알림, 로컬 전체 이력
- 관리자 `변경 이력`: 서버 공통 event envelope에서 문서·FieldComment·보고서·작업순서와 동기화 변경을 통합 조회한다. 기간, 사용자·역할, 장비, 업무 대상, version/revision, 결과, 위험도, run/correlation ID로 필터링하고 합계를 표시한다. 충돌·실패·미연결 mutation·필수 감사 필드 누락·권한 거부 뒤 변경을 먼저 보여주며 영향, 현재 상태, 담당자, 다음 행동과 실제 조치 화면 이동을 제공한다. 목록·상세는 같은 서버 권한 정책을 사용한다.
- 관리자 파일 감시 후보 처리
- 작업순서 관리자 화면과 TV 화면. 서버 snapshot·`board_revision`을 권위 원천으로 사용하고 mutation key와 `baseBoardRevision`으로 직접 변경하며, 미연결/조회 실패 시 로컬 row는 읽기 캐시·초안으로만 표시하고 모든 확정 변경을 차단
- FieldComment 작업함·상세에서 보고서 근거 전달, 공개 문서·작업순서 이력·기존 보고서 source 유형별 확인, 서버 초안→검토중→확정→보관 상태 전이와 원천 역추적. 확정 상세의 `정정본 만들기`는 위험 설명과 필수 정정 사유를 받고 같은 계열의 독립 초안을 만든다. 정정 화면은 기존 내용과 source snapshot을 읽기 기준으로 가져오며 필요하면 `현재 원천 선택`에서 전체 source를 다시 고정한다. `재검토 요청 → 정정본 확정`을 수행하고 내용 변경 시 재검토를 다시 요구한다. 목록·상세·계보는 `● 유효`, `↪ 대체됨`, `▣ 보관`, `◐ 재검토중`, `○ 초안`을 한글 상태명과 함께 표시하며 과거·현재 생성 문서를 유지한다. 원천 충돌은 실패 내용, 기존 확정본 보존, 담당 검토자, 현재 source 다시 선택 순서로 안내한다. 일반 최종 저장은 로컬 보고서/source를 먼저 보존하며 재시도 큐는 source 집합 hash를 고정하고 서버 응답의 report revision·내용 hash·source 집합 hash를 다시 계산해 일치할 때만 로컬 문서에 보존
- 채널함: 서버 내 채널, 채널 메시지/알림, 인수인계 조회, 읽음/수신 확인, 원천 링크 복사, 후속 FieldComment 생성. 같은 인수인계·작성자·내용은 안정된 요청 식별값을 재사용하고 채널 알림 실패를 부분 성공으로 구분해 원천 코멘트 중복을 막는다.
- 채널 관리: 서버 채널 생성, 멤버 추가/제외
- 인수인계 확인 현황: 운영 단위·채널별 목록, 미확인·후속 조치 인원 집계, 수신자별 receipt 상태 변경, 후속 FieldComment 생성과 원천/수신 확인 보존·다음 행동 안내
- FastAPI 서버 인증과 승인 단말/문서 검토·공개 승인/controlled copy/FieldComment/첨부/접근 로그/보고서/작업순서/채널·인수인계 API 클라이언트
- 서버 동기화 큐: 문서 최초 등록, 문서 버전, 문서 상태, 문서 태그, FieldComment, FieldComment 검토, FieldComment 첨부, 문서 접근 로그, 보고서 서버 저장. 태그 delta 병합과 revision별 기준 집합, 상태·태그 mutation receipt와 read-back, FieldComment 검토 base revision·mutation key, 첨부 부모·파일 SHA-256, 보고서 source 집합 hash, 문서 버전·첨부 idempotency key 전달을 포함한다. 현재 UI의 문서 공개는 이 큐에 새 항목을 만들지 않고 서버 승인 작업함에서 승인 ID와 함께 직접 처리한다. 기존 `document_publish/publish_document_version` 큐는 누적 이력과 호환 처리기로만 보존하며 승인 강제 기본값에서는 승인 ID가 없어 자동 공개하지 못한다. 이력 창은 큐 깊이·최장 대기·최근 처리량·실패 분포·row별 운영 상태와 구조화된 충돌의 서버 값·로컬 요청·자동 병합 가능·사용자 선택 항목을 표시한다.
- 서버 복구 경계 보호: sync manifest의 instance/epoch/API contract와 알림 cursor를 URL별 binding에 저장하고, URL·instance·epoch 변경, cursor 역행 또는 `partial_restore`·`old_database_new_files`·`missing_file`·`wrong_server_epoch` 복구 장애 신호 시 자동 전송과 polling 중지. 복구 장애 manifest의 pilot run·backup set·복구 승인·담당자와 수렴 상태도 binding에 보존
- 이력 창 `서버 재결합`: 연결 상태와 안전 수렴 상태, 차단 원인, 보존된 원천, 승인 전 금지 행동, 담당자·증거 연결, 다음 단계를 분리해 표시하고 전체 큐 inventory의 `CONFIRMED`/`ABSENT`/`DIVERGED` 판정과 `REBOUND`/`REQUEUE`/`CONFLICT` 제안 검토. 명시적 장애 run은 관리자 승인 뒤에도 `POST_APPROVAL_RESTART_REQUIRED`로 전송·polling 차단을 유지하고, 서버의 `FLOWNOTE_RESTORE_*` 표지 제거와 재시작 뒤 `업무 재개 확인`에서 정상 manifest를 읽어야 cursor 재추적·재전송·polling 재개
- 보존 동기화 실패 전환 CLI: FAILED 큐를 읽기 전용 dry-run으로 분류하고, plan hash와 row별 운영자 승인을 받은 구 `create`/FieldNote 항목만 현재 action의 별도 큐로 무손실 전환
- 동기화 backlog 읽기 전용 감사: 큐 운영 상태·담당자·처리 기한·자동 재시도 한도·수동 종결 기준과 DB 전후 SHA-256, 무결성, 중복, 고아 mapping/source를 JSON으로 보존

## AI 연구·시험 화면 — 완료 목록 제외

WPF에는 `/api/v1/ai/queries`를 호출하는 실제 외부 AI 질의 실행 화면이나 운영 provider client가 없다. 아래 화면은 후속 연구를 위한 후보 품질·ground-truth·안전장치 운영 도구이며 실제 AI 사용자 기능의 완료 판정에 포함하지 않는다.

AI 검색 근거 후보는 현재 FastAPI 서버 API, WPF 서버 클라이언트, `AI 근거 후보 운영 점검` 화면에 구현되어 있다. 이 화면은 `/api/v1/ai-search/candidates/rebuild`, `/api/v1/ai-search/quality`, `/api/v1/ai-search/candidates`, `/api/v1/ai-search/readiness`를 호출해 외부 AI 호출 전 데이터 품질, 원천 추적 가능성, 서버 scope별 실제 현장/스모크 준비도를 확인한다. `AI 정답셋`의 `사례·원천 구성` 창은 후보를 포함 근거로 선택하고 실제 source ID·선택적 version ID·제외 사유·설명을 제외 근거로 입력한다. 첫 등록 사례는 비활성으로 남고 다른 사용자가 2차 승인해야 활성화된다. 승인 사례는 dataset version으로 묶어 작성자·검토자·두 승인자를 분리하고, 승인 snapshot에 결합한 평가 run을 실행·비교한다. 합성/시험 회귀와 실제 현장 준비도는 별도 계열로 유지한다.

실제 익명 현장 dataset의 24칸 독립 표본 검토와 불일치 제3 합의는 FastAPI, 서버 DB와 WPF에 구현되어 있다. `AI 정답셋`에서 승인된 `FIELD_READINESS` dataset과 그 dataset을 통과한 평가 run을 함께 선택하면 `24칸 독립 검토`가 활성화된다. 화면은 서버가 고정한 표본 계획과 기대·실제·제외 근거 trace를 보여주며, 첫 판정은 두 번째 제출 전까지 숨긴다. 두 판정이 다르면 앞선 두 사람과 다른 제3 사용자에게 불일치 case만 열어 합의를 받는다.

같은 창의 `운영 준비도` 탭은 고객 승인을 받은 실제 현장 사례와 합성·시험 사례를 분리해 표시한다. 원천별 현재/필수 수, 부족한 범주·유형, dataset 작성자·검토자·두 승인자의 분리, 최신 평가 run, 24칸 검토 상태를 한곳에서 확인할 수 있다. 준비도나 외부 호출 설정이 미달이면 서버가 반환한 한글 사유와 담당자, 다음 조치를 보여주며 자격증명, endpoint, 로컬 경로는 표시하지 않는다.

`AI 운영` 화면은 `/api/v1/ai-operations`로 승인, 프롬프트, 민감정보 정책, 전역/현장 운영 정책과 질의 감사 메타데이터를 조회·변경한다. 민감정보 정책 탭은 현재 고객·현장 범위만 표시하고 정책 원문 대신 상태·content hash·항목 수·담당자·다음 행동을 보여준다. 질의 감사는 차단 구분과 실제 외부 전송 여부를 따로 표시한다. provider 자격증명·질의 원문·응답 원문은 표시하지 않으며 provider 자격증명은 설정 여부만 표시한다. 감사 CSV는 현장 정책에서 내보내기를 허용한 경우에만 저장할 수 있다. 서버는 설정된 주기로 만료 보존을 자동 처리하며, 화면의 실행 버튼은 다음 주기를 기다리지 않고 같은 일괄 처리를 즉시 요청한다. 감사·보존 탭은 선택 질의의 고객/현장, hold 상태, 두 보존 예정 시각, 전체 hold/감사 이력을 read-back한다. 민감정보 정책 상태 변경, 단일 만료와 hold 설정·해제는 사유·근거 번호, 이중 확인, 최신 상태 태그와 안정 operation key를 사용하며 응답 유실은 같은 요청으로 한 번 재시도한다. 성공 뒤 서버 상세를 다시 읽기 전에는 완료로 표시하지 않는다.

`작업내역` 화면의 서버 동기화 큐는 완료, 보존 구 형식, 선행 조건 대기, 수동 조치 필요, 재시도 가능을 별도 운영 상태로 표시한다. 요약에는 `SYNCED`가 아닌 큐 깊이, 최장 대기 시간, 최근 1시간 처리량과 실패 분포가 나온다. 인증 만료나 서버 연결 실패·시간 초과는 현재 재시도 묶음을 중단하며, 개별 항목의 검증·파일 오류는 해당 항목을 실패로 남기고 다음 독립 항목을 계속 처리한다. 모든 경우 로컬 원천과 큐는 유지한다.

## 후속 제품 방향

- 채널/인수인계 화면의 운영 UX 고도화와 현장별 권한 세분화
- 인수인계 등록 작성 화면과 템플릿 보강
- 채널 메시지와 인수인계를 문서, FieldComment, 작업순서, 작업내역, 보고서 근거로 더 쉽게 연결하는 운영 흐름
- 백그라운드 알림 정책과 현장별 polling 운영 UX 검증

초기 알림 전달 방식은 사내망 REST API 전경 polling으로 구현·확정되어 있다. WPF는 기본 15초 간격으로 먼저 sync manifest를 확인한 뒤 `/api/v1/notifications?afterId={cursor}`를 조회하고 연결 실패 시 최대 120초까지 backoff한다. 서버 scope와 사용자 ID별 cursor 및 처리한 `message_id`를 로컬 SQLite에 보존하고, 응답 처리가 끝난 뒤 같은 트랜잭션에서만 cursor를 전진시킨다. 서버 URL·instance·epoch 변경 또는 cursor 역행은 자동 초기화하지 않고 polling을 중지하며, 복구 경계에서는 단독 `알림 위치 초기화`도 차단한다. 일반 재결합은 관리자가 모든 판정을 사유와 함께 승인한 뒤 cursor를 0으로 재추적한다. 명시적 복구 장애 run은 승인 뒤에도 서버 장애 표지가 사라진 정상 manifest를 다시 읽을 때까지 polling을 재개하지 않는다. 기존 처리 `message_id`는 두 경우 모두 재조회 멱등 근거로 보존한다. 상세 정책은 [WPF 사용자별 알림 cursor 보존 정책](./docs/notification-cursor.md)을 따른다. 외부 push나 WebSocket은 초기 구현의 대안이 아니라 현장 네트워크 정책과 백그라운드 알림 요구가 확인될 때 검토하는 확장 선택지다.

이 기능은 개인 메신저나 사내 메신저 전체 대체가 아니라, 현장 기록과 관리자 검토 흐름을 이어주는 업무 채널 기능이다.

## 작업순서 후보 전달

작업순서 관리 창의 `알림 후보 전달`은 별도 전달 창을 연다. 이 창은 현재 후보 목록과 사용자가 실제 `OWNER` 또는 `MANAGER`인 활성 채널만 표시하고, 전송 전에 채널 운영 단위·수신자 수와 사용자 ID·작업 항목·change ID·관련 공개 문서를 한 화면에서 보여준다. 권한 없는 채널 이름은 표시하지 않으며 필요한 채널 역할과 관리자 문의 방법을 안내한다.

관리자는 현장 범위 문구 템플릿을 선택하거나 긴 안내 문구를 직접 입력하고 전달 사유를 남긴 뒤 `채널로 전달` 또는 `인수인계 만들기`를 실행한다. 응답 유실은 같은 요청 객체와 멱등키로 한 번 재확인하며, 후보·채널·전달 의도로 만든 안정 키는 앱 재시작 뒤에도 같은 실패 수신자 재시도를 이어 준다. 결과 영역은 성공·실패 수신자, message·handover·change ID, 기존 원천과 성공 receipt 보존, 담당자와 실패 수신자 재전송 방법을 텍스트로 표시한다. 완료 후 `채널함으로 이동`과 `인수인계 현황으로 이동`으로 읽음·확인·보류와 후속 FieldComment를 이어서 확인한다.

전달 창은 크기 조절과 세로 스크롤을 사용하고 주요 목록·입력·결과·버튼에 화면 읽기 이름을 둔다. Windows 실기에서는 키보드 초점 순서, 200% 확대, 고대비, 긴 템플릿 문구의 전체 접근과 버튼 겹침을 확인한다.

## 프로젝트 구조

```text
apps/windows/
  docs/                         Windows 앱 구현 문서
  src/FlowNote.Windows.App/     WPF UI
  src/FlowNote.Windows.Core/    로컬 DB, 서비스, 정책, 서버 API 클라이언트
  src/FlowNote.Windows.Core.Tests/  서버 알림 cursor 등 Core 단위 테스트
  src/FlowNote.Windows.SmokeTests/  콘솔 스모크 테스트
  src/FlowNote.Windows.SyncConvergenceTests/  서버 권위 mutation과 재실행 멱등 수렴 검증
  src/FlowNote.Windows.SyncMigrationTool/  보존 FAILED 큐 진단·승인 전환 CLI
```

## Windows 설치 matrix

| 패키지/조건 | .NET Desktop Runtime 10 | WebView2 | 필수 수명주기 |
| --- | --- | --- | --- |
| framework-dependent MSI | 설치 조건과 미설치 차단 조건을 각각 실기 | 설치/미설치 각각 실기 | 신규 설치, 이전 승인본→후보 업그레이드, 제거, 재설치, 이전 승인본 rollback |
| self-contained MSI | 설치/미설치와 무관하게 실행 확인 | 설치/미설치 각각 실기 | 신규 설치, 이전 승인본→후보 업그레이드, 제거, 재설치, 이전 승인본 rollback |

두 MSI 모두 승인 SHA-256, Authenticode signer SHA-256, chain, RFC 3161 timestamp를 먼저 통과해야 한다. self-contained MSI도 WebView2 Evergreen Runtime을 포함하지 않는다. 운영 기본은 self-contained이고, 중앙 관리로 Desktop Runtime 설치와 업데이트를 보장하는 PC만 framework-dependent를 사용한다.

전용 Windows snapshot에서는 다음 순서로 같은 `run_id`를 사용한다.

```powershell
.\scripts\package-wpf-msi.ps1
.\scripts\verify-windows-server-packages.ps1 -RunId <run_id> <승인 패키지 인자>
.\scripts\verify-wpf-msi-install.ps1 `
  -RunId <run_id> `
  -EvidenceRoot D:\FlowNotePilotEvidence `
  -ArtifactRoot D:\FlowNoteApprovedPackages
py -3 scripts\manage-pilot-run.py verify `
  --run-id <run_id> `
  --evidence-root D:\FlowNotePilotEvidence
```

`verify-wpf-msi-install.ps1 -RunId`는 실행 중인 WPF나 기존 FlowNote 설치를 발견하면 임의 제거하지 않고 중단한다. 깨끗한 snapshot과 보존 확인용 `C:\FlowNote\LocalData\flownote.local.sqlite`, `Files\`가 필요하다. 두 MSI의 10개 수명주기 단계마다 데이터 fingerprint가 같아야 하며 마지막에는 이전 승인 WPF가 설치된 rollback 상태가 남는다. 실패 로그와 로컬 시험 데이터는 삭제하지 않고 새 `run_id`에서 다시 수행한다.

## 네트워크·시작 실패 운영

| 실패 | 사용자에게 구분할 항목 | 담당자와 다음 조치 |
| --- | --- | --- |
| .NET Desktop Runtime 없음 | 누락 runtime, 기존 로컬 데이터 보존 | Windows 설치 담당자가 승인 runtime을 설치하거나 self-contained MSI로 전환 |
| WebView2 없음 | PDF 뷰어 runtime, 원본·DB·열람 이력 보존 | Windows 설치 담당자가 승인 WebView2를 설치 |
| 서명/hash 불일치 | 승인 패키지 부재, 서버/WPF 데이터 미변경 | 패키지 담당자와 보안 승인자가 승인 대장·전달 경로 대조, 설치 중단 |
| 서버 주소·방화벽·timeout | 현재 HTTPS 경로, 로컬 DB·Files·큐 보존 | 서버·네트워크 담당자가 승인 URL, DNS, 포트, 서버 자동 시작 확인 |
| 인증서·PC 시간·폐기 확인 | 신뢰 chain/SAN/시간/폐기 상태, HTTP·로컬 로그인 우회 없음 | 인증서 운영 담당자가 시간 원천, 갱신 인증서, CRL/OCSP 접근과 신뢰 배포 확인 |
| 서버 자동 시작 실패 | 작업 스케줄러/SYSTEM/부팅 트리거, 서버 DB·storage 보존 | 서버 운영 담당자가 작업 최근 결과와 서버 로그를 확인하고 승인 작업을 재등록 |

로그인·시작 실패 화면은 실패 내용을 작은 상태 문구로 줄이지 않는다. 로컬 문서·FieldComment·보고서 원천과 `Files`, 동기화 큐, 알림 cursor·처리한 `message_id`의 보존 상태, 처리 담당자와 가능한 다음 행동을 한 화면에서 구분한다. 안내문은 읽기 전용 스크롤 영역에서 전체 선택·복사할 수 있고, `Alt+R`로 다시 시도하고 `Alt+X`로 종료할 수 있다. 창은 크기 조절이 가능하며 버튼은 줄바꿈 배치되어 긴 오류와 200% 이상 표시 배율에서도 고정 폭 영역에 잘리거나 서로 겹치지 않도록 했다. 로컬 DB 시작 실패 때도 DB 교체·초기화·재설치를 먼저 제안하지 않고 DB와 `Files`의 동시 보존과 관리자 승인을 먼저 안내한다.

HTTPS 클라이언트는 인증서 폐기 목록 확인을 사용한다. 인증서 갱신·폐기나 서버 주소 변경 중에는 기존 세션으로 잘못 성공하거나 로컬 계정으로 자동 우회하면 안 된다. 동기화 큐와 알림 polling은 실패 상태에서 멈추고 로컬 원천·큐·cursor를 유지한다. 주소/instance/epoch 경계는 관리자 재결합 승인 뒤에만 재개하며 복구 후 중복 전송은 0건이어야 한다. 이 결과는 `windows-network-fail-closed.csv`의 세 행과 화면·WPF 로그·서버 감사 증거로 확인한다.

서버 재부팅 후와 최종 승인 rollback 후에는 로그인, 문서 열람, FieldComment, 동기화, 알림, 감사 로그를 각각 확인해 12개 업무 행을 남긴다. schema version 13의 시작 실패 UX 표는 처음 화면을 본 참여자 여부, 실패·보존 원천/큐/cursor·담당자·다음 행동 식별, 키보드 전용 완료, 긴 문구 전체 접근, 200% 이상 배율과 버튼 겹침 0건을 별도로 요구한다. 2026-08-01 현재 Core 테스트와 Windows 타기팅 빌드에서 복구 문구와 로컬 로그인 우회 차단은 통과했지만, 실제 Windows PC의 두 MSI 수명주기, 승인 서명 패키지, 시험 사용자 접근성 관찰, 고객 유사망 인증서·CRL/OCSP·방화벽·주소·시간 주입 결과는 이 저장소에 없다. 따라서 `windows_server_rehearsal` 운영 판정은 여전히 `대기`이며 framework-dependent 또는 self-contained 어느 쪽도 현장 PASS로 추정하지 않는다.

## 로컬 데이터

기본 DB 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다.

- `FLOWNOTE_LOCAL_DATA_DIR`: 로컬 데이터 폴더 override
- `FLOWNOTE_LOCAL_DATABASE_PATH`: SQLite 파일 경로 override
- `FLOWNOTE_API_BASE_URL`: FastAPI 서버 URL override. 미설정 시 승인 운영 주소
  공개 저장소 기본값인 `https://flownote.example`을 사용한다. 실제 연결에는 `FLOWNOTE_API_BASE_URL`로 승인된 HTTPS 주소를 지정한다.

업로드 파일과 FieldComment 첨부는 로컬 데이터 폴더의 `Files/` 아래 보존한다.

## 권한 요약

- 문서 등록/작업순서 편집: 관리자 계열, 반장, 조장
- 문서 검토 요청: 문서 등록 권한과 같은 관리자/반장/조장 계열
- 문서 승인·반려·공개·승인 취소: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`
- 보고서 작성: 관리자/문서관리/부서관리 계열
- 파일 감시: 관리자 계열만
- 사용자 관리: `admin`, `system-admin`
- 승인 단말 관리: 서버 로그인 `admin`, `system-admin`
- 외부 AI 운영 관리: 서버 로그인 `system-admin`
- 채널 관리/인수인계 확인 현황: 문서 등록 권한과 같은 관리자/반장/조장 계열
- 다운로드 허용: 관리자 계열 중 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`
- FieldComment 작성: 모든 기본 현장 role
- 변경 이력·운영 준비도: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`

## 운영 준비도

`현장 운영 > 운영 준비도`는 서버의 통합 감사 snapshot과 현재 권위 상태를 읽는 별도 창이다. 영역별 `정상/주의/차단/집계 없음`, 오래된 조치, blocker code, 담당 역할·담당자와 다음 행동을 확인할 수 있다. 새 event가 생긴 기존 cursor에서는 기준 시각과 새로고침 필요를 표시하며, 필터를 바꾸면 첫 페이지부터 다시 조회한다.

`기존 업무 화면 열기`는 문서 승인, 로컬 이력/재결합, FieldComment 검토, 보고서, 작업판, 채널함, 인수인계 확인, 승인 단말 관리 창만 연다. 서버가 반환한 `actionTargetId`로 문서·코멘트·보고서·작업판·채널·인수인계·단말·재결합 항목을 선택하고 FieldComment blocker는 기존 작업함 필터로 변환한다. 대시보드가 직접 mutation key를 만들거나 업무 row를 수정하지 않는다. 단말·재결합 수치는 관리자/시스템 관리자에게만 보이며 다른 허용 역할에는 필요한 역할과 문의 안내만 표시한다. AI 카드는 실제 익명 현장 준비도만 보여주고 합성·테스트 자료를 합산하지 않는다.

`RolePermissionPolicy` 정합성 검증 기준:

- `CanRegisterDocuments`: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`
- `CanWriteFieldComments`: 모든 기본 role
- `CanWriteReports`, `CanDownloadDocuments`: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`
- `CanReadAccessLogs`, `CanManageUsers`: `admin`, `system-admin`

표준 실행은 `FLOWNOTE_API_BASE_URL`에 설정한 승인 HTTPS 주소를 항상 사용한다. 서버가 401 또는 403을 반환하거나 인증서·주소·방화벽·시간 초과로 연결에 실패해도 HTTP나 로컬 계정으로 우회하지 않는다. 로그인 화면은 인증서와 PC 시간, 현재 서버 주소, 방화벽을 순서대로 확인하도록 안내한다.
서버 로그인 성공 시에는 같은 로그인 ID의 로컬 role과 다르더라도 서버 응답 role이 화면 버튼과 정책 결과의 기준이다.
임시 비밀번호 서버 로그인은 메인 화면보다 비밀번호 변경 창을 먼저 표시하며, 변경 성공 후 새 비밀번호 재로그인을 요구한다. 서버 계정 화면의 401은 재로그인, 403은 권한 부족으로 안내하고 작업 버튼을 비활성화한다. 서버 연결이 끊겨도 열린 서버 계정 화면을 로컬 계정 화면으로 자동 전환하지 않는다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

서버 연동 스모크는 승인된 운영 HTTPS 서버만 사용한다. `FLOWNOTE_API_BASE_URL`에는 운영 주소를, `FLOWNOTE_SMOKE_ADMIN_USERNAME`과 `FLOWNOTE_SMOKE_ADMIN_PASSWORD`에는 실행 시 발급한 전용 관리자 자격 증명을 주입한다. 주소나 자격 증명이 없으면 로컬 FastAPI로 우회하지 않는다. `system-admin` 전용 AI 보존 블록은 별도의 `FLOWNOTE_SMOKE_SYSTEM_ADMIN_USERNAME`과 `FLOWNOTE_SMOKE_SYSTEM_ADMIN_PASSWORD`가 있을 때만 실행한다. 모든 비밀값은 실행 환경에만 두고 파일이나 저장소에 기록하지 않는다.

표준 통합 실행은 저장소 루트의 `scripts/verify-preserved-tests.ps1`을 사용한다. 스크립트는 새 `FLOWNOTE_SMOKE_RUN_ID`와 로컬 클라이언트 증거 폴더를 주입하지만 FastAPI 프로세스나 서버용 SQLite·storage를 만들지 않는다. 서버 연동 단계에 들어가기 전 운영 HTTPS health와 전용 계정을 확인하고 `운영 서버 테스트로 이관`을 출력한다. 구 FAILED 큐 dry-run·승인 재실행 멱등성, 서버 viewer 비밀번호 변경·Windows/승인 Android 세션·비활성화 차단, AI ground-truth 평가와 provider 차단, 선택적 AI 보존 검증, cursor 재시작 복구, SQLite 무결성·매핑/idempotency 중복을 같은 실행 ID로 검증한다.

WPF smoke는 시작·종료 시 주요 로컬 테이블 건수를 읽고 오늘 사진/인수인계 문서 2건과 기존 과거 문서의 신규 버전을 SQL로 다시 확인한다. 결과는 `wpf-smoke-database-evidence.json`에 문서 ID, 이전·신규 버전, 무결성 값과 함께 보존하며 표준 스크립트의 단계별 로그·WPF Core TRX·최종 요약과 한 run ID를 공유한다.

별도 PC 복구 리허설에서는 `scripts/verify-pilot-restore.py`의 `wpf` 대상을 사용해 앱이 종료된 WPF DB와 `Files`의 복구 전후 증거를 수집·비교한다. 도구는 수집 중 DB·파일 불변과 checkpoint되지 않은 WAL 부재도 검사하며 같은 실행 경로의 기존 증거를 덮어쓰지 않는다. server와 wpf 비교를 마친 뒤 `compare-set`으로 두 대상의 `backup-set-id`·`restore-approval-id`가 서로도 같은지 확인한다. 이 도구의 통과는 실제 별도 PC 복구 절차 자체를 대신하지 않는다.

서버 전용 `controlled_copy_grants`가 WPF 공통 DB에 잘못 생성되어 `document_versions.version_id` FK mismatch가 나는 경우 DB나 원천 파일을 삭제하지 않는다. 앱과 서버를 멈춘 뒤 `python scripts/repair-wpf-controlled-copy-schema.py --database data/local/flownote.local.sqlite --run-id <새-run-id>`를 저장소 루트에서 실행한다. 도구는 `data/local/wpf-schema-repair/<run-id>/`에 원본 SQLite backup, 전후 row 수·DDL·FK·hash와 요약을 먼저 보존하고 grant row를 보존 테이블로 옮긴 뒤 무결성을 재검사한다. 실제 공통 DB 복구 run `WPF-P0-20260720-0840`은 문서 버전 3,384행 hash를 유지하며 `quick_check=ok`, FK 위반 0건으로 끝났다. FastAPI도 WPF 로컬 schema를 서버 DB URL로 받으면 테이블 생성 전에 거부한다.

2026-08-15 현재 소스의 수집 대상과 표준 스크립트 guard는 FastAPI 212건·WPF Core 120건·Android 39건으로 일치한다. 보조 실행에서 FastAPI 누적 DB·새 DB 212/212, WPF Core 120/120과 WPF 빌드가 통과했고, 변경되지 않은 Android의 최신 기준은 39/39와 debug 빌드·lint 통과다. 최신 운영 HTTPS 스모크는 2026-08-09에 통과했다. Windows에서 수집 목록·JUnit·원시 TRX와 운영 HTTPS 스모크를 같은 clean 소스 커밋으로 새 run ID에서 2회 완료해 각각 `partial_run=false`, `verification-summary.json=PASSED`가 나오기 전까지 Windows 통합 기준선 재확립은 `대기`다.

스모크 테스트는 공통 SQLite에 기록을 누적한다. 테스트 DB와 파일 산출물은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.

파일 유형별 미리보기 샘플과 실패 안내 기준은 [문서 미리보기 안정화 기준](./docs/document-preview-stability.md)을 따른다.
보존 FAILED 큐의 dry-run, 승인 전환과 무손실 검증 기준은 [보존 동기화 실패 무손실 전환](./docs/legacy-sync-migration.md)을 따른다.
