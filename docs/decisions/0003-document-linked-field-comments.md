# 0003. 문서 연결형 현장 코멘트와 정형 문구

## 상태

Accepted

## 결정

현장 코멘트, 작업 평가, 문제점은 `FieldNote`로 관리한다.

`FieldNote`는 다음을 참조할 수 있다.

- 연결 문서
- 연결 문서 버전
- 선택한 정형 문구
- 입력 단말기
- 입력자
- 실제 전달자 또는 작업자/작업그룹
- 관리자 분석 내용

현장 사용자는 신호등식 상태, 짧은 문구 직접 입력, `CommentTemplate` 선택 중 하나로 등록할 수 있다. 현장 사용자가 직접 입력하기 어려운 경우 관리자가 현장에서 전달받은 내용을 대신 입력할 수 있다. 관리자는 원문을 검토하고 `normalized_content`로 정리하며, 필요 시 `analysis_content`로 판단과 분석을 남긴다.

## 근거

현장에서는 긴 입력이 어렵고, 실시간 입력은 작업 흐름에 직접 들어가야 하므로 초기 안착이 어렵다. 신호등식 기록과 정형 문구는 입력 부담을 줄이고 데이터 품질을 높인다. 관리자 대리 입력은 현장에서 아직 말로 전달되는 내용을 시스템에 남기기 위한 현실적인 중간 단계이다. 원문, 정리 문구, 관리자 분석을 분리하면 현장의 실제 표현을 보존하면서 보고서 품질을 개선할 수 있다.

## 결과

- `FieldNote.raw_content`, `FieldNote.normalized_content`, `FieldNote.analysis_content`를 분리한다.
- `FieldNote.author_id`, `reported_by`, `operator_id`로 입력자와 실제 전달자 또는 작업자/작업그룹을 구분한다.
- `FieldNote.input_mode`는 `signal`, `free_text`, `template`, `template_with_text`, `admin_proxy`, `mes_integration`을 고려한다.
- 정형 문구는 `CommentTemplate`로 관리한다.
- 문서별 코멘트 조회 API를 제공한다.
