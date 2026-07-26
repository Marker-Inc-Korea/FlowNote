# AI 준비 ground-truth와 48건 회귀 기준

이 문서는 2026-07-26 현재 `ai_search` API, WPF `AI 정답셋`, 시드·검증 스크립트 구현 기준이다. 실제 현장 데이터셋·승인자·provider 심사가 아직 없는 부분은 운영 착수 조건으로 구분한다.

외부 provider를 운영 연결하기 전에 근거 검색 품질을 같은 snapshot에서 반복 평가한다. 기준 매트릭스는 안전, 품질, 설비 이상, 작업 보류, 재작업, 인수인계, 최신 공개 문서, 상충 기록의 8범주와 `NORMAL`, `EXCLUSION`, `CONFLICT` 3유형을 조합하고 각 칸에 2건씩 둬 총 48건이다.

## 사례 계약

각 사례는 고객, 현장, 선택적 라인, 경로·자격정보를 노출하지 않는 DB fingerprint, `as_of`, 중복 없는 case key, 허용 순위 범위를 가진다. 기대 포함/제외 reference는 source type/ID/version ID, trace ID/version ID, content SHA-256과 사람이 작성한 근거를 보존한다. 제외 사례에는 정책상 제외 사유도 필수다.

`ai_search_ground_truth_provenance`는 질문 본문과 분리해 다음을 보존한다.

- 데이터 분류: `SYNTHETIC`, `TEST`, `ANONYMOUS_FIELD`, `PILOT`
- 준비도 계열: `SYNTHETIC`/`TEST`는 `SMOKE_REGRESSION`, `ANONYMOUS_FIELD`/`PILOT`은 `FIELD_READINESS`. 다만 승인 `FIELD_READINESS` dataset 구성과 provider 착수 48건에는 고객 승인을 받은 `ANONYMOUS_FIELD`만 허용
- 원천 snapshot hash, 비민감 여부, provenance 설명
- 첫 승인자/시각과 서로 다른 두 번째 승인자/시각
- `PENDING_SECOND_APPROVAL`, `APPROVED`, `REJECTED` 상태

첫 승인만 받은 사례는 비활성이고 준비도·평가 세트에 포함하지 않는다. 두 번째 승인자가 첫 승인자와 다를 때만 활성화한다. 서로 다른 준비도 계열의 사례를 한 평가 run에 섞지 않는다. 스모크 회귀 48건 통과는 실제 현장 자료 48건 확보를 뜻하지 않으며 provider 착수 판정에는 `FIELD_READINESS`만 사용한다.

## Windows 운영 흐름

WPF `AI 정답셋` 화면의 `사례·원천 구성` 창은 서버 `ai_search_candidates`와 현재 scope의 사례 풀을 함께 조회한다. 포함 근거는 후보 목록에서 선택하고, 제외 근거는 실제 source type/ID와 선택적 version ID, 서버가 판정하는 제외 사유 코드, 운영자 근거 설명을 입력한다. 사례 등록 시 서버가 후보 적격성, 승인자의 접근권한, `as_of`, 원천 존재, content hash와 provenance를 검증하며 등록자는 첫 승인자로 기록된다. `NORMAL`은 포함 근거 1건 이상, `EXCLUSION`은 제외 근거 1건 이상, `CONFLICT`는 포함 근거 2건 이상이 필요하다.

