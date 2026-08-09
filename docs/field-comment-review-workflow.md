# FieldComment 검토·분석·선정 운영

이 문서는 2026-08-09 현재 FastAPI FieldComment 검토 API·데이터 모델과 WPF 관리자 검토 화면을 기준으로, FieldComment 원천 기록을 관리자 해석과 섞지 않고 보고서 근거로 정제하는 운영 계약을 정리한다.

## 원천과 해석의 분리

- 원천 영역은 대상 문서/버전, 유형, 입력 방식, 신호등, 원문, 작성자·실제 작업자·대리 입력자, 단말, 위치, 등록 시각이다. 생성 후 수정·삭제하지 않으며 서버 ORM 불변 검사와 `source_hash_sha256`으로 검증한다.
- 관리자 영역은 담당자, 검토 기한, 정리 내용, 분석 내용, 상태, 변경 사유, 분석자·검토자와 각 시각이다.
- 모든 관리자 변경은 `activity_history`에 변경 전·후 snapshot, actor, 사유를 남긴다. 두 snapshot의 원천 hash는 같아야 한다.
- 검토 snapshot의 서버 권위 기준은 `review_revision`이다. WPF는 읽은 `review_revision`을 `baseReviewRevision`으로, 큐의 안정 키를 `mutationKey`로 보내며 서버는 compare-and-swap으로 revision을 1만 증가시킨다. 같은 mutation/의도 재시도는 receipt를 반환하고, 다른 의도 재사용이나 오래된 revision은 409로 보존한다.

## 상태 전이와 권한

주 흐름은 `NEW → ASSIGNED → ANALYZED → REVIEWED → SELECTED`이다. 담당자 지정 없이 바로 분석할 수 있어 `NEW → ANALYZED`도 허용한다. `ASSIGNED`는 기존 SQLite 호환을 위해 물리 `NEW + assigned_to`로 저장하고 API·감사·화면에서 논리 상태로 노출한다. `NEEDS_REVIEW`는 정보 보강 또는 상충 판단을 기다리는 운영 보류 상태다.

| 전이 | 허용 역할 | 필수 조건 |
|---|---|---|
| `NEW/NEEDS_REVIEW → ASSIGNED` | `line-foreman`, `team-lead` 이상 분석 역할 | 유효한 `assignedTo`, 3자 이상 배정 사유 |
| `NEW/NEEDS_REVIEW → ANALYZED` | `line-foreman`, `team-lead` 이상 분석 역할 | 분석 내용, 3자 이상 사유. 담당자·검토 기한 미지정은 작업함 경고 |
| `ANALYZED → REVIEWED` | `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager` | 정리·분석 내용, 검토자, 3자 이상 사유. `red` 또는 상충 원천은 분석자와 다른 결정자 |
| `REVIEWED → SELECTED` | 위 결정 역할 | 정리·분석, 원천 작성자, 관찰 문서 버전, 원천 hash 일치, 3자 이상 사유 |
| 활성 상태 → `EXCLUDED` | 위 결정 역할 | 중복·오입력·범위 밖·근거 부족 중 하나를 명시한 제외 사유 |
| `SELECTED/EXCLUDED → ARCHIVED` | 위 결정 역할 | 후속 보고서 또는 제외 결정 확인, 보관 사유 |

되돌림은 `ASSIGNED → NEW`, `ANALYZED → NEW/NEEDS_REVIEW`, `REVIEWED → ANALYZED`, `SELECTED → REVIEWED`, `EXCLUDED → NEW`, `ARCHIVED → EXCLUDED`만 허용한다. `/bulk-review/preview`는 최대 200개 항목의 허용 전이와 실패 코드·사유를 쓰기 없이 반환한다. `/bulk-review/execute`는 항목별 `baseReviewRevision`과 고유 `mutationKey`를 검사하고 항목별 transaction으로 처리한다. 한 항목이 stale/권한/조건 실패여도 다른 성공을 되돌리지 않으며 입력 순서대로 성공 여부, 새 revision, receipt, 최초 응답 snapshot을 보존한다. 기존 원자형 `/bulk-review`는 호환 경로로만 유지한다.

