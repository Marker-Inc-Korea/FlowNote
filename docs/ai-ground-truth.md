# AI 준비 ground-truth와 48건 회귀 기준

외부 provider를 운영 연결하기 전에 근거 검색 품질을 같은 snapshot에서 반복 평가한다. 기준 매트릭스는 안전, 품질, 설비 이상, 작업 보류, 재작업, 인수인계, 최신 공개 문서, 상충 기록의 8범주와 `NORMAL`, `EXCLUSION`, `CONFLICT` 3유형을 조합하고 각 칸에 2건씩 둬 총 48건이다.

## 사례 계약

각 사례는 고객, 현장, 선택적 라인, 경로·자격정보를 노출하지 않는 DB fingerprint, `as_of`, 중복 없는 case key, 허용 순위 범위를 가진다. 기대 포함/제외 reference는 source type/ID/version ID, trace ID/version ID, content SHA-256과 사람이 작성한 근거를 보존한다. 제외 사례에는 정책상 제외 사유도 필수다.

`ai_search_ground_truth_provenance`는 질문 본문과 분리해 다음을 보존한다.

- 데이터 분류: `SYNTHETIC`, `TEST`, `ANONYMOUS_FIELD`, `PILOT`
- 준비도 계열: `SYNTHETIC`/`TEST`는 `SMOKE_REGRESSION`, `ANONYMOUS_FIELD`/`PILOT`은 `FIELD_READINESS`
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

시드는 공개 문서 근거와 민감정보 형태, 고객 식별자 형태, 로컬 경로, 권한 밖 채널, 삭제/비공개 문서, `EXCLUDED`/`ARCHIVED` FieldComment 부정 근거를 함께 만든다. 모든 값은 합성 시험값이며 `TEST`/`SMOKE_REGRESSION` provenance를 가진다.

`scripts/sql/verify-ai-ground-truth-48.sql`은 48건 수, 24칸×2건, case key 중복, 승인자 중복, provenance·snapshot hash, reference hash·근거, 원천 orphan을 검사한다. Python 검증기는 같은 48건을 두 번 평가하고 candidate ID/content hash/rank 변화가 없는지 확인한다. 두 실행 모두 top-k 포함, 인용 trace, 의미 일치, 상충 표시가 100%이고 권한 누출, 존재하지 않는 인용, 제외 원천 노출이 0건이어야 통과한다.

오늘 사진/인수인계 문서와 기존 과거 문서 버전 증가는 Windows 통합 스모크의 기존 폴더 규칙을 그대로 따른다. 이 AI 시드는 그 문서 구조에 새 스모크 전용 업무 폴더를 만들지 않으며, 부족한 현장 자료를 합성 데이터로 실제 현장 준비도에 올리지 않는다.
