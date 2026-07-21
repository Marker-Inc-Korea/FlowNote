# FlowNote 설계 결정

이 문서는 2026-07-21 현재 코드와 유효한 결정을 함께 기록한다. 대체된 결정은 현재 동작으로 오해되지 않도록 대체 사실만 남긴다.

## 2026-07-15. FieldComment 원천 불변과 단계형 검토 결정

- 주 검토 흐름은 `NEW → ANALYZED → REVIEWED → SELECTED`로 고정하고 보강 대기 `NEEDS_REVIEW`, 근거 부적합 `EXCLUDED`, 결정 완료 장기 보관 `ARCHIVED`를 별도 의미로 사용한다.
- 모든 상태 변경과 되돌림은 역할·필수 내용·사유를 검사한다. 서버는 요청 본문의 actor 필드 대신 인증 사용자를 분석자·검토자로 기록한다.
- 작업자 원문과 작성·대상·단말 정보는 불변 원천이며 관리자 정리·분석은 별도 필드다. 감사 snapshot 전후의 원천 hash가 다르면 저장하지 않는다.
- FieldComment 원천 row는 삭제하지 않는다. 서버 ORM은 직접 삭제도 거부하며 오입력·중복·근거 부적합 기록은 사유와 함께 `EXCLUDED`로 분류해 추적성을 유지한다.
- 일괄 검토는 요청당 최대 200건이며 개별 항목이 모두 같은 정책을 통과할 때만 저장하고 각 원천별 감사 이력을 남긴다. 오래된 NEW, 빈약한 SELECTED, 누락 report source는 품질 작업함에서 운영한다.

## 2026-07-20. 보고서 근거는 선정 상태·고정 버전·원천 hash로 확정

- 보고서 초안과 최종 저장은 서로 다른 source type을 최소 2종 요구하며 같은 `source_type + source_id + source_version_id` 중복을 거부한다.
- FieldComment source는 `SELECTED` 상태, 관찰 문서 버전과 원천 작성자가 모두 있어야 한다. 문서 source는 현재 공개 버전만 허용한다.
- 작업순서 항목은 최신 변경 ID 또는 항목 ID, 작업순서 이력은 변경 ID, 작업내역은 최신 버전 ID를 `source_version_id`로 고정한다.
- 각 `report_sources` row는 독립 `trace_id`와 저장 시점 `source_hash_sha256`를 가진다. 최종 문서 저장 직전에 원천 version과 hash를 다시 계산해 달라졌으면 `409`로 차단한다.
- 승인·보관 상태 보고서는 기존 draft ID를 통한 source 교체를 허용하지 않는다. WPF 로컬 보고서도 같은 2종·version·중복 조건을 먼저 검사하고 trace/hash를 보존한다.
- 기존 2026-07-01 결정의 보고서 후보 범위는 유지하되 FieldComment 후보 상태는 현재 코드의 `SELECTED` 전용 조건으로 좁힌다.

## 2026-07-20. AI ground-truth는 2인 승인과 준비도 계열을 분리

- ground-truth 최초 등록자는 첫 승인자로 기록하며 사례는 비활성으로 둔다. 첫 승인자와 다른 권한 사용자의 두 번째 승인 뒤에만 활성화한다.
- `SYNTHETIC`, `TEST`는 스모크 회귀, `ANONYMOUS_FIELD`, `PILOT`은 실제 현장 준비도로 고정해 서로 합산하거나 한 평가 run에 섞지 않는다.
- provider 착수 게이트의 48건은 실제 현장 준비도만 사용한다. 합성 48건 통과는 회귀 기준선일 뿐 현장 자료 확보로 간주하지 않는다.

## 2026-07-20. AI ground-truth 운영은 불변 dataset version과 평가 run 결합을 사용

- 개별 사례의 독립 2인 승인은 유지하되, 릴리스 단위는 승인 사례 48건을 묶은 `dataset_version_id`로 고정한다.
- dataset 작성자, 검토자, 1차 승인자, 2차 승인자는 모두 분리한다. 일반 운영 role은 작성·검토할 수 있지만 승인 단계는 `admin`, `system-admin`, `document-admin`, `department-manager`로 좁힌다.
- 최종 승인 시 8범주×3유형×2건 coverage와 각 사례 snapshot hash를 검증한다. 승인본은 수정하지 않고 대체 version을 만들어 이전 version을 `SUPERSEDED`로 남긴다.
- 모든 provider 준비도 판정은 최신 `FIELD_READINESS` 승인 dataset version과 정확히 결합된 evaluation `run_id`를 요구한다. 다른 version이나 ad-hoc 평가의 성공을 재사용하지 않는다.
- 승인본 평가가 없으면 `PENDING`, 결합 평가가 임계값에 미달하면 `FAIL`이다. 두 상태 모두 외부 provider 경계만 닫고 후보 재생성, 내부 품질 점검, 문서·FieldComment·작업순서·보고서 입력은 계속 허용한다.
- 포함·제외 reference 모두 재검증 가능한 content hash와 근거 설명을 갖고, 제외 reference는 제외 사유도 필수다. provenance는 전체 source snapshot hash와 두 승인자를 질문 원본과 별도로 보존한다.
- WPF 사례 운영은 서버 후보 선택과 수동 제외 원천 입력을 분리하고 `includePending=true`로 첫 승인 대기 사례를 조회한다. 개별 사례의 등록·2차 승인은 보고서 작성 role에 허용하되 동일 사용자 재승인은 금지한다. dataset 최종 승인·폐기는 더 좁은 승인 role을 유지한다.
- dataset ID 기반 구성 변경·상태 전이는 고객·현장·DB scope를 다시 확인하고, 대체 대상은 라인·준비도 계열·dataset key까지 같은 불변 version만 허용한다. 승인자 분리 규칙은 API 검사뿐 아니라 DB 제약으로도 유지한다.

## 2026-06-30. 현재 문서 기준

- 문서는 현재 코드에 맞춰 작성한다.
- 아직 구현되지 않은 기능은 제품 방향 또는 후속 범위로 분리한다.
- 과거 일일 기록보다 `README.md`와 `docs/` 상위 문서를 최신 기준으로 본다.

## 2026-07-21. 서버 복구 경계는 자동 전송 차단과 관리자 재결합으로 처리

- FastAPI는 `server_identity` singleton의 설치 instance ID, 명시적으로 증가시키는 epoch, schema/API contract 범위와 알림 high-water cursor를 manifest로 제공한다.
- WPF는 정규화 서버 URL별 binding을 보존한다. 다른 서버 URL, instance/epoch 변경, cursor 역행을 관측하면 기존 승인 binding을 자동으로 덮어쓰지 않고 `RECONCILIATION_REQUIRED`로 전환해 polling과 서버 mutation을 중지한다.
- reconciliation은 전체 로컬 서버 큐를 idempotency key와 선택적 hash로 서버 원천에 대조해 `REBOUND`, `REQUEUE`, `CONFLICT`를 제안한다. 관리자는 모든 항목과 사유를 승인해야 하며 임의의 다른 조치로 바꿀 수 없다.
- 승인 적용은 `REBOUND` 큐와 mapping을 서버 식별자에 다시 묶고, `REQUEUE`는 기존 key를 유지한 채 `PENDING`으로 되돌린다. `CONFLICT`는 자동 병합하지 않고 `DISCARDED`와 `RECONCILIATION_DIVERGED` 감사로 종결한다.
- 승인 뒤에만 binding을 새 instance/epoch로 활성화하고 알림 cursor를 0부터 재추적한다. 처리 완료 `message_id`, 로컬 원천, 큐와 과거 mapping 이력은 삭제하지 않는다.

## 2026-07-15. 단일 실행 ID 기반 Windows 통합 검증 증거

- 배포 통합 기준선은 Windows x64에서 표준 PowerShell/.NET/Python/JDK/Android SDK/Git 도구 조건을 먼저 통과한 실행만 인정한다.
- FastAPI JUnit, WPF Core TRX·앱 build·통합 smoke, Android JUnit·debug build, WPF SQLite SQL 증거와 실행 전후 Git 산출물 점검을 하나의 새 run ID에 보존한다.
- `5184` 포트의 외부 FastAPI는 설정을 추정해 재사용하거나 종료하지 않는다. 표준 실행은 빈 포트에 보존 설정을 식별할 수 있는 관리형 서버를 직접 시작한다.
- 기존 run ID의 증거는 덮어쓰지 않는다. 실패 단계까지 생성된 DB·로그·결과도 삭제하지 않으며 요약에 실패 단계와 원인을 남긴다.
- 생략 옵션이 없는 `PASSED` 요약과 모든 필수 단계·무결성 값이 함께 통과해야 기준선으로 확정한다. `PASSED_PARTIAL`, 비 Windows 실행 또는 테스트 수집 개수 일치는 부분 근거로만 취급한다.

