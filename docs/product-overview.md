# FlowNote 제품 개요

현재 구현 설명은 2026-07-28 코드 기준이며 장기 제품 방향이나 아직 구현하지 않은 기능은 배포 방향·제외 범위에서 명시적으로 구분한다.

## 목적

FlowNote는 생산공장 현장의 문서와 현장 경험을 함께 남기는 서버형 시스템이다. 목표는 단순 문서 보관이나 순수 지식관리 중 한쪽으로 치우치지 않고, 문서 버전, 공개 상태, 현장 코멘트, 작업순서, 보고서 근거를 같은 흐름에서 축적하는 것이다.

초기 제품은 AI 기능보다 데이터 축적과 현장 사용성을 우선한다. 현재 AI 관련 구현은 DB 원천에서 `ai_search_candidates` 근거 후보를 재생성·조회·품질 점검하는 API와 WPF 운영 점검 화면, 사례·원천 구성과 독립 승인을 거쳐 불변 dataset version을 운영·평가하는 WPF `AI 정답셋`, `/api/v1/ai/queries` 질의 생성·조회 및 제한형 provider adapter, `system-admin` 전용 `/api/v1/ai-operations` 운영 제어 API와 WPF `AI 운영` 화면까지다. 질의 라우터는 기본 비활성 플래그, 보고서 작성 role, 허용 목적, 고객·현장·provider·model 승인, 승인된 프롬프트, 근거 원천 상태·작성자 role·채널 권한, 현장별 민감정보 정책, 전역/현장 kill switch와 한도, 응답 인용 ID를 검사하고 감사 row를 남긴다. 응답은 구조·크기·중복·prompt injection과 규칙 기반 의미 일치를 검사하고 호출 후 원천·권한·승인을 다시 확인한다. 운영 API와 WPF 화면은 승인 철회, 불변 프롬프트 수명주기, 요청·동시성·timeout·비용·보존 정책, 현재 고객·현장 scope의 정제 감사, 만료 보존 일괄·단일 실행과 legal hold 설정·해제를 제공한다. 활성 hold는 자동·수동·단일 만료보다 우선하며 해제 이력도 보존한다. WPF의 단일 만료·hold 조작은 이중 확인, 최신 `stateTag`, 안정 operation key와 서버 상세 read-back으로 충돌·응답 유실·감사 중복을 방지한다. provider 경계는 필터를 통과한 최소 발췌와 안정 ID/hash만 전달한다. generic 네트워크 adapter는 명시적 test scope로 제한되어 실제 외부 AI 요약을 운영할 단계는 아니다. 후속 운영 연동도 “근거가 있는 검색과 요약”으로 제한하고 모든 사실 주장을 질의 시점 근거와 연결한다.

## 현재 구현 상태

현재 개발된 코드는 다음 범위까지 동작한다.

