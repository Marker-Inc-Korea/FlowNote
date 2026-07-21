# FieldComment 검토·분석·선정 운영

이 문서는 FieldComment 원천 기록을 관리자 해석과 섞지 않고 보고서 근거로 정제하는 운영 기준이다.

## 원천과 해석의 분리

- 원천 영역은 대상 문서/버전, 유형, 입력 방식, 신호등, 원문, 작성자·실제 작업자·대리 입력자, 단말, 위치, 등록 시각이다. 생성 후 수정·삭제하지 않으며 서버 ORM 불변 검사와 `source_hash_sha256`으로 검증한다.
- 관리자 영역은 담당자, 검토 기한, 정리 내용, 분석 내용, 상태, 변경 사유, 분석자·검토자와 각 시각이다.
- 모든 관리자 변경은 `activity_history`에 변경 전·후 snapshot, actor, 사유를 남긴다. 두 snapshot의 원천 hash는 같아야 한다.
- 검토 snapshot의 서버 권위 기준은 `review_revision`이다. WPF는 읽은 `review_revision`을 `baseReviewRevision`으로, 큐의 안정 키를 `mutationKey`로 보내며 서버는 compare-and-swap으로 revision을 1만 증가시킨다. 같은 mutation/의도 재시도는 receipt를 반환하고, 다른 의도 재사용이나 오래된 revision은 409로 보존한다.

## 상태 전이와 권한

주 흐름은 `NEW → ANALYZED → REVIEWED → SELECTED`이다. `NEEDS_REVIEW`는 정보 보강을 기다리는 운영 보류 상태이며 `EXCLUDED`는 오입력·중복·근거 부적합 결정, `ARCHIVED`는 선정 또는 제외 결정이 끝난 장기 보관 상태다.

| 전이 | 허용 역할 | 필수 조건 |
|---|---|---|
| `NEW/NEEDS_REVIEW → ANALYZED` | `line-foreman`, `team-lead` 이상 분석 역할 | 분석 내용, 3자 이상 사유. 담당자·검토 기한 미지정은 작업함 경고 |
| `ANALYZED → REVIEWED` | `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager` | 정리·분석 내용, 검토자, 3자 이상 사유 |
| `REVIEWED → SELECTED` | 위 결정 역할 | 정리·분석, 원천 작성자, 관찰 문서 버전, 원천 hash 일치, 3자 이상 사유 |
| 활성 상태 → `EXCLUDED` | 위 결정 역할 | 중복·오입력·범위 밖·근거 부족 중 하나를 명시한 제외 사유 |
| `SELECTED/EXCLUDED → ARCHIVED` | 위 결정 역할 | 후속 보고서 또는 제외 결정 확인, 보관 사유 |

되돌림은 `ANALYZED → NEW/NEEDS_REVIEW`, `REVIEWED → ANALYZED`, `SELECTED → REVIEWED`, `EXCLUDED → NEW`, `ARCHIVED → EXCLUDED`만 허용한다. FastAPI 일괄 API는 요청당 최대 200건이며 각 대상의 현재 `review_revision`을 1 증가시키고, 항목별로 같은 규칙을 모두 통과해야 한 transaction으로 저장하며 각 원천별 감사 이력을 남긴다. 일괄 API에는 항목별 base revision과 mutation receipt가 없다. WPF의 다중 선택 저장은 선택 항목을 순서대로 로컬 저장하고 개별 PATCH/재시도 큐로 동기화한다.

## 승인자와 SLA

- `NEW` 등록 시 라인 또는 공정 책임자가 담당자를 지정하고 1영업일 안에 `ANALYZED` 또는 `NEEDS_REVIEW`로 분류한다. 적색 신호, 안전 우려, 생산 중단·보류는 2시간 안에 우선 분류한다.
- `ANALYZED`는 결정 역할 검토자가 2영업일 안에 `REVIEWED`, `EXCLUDED` 또는 정보 보강을 위한 `NEEDS_REVIEW`로 판정한다.
- `REVIEWED`는 보고서 책임자가 2영업일 안에 `SELECTED` 또는 `EXCLUDED`로 확정한다. `SELECTED`는 보고서에 자동 포함한다는 뜻이 아니라 적격 후보 확정이다.
- 담당자 부재, 휴무 또는 조직 변경 시 상위 관리자가 담당자와 기한을 다시 지정한다. 기존 기한과 변경 사유는 감사 이력에 남기며 과거 초과를 지우지 않는다.
- SLA 시간은 서버에 저장된 UTC 시각으로 계산하고 화면에서 현장 시간대로 표시한다. 현재 구현 지표는 달력일 기준이며 영업일·휴일 달력 적용은 배포 현장 설정 후속 항목이다.