## 2026-07-15. 서버 동기화 재시도 멱등성과 운영 진단

- WPF 큐가 재전송하는 문서 버전과 FieldComment 첨부는 기존 큐의 안정된 idempotency key를 서버에 전달한다. 서버는 `document_versions`와 `field_comment_attachments`에 키를 유일하게 저장하고 같은 부모의 재요청에는 기존 결과를 반환한다.
- 문서 공개 요청은 대상 버전이 이미 현재 공개 버전이고 문서·버전 상태가 모두 공개로 일치하면 성공한 멱등 요청으로 처리한다.
- 인증 만료와 서버 연결 실패·시간 초과는 같은 실행의 후속 항목도 성공할 수 없는 공통 장애로 보고 현재 재시도 묶음을 중단한다. 개별 항목의 계약·파일 오류는 그 항목을 실패로 남기고 다음 독립 항목을 계속 시도한다.
- 운영 화면은 비완료 큐 깊이, 최장 대기, 최근 1시간 처리량, 실패 분포와 row별 운영 상태를 함께 표시한다. 이 값은 현재 로컬 큐를 관찰하는 진단 지표이며 서버 전송 데이터나 별도 원격 모니터링 지표가 아니다.

## 2026-07-16. 문서 aggregate는 서버 revision과 공개 포인터가 권위 원천

- 서버 `documents.revision`, `latest_version_id`, `published_version_id`, 문서/버전 상태와 `file_objects.hash_sha256`가 권위 원천이다. WPF의 `version_no`, `updated_at`, 상태는 로컬 작업과 재전송 원천이며 서버 확인 전 권위값이 아니다.
- 새 버전, 공개, 문서·버전 상태, 태그 전체 교체, 삭제 요청은 base revision과 필요한 기준 버전 ID를 서버에 보낸다. 서버는 실제 변경 시 revision을 조건부 갱신해 두 Windows 사용자와 서버 관리 변경 중 하나만 성공시키며, 나머지는 구조화된 409로 돌려보낸다. 태그 교체는 필수 `baseRevision` query, 버전 상태 변경은 필수 `baseRevision` JSON 필드를 사용한다.
- 파일 내용, 공개본, 상태, 삭제는 자동 병합하지 않는다. 태그처럼 서로 독립된 집합형 메타데이터만 후속 patch 설계에서 서버 최신값과 명시적으로 합칠 수 있으며 현재 문서 mutation은 자동 병합하지 않는다.
- 같은 idempotency key는 같은 의도와 파일 hash에만 재사용한다. 다른 내용은 기존 결과로 위장하지 않고 `IDEMPOTENCY_KEY_REUSED`로 분리한다. 서버 버전 번호가 우연히 같아도 SHA-256이 다르면 성공 매핑하지 않는다.
- `PUBLISHED` 문서는 항상 같은 문서의 유효한 공개 버전 하나와 연결한다. publish transaction 전에 서버 파일 SHA-256을 재검사하고, 공개본 교체는 예상 공개 버전 ID와 revision이 모두 맞을 때만 수행한다.
- 충돌은 `CONFLICT` 큐와 원 서버 응답으로 영속화한다. 관리자가 최신 서버본 기준 로컬 변경 재시도 또는 서버본 유지·로컬 요청 폐기를 사유와 함께 선택하며 `DISCARDED`도 삭제하지 않는 종결 감사 상태다.
- 생성 시점의 서버 revision이 없는 구 공개·문서 상태 큐는 최신 revision을 추정하지 않는다. 서버 호출 전에 `LEGACY_BASE_MISSING`으로 충돌 전환해 관리자가 최신 서버본을 확인한 뒤 처리하게 한다.
- 서버 확인 응답과 로컬 매핑 저장이 끝난 항목만 `SYNCED`다. `PENDING`, `FAILED`, `CONFLICT`가 남아 있으면 화면은 “동기화 완료”를 표시하지 않는다.
- 네트워크 실패 뒤 앱을 재시작해도 같은 큐와 안정된 idempotency key를 재사용한다. 성공 응답을 받은 문서·버전 서버 ID 매핑은 유일하게 유지하며 같은 재시도를 반복해도 큐나 매핑을 추가하지 않는다.

## 2026-07-20. WPF 로컬 우선 원장과 서버 권위 원천은 revision·mutation receipt로 수렴

- WPF 공통 SQLite는 불안정한 사내망에서도 파일·입력·큐를 잃지 않기 위한 로컬 작업 원장이다. FastAPI DB는 운영 상태, 공개 포인터, FieldComment 검토, 보고서 source, 작업순서와 AI 근거 판정의 권위 원천이다. 로컬 row 수와 서버 row 수가 같다는 사실만으로 수렴을 판정하지 않는다.
- 서버 수락 전 로컬 원천·파일·큐를 삭제하지 않는다. 서버가 2xx를 반환해도 entity ID, revision, file/content/source hash를 read-back하고 `server_id_mappings`와 큐 종결을 같은 로컬 transaction에 저장하기 전에는 `SYNCED`가 아니다.
- 모든 재전송 가능한 mutation은 안정된 idempotency key와 의도를 식별할 hash를 갖는 것을 수렴 목표로 둔다. 현재 FieldComment 검토와 보고서는 도메인별 mutation receipt를 같은 transaction에 저장하고, 공통 `sync_mutation_receipts`는 후속 범위다. 응답 유실, 503, timeout, 앱 재시작은 같은 key와 같은 요청 의도로 재시도하며 서버 결과 row와 의미상 이력은 각각 한 번만 생성한다.
- 409 충돌은 자동 최신값 추정, 단계 보간, last-write-wins로 해결하지 않는다. `STALE_REVISION` 계열, source/hash 변경, orphan, key 재사용을 구조화된 코드로 보존하고 관리자가 최신 서버본 기준 재시도 또는 사유가 있는 `DISCARDED`를 선택한다. `SYNCED`, `DISCARDED`만 종결 상태이며 원천·큐·감사는 어느 상태에서도 자동 삭제하지 않는다.
- FieldComment 원천은 불변 `source_hash`로, 검토 영역은 별도 `review_revision`으로 관리한다. 검토 PATCH는 WPF에서 base review revision과 mutation key를 보내며 서버 상태를 맞추기 위한 WPF의 자동 중간 상태 생성은 금지한다. 현재 API는 예상 원천 hash를 요청 필드로 받지 않고 응답·감사 snapshot에서 검증한다. 첨부는 부모 ID와 파일 SHA-256을 별도로 검증한다.
- 보고서는 본문 hash와 정렬된 source ID/version/hash 집합 hash를 하나의 저장 의도로 취급한다. report, 모든 source, 생성 문서/버전과 mutation receipt는 한 서버 transaction에 저장한다. source가 바뀌었거나 사라졌으면 보고서를 낡은 근거로 자동 저장하지 않는다.
- 작업순서는 WPF 동기화 큐에 넣지 않고 서버 직접 API로 운영한다. 보드 revision이 보드·항목의 동시성을 직렬화하고 서버 mutation transaction이 change history를 정확히 한 번 만든다. WPF 로컬 작업순서 테이블은 전환 기간의 오프라인 초안·읽기 캐시와 기존 테스트 기록으로 보존하며 서버 미연결 상태의 운영 확정은 금지한다.
- 재시도 순서는 문서 등록 → 버전 → 공개 → 상태/태그 → FieldComment 원천 → 검토 → 첨부 → 접근 로그 → 보고서/source다. 같은 aggregate는 직렬화한다. 선행 ID 누락은 attempt를 늘리지 않고 보류하고, 공통 인증·연결 장애는 묶음을 중단한다.
- 서버는 설치 ID와 복구 epoch를 분리한다. instance/epoch 변경이나 cursor 역행을 감지하면 WPF는 mutation과 polling을 중지하고 기존 cursor·mapping을 보존한 채 reconciliation을 실행한다. 같은 key/hash는 새 ID에 재결합하고, 서버에 없으면 같은 key로 재전송하며, 불일치는 `SERVER_RECOVERY_DIVERGED`로 보존한다. 관리자 감사 후에만 cursor 0 재추적을 허용하고 처리한 `message_id`는 유지한다.
- 수렴 완료는 비종결 큐 0건, 동일 idempotency key 서버 중복 0건, orphan mapping/source 0건, 문서 공개 포인터·source/version ID·hash 일치와 cursor 재추적 완료를 모두 요구한다. AI 후보 재생성과 보고서 운영은 이 gate 뒤에 수행한다.