- Windows WPF 설치형 클라이언트
- 로컬 SQLite 기반 로그인, 사용자/그룹 시드, 사용자 관리
- 탐색기형 문서 폴더와 파일 목록
- 파일 업로드, Drag & Drop, 로컬 파일 복사
- 문서 등록, 버전 추가, 상태 변경, 공개 버전 지정
- 문서 태그 저장
- 문서 미리보기와 열람 로그
- 다운로드 차단과 Windows 뷰어 수동 닫힘
- 허용 role이 공개 버전을 서버의 60초 1회성 controlled copy 티켓으로 저장하고 SHA-256을 검증하는 제한 다운로드
- FieldComment 원천 불변 기록, 첨부, 단계형 검토, 담당자·기한, 저장된 보기, preview 뒤 항목별 부분 성공 일괄 처리, 감사·품질 작업함과 알림. 개별·일괄 검토 revision·mutation receipt와 첨부 부모/파일 hash 검증 포함
- 작업순서 보드/항목/이력/알림 후보와 TV 화면
- 보고서 초안 생성 보조, 문서 저장, 서버 보고서 저장 시도. 보고서 revision·내용/source 집합 hash·mutation receipt와 원천 재검증 포함
- FastAPI 공통 채널, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음, 인수인계 수신 확인 API
- Windows 채널함, 채널 관리, 인수인계 확인 현황 화면
- Android 현장 단말 최소 앱: 승인 단말 로그인, 공개 문서 목록·상세, PDF/PNG/JPEG/WebP/UTF-8 TXT 앱 내부 보안 열람, FieldComment, 사진 첨부 outbox, 신호등식 기록, 전경 채널 알림 polling/읽음, 인수인계 확인
- FastAPI 승인 단말 등록·조회·정보/상태 변경·교체 API와 Windows WPF 승인 단말 관리 화면
- FastAPI 서버 계정 수명주기 API와 Windows WPF 서버 계정 운영 화면: 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기
- 임시 비밀번호 로그인 후 WPF 비밀번호 변경 강제, 변경 완료 시 기존 세션 폐기와 새 비밀번호 재로그인
- AI 자동 조언 전 단계의 근거 검색 후보 재생성, 목록 조회, 품질 점검, scope별 ground-truth 첫 승인·독립 2차 승인, 실제 현장/스모크 준비도 분리, 불변 dataset version과 오프라인 회귀 평가, 실제 익명 현장 24칸 독립 표본 검토·제3 합의 서버 API, WPF 운영 점검·`AI 정답셋`·사례 원천 구성·24칸 blind 검토 화면
- FastAPI 외부 AI 질의 생성·조회, 기능 플래그·승인·목적·프롬프트, 원천 권한·민감정보·최소 payload provider adapter, 근거 snapshot·인용·의미 일치·호출 후 재검증과 감사 모델. generic 네트워크 adapter는 명시적 test scope 전용이며 provider별 운영 연동은 미구현
- FastAPI `system-admin` 전용 외부 AI 운영 API와 WPF `AI 운영` 화면: 전송 승인 생성·철회, 프롬프트 검토·승인·활성화·폐기, 전역/현장 kill switch와 한도·보존 정책, 정제 감사 조회/내보내기, 만료 보존 일괄·단일 즉시 실행과 legal hold 설정·해제. 서버는 활성 hold를 제외한 만료 처리를 설정 주기로 자동 실행하며, WPF 고위험 조작은 이중 확인과 서버 read-back을 거친다.
- 관리자 파일 감시 후보와 버전 확정
- FastAPI 인증, 승인 단말, 문서, controlled copy, FieldComment, 첨부, 접근 로그, 태그, 작업순서, 채널/인수인계, 보고서, AI 검색 근거 후보·회귀 평가와 외부 AI 안전장치 API
- framework-dependent와 self-contained WPF MSI 동시 패키징, FastAPI 작업 스케줄러 등록·검증/관리, 서버 DB+`storage`·WPF DB+`Files` 복구 전후 증거 비교 스크립트

서버와 WPF 동기화 큐는 문서 최초 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 서버 저장을 대상으로 하며, 서버 URL이 없거나 실패하면 로컬 저장을 우선한다. 재시도는 같은 문서/근거 단위로 묶은 뒤 문서 등록, 버전, 공개, 상태, FieldComment, 검토, 첨부, 접근 로그, 보고서 순서로 처리한다. 선행 서버 ID가 없으면 실제 서버 호출 없이 보류 사유를 남기고 로컬 데이터는 삭제하지 않는다.

운영 판정과 AI·보고서 근거의 권위 원천은 FastAPI 서버다. WPF 로컬 DB는 연결이 불안정한 동안 원천 파일·입력·outbox를 무손실 보존하는 로컬 우선 작업 원장이지, 서버와 별개의 최종 상태 원장이 아니다. 서버가 수락하기 전 로컬 원천은 삭제하지 않고, 서버가 수락한 뒤에는 서버 ID·revision·파일 hash·공개 포인터·보고서 source ID를 다시 읽어 매핑까지 확인한 경우에만 수렴 완료로 판정한다. timeout, 503, 응답 유실과 앱 재시작은 같은 idempotency key로 재시도하고 409는 자동 덮어쓰기하지 않는다.

