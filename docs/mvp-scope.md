# FlowNote MVP 범위

이 문서는 2026-08-04 현재 코드 기준이다. 구현되지 않은 기능은 “현재 제외 범위”, “후속 계층 착수 기준”, “후속 MVP 후보”에만 둔다.

## 현재 MVP 구현

현재 코드 기준으로 MVP에 포함되어 실제 구현된 범위는 다음과 같다.

- Windows WPF 로그인과 탐색기형 문서 화면
- 로컬 SQLite 기반 문서/폴더/사용자/이력 저장
- FastAPI 서버 로그인과 Bearer token 인증
- 문서 등록, 버전 추가, 상태 변경, 최신 version·revision·file hash 검토 요청, 지정 검토자의 승인·반려, 승인 ID 기반 공개·취소와 append-only 승인 이력
- 문서 태그
- 문서 미리보기, 열람 시작/수동 종료 로그, 다운로드 차단
- WPF 허용 role의 공개 버전 controlled copy 1회성 저장과 SHA-256 검증
- FieldComment 원천 불변 기록과 첨부, 단계형 검토·담당/기한·일괄 처리·감사·품질 작업함, 개별 검토 revision·mutation receipt와 첨부 부모/파일 hash 검증. 서버 권위 검토 대시보드와 WPF 화면은 미검토·상충·안전/품질 위험·보고서 미연결·담당자 없음, 담당 역할과 다음 조치를 제공한다.
- 알림과 활동 이력
- WPF 로컬 계정 추가/수정/역할 변경/비밀번호 변경
- FastAPI 서버 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기 API와 WPF 운영 화면
- 서버 임시 비밀번호 계정의 첫 로그인 비밀번호 변경 강제, 기존 세션 전체 폐기와 재로그인 흐름
- 작업순서 보드, 항목, 순서 변경, 상태 변경, 이력, 알림 후보, 관리자·TV 화면. FastAPI `board_revision`·mutation receipt를 권위 원천으로 쓰고, WPF 로컬 row는 초안·읽기 캐시로만 보존하며 오프라인 확정 변경을 차단
- 보고서 초안 생성 보조, 검토중·확정·보관 상태 전이, 확정 문서 저장, report revision·내용/source 집합 hash·mutation receipt와 source 재검증
- 관리자 파일 감시 후보와 버전 확정
- AI 자동 조언 전 단계의 `ai_search_candidates` 근거 후보 재생성, 목록, 품질 점검 API와 WPF 운영 점검 화면
- 고객·현장·선택적 라인·DB fingerprint scope별 ground-truth 첫 승인과 서로 다른 사용자의 2차 승인, WPF 사례·원천 구성, 고정 원천 snapshot/provenance, 실제 현장/스모크 준비도 분리, 불변 dataset version의 작성·검토·독립 2단계 승인, dataset 결합 회귀 평가 API와 48건 비민감 스모크 검증 도구
- FastAPI `/api/v1/ai/queries` 질의 생성·조회와 기본 비활성, role, 목적, 외부 전송 승인, 프롬프트, 원천 권한·민감정보·최소 payload provider adapter, 근거 snapshot·인용·규칙 기반 의미 일치·호출 후 재검증과 감사 모델. 네트워크 adapter는 명시적 test scope 전용
- FastAPI `system-admin` 전용 외부 AI 운영 API와 WPF `AI 운영` 화면: 전송 승인 생성·철회, 불변 프롬프트 수명주기, 고객·현장별 민감정보 정책 작성·분리 검토·승인·활성·대체·철회·폐기, 전역/현장 kill switch와 한도·보존 정책, 정제 감사 조회/CSV 내보내기, 만료 보존 일괄·단일 즉시 실행과 legal hold 설정·해제. 민감정보 정책과 hold 관련 고위험 조작은 이중 확인, 최신 상태 태그, 멱등 키와 서버 read-back을 사용하며 활성 hold는 주기·일괄·단일 만료에서 제외된다.
- FastAPI 공통 채널, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음, 인수인계 수신 확인 API
- Windows 채널함, 채널 관리, 인수인계 확인 현황 화면
- Android 현장 단말 최소 앱: 승인 단말 로그인, 공개 문서 목록·상세, PDF/PNG/JPEG/WebP/UTF-8 TXT 앱 내부 보안 열람, FieldComment, 사진 첨부 outbox, 신호등식 기록, 전경 채널 알림 polling/읽음, 업무 채널·수신자·원천을 고르는 인수인계 작성, 받은 인수인계 확인·보류와 같은 원천의 후속 FieldComment
- Android 보안 본문 열람용 승인 단말·사용자·세션·현재 공개 버전 바인딩 1회 grant, 크기·SHA-256 검증, 내부 캐시 자동 정리와 화면 캡처 차단
- FastAPI 승인 단말 등록·조회·정보/상태 변경·교체 API와 Windows WPF 승인 단말 관리 화면
- WPF 로컬 저장 후 문서 최초 등록, 문서 버전, 문서 상태, 문서 태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 서버 저장 큐와 서버 ID 매핑. 현재 UI의 문서 공개는 서버 승인 작업함이 직접 처리하며 새 공개 큐를 만들지 않는다. 누적 구 공개 큐와 처리기는 보존한다.
- 같은 소스와 버전에서 framework-dependent와 self-contained WPF MSI를 함께 만드는 패키징 스크립트, .NET Desktop Runtime 설치 차단 안내와 FastAPI 작업 스케줄러 등록·검증/관리 스크립트