2026-07-21 구현 상태에서 작업순서 직접 운영 경계와 FieldComment 검토·첨부, 보고서 저장의 도메인별 서버 수렴 계약에 더해 server manifest, WPF URL별 binding, instance/epoch/cursor 복구 경계 차단과 관리자 reconciliation 적용까지 구현되었다. FastAPI는 FieldComment `review_revision`과 검토 receipt, 보고서 `report_revision`·내용/source 집합 hash와 보고서 receipt, 첨부 부모·파일 hash 검증을 사용한다. WPF는 검토 큐의 base revision/mutation key, 첨부 SHA-256을 보내고 자동 중간 상태 생성을 하지 않으며 성공 응답의 검토 revision을 로컬에 반영한다. 보고서 큐는 안정 key를 `idempotencyKey`와 `mutationKey`로 보내고, 응답 source를 정규화해 source-set hash를 대조한 뒤 report revision과 두 hash를 로컬에 보존한다. 공통 `sync_mutation_receipts`는 여전히 목표 계약이다. 제품 전체의 운영 완료 판정은 두 WPF 인스턴스와 한 서버에서 동시 문서 수정/공개, FieldComment 검토/첨부, 보고서 저장, 작업순서 변경을 수행하고 503·응답 유실·stale revision·서버 복구·앱 재시작을 주입한 뒤 SQL 증거를 비교해야 한다.

## 2026-07-20. DB schema 호환은 additive versioned migration과 무손실 증거로 판정

- WPF `EnsureColumn`과 서버 초기화 보완 로직에 의존하던 schema 변경을 local/server 단조 version과 고유 migration ID로 일반화한다. 클라이언트와 서버는 각자 지원 schema 범위와 API contract 범위를 교환하며 교집합이 없으면 쓰기를 중지한다.
- 기본 migration은 additive다. 파괴적 변경은 expand, backfill, verify, contract 단계로 나누며 실행 전 backup과 명시적 운영 승인이 필요하다. 새 버전의 앱이 구 DB를 열 때 순차 migration할 수 있지만, 지원 최대보다 새로운 DB에는 쓰지 않는다.
- 각 migration은 한 transaction에서 실행하고 적용 version을 마지막에 기록한다. 실행 전후 `quick_check`, `foreign_key_check`, 보호 원천 count/hash, idempotency 중복, mapping/report source orphan을 검사한다. 실패 transaction, DB, backup, 로그와 테스트 산출물은 삭제하지 않는다.
- WPF 보호 집합에는 모든 큐 상태가 포함된다. 특히 누적 `FAILED`/`CONFLICT`/`DISCARDED` row 수와 canonical hash, 로컬 파일 hash, FieldComment·첨부, 보고서 source, 작업순서 이력을 migration 전후 동일하게 유지한다.
- 서버 보호 집합에는 문서/버전/file object, FieldComment/첨부, 보고서/source, 작업순서/이력, 접근 로그와 mutation receipt를 포함한다. 공개 포인터와 source/version 관계의 orphan은 0건이어야 한다.
- 구 DB → 신규 DB 업그레이드 완료는 schema version 기록만으로 판정하지 않는다. 보호 원천 count/hash와 보존 FAILED 큐가 같고 모든 무결성 SQL이 통과한 단일 run 증거가 있어야 한다.

## 2026-06-30. FieldComment 명칭

- 현장 코멘트 도메인 명칭은 `FieldComment`, `field_comments`, `field-comments`를 사용한다.
- `FieldNote`, `field_notes`, `field-notes`, `FIELD_NOTE`는 FlowNote 제품명과 혼선을 만들 수 있으므로 새 작업에 사용하지 않는다.
- 새 WPF 코멘트는 문서 버전이 아니라 `field_comments` 원천 이력으로 저장한다.
- 기존 공통 SQLite에 남아 있는 구 FieldNote 테이블과 큐 row는 테스트 이력으로 보존한다. 현재 WPF는 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 큐를 FieldComment API로 자동 변환하지 않고 별도 전환 또는 마이그레이션 검토 대상으로 분류한다.

## 2026-07-14. 보존 동기화 실패 무손실 전환

- FAILED 누적 큐의 진단은 구 create, 구 FieldNote/첨부, 선행 서버 ID 누락, 로컬 파일 누락, 실제 서버/인증 오류의 배타적 분류를 사용한다.
- 전환 상태는 `자동 전환 가능`, `관리자 확인 필요`, `원본 누락으로 전환 불가`, `계속 보존` 네 가지다.
- dry-run은 SQLite read-only 연결만 사용하고 원천 row, 대상 action, 예상 idempotency key와 안정된 plan hash를 출력한다.
- 승인 실행은 직전 plan hash와 명시한 원천 큐 row ID만 받는다. 기존 큐와 파일은 수정·삭제하지 않고 현재 action의 신규 큐와 `server_sync_migration_audit`를 추가한다.
- 구 FieldNote는 새 FieldComment/첨부 원천으로 복제하되 작성자, 시각, 본문, 첨부 메타데이터, 원천 ID와 `FieldNote` 구 명칭을 감사 snapshot으로 보존한다.
- 원천 큐 ID와 대상 idempotency key를 유일하게 연결해 같은 승인을 반복해도 신규 큐·매핑·감사 중복이 생기지 않게 한다.

## 2026-06-30. 사용자 관리

- WPF 사용자 관리는 `admin`, `system-admin` 역할만 사용할 수 있다.
- 사용자 관리 화면은 사용자 추가, 표시 이름 변경, 역할 변경, 비밀번호 변경을 지원한다.
- 새 사용자 ID는 `user-{loginId}`로 자동 생성한다.
- 로그인 ID는 소문자 정규화 후 영문/숫자/하이픈/밑줄/점만 허용한다.
- 사용자 생성과 수정은 `activity_history`에 `user.created`, `user.updated`로 기록한다.

## 2026-06-30. 문서 공개 버전

- 문서 업로드 또는 새 버전 등록은 자동 공개가 아니다.
- 문서 최신 버전과 공개 버전은 분리한다.
- 서버는 `documents.latest_version_id`와 `documents.published_version_id`를 분리한다.
- WPF는 `documents.version_no`와 `documents.published_version_no`를 분리한다.
- 공개하려면 명시적 publish 동작을 수행해야 한다.

## 2026-06-30. WPF 로컬 저장 우선

- WPF 앱은 서버 연결 여부와 관계없이 로컬 SQLite 저장을 먼저 성공시킨다.
- 서버 URL이 있으면 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 남긴다.
- 서버 ID는 `server_id_mappings`와 각 로컬 원천 테이블의 서버 ID/synced_at 컬럼에 기록한다.

## 2026-06-30. 서버 인증 세션

- FastAPI는 HMAC Bearer access token과 `auth_sessions` 테이블을 함께 사용한다.
- login은 세션을 만들고 access/refresh token을 반환한다.
- refresh는 같은 세션에서 access token ID와 refresh token hash를 회전한다.
- logout은 현재 세션을 `REVOKED`로 바꾼다.

## 2026-07-01. WPF와 서버 계정 정책

