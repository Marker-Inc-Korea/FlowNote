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

## 비민감 48건 시드와 검증

다음 명령은 이름에 `test`가 포함된 DB만 허용한다. 기존 DB와 실행 이력은 지우지 않고 `smoke48-v1` 고정 case key로 수렴한다. 별도 업무 폴더나 고객 식별자를 만들지 않는다.

```bash
services/api/.venv/bin/python scripts/seed-ai-ground-truth-48.py
services/api/.venv/bin/python scripts/verify-ai-ground-truth-48.py
```

시드는 공개 문서 근거와 민감정보 형태, 고객 식별자 형태, 로컬 경로, 권한 밖 채널, 삭제/비공개 문서, `EXCLUDED`/`ARCHIVED` FieldComment 부정 근거를 함께 만든다. 모든 값은 합성 시험값이며 `TEST`/`SMOKE_REGRESSION` provenance를 가진다.

`scripts/sql/verify-ai-ground-truth-48.sql`은 48건 수, 24칸×2건, case key 중복, 승인자 중복, provenance·snapshot hash, reference hash·근거, 원천 orphan을 검사한다. Python 검증기는 같은 48건을 두 번 평가하고 candidate ID/content hash/rank 변화가 없는지 확인한다. 두 실행 모두 top-k 포함, 인용 trace, 의미 일치, 상충 표시가 100%이고 권한 누출, 존재하지 않는 인용, 제외 원천 노출이 0건이어야 통과한다.

오늘 사진/인수인계 문서와 기존 과거 문서 버전 증가는 Windows 통합 스모크의 기존 폴더 규칙을 그대로 따른다. 이 AI 시드는 그 문서 구조에 새 스모크 전용 업무 폴더를 만들지 않으며, 부족한 현장 자료를 합성 데이터로 실제 현장 준비도에 올리지 않는다.