사례 등록과 사례 2차 승인은 보고서 작성 role인 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`가 수행할 수 있다. 사례 풀은 기본적으로 활성 사례만 반환하고 운영 창에서는 `includePending=true`로 미승인 사례까지 조회한다. 두 번째 승인자는 첫 승인자와 달라야 하며, 서버는 고정된 포함·제외 원천과 접근권한을 다시 검사한 뒤 사례를 활성화한다.

dataset 운영은 사례 승인과 별도 권한 경계를 사용한다. 위 보고서 작성 role은 dataset 작성·구성·검토를 수행할 수 있지만 `FIRST_APPROVE`, `SECOND_APPROVE`, `RETIRE`는 `admin`, `system-admin`, `document-admin`, `department-manager`만 수행한다. 작성자·검토자·두 승인자는 모두 서로 달라야 하고 이 분리는 서버 상태 전이와 DB 제약으로 함께 보호된다. 대체본은 같은 고객·현장·DB·라인·준비도 계열과 같은 dataset key의 승인·대체·폐기 version만 참조할 수 있다.

## 비민감 48건 시드와 검증

다음 명령은 이름에 `test`가 포함된 DB만 허용한다. 기존 DB와 실행 이력은 지우지 않고 `smoke48-v1` 고정 case key로 수렴한다. 별도 업무 폴더나 고객 식별자를 만들지 않는다.

```bash
services/api/.venv/bin/python scripts/seed-ai-ground-truth-48.py
services/api/.venv/bin/python scripts/verify-ai-ground-truth-48.py
```

시드는 기존 FieldComment 정제의 6개 슬롯(`NORMAL` 2, `EXCLUSION` 2, `CONFLICT` 2)을 아래 8범주에 각각 배분한다. 따라서 범주당 6건, 전체 48건이며 고정 case key와 고정 업무 idempotency key를 재사용한다.

| 범주 | `NORMAL-01/02` | `EXCLUSION-01/02` | `CONFLICT-01/02` |
| --- | --- | --- | --- |
| 안전 `SAFETY` | 분석/검토 FieldComment | 제외 FieldComment + 비공개·정책 부정 원천 | 공개 안전 문서 + 선정 FieldComment + 작업순서 + 보고서 source |
| 품질 `QUALITY` | 분석/검토 FieldComment | 제외 판정 + 상충 미해결 부정 원천 | 공개 검사 기준 + 선정 품질 기록 + 작업순서 + 보고서 source |
| 설비 이상 `EQUIPMENT_ANOMALY` | 분석/검토 FieldComment | 제외 판정 + 다른 설비/비공개 부정 원천 | 공개 점검 기준 + 선정 설비 기록 + 작업순서 + 보고서 source |
| 작업 보류 `WORK_HOLD` | 분석/검토 FieldComment | 제외 판정 + 사유/권한 부적합 원천 | 보류 문서 + 선정 기록 + `HOLD` 이력 + 보고서 source |
| 재작업 `REWORK` | 분석/검토 FieldComment | 제외 판정 + 원문/정책 부적합 원천 | 공개 검사 기준 + 선정 재작업 기록 + 작업순서 + 보고서 source |
| 인수인계 `HANDOVER` | 분석/검토 FieldComment | 제외 판정 + 비공개/권한 밖 원천 | 공개 인수인계 기준 + 선정 후속 기록 + 작업순서 + 보고서 source |
| 최신 공개 문서 `LATEST_PUBLISHED_DOCUMENT` | 분석/검토 FieldComment | 삭제·비공개 version + 제외 기록 | 현재 공개 version + 선정 기록 + 작업순서 + 보고서 source |
| 상충 기록 `CONFLICTING_RECORDS` | 분석/검토 FieldComment | 제외 판정 + 정책 부정 원천 | 서로 다른 고정 원천을 함께 표시하는 복합 근거 |

48개 FieldComment의 승인 상태 분포는 `ANALYZED 8`, `REVIEWED 8`, `SELECTED 16`, `EXCLUDED 16`이다. `NEW`를 매번 늘리는 방식은 사용하지 않는다. 각 행은 `assigned_to`, `review_due_at`, `last_transition_reason`, `activity_history.before_value/after_value`의 동일 source SHA-256을 보존한다. `SELECTED` 16건은 범주·variant별 보고서에 사용하고 각 보고서는 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_HISTORY` 세 source type을 가진다. source마다 고정 version ID, 저장 시점 source hash와 독립 trace ID를 보존한다.

시드는 공개 문서 근거와 민감정보 형태, 고객 식별자 형태, 로컬 경로, 권한 밖 채널, 삭제/비공개 문서, `EXCLUDED`/`ARCHIVED` FieldComment 부정 근거를 함께 만든다. 모든 값은 합성 시험값이며 `TEST`/`SMOKE_REGRESSION` provenance를 가진다. 문서에는 `equipment`, `item`, `process`, `error_type` 네 축의 도메인 태그를 연결하며 고객 문서 트리나 BOM 구조를 만들거나 강제하지 않는다.

`scripts/sql/verify-ai-ground-truth-48.sql`은 48건 수, 24칸×2건, case key 중복, 승인자 중복, provenance·snapshot hash, reference hash·근거, 원천 orphan에 더해 다음을 검사한다.

- 48개 matrix FieldComment와 네 상태 분포, 담당자·기한·전이 사유
- 감사 before/after source hash 동일성과 고정 idempotency key 중복 0건
- 범주별 2개, 전체 16개 보고서와 보고서당 source type 2종 이상
- 모든 report source의 고정 version, 64자리 source hash, trace ID
- 문서별 설비/품목/공정/오류 유형 중 최소 2개 태그 축