## 승인자와 SLA

- `NEW` 등록 시 라인 또는 공정 책임자가 담당자를 지정하고 1영업일 안에 `ANALYZED` 또는 `NEEDS_REVIEW`로 분류한다. 적색 신호, 안전 우려, 생산 중단·보류는 2시간 안에 우선 분류한다.
- `ANALYZED`는 결정 역할 검토자가 2영업일 안에 `REVIEWED`, `EXCLUDED` 또는 정보 보강을 위한 `NEEDS_REVIEW`로 판정한다.
- `REVIEWED`는 보고서 책임자가 2영업일 안에 `SELECTED` 또는 `EXCLUDED`로 확정한다. `SELECTED`는 보고서에 자동 포함한다는 뜻이 아니라 적격 후보 확정이다.
- 담당자 부재, 휴무 또는 조직 변경 시 상위 관리자가 담당자와 기한을 다시 지정한다. 기존 기한과 변경 사유는 감사 이력에 남기며 과거 초과를 지우지 않는다.
- SLA 시간은 서버에 저장된 UTC 시각으로 계산하고 화면에서 현장 시간대로 표시한다. 현재 구현 지표는 달력일 기준이며 영업일·휴일 달력 적용은 배포 현장 설정 후속 항목이다.

## 예외와 재개

- 사진·문서 버전·작업자 확인이 부족하면 `NEEDS_REVIEW`로 보류하고 필요한 근거와 재개 담당자·기한을 사유에 적는다. 근거가 보완되면 `NEW → ANALYZED` 주 흐름으로 재개한다.
- 잘못 제외한 원천은 `EXCLUDED → NEW`, 잘못 보관한 원천은 `ARCHIVED → EXCLUDED → NEW`로만 재개한다. 중간 상태를 건너뛰지 않는다.
- 서버와 WPF 상태가 충돌하거나 현장 진술이 상충하면 원천 본문을 병합하지 않는다. `conflict_flag`로 `CONFLICT / 검토 필요`를 표시하고 `conflict_basis`에 상충 지점·판단 근거·선정/제외 사유를 남긴다. `red` 신호 또는 상충 표지가 있는 원천을 `REVIEWED`, `SELECTED`, `EXCLUDED`, `ARCHIVED`로 바꿀 때는 분석자와 다른 사용자가 결정해야 하며 판단 근거도 필수다.
- 충돌 해결자는 해당 라인 책임자 또는 보고서 책임자이며 최종 `SELECTED/EXCLUDED` 결정 충돌은 결정 역할 보유자만 종결한다. WPF는 자동으로 `NEW → ANALYZED → REVIEWED` 단계를 보간하지 않는다. 해결자는 서버 snapshot을 새로 읽고 담당자·기한·정리·분석을 함께 비교한 뒤 `재적용`, `서버본 유지`, `재검토 전환` 중 하나와 사유를 감사에 남긴다.
- WPF 동기화는 `ANALYZED`, `REVIEWED`, `SELECTED` 전이를 하나로 합치지 않고 단계마다 별도 큐 기록과 mutation key를 남긴다. 직접 서버를 검토할 때는 확인하지 않은 `baseReviewRevision`을 임의 값으로 보내지 않으며 동기화 큐는 저장해 둔 기준 revision을 그대로 사용한다. `red` 또는 상충 원천의 분석과 결정은 서로 다른 로그인 계정으로 수행한다.
- 원천 보완, 담당자 변경, 기한 재산정, 분석 근거 변경, 충돌 해결로 결론이 달라질 가능성이 있으면 재검토한다. 단순 오탈자라도 이미 `SELECTED`인 원천의 관리자 해석을 바꿀 때는 `REVIEWED`로 되돌린 뒤 다시 선정한다.
- 원천 hash 불일치, 관찰 문서 버전 누락, 권한 부족은 재시도로 우회하지 않는다. 품질 작업함에서 원인을 해소한 뒤 같은 idempotency key로 다시 전송한다.

## 관리자 작업함