이 결정의 서버 계정 관리 경로는 [2026-07-14 서버 계정 수명주기 API와 Windows 운영 화면](#2026-07-14-서버-계정-수명주기-api와-windows-운영-화면) 결정으로 대체되었다. 로컬/서버 계정 분리와 서버 role 우선 원칙은 유지한다.

- 서버 미연결 로컬 로그인은 로컬 SQLite 계정을 관리하고, 서버 로그인은 현재 서버 계정 수명주기 API와 WPF 운영 화면을 사용한다.
- 서버 로그인 성공 시 WPF 현재 세션은 서버 사용자 ID, 표시 이름, role을 우선 사용한다.
- 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.
- WPF 보고서 버튼은 FastAPI `ReportWriteUser`와 같은 role 집합만 활성화한다.

## 2026-07-02. 운영 초기 서버 계정

이 결정의 앱 강제 변경 미구현과 스크립트 중심 운영 범위는 2026-07-14 결정으로 대체되었다. 최초 `admin`의 비상·초기 스크립트 경로는 유지한다.

- 서버 DB 최초 생성 시 만들어지는 `admin` 계정을 최초 서버 관리자 계정으로 사용한다.
- 개발/스모크 테스트 기본 비밀번호 `1234`는 운영 로그인 전에 서버 PC에서 현장 비밀번호로 변경한다.
- 현재 서버 계정 생성·재설정은 `must_change_password`를 설정하고 WPF가 첫 로그인 직후 변경을 강제한다. 운영 스크립트는 비상·초기 서버 콘솔 경로로만 유지한다.
- WPF 로컬 계정은 오프라인 또는 서버 미설정 상황의 별도 계정이며 서버 계정의 대체 관리 화면이 아니다.

## 2026-07-06. 서버 계정 API와 WPF role 우선순위

이 결정의 서버 계정 API 보류 범위는 2026-07-14 결정으로 대체되었다. 서버 role 우선과 명시적 401/403에서 로컬 fallback 금지 원칙은 유지한다.

- 서버 계정 관리 API와 `must_change_password` 강제 변경 흐름은 2026-07-14에 구현되었고, `app.ops.server_accounts`는 비상·초기 운영 경로로 유지한다.
- 서버 로그인 성공 시 WPF 화면 권한은 서버 응답 role을 우선한다. 같은 로그인 ID의 로컬 role은 서버 세션의 버튼 활성/비활성 계산에 사용하지 않는다.
- 서버가 로그인에 401 또는 403을 반환하면 WPF는 같은 ID의 로컬 계정으로 fallback하지 않는다. fallback은 서버 URL이 없거나 연결 자체가 실패한 경우에만 허용한다.
- 서버와 WPF의 role 집합과 권한표는 FastAPI `test_role_permissions_api.py`와 WPF 스모크의 `RolePermissionPolicy` 행렬로 함께 고정한다.

## 2026-07-14. 서버 계정 수명주기 API와 Windows 운영 화면

- 설치형 WPF에서 서버 로그인한 `admin`, `system-admin`은 `/api/v1/server-accounts` 계정 수명주기 API를 사용한다. 서버 미연결 로컬 로그인은 별도 로컬 계정 화면을 유지한다.
- `admin`은 일반 계정을 운영하고 `system-admin`만 system-admin 계정을 생성·변경·조회·폐기할 수 있다. 자기 자신 잠금/비활성화와 마지막 활성 system-admin 제거는 서버가 거부한다.
- 계정 생성과 비밀번호 재설정은 운영자가 입력한 8자 이상 임시 비밀번호를 요청에서만 받고 `must_change_password = true`로 저장한다. 임시 비밀번호는 응답, 일반 로그, 활동 이력에 재노출하지 않는다.
- 강제 변경 계정은 로그인 토큰을 비밀번호 변경에만 사용할 수 있고 refresh와 나머지 보호 API는 거부한다. 변경 성공 시 모든 기존 세션을 폐기하고 새 비밀번호 재로그인을 요구한다.
- 계정 잠금/비활성화, role 변경, 비밀번호 변경/재설정, 관리자 세션 폐기는 `auth_sessions`를 즉시 `REVOKED`로 바꿔 기존 access/refresh를 함께 차단한다.
- 모든 운영 변경은 actor, 대상, 비밀번호를 제외한 전후 상태, 사유, 시각을 `activity_history`에 남긴다.

## 2026-07-06. AI 검색 기초 범위

- AI 계층의 첫 범위는 자동 조언이 아니라 근거가 있는 검색과 요약 후보 생성으로 제한한다.
- 검색 후보 원천은 공개 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source 네 종류만 사용한다.
- 후보는 `ai_search_candidates` read model에 저장하고, 원문 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source row로 돌아갈 수 있는 `source_*`와 `trace_*` 식별자를 함께 둔다.
- FieldComment가 `ANALYZED`, `REVIEWED`, `SELECTED` 상태로 충분히 쌓이기 전에는 AI 답변 품질보다 관리자 검토/분석/선정 운영 흐름 보강을 우선한다.
- MES/ERP 외부 연동 필드는 검색 후보 생성에 사용하지 않는다. `mes_integration` FieldComment도 어댑터 정책이 확정되기 전에는 후보에서 제외한다.

## 2026-07-07. AI 검색 운영 점검 흐름

- AI 검색 운영 점검 화면은 외부 AI 호출 없이 `ai_search_candidates` 재생성 결과와 품질 지표를 확인하는 범위로 둔다.
- 운영자는 공개 문서 버전, FieldComment, 작업순서 이력, 보고서 source별 후보 수와 제외 사유를 먼저 확인한다.
- 제외 사유는 공개 문서 미충족, FieldComment 보관/제외, MES 통합 입력, 빈 FieldComment, 텍스트 없는 작업순서 이력, 누락/보관/원천 누락 보고서 source로 구분하고 운영 조치 힌트를 함께 제공한다.
- 후보 row는 `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`로 원문 문서 버전, FieldComment, 작업순서 이력, 보고서 source row까지 역추적되어야 한다.
- WPF 운영 점검 화면은 서버의 후보 재생성/품질/목록 API를 호출하고, 선택한 후보의 추적값을 운영자가 복사해 원천 row 확인에 사용할 수 있게 한다.
- 자동 답변 생성, 자동 의사결정, 작업지시 자동 변경은 이번 운영 점검 범위에 포함하지 않는다.

## 2026-07-01. WPF 보고서 저장 흐름

- WPF 보고서 창은 `SELECTED` FieldComment, 현재 공개 문서, 작업순서 항목/이력을 보고서 근거 후보로 사용한다.
- 서로 다른 source type 2종 이상과 source별 고정 version이 있어야 초안과 로컬 보고서 문서를 만들 수 있으며 같은 type/ID/version 중복은 거부한다.
- WPF 보고서 저장은 로컬 보고서 문서와 `report_sources`를 먼저 만든 뒤 서버 `/api/v1/reports` 저장을 시도한다.
- 보고서 저장 실패는 보고서 전용 큐를 새로 만들지 않고 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남긴다.
- 큐에는 한글 실패 사유, 마지막 시도 시간, 시도 횟수를 기존 동기화 항목과 같은 방식으로 기록한다.
- 서버 재시도 중복 방지는 `/api/v1/reports`의 `idempotencyKey`와 WPF `wpf:report:{localReportDocumentId}` 키로 처리한다.
- 서버 보고서 저장에 성공한 로컬 보고서 문서는 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`에 연결한다.

## 2026-07-02. 서버-WPF 문서 동기화 우선순위

- WPF는 로컬 저장을 먼저 성공시키고 `server_sync_queue` 재시도 시 같은 문서 또는 보고서 근거 단위의 선행 조건을 우선한다.
- 재시도 처리 순서는 문서 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 접근 로그 시작/종료/자동 종료/다운로드 차단, 보고서 저장이다.
- 선행 문서, 문서 버전, FieldComment, 보고서 근거의 서버 ID가 없으면 해당 큐는 실제 서버 호출 없이 보류로 분류하고 `attempt_count`를 증가시키지 않는다.
- 문서 최초 등록이 서버 ID를 받아야 문서 버전, FieldComment, 첨부, 접근 로그가 서버 문서/버전 ID에 연결된다.
- 문서 최신 버전은 로컬 `document_versions.version_no` 기준으로 서버 버전을 찾고, 서버에 같은 번호가 있으면 매핑을 복구하며 없으면 업로드한다.
- 공개 버전은 해당 로컬 버전의 서버 버전 ID가 있을 때만 서버 publish API에 반영한다.
- 문서 상태는 현재 로컬 `documents.status`를 서버에 반영한다. `PUBLISHED` 상태는 공개 버전 동기화가 선행되어야 한다.
- 서버 미동작, 인증 만료, 선행 문서/버전 미동기화 상황에서도 로컬 데이터와 큐는 삭제하지 않는다.
- 작업순서 보드/항목/이력은 WPF 로컬 큐 대상이 아니다. 이 결정의 당시 범위는 2026-07-21 서버 권위 직접 운영 구현으로 확장되었다. WPF 관리자·TV 화면은 서버 snapshot을 읽고, 관리 화면은 `board_revision`과 mutation key로 직접 변경하며, 로컬 row는 읽기 캐시·초안으로만 보존한다.

## 2026-06-30. 관리자 파일 감시

- 파일 감시는 WPF 네이티브 `FileSystemWatcher` 기반 로컬 기능이다.
- `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 사용할 수 있다.
- 감지된 파일은 즉시 업로드하지 않고 `file_watch_candidates`에 `PENDING`으로 저장한다.
- 확정 시 대상 문서, 버전명, 변경 사유가 필요하며 새 `document_versions` row를 만든다.

## 2026-07-02. Windows 운영 배포 방식

- WPF 클라이언트 설치파일은 MSI를 기준으로 한다.
- MSI 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`이며 로컬 SQLite와 `Files`는 `FLOWNOTE_LOCAL_DATA_DIR` 아래에 분리한다.
- MSIX는 서명, 패키지 아이덴티티, 앱 컨테이너 제약을 현장별로 더 검토해야 하므로 초기 기준에서 제외한다.
- FastAPI 서버 상시 실행은 Windows 작업 스케줄러 `\FlowNote\FlowNoteApi` 작업으로 등록한다.
- 작업 스케줄러는 Windows 기본 기능만으로 부팅 시 실행, 수동 시작, 중지, 재시작, 로그 남김을 처리할 수 있어 초기 서버 PC 배포 기준에 맞다.
- Windows Service 직접 등록은 Python/FastAPI 프로세스용 서비스 래퍼 또는 별도 호스트 구현이 필요하므로 후속 선택지로 둔다.
- 현재 저장소에는 `package-wpf-msi.ps1`, `install-flownote-server-task.ps1`, `manage-flownote-server-task.ps1`, `run-flownote-server.ps1`가 있으며, 운영 현장 적용 전에는 MSI 설치 검증, 서명, 런타임 포함 여부를 별도로 확인한다.

## 2026-07-06. WPF MSI 런타임과 서명 기준

- `package-wpf-msi.ps1`의 기본 산출물은 framework-dependent MSI다. 설치 대상 PC에 대상 버전의 `.NET Windows Desktop Runtime`이 보장되지 않으면 `-SelfContained` MSI를 별도 생성한다.
- self-contained MSI는 .NET 런타임 파일을 포함하지만 WebView2 Evergreen Runtime은 포함하지 않는다. WebView2 Runtime은 설치 전 별도 점검과 설치 절차로 관리한다.
- MSI 파일 세트에는 WPF 실행 파일, `.deps.json`, `.runtimeconfig.json`, 앱 DLL, 의존 DLL, 네이티브 DLL만 포함한다. 로컬 SQLite, WAL/SHM, `Data`/`Files`, 테스트 산출물, 고객 파일 패턴이 publish 파일 세트에 있으면 패키징을 실패시킨다.
- framework-dependent와 self-contained MSI를 번갈아 만들 때 publish 폴더의 이전 파일이 섞이지 않도록 `package-wpf-msi.ps1`는 publish 폴더를 비운 뒤 새로 생성한다.
- 설치 후에는 `verify-wpf-msi-install.ps1`로 MSI 파일 목록 금지 패턴, 설치 폴더와 로컬 데이터 폴더 분리, .NET Desktop Runtime, WebView2 Runtime, 선택적 서명 검증을 확인한다.
- 운영 배포 MSI는 코드 서명 인증서로 서명하는 것을 기준으로 한다. 서명 시 publish된 `FlowNote.Windows.App.exe`를 먼저 서명하고, 그 EXE가 포함된 MSI를 생성한 뒤 최종 MSI도 서명하고 검증한다.
- 미서명 MSI는 내부 임시 검증용으로만 허용하며, 배포 대상, MSI 해시, 승인자, Windows 경고 안내를 운영 기록에 남긴다.

## 2026-07-02. 운영 백업/복구와 후속 계층 착수 기준

- 서버 SQLite, 서버 `storage`, 서버 `.env`/로그는 서버 운영 백업 세트로 관리한다.
- WPF 로컬 SQLite와 WPF `Files`는 PC별 로컬 백업 세트로 관리한다.
- 서버 DB와 서버 `storage`는 같은 시점의 백업을 정상 복구 기준으로 삼는다. DB만 또는 `storage`만 복원한 상태는 정상 운영 재개가 아니라 장애 대응 상태다.
- 복구 검증은 서버 health, DB health, WPF 로그인, 문서 목록, 문서 열람, FieldComment, 보고서 근거 조회를 포함한다.
- 복구 후 가능한 환경에서는 `.\scripts\verify-preserved-tests.ps1` 또는 동등 운영 점검을 실행한다.
- 외부 AI 호출 기반 검색/작업 조언은 공개 문서, FieldComment, 보고서, 작업순서 이력이 충분히 축적되고 근거 역추적이 가능해진 뒤 후속 계층으로 착수한다. 현재 구현은 `ai_search_candidates` 근거 후보 운영과 외부 호출 전 비활성·승인·목적·원천 권한·민감정보·최소 payload·snapshot·인용 검증·감사 게이트까지이며, provider는 테스트용 주입 경계만 두고 운영 네트워크 연동은 하지 않는다.
- MES/ERP 어댑터는 후속 연동 대상이며, 초기 수동 작업지시의 `work_order_no`, 문서 연결, 작업순서, FieldComment, 보고서 근거와 연결되는 방식으로 설계한다.

## 제품 범위 결정

- FlowNote는 MES/ERP를 대체하지 않는다.
- 문서 구조는 고객이 결정한다.
- BOM 문서 구조는 현장 표현 예시이며 기본 강제 구조가 아니다.
- 외부 AI 호출 기반 검색과 작업 조언은 충분한 데이터 축적 뒤 후속 기능으로 둔다.
- 초기 배포는 서버 PC 1대와 Windows 설치형 클라이언트를 기준으로 하되, 제품 클라이언트 범위에는 Android 현장 단말 앱을 포함한다.

## 2026-07-07. 설치형 클라이언트와 채널 알림

- Windows WPF는 관리자/현장 PC의 문서 운영, 파일 감시, 보고서 정리, 로컬 저장 보강, 채널 감독, 인수인계 관리를 담당한다.
- Android 앱은 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세 메타데이터 확인, FieldComment, 사진 기록, 신호등식 상태 기록, 인수인계 확인, 채널 알림을 담당한다. 당시 1차 범위에는 문서 파일 본문 뷰어와 인수인계 신규 작성 화면을 넣지 않았으며, 본문 뷰어는 2026-07-16 별도 결정으로 추가했다.
- Windows와 Android 알림은 개인 메신저나 사내 메신저 대체가 아니라 업무 채널 모델로 설계한다.
- 채널은 라인, 설비, 공정, 작업조, 작업내역, 인수인계 같은 운영 단위에 연결한다.
- 인수인계는 채널에 등록되는 업무 이벤트이며 수신자는 확인, 보류, 후속 FieldComment 작성 같은 상태를 남긴다.
- 개인 휴대폰 기본 배포, 개인 메신저 수집, GPS 추적, 근태 관리는 초기 범위에 포함하지 않는다.

## 2026-07-09. 서버 공통 채널과 인수인계 모델

- FastAPI 서버는 `notification_channels`, `notification_channel_members`, `channel_messages`, `handovers`, `handover_receipts`를 Windows와 Android가 공유하는 채널/인수인계 원천 모델로 둔다.
- 사용자별 알림은 별도 개인 DM 테이블이 아니라 채널 멤버십과 `channel_messages` 읽음 위치로 계산한다.
- 채널 메시지와 인수인계는 문서, FieldComment, 작업순서 항목/이력, 작업내역, 보고서, 인수인계 원천 ID를 보존한다.
- 인수인계 receipt는 수신자별 `UNREAD`, `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`를 기록한다.
- 서버 API는 채널 멤버 또는 `admin`, `system-admin`만 채널 메시지와 인수인계를 조회할 수 있게 한다.
- 개인 DM, 개인 메신저 수집, GPS, 근태 기능은 서버 채널/인수인계 모델에 포함하지 않는다.

## 2026-07-13. 사내망 polling을 채널·인수인계 알림의 1차 전달 방식으로 확정

- 서버 PC와 승인된 설치형 단말이 같은 사내망에서 동작하는 초기 배포는 HTTP polling을 1차 알림 전달 방식으로 사용한다.
- `/api/v1/notifications`의 단조 증가 `cursor`와 `afterId`를 사용해 마지막 성공 위치 다음부터 오름차순으로 조회한다. 클라이언트는 `message_id`와 cursor를 멱등 키로 사용하며, cursor는 응답을 처리한 뒤에만 전진시킨다.
- Windows와 Android 전경 상태는 기본 15초 주기로 확인한다. 연결 실패 시 30초, 60초, 최대 120초까지 지수 백오프하고 성공 즉시 15초로 복귀한다. 서버 또는 네트워크 복구 뒤에는 현재 보유한 마지막 cursor부터 재개한다. Android 부분은 아래 2026-07-16 운영 결정으로 대체했다.
- HTTP 401이면 polling을 중지하고 재로그인을 요구한다. Android는 사용자별 cursor를 `SharedPreferences`에 보존해 다른 사용자와 공유하지 않는다. WPF 영구 보존 정책은 아래 2026-07-14 결정을 따른다. Android의 scope와 refresh 처리는 아래 2026-07-16 결정으로 대체했다.
- Windows는 창이 열린 동안만 15초 polling한다. 이 결정 당시 Android는 Activity 전경에서만 polling했으나 아래 2026-07-16 foreground service 결정으로 대체했다.
- Android 백그라운드 확인을 두지 않는다는 당시 범위는 아래 2026-07-16 결정으로 대체했다. WorkManager의 최소 주기·Doze·배터리 최적화로 즉시성이 보장되지 않는다는 평가는 유지한다.
- WebSocket은 프록시, 재연결, 서버 fan-out 운영 기준이 마련된 뒤의 사내망 저지연 선택지다. FCM 등 외부 push는 인터넷 연결과 외부 전송 보안 정책을 별도 승인한 현장의 후속 선택지다.

## 2026-07-16. Android 운영 알림은 전용 단말 foreground polling으로 복구

| 방식 | 외부 의존 | 예상 지연/복구 | 배터리·운영 비용 | 판정 |
| --- | --- | --- | --- | --- |
| WorkManager 제한 polling | 없음 | 최소 주기·Doze로 수십 분까지 지연 가능 | 낮음 | missed 복구 보조만 가능, 30초 목표에는 부적합 |
| foreground service HTTPS polling | 없음 | 15초 주기, 단절·재부팅 cursor 복구 | 상시 알림·무선 wake로 높음 | 전원 공급/거치형 승인 단말의 기본 |
| MDM 허용 push+사내 relay | 사내 relay만, FCM 미사용 기준 | 저지연 wake 후 cursor 복구 | 단말 배터리 낮음, relay HA·인증 운영 높음 | 현장 실기 후 후속 대안 |

- 제한 주기 WorkManager polling은 최소 주기와 Doze 지연 때문에 30초 목표를 충족하지 못한다. 일반 foreground service는 배터리와 상시 알림 비용이 있지만 승인된 거치형/러기드 전용 단말에서 사내 HTTPS만으로 15초 확인과 재부팅 복구를 제공하므로 운영 기본으로 선택한다.
- 외부 FCM 의존은 두지 않는다. 현장 MDM이 허용하고 사내 relay의 인증·재연결·감사가 검증되면 relay push를 저전력 후속 대안으로 추가하되 cursor polling을 missed notification 복구 원천으로 유지한다.
- 정상 연결 목표 표시 지연은 30초, 5분 이상 단절 복구는 연결 회복 후 30초+page 전송 시간이다. 시각 알림 중복 허용은 crash 경계 최대 1건, 서버 read/receipt 중복 row 허용은 0건이다.
- cursor는 서버 주소와 사용자 ID scope로 분리하고 각 항목 표시 뒤 전진한다. 첫 로그인은 과거 page를 따라잡되 새 시스템 알림을 만들지 않는다. 재부팅은 저장 세션으로 서비스를 재개하지만 사용자의 Android 강제 중지는 OS 정책상 MDM kiosk 또는 명시적 앱 재실행 전까지 복구할 수 없는 운영 예외다.

## 2026-07-20. FastAPI 서버 DB와 WPF 로컬 DB의 schema 소유권을 분리하고 교차 초기화를 거부

- FastAPI `FLOWNOTE_DATABASE_URL`과 `FLOWNOTE_LOCAL_DATA_DIR`/`FLOWNOTE_LOCAL_DATABASE_PATH`로 결정되는 WPF 로컬 DB는 서로 다른 SQLite 파일이어야 한다. 이미 WPF `documents`/`document_versions` 형태인 DB를 감지한 FastAPI 초기화는 `Base.metadata.create_all()` 전에 실패하며 서버 테이블을 추가하지 않는다.
- WPF 로컬 `document_versions`는 로컬 `id` PK와 문서별 `version_no`를 사용한다. 서버 `document_versions.version_id`를 참조하는 `controlled_copy_grants`를 WPF DB에 맞추려고 로컬 schema에 가짜 서버 key를 추가하지 않는다.
- 이미 교차 생성된 서버 전용 grant 테이블은 DB 삭제나 초기화로 처리하지 않는다. 원본 SQLite backup, 전체 DDL·FK·row 수, 보호 대상 row hash를 먼저 보존하고 grant row를 별도 무참조 보존 테이블과 migration 감사에 복사한 뒤 충돌하는 활성 테이블만 제거한다.
- 표준 WPF 스모크는 실행 전후 `quick_check`와 `foreign_key_check`를 별도 증거로 남기며, 오류 또는 위반이 있으면 기능 스모크 결과와 무관하게 실패한다.

## 2026-07-16. Android 비밀과 outbox는 Keystore 앱 수준 암호화를 기본 통제로 사용

- access/refresh token, outbox JSON과 새 사진 첨부는 Android Keystore 비반출 AES-256 GCM 키로 보호한다. OS sandbox·backup 차단을 함께 사용하며 MDM 전체 디스크 암호화만을 유일한 보호 수단으로 의존하지 않는다.
- 키는 단말 밖으로 export하거나 교체 단말로 이전하지 않는다. 키 분실·무효화 시 해당 단말을 비활성화하고 미전송 항목의 서버 반영 여부를 idempotency key로 확인한 뒤 승인된 보존/폐기와 새 `deviceId` 등록을 수행한다.
- 운영 배포 기본은 조직 키로 서명한 사내 APK다. AAB는 관리형 스토어 선택 시에만 사용한다. keystore와 암호는 환경의 승인된 비밀 주입 경로로 제공하고 저장소·패키지 증거에 포함하지 않는다.

## 2026-07-14. WPF 서버 scope·사용자별 알림 cursor 영구 보존

- WPF는 정규화한 서버 base URL과 서버 `user_id` 조합을 키로 `server_notification_cursors`에 마지막 성공 cursor와 갱신 시각을 저장한다. 사용자 전환과 다른 서버 URL은 cursor를 공유하지 않으며 로그아웃은 row를 삭제하지 않는다.
- 처리한 공개 `message_id`는 `server_notification_messages`에 같은 scope와 사용자별로 유일하게 저장한다. 응답 항목 처리, `message_id` 기록과 cursor 전진은 한 SQLite 트랜잭션으로 완료하며 실패하면 모두 rollback한다.
- FastAPI는 `X-FlowNote-Notification-Cursor`에 서버 high-water cursor를 반환한다. 이 값이 로컬 성공 cursor보다 낮으면 서버 DB 복구/초기화 의심 상태로 보고 polling을 중단하며 자동으로 cursor를 낮추지 않는다.
- cursor 0 초기화는 서버 복구를 확인한 `admin`, `system-admin`이 WPF 경고 창에서 명시적으로 확인한 현재 서버 scope·현재 사용자에만 적용한다. Core 서비스도 전달받은 role을 다시 검사해 일반 사용자의 직접 호출을 거부한다. 확인 관리자와 시각을 남기고 다른 사용자·서버 row는 유지하며, 기존 `server_notification_messages`의 처리 완료 `message_id`는 초기화 뒤 재조회 멱등 근거로 삭제하지 않는다.
- 로컬 DB 복구 후 row가 없거나 신규 사용자인 경우 0부터 따라잡는다. 이 과정은 새 알림으로 중복 표시하지 않고 `이전 알림을 재확인 중입니다`와 cursor 진행 위치를 한글로 안내한다.
- 401은 polling 중지와 재로그인 요구를 유지하며 cursor를 전진시키지 않는다.

## 2026-07-09. Android 현장 단말 최소 앱

- Android 현장 앱은 Java, Android 네이티브 View, Gradle Android plugin을 최소 기술 스택으로 시작한다.
- 최소 OS는 Android 8.0(API 26)으로 둔다. 초기 현장 대상은 승인된 태블릿 또는 러기드 단말이며 개인 휴대폰 기본 배포는 제외한다.
- 패키지는 `com.flownote.fieldapp`를 사용한다.
- Android 로그인은 서버 `/api/v1/auth/login`에 `deviceId`를 보내며, 서버 `terminal_devices.status = ACTIVE`인 승인 단말만 세션을 받을 수 있다.
- 서버 세션은 Android 승인 단말 ID를 `auth_sessions.device_id`에 보존한다.
- Android 로컬 저장은 장기 원천 DB가 아니라 FieldComment와 사진 첨부 재전송용 outbox로 제한한다.
- FieldComment 재전송은 `android:{deviceId}:{localId}` idempotency key를 사용해 서버 중복 생성을 막는다.
- 채널 알림과 인수인계는 새 개인 메시지 체계가 아니라 서버 공통 채널/인수인계 API 조회, 읽음, 수신확인으로 붙인다.
- GPS 추적, 근태 관리, 개인 메신저 수집, 사내 메신저 전체 대체는 Android 앱 초기 범위에 포함하지 않는다.

## 2026-07-10. 승인 단말 운영 상태와 교체 이력

- 승인 단말 상태는 `ACTIVE`, `INACTIVE`, `RETIRED`로 통일한다. `RETIRED`는 폐기·교체 완료 상태이므로 재활성화하지 않는다.
- 단말 관리 API와 WPF 운영 화면은 서버 계정 `admin`, `system-admin`만 사용한다.
- 교체는 기존 단말을 `RETIRED`로 변경하고 새 단말을 등록하는 하나의 서버 트랜잭션으로 처리한다.
- 단말 등록자, 마지막 변경자, 대체한 기존 device ID를 `terminal_devices`에 보존하고 등록·변경·상태·교체 이벤트는 `activity_history`에 남긴다.
- Android 로그인 성공 때마다 `terminal_devices.last_seen_at`을 갱신하고 각 로그인 세션의 `auth_sessions.device_id`를 유지한다.

## 2026-07-10. 외부 AI 1단계 안전장치와 API 계약

- 외부 AI 첫 범위는 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`로 제한한다. 자동 의사결정, 작업지시 생성·변경, 승인·공개 자동화, 설비 제어, 안전·품질 판정은 금지한다.
- 외부 호출은 기본 비활성화하고 고객·현장별 운영자 승인과 기능 플래그를 모두 요구한다. 내부 `PUBLISHED` 상태를 외부 전송 동의로 해석하지 않는다.
- 응답의 모든 사실 주장은 질의 시점 `ai_search_candidates` snapshot에 있는 문서 버전, FieldComment, 작업순서 이력 또는 `report_sources.id` 인용을 가져야 한다. 근거 부족이나 인용 검증 실패 시 답변 본문을 반환하지 않는다.
- `ai_queries`, `ai_query_evidence_candidates`, `ai_query_citations`, `ai_prompt_versions`, `ai_call_attempts`, `ai_transfer_approvals` 안전장치 골격을 구현한다. 응답은 기본 미저장, 질의 원문과 승인 저장 응답은 90일, 근거·인용·호출·오류·승인 감사 메타데이터는 1년 보존한다.
- 재생성은 보존 중인 질의, 불변 프롬프트 버전, 근거 snapshot과 provider/model을 다시 사용하되 동일 문구를 보장하지 않는다. 원천 권한·상태·승인이 바뀌면 재생성하지 않는다.
- 민감정보와 고객 문서의 외부 전송 금지·최소화·승인·철회 절차는 [보안 문서](./security.md#외부-ai-전송과-운영자-승인)를 단일 운영 기준으로 사용한다.
- 이 결정은 운영 provider client나 네트워크 호출을 활성화하지 않는다. 주입 가능한 테스트 경계만 두며 기존 `ai_search_candidates` read model과 후보 API는 기능 플래그에 의존하지 않고 현재 테스트 계약을 유지한다.

## 2026-07-13. 외부 AI 착수 전 ground-truth 회귀 게이트

- 후보 ID는 source type/id/version의 결정적 hash로 만들고 검색 본문의 별도 `content_hash`를 둬 재생성 전후 동일 원천을 비교한다.
- 사람형 스모크와 API 테스트는 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source가 함께 필요한 질문과 기대 candidate/source/version/trace ID를 저장한다.
- 삭제·비공개 문서, 제외/보관 FieldComment, 사라진 보고서 원천, 권한 없는 채널, 근거 부족 질문을 부정 사례로 유지하며 근거 부족은 `INSUFFICIENT_EVIDENCE`로 판정한다.
- provider 착수 지표는 평가 전건 통과, 네 원천 유형 커버, candidate ID/content hash와 순위 재현성, 검토 완료 FieldComment 100건 충족을 모두 요구한다. 이 지표는 운영 승인과 기능 플래그를 대신하지 않으며 외부 호출을 자동 활성화하지 않는다.

## 2026-07-14. 외부 AI provider 직전 최소 payload 게이트

- 문서 버전, FieldComment, 작업순서 이력, report source는 공통 정책 서비스가 query snapshot 시점에 원천 상태, 작성자 계정·role과 연결 채널 멤버십을 다시 검사한다.
- 주민등록번호·전화번호·이메일은 마스킹하고 계정·token·경로·고객 식별자와 현장별 금칙어는 원천 전체를 차단한다. 금칙 원문은 provider DTO, 근거 snapshot과 일반 로그에 남기지 않는다.
- provider 경계 DTO는 정제 질의, 최소 발췌, 안정된 candidate/source/version/trace ID, content hash, rank와 prompt version만 허용한다. 운영 provider SDK나 네트워크 client는 이 결정에 포함하지 않는다.
- 차단 감사 코드는 `CONTENT_RESTRICTED`, `SOURCE_FORBIDDEN`, `APPROVAL_REVOKED`, `INSUFFICIENT_EVIDENCE`로 정제한다. 제외 후보는 ID/hash와 사유만 snapshot으로 남기며 `sent_externally = false`를 유지한다.
- 승인 철회는 신규 질의를 즉시 차단하지만 `ai_search_candidates`와 외부 호출 없는 ground-truth 품질 점검은 계속 사용할 수 있어야 한다.

## 2026-07-15. scope별 승인 ground-truth와 운영 호출 readiness 게이트

- 고객·현장·선택적 라인과 DB fingerprint를 서로 다른 readiness scope로 집계한다. WPF 공통 로컬 SQLite, FastAPI 테스트 DB, 운영 서버 DB의 수치를 합산하지 않는다.
- 승인 질문 원본은 평가 run과 분리해 저장하고 안전·품질·설비 이상·작업 보류·재작업·인수인계·최신 공개 문서·상충 기록 범주와 정상·제외·상충 유형, 기대 포함/제외 근거, 허용 순위, 시점을 고정한다.
- 당시 시작안은 승인 질문과 같은 scope 평가 50건이었다. 2026-07-16 결합 게이트 결정에서 8범주×3유형×각 2건인 48건과 조합별 하한, 추가 품질 임계값으로 대체했다.
- 주민번호·전화번호·이메일, 계정/token/경로 패턴과 고객·현장 활성 민감정보 정책에 걸린 원천은 마스킹 후보가 아니라 검색 후보 생성 단계에서 제외한다. 원천 row는 삭제하지 않는다.

## 2026-07-15. 외부 AI 운영 제어면과 불변 snapshot

- 승인·프롬프트·운영 정책·감사·보존 API와 WPF 화면은 `system-admin`에만 노출한다.
- 기능 플래그, 전역/현장 kill switch, 고객·현장·provider·model·목적·source type 승인, 프롬프트 승인, 요청·동시성·timeout·비용 한도를 provider 경계 전에 검사하고 정제 사유를 감사한다.
- 승인과 프롬프트는 질의별 JSON snapshot으로 복제한다. 운영 객체의 폐기나 새 버전 활성화는 과거 질의를 변경하지 않는다.
- provider 자격증명은 DB 모델과 API DTO에 두지 않고 서버 환경/비밀 저장소에서만 읽는다. 화면은 설정 여부만 표시한다.
- 만료 작업은 참조 row를 삭제하지 않고 질의 payload 비식별화와 응답 원문 삭제를 수행하며 hash·근거·인용·호출 메타데이터와 처리 감사를 보존한다.
- 같은 만료 작업을 서버 lifespan 스케줄러가 기본 1시간 간격으로 실행하고, `system-admin` API/WPF는 다음 주기를 기다리지 않는 즉시 실행 경로로 유지한다. 활성 여부와 간격은 서버 설정으로 제어한다.

## 2026-07-15. 제한형 AI provider adapter와 응답 근거 검증

- provider 계약은 `invoke(payload)` 중립 인터페이스로 고정하고 fake, recording, callable 호환, 제한형 JSON 네트워크 adapter를 분리한다. 기본 adapter mode는 `DISABLED`다.
- 네트워크 adapter는 `environment=test`, `NETWORK_TEST` mode, 별도 test-scope switch, HTTPS endpoint, 환경 변수 자격증명을 모두 요구한다. 이 조건은 운영 provider 활성 승인을 대신하지 않는다.
- provider-bound payload는 정제 질의, 승인된 최소 발췌, 안정 candidate/source/version/trace ID, content hash, 순위, prompt version과 허용 JSON 출력 형식만 포함한다.
- 응답은 완전한 제한 크기 JSON, claim별 기존 citation ID, 중복 없는 claim/citation 구조를 요구한다. 숫자, 핵심 토큰 겹침, 부정 극성 규칙으로 claim과 summary를 근거 발췌에 대조하며 provider 모델의 자기평가만으로 승인하지 않는다.
- 근거 없음, 상충, 낮은 의미 확신, 호출 중 승인·원천 상태·열람 권한 변경은 실패 문구를 생성하지 않고 `INSUFFICIENT_EVIDENCE` 정상 보류로 다룬다. 낮은 확신은 사람 검토 필요 상태를 함께 반환한다.
- timeout, 429, 5xx만 제한 횟수까지 재시도하고 각 시도를 같은 `query_id`의 `ai_call_attempts`로 남긴다. 불완전 JSON, 과대 응답, prompt injection, 중복 인용은 재시도하지 않고 본문 전체를 폐기한다.
- provider 장애와 검증 보류는 문서, FieldComment, 작업순서, 보고서와 로컬 저장 흐름에 영향을 주지 않는다. 외부 호출 없는 후보 재생성·ground-truth 평가는 계속 동작한다.

## 2026-07-15. 운영 배포 완료는 실제 리허설과 제한 파일럿 통과로 판정

- 코드 구현과 자동 테스트 통과만으로 운영 배포 완료를 선언하지 않는다. 깨끗한 Windows 서버/클라이언트, 승인 Android 단말과 고객 유사 네트워크에서 실제 설치·복구·운영 동선을 검증한다.
- Windows 설치·업그레이드·제거, 서버 재부팅, 네트워크 단절·복구, 인증서 갱신, 단말 교체, 서버 DB+`storage`와 WPF DB+`Files`의 별도 PC 복구를 필수 장애 시나리오로 둔다.
- 각 리허설은 단일 `run_id`로 패키지 hash/서명, 화면, 서버·클라이언트 로그, DB 무결성, 원천별 개수와 파일 hash, 역할별 성공률·시간을 연결한다. 실패 증거도 삭제하지 않는다.
- 데이터 손실, 권한 우회, 미승인 파일·비밀·개인정보 유출 허용치는 0건이다. 하나라도 발생하면 신규 입력과 배포 확대를 중단하고 실패 상태를 보존한 뒤 승인된 백업과 이전 패키지로 rollback한다.
- 제한형 AI는 승인된 비민감 시험 scope의 근거 포함 참고 요약으로만 허용하며 자동 조치에 연결하지 않는다. 그 외 파일럿에서는 외부 호출을 비활성으로 유지한다.
- 화면과 입력 UX는 단말 거치 위치, 장갑 사용, 네트워크 단절, 실제 입력 가능 순간을 관찰해 공통 제품·설정/교육·현장 전용 요구로 나눠 반영한다.

실행 체크리스트와 완료 판정은 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)을 단일 기준으로 사용한다.

## 2026-07-16. AI ground-truth 정량 회귀와 provider 운영 착수는 결합 게이트로 판정

- 승인 ground-truth 하한은 8범주 × `NORMAL`/`EXCLUSION`/`CONFLICT` × 각 2건인 총 48건으로 고정한다. 총량뿐 아니라 24개 조합별 하한을 모두 만족해야 하며 실제 익명 현장 표본으로 교체·확장한다.
- 승인 시 기대 포함 근거를 현재 candidate, source/version/trace ID, content hash, 승인자 권한과 `as_of`로 검증해 고정한다. 제외 근거도 실제 원천으로 역추적되어야 하고 `CONFLICT` case는 최소 두 근거를 요구한다.
- 릴리스 품질 임계값은 candidate ID/hash와 ranking 안정성, top-k 포함률, 인용 trace·의미 일치, 상충 표시 100%와 제외 근거 노출·권한 누출·존재하지 않는 인용 0건이다. 실패 run과 case는 삭제하거나 성공 결과로 덮어쓰지 않는다.
- provider/model별 계약, 보존, 학습 사용, 처리 지역, TLS, timeout, 429/5xx, 비용, kill switch, 법무와 고객 승인을 versioned checklist로 기록한다. 기술·보안·법무·고객 네 영역과 체크리스트가 모두 승인되기 전에는 데이터 회귀가 통과해도 운영 provider client를 활성화하지 않는다.
- 첫 운영 범위는 근거 검색과 `참고 요약`인 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`뿐이다. 안전·품질 자동 판정, 작업 지시 변경과 자동 조치는 이 승인에 포함되지 않는다.

## 2026-07-16. WPF controlled copy와 Android 본문 열람은 같은 원칙의 별도 계약

- 두 기능은 현재 공개 버전만 허용하고 단기 1회 token, 사용자·세션 바인딩, 크기·SHA-256 재검사, `no-store`, 접근 감사를 적용한다는 공통 보안 원칙을 공유한다.
- WPF controlled copy는 관리자급 role의 통제된 파일 사본이며 `attachment` 응답과 파일명을 제공한다. Android는 현장 role과 필수 승인 단말에 묶인 앱 내부 열람이며 `inline` 응답, 파일명 비노출, 외부 열기·공유 금지, 화면 캡처 차단과 자동 정리가 필요하다.
- 목적, 허용 role, 단말 필수 여부와 클라이언트 수명주기가 다르므로 controlled copy endpoint와 grant table을 재사용하지 않는다. Android는 `android_document_view_grants`와 Android 전용 grant/stream endpoint를 사용한다.
- Android 스트림 시점에 계정·세션·단말 활성 상태와 현재 공개 버전을 다시 조회한다. 공개 해제, 새 버전 공개, 사용자/세션/단말 비활성화 뒤에는 이미 발급된 grant도 거부한다.
- Android 임시 본문은 앱 내부 캐시의 난수 파일로만 유지하고 종료·만료·비활성화·오류·로그아웃·다음 시작에 정리한다. `FLAG_SECURE`는 기본 캡처 방지 수단이며 루팅·변조 단말과 외부 촬영까지 막는 DRM으로 간주하지 않는다.

## 2026-07-13. controlled copy는 짧은 만료의 1회성 인증 스트리밍 사용

- 사내 서버 운영의 controlled copy는 일반 정적 파일 URL이나 로컬 원본 복사가 아니라 기본 60초의 1회성 티켓 발급 후 인증 스트리밍으로 제공한다.
- 티켓은 사용자와 로그인 세션, 선택한 문서/버전에 묶고 원문 대신 SHA-256만 DB에 저장한다. 다른 사용자·세션, 만료, 재사용, Range 요청은 차단한다.
- controlled copy 대상은 삭제되지 않은 현재 `PUBLISHED` 문서의 정확한 공개 버전 하나로 제한한다. 저장 경로 경계, 크기 제한, 파일 SHA-256은 발급과 전송 시점에 다시 검사한다.
- 요청·허용·완료·실패·차단은 `document_access_logs`와 `activity_history`에 사용자, 세션 단말, 문서 버전, 접속 정보, 사유와 함께 남긴다. 존재하지 않는 문서 요청은 문서 외래키가 없으므로 `activity_history`에 남긴다.
- WPF 허용 role 버튼은 서버 API와 서버 ID 매핑을 사용하고 비허용 role은 기존 로컬 차단 안내와 접근 로그 흐름을 유지한다.
## 2026-07-21. 서버 epoch와 승인형 reconciliation

- 서버 URL만으로 동기화 연속성을 판단하지 않고, DB에 보존되는 불변 instance ID와 운영 복구 때 증가시키는 epoch를 함께 사용한다.
- epoch 변경이나 cursor 역행은 자동 복구하지 않는다. 전송과 polling을 함께 멈추고, idempotency key/hash 기반 전수 판정 후 관리자 승인으로만 binding을 교체한다.
- `CONFIRMED`는 새 ID/revision에 재결합하고 `ABSENT`는 기존 key로 재전송한다. `DIVERGED`는 충돌로 영구 보존하며 서버 또는 로컬 payload를 암묵적으로 선택하지 않는다.