Python 검증기는 같은 48건을 두 번 평가하고 candidate ID/content hash/rank 변화가 없는지 확인한다. 두 실행 모두 top-k 포함, 인용 trace, 의미 일치, 상충 표시가 100%이고 권한 누출, 존재하지 않는 인용, 제외 원천 노출이 0건이어야 통과한다. 실행별 JSON은 Git 제외 경로 `data/local/ai-smoke-regression/`에 새 파일로 누적하며 category, scenario type, 기대 reference의 source/version/trace/hash, 실제 후보와 판정을 모두 남긴다. readiness API의 `field_readiness.ground_truth_count`와 `smoke_regression_readiness.ground_truth_count`를 별도로 기록하고 `provider_start_ready=false`, 외부 질의의 `AI_EXTERNAL_CALL_DISABLED`를 함께 확인한다.

지표 산출 기준은 `scripts/sql/verify-ai-ground-truth-48.sql`과 `GET /api/v1/ai-search/readiness`이다. SQL의 모든 `*_violation`/`*_gap_count`가 0이고 API 평가 지표가 `1.0/0건` 기준을 만족해야 `SMOKE_REGRESSION`만 통과한다. `ground_truth_count`, `ground_truth_gap`, `provider_start_ready`는 오직 `FIELD_READINESS` 계열로 산출되므로 합성 48건을 더하는 SQL이나 API 경로는 허용하지 않는다.

오늘 사진/인수인계 문서와 기존 과거 문서 버전 증가는 Windows 통합 스모크의 기존 폴더 규칙을 그대로 따른다. 이 AI 시드는 그 문서 구조에 새 스모크 전용 업무 폴더를 만들지 않으며, 부족한 현장 자료를 합성 데이터로 실제 현장 준비도에 올리지 않는다.

## 실제 현장 준비도 검증

실제 익명 현장 또는 제한 파일럿 사례는 시드하지 않는다. 운영자가 승인한 `FIELD_READINESS` dataset version을 만든 뒤 다음 검증기를 실행한다. 비밀번호는 명령행이나 파일에 넣지 않고 지정 환경 변수로만 전달한다.

```bash
FLOWNOTE_FIELD_READINESS_VERIFY_PASSWORD='...' \
services/api/.venv/bin/python scripts/verify-ai-field-readiness.py \
  --database /approved/local/path/flownote.sqlite3 \
  --dataset-version-id aigdataset_... \
  --customer-scope CUSTOMER_SCOPE --site-scope SITE_SCOPE \
  --line-scope LINE_SCOPE --username verifier-account
```

검증기는 승인 dataset과 고객·현장·선택적 라인·DB fingerprint를 정확히 결합한다. SQL 단계에서 48건, 24칸×2건, case key 중복, 작성자/검토자/1차/2차 승인자 분리, `ANONYMOUS_FIELD` provenance, snapshot/reference hash, 제외 이유와 네 원천 orphan을 검사한다. 이어 외부 호출을 비활성화한 `FAKE` adapter로 같은 dataset snapshot을 두 번 평가해 candidate ID/content hash/rank의 `previous_run_delta`, top-k, citation trace·의미 일치, 상충 표시와 세 가지 0건 위반 지표를 확인한다. 실제 원천이나 승인자가 부족하면 실패 상태를 그대로 유지하며 합성 사례나 `PILOT` 사례를 이 48건에 보충하지 않는다.

## 실제 익명 현장 원천의 책임과 반출 금지

실제 현장 원천은 고객의 서면 승인을 받은 범위에서만 `ANONYMOUS_FIELD` 또는 제한 파일럿 `PILOT`으로 등록한다. 익명화 책임자는 고객이 지정한 현장 데이터 책임자이고 FlowNote 운영 담당자는 익명화 결과의 형식·추적값·승인 상태만 확인한다. 실제 담당자 이름, 승인 문서 번호와 유효기간은 고객별 비공개 운영대장에 기록하며 저장소 문서에는 쓰지 않는다. 현재 실제 담당자와 승인 값은 정해지지 않았으므로 상태는 `PENDING`이다.

다음 정보가 남아 있으면 익명 현장셋으로 반입하지 않는다.

- 고객명·협력사명·공장명·주소·계약번호·고객이 식별자로 지정한 코드
- 성명, 사번, 전화번호, 이메일, 얼굴, 차량번호와 개인을 알아볼 수 있는 자유서술
- 계정, 비밀번호, API key, token, 인증서·개인키, 내부 URL, 로컬 절대경로
- 고객이 대외비·영업비밀·수출통제 대상으로 지정한 원문이나 승인 범위 밖 사진·첨부
- 삭제·비공개 문서, `EXCLUDED`/`ARCHIVED` FieldComment, 접근권한 밖 채널과 라인의 내용