- WPF FieldComment 검토 화면 상단은 서버 권위 `review-dashboard`와 AI 준비도 응답을 함께 읽어 미검토, 상충, 빨간 신호·상충 기반 안전/품질 위험, 활성 보고서 미연결, 담당자 없음, 기한 초과 수를 표시한다. 각 수치는 바로 해당 작업함을 열며 검토 상태 분포와 담당자·다음 조치를 같은 화면에서 확인한다. 서버에 연결할 수 없으면 로컬 수치나 합성 수치로 대신 채우지 않고 `실제 서버 집계 없음`으로 표시한다.
- 같은 화면의 AI 준비도는 후속 참고 영역으로만 표시하며 FieldComment 작업함 조회·처리 가능 여부를 좌우하지 않는다. AI 준비도 조회가 실패해도 서버 FieldComment 집계와 작업함은 유지한다. 참고 수치는 고객 승인 `ANONYMOUS_FIELD / FIELD_READINESS` 48건과 부족한 8범주×3유형 칸만 기준으로 삼고 `SYNTHETIC`·`TEST / SMOKE_REGRESSION`은 실제 현장 준비도에 더하지 않는다.
- 목록은 상태, 담당자, 담당 역할, 신호등, 채널, 문서·버전, 작성자, 태그, 라인, 설비, 공정, 오류 유형, 등록 기간, 검토 기한, 오래된 NEW, 첨부 유무, 보고서 연결 여부와 `CONFLICT`, `UNREVIEWED`, `OVERDUE`, `UNASSIGNED`, `MISSING_EVIDENCE`, `DUPLICATE_SUSPECTED`, `REPORT_UNLINKED` 작업함 플래그로 필터링한다. 서버 목록은 `priorityMin/priorityMax`도 지원한다.
- `priorityOrder=true`일 때 상충, 기한 초과, 담당자 없음, 근거 누락, 중복 의심, 미검토, 보고서 미연결 순으로 가중치를 합산한다. WPF의 `우선순위/작업함` 보기와 SQLite에 보존되는 `저장된 보기`가 같은 필터를 재사용한다.
- 선택 상세는 원천 hash, 검토 revision, 첨부 수, 관찰 문서 버전, 담당 역할, 연결 채널과 접근 권한을 서버에서 읽어 표시한다. 빨간 신호 또는 상충 기록은 분석자와 다른 결정 역할 사용자가 처리해야 한다는 안내를 상태 선택 영역에 계속 표시한다. 다중 선택은 사전검증 표를 확인한 뒤 실행하며 부분 성공 표를 닫아도 서버 receipt와 revision은 보존된다.
- 품질 작업함은 `OLD_NEW`, `WEAK_SELECTED`, `MISSING_REPORT_SOURCE`, `INCOMPLETE_REPORT_TRACE`, `SOURCE_HASH_MISMATCH`, `SOURCE_REVISION_MISMATCH`를 제공한다.
- 품질 지표는 상태·신호등·actor·라인·오류 유형 분포, 문서↔FieldComment와 FieldComment↔보고서 연결률, 2종 이상 source 보고서 비율, source type 수, orphan 비율, 라인·설비·품목·공정·오류 유형 태그 축 커버리지를 산출한다.

## 보고서 선정과 역추적