## 예외와 재개

- 사진·문서 버전·작업자 확인이 부족하면 `NEEDS_REVIEW`로 보류하고 필요한 근거와 재개 담당자·기한을 사유에 적는다. 근거가 보완되면 `NEW → ANALYZED` 주 흐름으로 재개한다.
- 잘못 제외한 원천은 `EXCLUDED → NEW`, 잘못 보관한 원천은 `ARCHIVED → EXCLUDED → NEW`로만 재개한다. 중간 상태를 건너뛰지 않는다.
- 서버와 WPF 상태가 충돌하면 원천 본문을 병합하지 않는다. 서버 원천 hash와 로컬 원천 hash를 먼저 대조하고, 관리자 해석 영역만 최신 서버 revision에서 재시도하거나 서버본 유지로 감사 종결한다.
- 충돌 해결자는 해당 라인 책임자 또는 보고서 책임자이며 최종 `SELECTED/EXCLUDED` 결정 충돌은 결정 역할 보유자만 종결한다. WPF는 자동으로 `NEW → ANALYZED → REVIEWED` 단계를 보간하지 않는다. 해결자는 서버 snapshot을 새로 읽고 담당자·기한·정리·분석을 함께 비교한 뒤 `재적용`, `서버본 유지`, `재검토 전환` 중 하나와 사유를 감사에 남긴다.
- 원천 보완, 담당자 변경, 기한 재산정, 분석 근거 변경, 충돌 해결로 결론이 달라질 가능성이 있으면 재검토한다. 단순 오탈자라도 이미 `SELECTED`인 원천의 관리자 해석을 바꿀 때는 `REVIEWED`로 되돌린 뒤 다시 선정한다.
- 원천 hash 불일치, 관찰 문서 버전 누락, 권한 부족은 재시도로 우회하지 않는다. 품질 작업함에서 원인을 해소한 뒤 같은 idempotency key로 다시 전송한다.

## 관리자 작업함

- 목록은 상태, 담당자, 문서, 작성자, 라인, 설비, 공정, 오류 유형, 기간, 오래된 NEW, 첨부 유무, 보고서 연결 여부와 `UNREVIEWED`, `OVERDUE`, `UNASSIGNED`, `MISSING_EVIDENCE`, `DUPLICATE_SUSPECTED`, `REPORT_UNLINKED` 작업함 플래그로 필터링한다.
- `priorityOrder=true`일 때 기한 초과, 담당자 없음, 근거 누락, 중복 의심, 미검토, 보고서 미연결 순으로 가중치를 합산하고 높은 항목부터 표시한다. 이 점수는 사실 판정이 아니라 관리자 처리 순서다.
- 품질 작업함은 `OLD_NEW`, `WEAK_SELECTED`, `MISSING_REPORT_SOURCE`, `INCOMPLETE_REPORT_TRACE`, `SOURCE_HASH_MISMATCH`를 제공한다.
- 품질 지표는 상태·신호등·actor·라인·오류 유형 분포, 문서↔FieldComment와 FieldComment↔보고서 연결률, 2종 이상 source 보고서 비율, source type 수, orphan 비율, 라인·설비·품목·공정·오류 유형 태그 축 커버리지를 산출한다.

## 보고서 선정과 역추적

