# FieldComment 검토·분석·선정 운영

이 문서는 FieldComment 원천 기록을 관리자 해석과 섞지 않고 보고서 근거로 정제하는 운영 기준이다.

## 원천과 해석의 분리

- 원천 영역은 대상 문서/버전, 유형, 입력 방식, 신호등, 원문, 작성자·실제 작업자·대리 입력자, 단말, 위치, 등록 시각이다. 생성 후 수정·삭제하지 않으며 서버 ORM 불변 검사와 `source_hash_sha256`으로 검증한다.
- 관리자 영역은 담당자, 검토 기한, 정리 내용, 분석 내용, 상태, 변경 사유, 분석자·검토자와 각 시각이다.
- 모든 관리자 변경은 `activity_history`에 변경 전·후 snapshot, actor, 사유를 남긴다. 두 snapshot의 원천 hash는 같아야 한다.

## 상태 전이와 권한

주 흐름은 `NEW → ANALYZED → REVIEWED → SELECTED`이다. `NEEDS_REVIEW`는 정보 보강을 기다리는 운영 보류 상태이며 `EXCLUDED`는 오입력·중복·근거 부적합 결정, `ARCHIVED`는 선정 또는 제외 결정이 끝난 장기 보관 상태다.

| 전이 | 허용 역할 | 필수 조건 |
|---|---|---|
| `NEW/NEEDS_REVIEW → ANALYZED` | 조장·반장 이상 문서 운영 역할 | 분석 내용, 3자 이상 사유 |
| `ANALYZED → REVIEWED` | 관리자·부서 관리자·문서 관리자 계열 | 정리·분석 내용, 3자 이상 사유 |
| `REVIEWED → SELECTED` | 관리자·부서 관리자·문서 관리자 계열 | 정리·분석, 원천 작성자, 문서 버전, 3자 이상 사유 |
| 활성 상태 → `EXCLUDED` | 관리자·부서 관리자·문서 관리자 계열 | 제외 사유 |
| `SELECTED/EXCLUDED → ARCHIVED` | 관리자·부서 관리자·문서 관리자 계열 | 보관 사유 |

되돌림은 `ANALYZED → NEW/NEEDS_REVIEW`, `REVIEWED → ANALYZED`, `SELECTED → REVIEWED`, `EXCLUDED → NEW`, `ARCHIVED → EXCLUDED`만 허용한다. FastAPI 일괄 API는 요청당 최대 200건이며 항목별로 같은 규칙을 모두 통과해야 한 트랜잭션으로 저장하고 각 원천별 감사 이력을 남긴다. WPF의 다중 선택 저장은 선택 항목을 순서대로 로컬 저장하고 개별 PATCH/재시도 큐로 동기화한다.

## 관리자 작업함

- 목록은 상태, 담당자, 문서, 작성자, 라인, 설비, 공정, 오류 유형, 기간, 오래된 NEW, 첨부 유무, 보고서 연결 여부와 `UNREVIEWED`, `OVERDUE`, `UNASSIGNED`, `MISSING_EVIDENCE`, `DUPLICATE_SUSPECTED`, `REPORT_UNLINKED` 작업함 플래그로 필터링한다.
- `priorityOrder=true`일 때 기한 초과, 담당자 없음, 근거 누락, 중복 의심, 미검토, 보고서 미연결 순으로 가중치를 합산하고 높은 항목부터 표시한다. 이 점수는 사실 판정이 아니라 관리자 처리 순서다.
- 품질 작업함은 `OLD_NEW`, `WEAK_SELECTED`, `MISSING_REPORT_SOURCE`를 제공한다.
- 품질 지표는 상태·신호등·actor·라인·오류 유형 분포, 문서↔FieldComment와 FieldComment↔보고서 연결률, 2종 이상 source 보고서 비율, source type 수, orphan 비율, 라인·설비·품목·공정·오류 유형 태그 축 커버리지를 산출한다.

## 보고서 선정과 역추적

- 보고서의 `FIELD_COMMENT` source는 `SELECTED`만 허용하며 연결 시 해당 FieldComment의 `document_version_id`를 `report_sources.source_version_id`에 고정한다.
- `DOCUMENT` source는 현재 `PUBLISHED` 버전만 허용한다. 비공개 문서와 최신 작업중 버전, 과거 공개본이 아닌 버전은 후보에 섞지 않는다.
- source에 연결된 활성 업무 채널이 있으면 `admin`, `system-admin` 외 사용자는 활성 채널 멤버여야 한다.
- `GET /field-comments/{comment_id}/traceability`와 WPF `서버 역추적`은 원천 hash, 상태 전이 감사, 보고서 source, 생성된 최종 문서와 모든 문서 버전 ID를 한 흐름으로 보여준다.