- 보고서의 `FIELD_COMMENT` source는 `SELECTED`만 허용하며 연결 시 해당 FieldComment의 `document_version_id`를 `report_sources.source_version_id`에 고정한다.
- `DOCUMENT` source는 현재 `PUBLISHED` 버전만 허용한다. 비공개 문서와 최신 작업중 버전, 과거 공개본이 아닌 버전은 후보에 섞지 않는다.
- WPF 화면은 작업순서 변경 이력을 보고서 후보로 제공한다. Core는 `WORK_SEQUENCE_ITEM`을 받으면 서버의 현재 항목과 최신 변경 기록을, `WORK_SEQUENCE_HISTORY`를 받으면 선택한 변경 기록의 존재와 ID를 저장 전에 확인한다.
- 초안 생성과 승인에는 서로 다른 source type이 최소 2종 필요하다. 같은 `source_type + source_id + source_version_id` 중복은 거부한다.
- 각 `report_sources` row는 독립 `trace_id`, 고정 `source_version_id`, FieldComment의 `source_revision`, 저장 시점 `source_hash_sha256`를 가진다. source 요청의 선택적 `sourceRevision/sourceHashSha256`가 현재 값과 다르면 고정 단계부터 409다. 승인 및 파일 생성 직전에 상태·version·revision·hash·채널 권한을 다시 읽어 하나라도 달라지면 409로 차단한다.
- 생성된 최종 보고서 문서 본문에도 source type/ID/version/revision/trace/hash를 기록하므로 최종 문서에서 FieldComment 원문·첨부·관찰 문서 버전까지 역추적한다.
- 보고서 aggregate는 `report_revision`, 정규화 내용의 `content_hash_sha256`, 정렬된 source tuple의 `source_set_hash_sha256`를 가진다. 승인 시 보고서, source, 생성 문서/버전, mutation receipt를 같은 DB transaction으로 확정한다.
- 보고서 선정 뒤 원천 상태·version·hash가 바뀌면 기존 초안을 자동 갱신하거나 과거 snapshot으로 승인하지 않는다. 저장을 `REPORT_SOURCE_STALE_OR_ORPHAN` 409로 멈추고 원천을 재검토한 뒤 새 source-set hash로 새 보고서 mutation을 만든다. 이미 승인된 보고서는 원래 source snapshot을 보존하고 정정 보고서로 연결한다.
- source에 연결된 활성 업무 채널이 있으면 `admin`, `system-admin` 외 사용자는 활성 채널 멤버여야 한다.
- `GET /api/v1/field-comments/{comment_id}/traceability`와 WPF `원천 연결 확인`은 원천 본문·hash·검토 revision, 첨부와 파일 hash, 관찰 문서·버전, 관련 작업순서, 상태 전이 감사, 보고서의 고정 source version/revision/hash/trace ID, 생성된 최종 문서를 한 상세 흐름으로 보여준다.
- WPF 보고서 저장 결과는 보고서 ID, 생성 문서 ID와 각 source의 type/id/version/trace ID/hash를 함께 표시한다. 이 화면에서 확인한 FieldComment ID를 관리자 검토 화면의 서버 역추적으로 조회하면 반대 방향 연결도 확인할 수 있다.

## 보고서 폐기와 source 보존

- 승인된 보고서는 source 집합을 교체하지 않는다. 같은 idempotency key 재시도는 기존 보고서·문서·source를 반환하며 승인된 draft ID를 다시 저장하려는 요청은 거부한다.
- 보고서를 `ARCHIVED`로 폐기해도 `report_sources`, trace ID, source version/hash, 생성 문서 버전과 승인 감사는 삭제하지 않는다. 폐기는 검색·운영 사용 중단이지 근거 삭제가 아니다.
- 원천 FieldComment는 보고서 폐기, 재생성, 동기화 충돌 해결 중에도 수정·삭제하지 않는다. 새 해석이나 정정은 관리자 영역의 새 이력 또는 새 보고서로 남긴다.

확정 보고서의 오류는 보관이나 제자리 수정으로 처리하지 않는다. 상세 화면의 `정정본 만들기`에서 위험 설명을 확인하고 정정 사유를 입력하면 독립 `DRAFT`가 생성된다. 기준 보고서의 FieldComment source는 당시 snapshot 그대로 복사하되 생성·재검토·확정 직전에 현재 `SELECTED` 상태, `review_revision`, 원천 hash와 채널 권한을 다시 검사한다. 달라진 source는 자동 제외하지 않고 기존 확정본 보존 → 담당 검토자 문의 → `현재 원천 선택`에서 전체 source 다시 선택 순서로 안내한다.

정정본 승인 전에는 기존 확정본이 유효하다. 정정본을 다시 검토하고 확정하면 이전 보고서는 `대체됨`, 이전 생성 문서는 `보관`, 새 생성 문서는 `검토중`으로 표시한다. FieldComment 상세의 보고서 역추적과 보고서 계보에서는 이전·현재 source와 생성 문서를 모두 조회할 수 있다.

