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
- 작업순서 변경은 서버 `board_revision`과 mutation receipt, FieldComment 검토는 `review_revision`과 검토 receipt, 보고서 저장은 `report_revision`·내용/source 집합 hash와 보고서 receipt로 직렬화한다.
- 공통 채널, 채널 메시지, 사용자별 알림 읽음, 인수인계 수신 확인을 관리한다.
- 보고서는 FieldComment와 문서 데이터를 바탕으로 초안 생성 보조와 저장 기능을 제공한다.
- AI 검색 전 단계의 근거 후보 재생성, 목록 조회, 품질 점검 API를 제공한다.
- 독립 2인 승인 ground-truth 사례, 불변 dataset version에 결합된 회귀 평가, 외부 AI 질의의 기본 비활성·승인·근거 snapshot·응답 검증·인용 감사, `system-admin` 운영 제어와 자동·일괄·단일 만료, legal hold 설정·해제를 제공한다. generic 네트워크 adapter는 명시적 test scope에만 있고 provider별 운영 client는 없다.
- 서버 계정 생성·변경·재설정·세션 폐기와 `must_change_password` 강제 변경 흐름을 제공한다.
- 서버 instance/epoch/API contract manifest와 WPF 큐 inventory reconciliation, 관리자 승인 적용 이력을 제공한다.

## Windows 앱

- Windows WPF 앱은 로컬 SQLite를 사용한다.
- 문서 등록, 문서 열람, FieldComment 작성·단계형 검토·품질 작업함, 작업순서, 알림, 채널함, 채널 관리, 인수인계 확인 현황, 보고서, 사용자 관리 기능이 구현되어 있다.
- 서버 연결 시 AI 근거 후보 운영 점검 화면에서 후보 재생성, 품질 지표, 제외 사유, 원천 추적값을 확인하고 `AI 정답셋` 화면에서 사례·원천과 dataset version을 운영할 수 있다.
- `system-admin`은 별도 `AI 운영` 화면에서 승인·프롬프트·정책·감사, 만료 보존 일괄·단일 즉시 실행과 legal hold 설정·해제를 관리한다. 단일 고위험 조작은 이중 확인, 상태 충돌 검사와 서버 read-back을 거친다.
- 기본 DB는 저장소 루트의 `data/local/flownote.local.sqlite`이다.
- `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 있으면 해당 위치를 우선한다.
- 서버 scope·사용자별 알림 cursor와 처리 메시지를 로컬 SQLite에 보존하고 cursor 역행 시 polling을 중지한다.
- 서버 URL·instance·epoch 변경이나 cursor 역행 시 자동 동기화와 polling을 함께 중지하고, `서버 재결합` 화면에서 판정과 조치를 승인한 뒤 binding·mapping·큐를 적용한다.

## 현재 문서 기준

- 최신 구조는 `docs/product-overview.md`, `docs/system-map.md`, `docs/data-model.md`, `docs/api.md`를 기준으로 한다.
- 이 파일은 작업 기록이며, 현재 동작 기준을 판단할 때는 상위 문서를 우선한다.
- Android 현재 구현은 승인 단말 로그인, 공개 문서 목록·상세와 PDF/이미지/UTF-8 TXT 앱 내부 보안 열람, Keystore 보호 FieldComment/사진 outbox, foreground service 채널 알림과 인수인계 확인까지다.
