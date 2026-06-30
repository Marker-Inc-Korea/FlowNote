# 2026-06-24 인코딩과 상태 값 정리

이 문서는 인코딩 문제와 상태 값 정리 기록을 현재 코드 기준으로 갱신한 것이다.

## 인코딩 기준

- Markdown 문서는 UTF-8 한글로 작성한다.
- UI에 표시되는 창 제목, 메뉴, 버튼, 라벨, 컬럼명, 상태 문구, 오류 문구는 한글을 기본으로 한다.
- 한글 의미가 부정확하거나 현장/기술 표준 용어상 영문이 더 명확한 경우에만 영문을 사용한다.

## 현재 상태 값 기준

- 문서 상태: `WORKING`, `IN_REVIEW`, `PUBLISHED`, `ARCHIVED`
- 문서 버전 상태: `WORKING`, `IN_REVIEW`, `APPROVED`, `PUBLISHED`, `SUPERSEDED`, `ARCHIVED`
- FieldComment 상태: `NEW`, `NEEDS_REVIEW`, `ANALYZED`, `REVIEWED`, `SELECTED`, `EXCLUDED`, `ARCHIVED`
- 작업순서 항목 상태: `WAITING`, `IN_PROGRESS`, `HOLD`, `COMPLETED`
- 작업순서 보드 상태: `ACTIVE`, `ARCHIVED`
- 알림 후보 상태: `CANDIDATE`, `SENT`, `DISMISSED`

## 명칭 기준

현장 코멘트 도메인 명칭은 `FieldComment`, `field_comments`, `field-comments`를 사용한다. 새 작업에서 `FieldNote`, `field_notes`, `field-notes`, `FIELD_NOTE`를 사용하지 않는다.