작업순서의 최종 운영은 서버 직접 API로 구현되었다. WPF 관리자·TV 화면은 서버 목록과 상세 snapshot을 읽고, 관리 화면은 `board_revision`을 `baseBoardRevision`으로 보내며 사용자 동작마다 새 mutation key를 생성한다. 서버는 의미 있는 변경마다 revision을 1 증가시키고 change history 1건과 mutation receipt를 같은 트랜잭션에 저장한다. 응답 유실로 볼 수 있는 전송 오류는 같은 key로 한 번 재시도하고, stale revision은 최신 snapshot을 새로 읽은 뒤 사용자가 확인하고 다시 시도하게 한다. 로컬 작업순서 테이블은 오프라인 읽기 캐시·초안과 기존 테스트 기록으로 보존하며 `server_sync_queue`에 새 작업순서 mutation을 넣지 않는다. 서버 미연결·조회 실패로 권위 snapshot이 없으면 생성·항목 추가·순서·상태 확정을 차단한다.

FieldComment 검토·첨부와 보고서 aggregate의 도메인별 수렴 계약도 구현되었다. 개별 검토는 `review_revision`과 mutation receipt로 직렬화하고 WPF가 성공 revision을 로컬에 반영한다. 첨부는 부모 comment ID와 파일 SHA-256을 검증한다. 보고서는 고정 source version·trace ID·원천 hash를 재검증하고 `report_revision`, 내용/source 집합 hash, mutation receipt, 선택적 생성 문서/버전을 같은 서버 transaction에 저장한다. WPF는 응답 source 집합을 다시 hash해 일치할 때 revision/hash를 로컬 문서에 보존한다. 서버 instance/epoch/API contract manifest와 관리자 승인형 reconciliation도 구현되어 URL·instance·epoch 변경 또는 서버 cursor 역행 시 자동 전송과 polling을 함께 차단한다. 관리자는 큐 inventory의 `CONFIRMED`/`ABSENT`/`DIVERGED` 판정과 `REBOUND`/`REQUEUE`/`CONFLICT` 조치를 검토·승인한 뒤 mapping·큐·binding을 적용하고 cursor를 0부터 재추적한다. 공통 mutation receipt와 versioned migration은 후속 목표이며, 실제 WPF 2대 장애 주입 검증을 통과하기 전에는 전체 도메인 동시 쓰기를 운영 승인하지 않는다.

Android 현장 단말 앱과 Windows 채널/인수인계 전용 화면은 현재 최소 구현이 들어와 있다. 공통 채널과 인수인계 서버 모델/API는 FastAPI에 구현되어 있으며, Windows WPF는 관리자/현장 PC의 문서 운영, 파일 감시, 파일 미리보기, 보고서 정리, 로컬 동기화 보강, 채널 감독, 인수인계 관리, 서버 계정과 승인 단말 운영을 담당한다. Android는 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세와 PDF·이미지·UTF-8 TXT 앱 내부 보안 열람, FieldComment, 사진 기록, 신호등식 상태 기록, 인수인계 확인, 채널 알림 확인을 담당한다. 문서 본문은 현재 공개 버전만 사용자·세션·승인 단말에 묶인 단기 1회 grant로 받고, 앱 내부 난수 캐시에서 무결성을 확인한 뒤 표시한다. 외부 열기·공유는 제공하지 않으며 종료·백그라운드 전환·오류·로그아웃·다음 시작에 임시 파일을 정리한다. WPF는 창 활성 중, Android는 로그인 세션의 foreground service에서 기본 15초 간격으로 알림을 polling한다. Android는 단절·재부팅 뒤 서버 주소+사용자 scope별 마지막 cursor부터 복구하고, WPF는 서버 scope·사용자별 cursor와 처리한 `message_id`를 로컬 SQLite에 보존해 앱 재시작 후 이어간다. WPF 서버 계정 화면에서는 계정 수명주기와 활성 세션을 관리하고, 승인 단말 화면에서는 서버 단말의 목록·상세·마지막 접속 조회와 등록, 정보/상태 변경, 교체를 수행한다. Android 보안 뷰어의 승인 실단말 검증, 운영 배포 서명, MDM/인증서 적용, 현장별 단말 등록·비활성화 절차, foreground service의 Doze·강제 중지/MDM 복구 실기와 채널 운영 UX 고도화는 후속 범위다.

## 제품 원칙