Android 보안 뷰어의 승인 실단말 검증, 운영 배포용 서명/MDM/인증서, 현장별 단말 등록·비활성화 운영 절차, foreground service의 Doze·강제 중지/MDM 복구 실기와 장갑·한 손·거치 조건의 UX 실측은 아직 완료 범위가 아니다. 초기 알림 전달은 WPF 창 활성 polling과 Android 로그인 세션 foreground service의 사내망 HTTPS polling으로 구현되어 있다.

## MVP 판단 기준

MVP의 성공 기준은 AI가 답변하는 것이 아니라 현장 문서와 현장 기록이 지속적으로 쌓이는 것이다. 현장 사용자가 문서를 열람하고, 짧은 FieldComment와 사진/파일을 남기고, 관리자가 이를 보고서나 문서 이력으로 정리할 수 있어야 한다.

기능 MVP와 운영 배포 완료는 구분한다. 제한 파일럿에 투입하려면 자동 테스트 외에도 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)의 설치·HTTPS·단말·백업 복구·역할별 업무·중단/rollback 게이트를 통과해야 한다. 데이터 손실, 권한 우회와 미승인 파일 유출 허용치는 0건이다.

## 현재 제외 범위

- 운영 provider client를 통한 실제 외부 AI 검색/요약, 작업 조언과 자동 의사결정
- MES/ERP 자동 수신 어댑터
- 현장별 설치·코드 서명 실기 검증과 운영 승인
- 클라우드 배포
- 일반 브라우저 사용자 화면
- 개인 메신저 수집
- 사내 메신저 전체 대체
- GPS 추적
- 근태 관리
- 개인 휴대폰 기본 배포
- CAD 원본 직접 뷰어와 HWP 고급 미리보기
- Android Office/HWP/CAD 본문 렌더링

Windows와 Android의 업무 채널 알림, 인수인계 작성·확인·보류, FieldComment/작업순서 이벤트 알림은 제외 범위가 아니다. 현재 코드는 서버 API, 기본 클라이언트 화면, WPF 창 활성 15초 polling, Android 로그인 세션 foreground service 15초 polling·단절/재부팅 cursor 복구와 읽음/수신 확인까지 구현되어 있다. Android 신규 인수인계와 받은 인수인계의 확인·보류·후속 FieldComment는 암호화 outbox에서 안정된 멱등키로 재전송한다. 후속 FieldComment 저장 뒤 채널 알림만 실패하면 서버 comment ID를 보존하고 알림만 다시 보낸다. Android는 사용자별 cursor와 처리한 `message_id` 원장을 보존하고 WPF는 서버 scope·사용자별 cursor와 처리한 `message_id`를 로컬 SQLite에 보존한다. Android 강제 중지 뒤 MDM kiosk 재실행과 현장별 단말 운영 정책은 후속 실기·고도화 대상이다.