승인 원천은 승인된 고객 서버 안에서 익명화하고 원본 파일이나 원문 DB를 개발 저장소·개인 PC·공용 메신저·이메일·외부 AI 서비스로 반출하지 않는다. 검증 환경에는 승인된 최소 발췌와 source/version/trace/hash만 옮긴다. DB fingerprint는 경로나 접속 문자열이 아니라 `database_scope()`가 만든 driver+hash를 사용한다. 반출 금지 대상이 발견되면 해당 case는 활성화하지 않고 `PENDING` 또는 `REJECTED`로 남긴 뒤 고객 책임자에게 되돌린다.

## 독립 표본 검토 양식과 불일치 처리

승인된 `FIELD_READINESS` dataset snapshot을 동일하게 통과한 두 evaluation run 가운데 하나를 표본 검토 run으로 고정한다. 결과를 보기 전에 표본 계획 참조를 확정하고 24개 범주·유형 칸마다 1건씩 총 24건을 선택한다. 두 검토자는 같은 case 목록을 서로 독립적으로 확인하고 다음 항목을 case별로 기록한다.

| 필드 | 기록 기준 |
| --- | --- |
| dataset/run | `dataset_version_id`, dataset snapshot hash, 두 번의 비교 run ID, 검토 대상 run ID |
| 표본 계획 | 변경 불가능한 `samplingPlanReference`, 24개 case key와 sample hash |
| 인용 추적 | source/version/trace/content hash가 승인 원천으로 이어지면 `PASS`, 아니면 `FAIL` |
| 인용 의미 | 질문·기대 근거·실제 후보의 의미가 일치하면 `PASS`, 아니면 `FAIL` |
| 상충 표시 | `CONFLICT` case에서 양쪽 근거와 상충이 드러나면 `PASS`, 아니면 `FAIL`; 다른 유형은 `NOT_APPLICABLE` |
| 권한 경계 | 제외 근거·권한 밖 원천이 노출되지 않으면 `PASS`, 아니면 `FAIL` |
| 검토 메모 | 판단 근거를 재검토할 수 있는 짧은 설명. 원문 개인정보나 고객 식별정보는 복제하지 않음 |

`POST /api/v1/ai-search/field-readiness/sample-reviews`는 두 독립 검토자의 표본·판정을 `ai_field_readiness_sample_reviews`에 각각 보존한다. 첫 검토만 있을 때는 다른 사용자의 조회 응답에서 판정과 decision hash를 숨기고 표본 계획·case 목록만 제공한다. 두 결과가 같으면 `COMPLETED`다. 하나라도 다르면 `PENDING_CONSENSUS`이며 불일치 case key를 그대로 보존한다. 이 상태를 임의로 `PASS`로 바꾸지 않는다. 합의가 필요한 경우 앞선 두 사람과 다른 제3 검토자가 불일치 case만 다시 판정하고 두 review ID를 연결한다. 제3 기록이 없으면 provider 착수 게이트는 계속 닫힌다. 원래 두 판정은 수정하거나 삭제하지 않는다.

작성자·dataset 검토자·1차 승인자·2차 승인자는 모두 달라야 한다. 표본의 두 검토자도 서로 달라야 하며 제3 합의자는 두 표본 검토자와 달라야 한다. 실제 사용자 배정이 끝나지 않은 상태는 `PENDING`이고 대리 계정이나 공용 계정으로 분리를 충족한 것으로 보지 않는다.

## Dataset 교체 주기

정기 교체 검토는 분기 1회 실시한다. 다음 사건이 발생하면 정기일을 기다리지 않고 새 dataset version을 만든다.

- 문서 분류·권한 정책, 고객·현장·라인 scope 또는 DB fingerprint 변경
- 48건 가운데 원천 version/hash가 바뀌거나 원천이 폐기·비공개·권한 밖으로 전환
- 후보 생성·순위·인용·상충 판정 정책의 의미 있는 변경
- 익명화 누락, 권한 누출, 존재하지 않는 인용, 제외 근거 노출 발견
- 고객 승인 만료·철회 또는 표본 검토 불일치의 재발

승인 dataset은 제자리 수정하지 않는다. 같은 dataset key의 다음 version에 교체 사유와 `replaces_dataset_version_id`를 남기고 사례 48건·24칸, 네 사람의 dataset 역할 분리, 동일 snapshot 2회 평가와 독립 표본 검토를 다시 완료한다. 이전 version과 evaluation·검토 기록은 `SUPERSEDED` 이력으로 보존한다.