- 문서는 파일 원본과 메타데이터를 분리한다.
- 업로드 문서를 무조건 최신 확정본으로 보지 않는다.
- 최신 작업 버전과 현장 공개 버전을 분리한다.
- 로컬 입력과 파일은 서버 수락·매핑 확인 전까지 보존하고, 운영 상태·공개 포인터·검토 상태·보고서 근거·작업순서의 최종 판정은 서버 revision을 따른다.
- 동일 의도는 안정된 idempotency key 하나로만 전송하고, 충돌은 자동 병합이나 최신값 추정 없이 보존·해결한다.
- FieldComment는 현장 원천 이력이며 문서 버전과 다르다.
- 현장 코멘트와 첨부는 관리자 분석과 보고서 문서로 이어질 수 있어야 한다.
- 고객의 문서 구조를 강제하지 않는다. BOM 문서 구조는 현장 표현 예시일 뿐 기본 구조가 아니다.
- MES/ERP는 대체 대상이 아니라 후속 연동 대상이다.
- 일반 브라우저 직접 접근보다 승인된 설치형 클라이언트 접근을 기본으로 한다.
- Windows와 Android는 같은 채널 데이터를 공유하되 화면 역할을 분리한다. Windows는 관리와 파일 운영·미리보기, 채널 감독, 인수인계 관리 중심이고 Android 현재 코드는 공개 문서 보안 열람과 빠른 기록, 알림 확인 중심이다.
- Windows와 Android의 알림과 인수인계는 개인 메신저가 아니라 업무 채널 개념으로 다룬다. 채널은 라인, 설비, 공정, 작업조, 인수인계, 작업내역 같은 운영 단위에 연결되고, 알림과 짧은 응답은 문서, FieldComment, 작업순서, 보고서 근거로 추적 가능해야 한다.
- 외부 AI는 기본 비활성화한다. 활성화하더라도 [보안 기준](./security.md#외부-ai-전송과-운영자-승인)에 따라 외부 전송이 승인된 최소 근거만 사용하고, 질의·호출자·근거 후보·프롬프트 버전·응답 보관 여부·오류를 감사 가능하게 남긴다.

## 배포 방향

초기 운영은 서버 PC 1대에 FastAPI 서버, SQLite DB, 로컬 `storage/` 폴더를 두고, 관리자/현장 PC에는 Windows WPF 클라이언트를 설치하는 방식이다. Android 앱은 승인된 현장용 단말을 대상으로 추가하며, 개인 휴대폰 기본 배포는 초기 기준이 아니다. 현재 저장소에는 WPF MSI 패키징, FastAPI 작업 스케줄러 등록/관리, 파일럿 복구 전후 증거 비교 스크립트가 있다. Android에는 Keystore 보호 FieldComment/사진 outbox와 15초 foreground 알림 복구가 구현되어 있다. 채널 알림의 초기 전달 방식은 외부 인터넷에 의존하지 않는 사내망 HTTPS polling으로 확정되어 있다. Android 운영 APK 서명 계약은 구현됐고 실제 조직 키, MDM, 사내 Wi-Fi/인증서와 실단말 결과는 현장 승인 게이트로 남는다. 클라우드, 외부 접근, PostgreSQL, NAS, MES/ERP 어댑터는 현장 요구가 확인된 뒤 확장한다.

운영 배포 완료 판정은 코드와 자동 테스트만으로 내리지 않는다. 깨끗한 Windows 서버/클라이언트, 승인 Android 단말과 고객 유사 네트워크에서 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)의 설치, 인증서, 단말 교체, 백업 복구, 역할별 업무, 중단/rollback 기준을 단일 `run_id`로 통과해야 한다.

## 제외 범위

초기 범위에는 개인 메신저 수집, 사내 메신저 전체 대체 기능, GPS 추적, 근태 관리, 개인 휴대폰 기본 배포, MES/ERP 대체, 완성형 AI 조언 엔진을 포함하지 않는다. 외부 AI 1단계에서도 자동 의사결정, 작업지시 생성·변경, 승인·공개 자동화, 설비 제어, 안전·품질 판정과 근거 없는 조언은 금지한다. 단, Windows와 Android의 업무 채널 알림, 인수인계 알림, FieldComment/작업순서 이벤트 알림은 현장 기록 축적을 위한 제품 범위에 포함한다.