## 후속 계층 착수 기준

provider별 운영 client를 통한 실제 외부 AI 검색/작업 조언과 MES/ERP 자동 수신 어댑터는 현재 MVP 완료 범위가 아니다. 외부 AI는 질의·감사 모델, 호출 전후 원천 권한 재검사, 민감정보 필터, 최소 발췌·최대 원천 수 제한, 근거 snapshot, 인용·의미 일치 검증뿐 아니라 `system-admin` 전용 전송 승인·프롬프트·운영 정책·감사·보존 API와 WPF 운영 UI까지 구현했다. fake/recording adapter와 제한형 generic 네트워크 adapter가 있으나 네트워크는 명시적 test scope에서만 생성된다. 다음 조건은 운영 연동 착수 여부를 판단하기 위한 기준이며, 조건을 만족하기 전에는 문서 등록, FieldComment, 작업순서, 보고서 근거 축적을 우선한다.

### AI 검색/작업 조언

외부 AI 호출 기반 검색/작업 조언은 최소한 다음 데이터가 한 현장 또는 한 라인 기준으로 쌓인 뒤 검토한다.

테스트 데이터의 총 건수는 AI 준비 완료 판정이 아니다. 아래 수량은 연결·권한·최신성·태그·사람 승인 품질을 함께 만족할 때만 의미가 있으며, 랜덤 증식한 row는 ground-truth나 익명 현장 표본으로 계산하지 않는다.

| 기준 | 최소 조건 |
| --- | --- |
| 공개 문서 | 현장에서 실제 열람하는 `PUBLISHED` 문서 100건 이상, 또는 핵심 공정/설비별 공개 문서가 각각 10건 이상 |
| FieldComment | 문서나 작업내역에 연결된 FieldComment 300건 이상, 그중 관리자 검토 상태가 `ANALYZED`, `REVIEWED`, `SELECTED` 중 하나인 항목 100건 이상 |
| 보고서 | FieldComment, 문서, 작업순서, 작업내역 중 2종 이상을 근거로 연결한 보고서 30건 이상 |
| 작업순서 이력 | 상태 변경, 보류 사유, 순서 변경을 포함한 작업순서 변경 이력 200건 이상 |
| 태그 품질 | 설비, 품목, 공정, 오류 유형 중 최소 2개 축이 주요 문서와 FieldComment에 반복적으로 연결됨 |
| 검증 가능성 | AI 답변 근거로 연결할 문서 버전, FieldComment, 보고서 source를 화면에서 역추적할 수 있음 |

익명 현장 표본은 개인정보·고객 식별자·원본 파일 경로를 제거하고, 안전·품질·설비 이상·작업 보류·재작업·인수인계 범주별 정상·제외·상충 사례를 포함해야 한다. 관리자와 현장 책임자가 기대 포함/제외 근거, 적용 라인과 시점, 공개 버전, 채널 권한을 확인해 승인한 `ground-truth`만 품질 평가 표본으로 사용한다. 최소 2인이 승인하지 않았거나 원천 hash와 source/version ID를 재검증할 수 없는 표본은 수량 기준에서 제외한다.