- 보고서의 `FIELD_COMMENT` source는 `SELECTED`만 허용하며 연결 시 해당 FieldComment의 `document_version_id`를 `report_sources.source_version_id`에 고정한다.
- `DOCUMENT` source는 현재 `PUBLISHED` 버전만 허용한다. 비공개 문서와 최신 작업중 버전, 과거 공개본이 아닌 버전은 후보에 섞지 않는다.
- 초안 생성과 승인에는 서로 다른 source type이 최소 2종 필요하다. 같은 `source_type + source_id + source_version_id` 중복은 거부한다.
- 각 `report_sources` row는 독립 `trace_id`, 고정 `source_version_id`, 저장 시점 `source_hash_sha256`를 가진다. 승인 직전에 현재 원천을 다시 계산해 version 또는 hash가 달라지면 409로 차단한다.
- 보고서 aggregate는 `report_revision`, 정규화 내용의 `content_hash_sha256`, 정렬된 source tuple의 `source_set_hash_sha256`를 가진다. 승인 시 보고서, source, 생성 문서/버전, mutation receipt를 같은 DB transaction으로 확정한다.
- 보고서 선정 뒤 원천 상태·version·hash가 바뀌면 기존 초안을 자동 갱신하거나 과거 snapshot으로 승인하지 않는다. 저장을 `REPORT_SOURCE_STALE_OR_ORPHAN` 409로 멈추고 원천을 재검토한 뒤 새 source-set hash로 새 보고서 mutation을 만든다. 이미 승인된 보고서는 원래 source snapshot을 보존하고 정정 보고서로 연결한다.
- source에 연결된 활성 업무 채널이 있으면 `admin`, `system-admin` 외 사용자는 활성 채널 멤버여야 한다.
- `GET /api/v1/field-comments/{comment_id}/traceability`와 WPF `서버 역추적`은 원천 hash, 상태 전이 감사, 보고서 source, 생성된 최종 문서와 모든 문서 버전 ID를 한 흐름으로 보여준다.
- WPF 보고서 저장 결과는 보고서 ID, 생성 문서 ID와 각 source의 type/id/version/trace ID/hash를 함께 표시한다. 이 화면에서 확인한 FieldComment ID를 관리자 검토 화면의 서버 역추적으로 조회하면 반대 방향 연결도 확인할 수 있다.

## 보고서 폐기와 source 보존

- 승인된 보고서는 source 집합을 교체하지 않는다. 같은 idempotency key 재시도는 기존 보고서·문서·source를 반환하며 승인된 draft ID를 다시 저장하려는 요청은 거부한다.
- 보고서를 `ARCHIVED`로 폐기해도 `report_sources`, trace ID, source version/hash, 생성 문서 버전과 승인 감사는 삭제하지 않는다. 폐기는 검색·운영 사용 중단이지 근거 삭제가 아니다.
- 원천 FieldComment는 보고서 폐기, 재생성, 동기화 충돌 해결 중에도 수정·삭제하지 않는다. 새 해석이나 정정은 관리자 영역의 새 이력 또는 새 보고서로 남긴다.

## 품질 지표 계산 기준

- FieldComment↔보고서 연결률은 `report_sources.source_type = FIELD_COMMENT`인 distinct `source_id` 수를 전체 FieldComment 수로 나눈다. 한 원천을 여러 보고서가 사용해도 분자는 1이다.
- 2종 이상 근거 보고서 비율은 보고서별 distinct `source_type >= 2`인 보고서 수를 전체 보고서 수로 나눈다. row 수가 2개여도 같은 type이면 충족하지 않는다.
- orphan 비율은 부모 보고서가 없거나 source type별 원천 row가 없는 `report_sources` 수를 전체 source 수로 나눈다.
- hash 불일치 수는 고정 `source_hash_sha256`와 현재 동일 version 원천의 재계산 hash가 다른 source 수다. 원천 또는 version 자체가 없으면 orphan/trace 누락으로 먼저 센다.
- SLA 초과 수는 종결 상태가 아닌 항목 중 `review_due_at < now`인 수다. 담당자 없음은 활성 항목 중 `assigned_to IS NULL`인 수다.
- 비율은 분모가 0이면 0으로 표시한다. 모든 count는 서버 SQLite 기준이며 WPF 로컬 누적값과 합산하지 않고 동기화 격차는 별도 큐 지표로 본다.