## 품질 지표 계산 기준

- FieldComment↔보고서 연결률은 `report_sources.source_type = FIELD_COMMENT`인 distinct `source_id` 수를 전체 FieldComment 수로 나눈다. 한 원천을 여러 보고서가 사용해도 분자는 1이다.
- 2종 이상 근거 보고서 비율은 보고서별 distinct `source_type >= 2`인 보고서 수를 전체 보고서 수로 나눈다. row 수가 2개여도 같은 type이면 충족하지 않는다.
- orphan 비율은 부모 보고서가 없거나 source type별 원천 row가 없는 `report_sources` 수를 전체 source 수로 나눈다.
- hash 불일치 수는 고정 `source_hash_sha256`와 현재 동일 version 원천의 재계산 hash가 다른 source 수다. 원천 또는 version 자체가 없으면 orphan/trace 누락으로 먼저 센다.
- SLA 초과 수는 종결 상태가 아닌 항목 중 `review_due_at < now`인 수다. 담당자 없음은 활성 항목 중 `assigned_to IS NULL`인 수다.
- 비율은 분모가 0이면 0으로 표시한다. 모든 count는 서버 SQLite 기준이며 WPF 로컬 누적값과 합산하지 않고 동기화 격차는 별도 큐 지표로 본다.

## 사람형 시나리오와 품질 측정

- 역할별 시나리오는 라인 책임자의 배정, 분석자의 정상/상충 분석, 결정자의 선정/제외, 보고서 책임자의 source 고정·저장, 권한 없는 사용자의 차단을 포함한다.
- 각 시나리오는 시작·완료 UTC, 활성 작업 시간, 화면 이동 수, 서버 왕복 수, 재시도 수, 도움 요청 수, 실패 코드, blocker 등급을 동일 `run_id`로 기록한다. 치명적 blocker, 원천/receipt 유실, 중복 생성, 권한 우회 허용치는 모두 0건이다.
- 장애 주입은 정상, 일부 실패, stale revision, 성공 응답 유실 후 같은 mutation key 재시도, draft 뒤 source revision 변경을 각각 수행한다. 완료 조건은 200개 입력 ID와 200개 결과 행의 일대일 대응, 성공 receipt 유일성, 원천 변경 저장 409, 재검토·새 draft 뒤 저장 성공이다.
- 상태 분포와 SLA 초과 수는 `/quality-metrics` 및 목록 `overdue=true` 결과를 SQLite의 논리 상태 `CASE WHEN status='NEW' AND assigned_to IS NOT NULL THEN 'ASSIGNED' ELSE status END`, `review_due_at < now` 읽기 전용 집계와 교차 확인한다.

## 역할별 실제 화면 순서

| 역할 | 대표 업무 | 화면 순서 | 완료 표시 |
| --- | --- | --- | --- |
| 작업자 | 짧은 현장 기록과 사진 | 공개 문서 목록 → 문서 상세/보안 뷰어 → 신호등 또는 기본 정형 문구 → 짧은 메모 → 사진 촬영/확인 → 전송 상태 | 로컬 outbox ID와 서버 FieldComment/attachment ID가 1:1이고 재연결 뒤 중복이 없음 |
| 조장·반장 | 분류·담당·기한·근거 보강 | 채널/알림 → FieldComment 검토 → 품질 작업함 → 원천/첨부 확인 → 담당·기한 → 정리·분석 → 상태·사유 저장 | 새 `review_revision`, mutation receipt, 감사 이력과 원천 hash 동일성이 보임 |
| 문서관리자 | 선정 원천을 보고서로 확정 | FieldComment 검토의 `SELECTED` 후보 → 서버 역추적 → 보고서 초안 → 서로 다른 source 2종 이상 선택 → 초안 생성 → 고정 근거 확인 → 문서 저장 → 최종 역추적 | 각 source의 ID/version/revision/hash와 저장 뒤 trace ID·생성 문서 ID가 보임 |