정량 ground-truth 착수 하한은 고객 승인을 받은 `ANONYMOUS_FIELD`에서 안전, 품질, 설비 이상, 작업 보류, 재작업, 인수인계, 최신 공개 문서, 상충 기록 8범주와 `NORMAL`, `EXCLUSION`, `CONFLICT` 3유형의 각 조합당 2건, 총 48건이다. 이는 위 공개 문서·FieldComment·보고서·작업순서 데이터 하한을 대체하지 않고 추가로 적용한다. 같은 snapshot 전체 평가에서 candidate ID/content hash와 순위 안정성, top-k 포함·인용 존재·의미 일치·상충 표시 100%, 제외 노출·권한 누출·존재하지 않는 인용 0건을 모두 만족해야 한다. 이어 각 범주·유형 칸에서 1건씩 고정한 24건 표본을 두 사람이 독립 검토하고 불일치는 제3 합의 전까지 대기로 둔다. 합성/시험과 `PILOT`은 이 48건에 더하지 않는다. 기술·보안·법무·고객 provider 심사가 모두 승인되지 않으면 데이터 기준을 통과해도 운영 provider 착수는 `대기`다.

AI 계층의 첫 착수 범위는 “근거가 있는 검색과 요약”까지로 제한한다. 자동 의사결정, 작업 지시 자동 변경, 현장 조치 승인 자동화는 별도 보안/책임 기준이 정해지기 전까지 포함하지 않는다.

현재 구현 착수 범위는 `ai_search_candidates` read model의 재생성·목록·품질 API, WPF 운영 점검 화면, `/api/v1/ai/queries` 생성·조회와 원천 권한·민감정보·최소 payload·응답 검증 게이트다. 검색 후보는 `PUBLISHED` 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source로 제한하고 원문 ID와 version ID를 유지한다. 질의 시점과 응답 직후에는 원천 상태, 작성자 role, 연결 채널 멤버십, 승인 source type과 활성 민감정보 정책의 ID·content hash·revision snapshot을 다시 검사한다. 정책 원문은 불변 버전으로 관리하며 작성자·검토자·승인자를 분리한다. provider별 운영 연동은 아직 없다. FieldComment 관리자 검토 상태가 `ANALYZED`, `REVIEWED`, `SELECTED`로 충분히 쌓이기 전에는 답변 자동화보다 관리자 검토/분석/선정 운영 흐름을 먼저 보강한다.

### MES/ERP 어댑터

MES/ERP 어댑터는 외부 시스템을 FlowNote로 대체하기 위한 기능이 아니다. 초기 작업지시는 관리자가 직접 입력하고, 후속 어댑터는 그 수동 입력 데이터와 외부 작업지시를 연결하는 방식으로 검토한다.

MES/ERP 어댑터 착수 전에는 다음이 확인되어야 한다.

- 고객 현장의 MES/ERP가 제공하는 작업지시 식별자, 품목, 공정, 설비, 라인, 예정일, 수량, 작업자 또는 작업조 필드가 문서화되어 있다.
- FlowNote의 수동 작업지시 `work_order_no`와 외부 작업지시 번호가 1:1 또는 추적 가능한 1:N 관계로 매핑될 수 있다.
- 외부 수신 실패 시에도 WPF 작업순서, FieldComment, 보고서 작성이 수동 입력 기준으로 계속 동작한다.
- 외부 시스템 데이터는 읽기 수신을 우선하고, MES/ERP로 상태를 되돌려 쓰는 양방향 연동은 별도 후속 범위로 둔다.

## 후속 MVP 후보

- 고객 유사 네트워크에서 실제 배포 리허설과 제한 현장 파일럿을 수행하고 단일 `run_id` 증거로 승인
- 서버-WPF 동기화 정책 고도화
- Android 운영 배포 서명, MDM/인증서, 현장별 단말 등록/비활성화 절차 검증
- Windows 채널 수신함, 채널 관리, 인수인계 확인 현황 화면의 운영 UX 고도화
- 라인/설비/공정/작업조/인수인계 기준 공통 채널의 Android foreground service Doze·재부팅·강제 중지/MDM 복구 검증
- Android 인수인계 작성과 후속 FieldComment 연결의 장갑·한 손·거치 조건 실측
- 구현된 관리자 세션·계정 운영 UI의 실제 현장 권한 정책과 계정 발급 절차 검증