작업자는 장갑 착용/미착용, 한 손 사용, 고정 거치/손에 든 상태, 사진 있음/없음, 연결/단절을 나누어 수행한다. 조장·반장과 문서관리자는 정상 단건, 200건 일괄, 일부 실패, stale revision, 권한 변경, 성공 응답 유실을 각각 수행한다. 같은 역할·시나리오는 익명 참여자 또는 실행 회차를 바꿔 최소 2회 반복한다.

## 품질 임계값과 우선순위 검증

| 품질 이슈 | 기본 임계값 | 현장 확인 질문 | 처리 |
| --- | --- | --- | --- |
| `OLD_NEW` | 기본 7일, 현장 승인값으로 1~3650일 | 실제 미처리 위험 순서와 일치하는가 | 담당·기한 지정 또는 분석/보류 |
| `WEAK_SELECTED` | 문서 버전·작성자·분석·첨부·단계별 감사 중 하나라도 부족 | 첨부 없는 선정이 합리적인 예외인가 | 보강 또는 `REVIEWED`로 되돌림 |
| `MISSING_REPORT_SOURCE` | 참조 원천 row 0건 | 삭제·복구·잘못된 ID 중 무엇인가 | 승인 차단, orphan 원인 조사 |
| `INCOMPLETE_REPORT_TRACE` | trace ID/version/revision 중 하나라도 없음 | 최종 문서에서 원천까지 한 번에 도달하는가 | 승인 차단, 새 source snapshot 생성 |
| `SOURCE_HASH_MISMATCH` | 고정 hash와 현재 원천 hash 불일치 1건 이상 | 원천 불변 위반인가 잘못된 고정값인가 | 즉시 중단, 원천·감사 교차 비교 |
| `SOURCE_REVISION_MISMATCH` | 고정 선정 revision과 현재 revision 불일치 1건 이상 | 선정 뒤 관리자 해석이 바뀌었는가 | 재검토하고 새 초안 생성 |

서버 품질 작업함의 개별 이슈와 WPF 필터 결과 수를 비교한다. `MISSING_REPORT_SOURCE`처럼 로컬 FieldComment row가 없는 이슈는 WPF 전체 품질 이슈 표에서 보고서 ID와 원인을 확인하며, 로컬 검토 목록에 억지로 가상 원천을 만들지 않는다. 파일럿에서는 오래된 NEW·근거 부족 SELECTED 표본을 각각 5건 이상 섞고, 현장 우선순위와 다른 결과를 관찰 항목으로 남긴다.

## 일괄 처리와 보고서 예외 UX

- 사전검증은 요청 ID와 결과 ID의 집합·행 수를 먼저 확인한다. 실행은 `requested_count = items.count = success_count + failure_count`와 결과 행별 성공 판정을 모두 확인한 뒤 성공 행만 로컬에 적용한다.
- stale revision과 권한 변경은 실패 행에 코드·원인·복구 안내를 표시한다. 오류 안내는 `무엇이 실패했는지 → 무엇이 보존됐는지 → 누가 처리해야 하는지 → 사용자가 지금 할 수 있는 일` 순서를 사용한다. stale revision은 자동 덮어쓰기나 로컬 권한 우회를 제공하지 않고 서버 원문 재조회와 로컬 입력 비교를 요구한다.
- 실행 응답을 정상적으로 받으면 성공 행의 재확인 상태를 즉시 해제하고 `재전송 안 함`으로 표시한다. 실패 행만 `재조회 후 다시 선택`, `관리자 확인 후 다시 선택` 또는 `실패 항목만 다시 선택`으로 구분하고 WPF 목록에서 다시 선택한다. 사용자가 일괄 저장을 다시 누를 때는 이 실패 항목만 최신 revision과 새 mutation key로 요청한다.
- 실행 성공 뒤 응답 자체가 유실된 경우에만 WPF의 `일괄 결과 다시 확인`이 원래 전체 요청과 mutation key를 그대로 재전송한다. 새 key로 전체를 반복하지 않으며 서버 receipt의 최초 응답 snapshot으로 결과를 복구한다. 응답을 한 번 확인한 뒤에는 이 버튼을 비활성화한다.
- 보고서 초안 생성은 선택한 source의 서버 ID/version/revision/hash를 고정하고 `고정 근거 확인` 표에 적격 여부를 표시한다. source type이 2종 미만이거나 WPF에서 검증할 수 없는 유형은 저장하지 않는다.
- 저장 직전 같은 source를 다시 조회한다. 서버에 연결할 수 없거나 상태, 공개 version, 선정 revision, 작업순서 변경 기록 또는 hash가 초안 시점과 다르면 로컬 보고서 파일과 동기화 큐를 만들기 전에 중단하고 새 초안을 요구한다.

## UX 측정과 개발 항목 전환

`role-metrics.csv`에는 성공 여부와 소요 시간 외에 재시도, 도움 요청, 화면 이동 수를 기록한다. `role-observations.csv`에는 장갑, 거치 위치, 한 손 사용, 사진 촬영, 짧은 메모, 신호등식 입력, 네트워크 상태를 각각 명시한다. 화면 녹화 또는 시간 기록은 같은 `run_id` 아래 상대경로로 연결한다.

FieldComment가 들어가는 UX BEFORE는 `WPF-DOCUMENT-FIELD-COMMENT`, `WPF-HANDOVER-FOLLOW-UP`, 관리자용 `WPF-REVIEW-REPORT` 또는 비관리자용 `WPF-REVIEW-REPORT-PERMISSION`을 역할별로 2회 이상 측정한다. 각 원시 행에는 실행 폴더와 같은 `pilot_run_id`, 익명 참여자, 조건·시도 번호, `MEASURED`, 시간대 포함 시작·완료 시각, 장갑·한 손·거치·연결 조건, 완료 시간, 화면 이동, 재시도, 도움 요청, 실제 FieldComment·인수인계·보고서 source ID와 화면·감사 증거가 있어야 한다.

비관리자 검토·보고서 시나리오의 기대 결과와 실제 결과는 모두 `HTTP_403`이다. 이 403은 권한 우회가 차단된 성공 결과이며 기능 실패로 분류하지 않는다. 반대로 403 없이 관리 기능에 들어가거나 원천·receipt가 유실된 경우에는 보안 또는 데이터 손실 후보로 즉시 분류한다.

모든 관찰은 `development-items.csv`의 항목 하나와 1:1로 연결한다. 결정은 `ACCEPTED(수용)`, `REJECTED(불수용)`, `REVIEW(검토)` 중 하나이며 결정 근거, P0~P3, 영향 역할, 원천 보존 위험, 담당, 기한, 측정 가능한 완료 기준을 반드시 남긴다. `common_product`는 현장과 무관하게 제품에 반영할 요구, `configuration_or_training`은 단말 설정과 교육, `site_layout`은 거치 위치와 현장 동선에 관한 요구다. `classification_basis`에는 이 판단 근거를 적으며 한 현장의 거치 위치, 동선, 교육 수준이나 표현 선호만으로 `common_product`를 선택하지 않는다.

운영·보안·현장 검토자는 원시 행과 개발 항목을 함께 확인한다. 참여자 대응표가 Git 또는 공용 로그에 없는지, 측정하지 않은 값을 0이나 성공으로 채우지 않았는지, 화면 증거와 source ID가 같은 `run_id`인지, 원천 보존 위험을 낮춰 적지 않았는지를 검토한 뒤 `pilot-run.json.ux_before_baseline.review_approvals`에 각각 서명한다. 이 승인은 전체 파일럿 통과가 아니라 신뢰할 수 있는 BEFORE와 후속 개발 항목 확정에 대한 승인이다.

현재 보존된 실제 파일럿 실행에는 수용된 P0/P1 개발 항목과 역할별 BEFORE 원시 행이 없다. 따라서 코드·계약 검증 결과를 AFTER로 대체하지 않으며, `comparison_id`와 `development_cycle_id` 연결, 동일 참여자·역할·시나리오·조건의 AFTER 2회 측정, 중앙 완료 시간·화면 이동·도움 요청 비교는 계속 `미측정`으로 둔다.
