# 2026-06-24 FieldComment 분리와 빌드 테스트 기록

이 문서는 FieldComment 도메인 분리 작업을 현재 코드 기준으로 정리한 기록이다.

## 분리 기준

- FieldComment는 문서 버전의 부속 메모가 아니라 현장 원천 기록이다.
- 하나의 FieldComment는 문서와 연결될 수 있고, 공정, 설비, 품목, 오류 유형 등 태그성 정보로 보완할 수 있다.
- FieldComment는 관리자 검토와 분석을 통해 보고서 초안이나 정제 문서의 근거가 될 수 있다.
- 사진이나 파일은 `field_comment_attachments`로 별도 관리한다.

## 서버 구현

- `POST /api/v1/field-comments`로 FieldComment를 등록한다.
- `GET /api/v1/field-comments`와 `GET /api/v1/documents/{document_id}/field-comments`로 목록을 조회한다.
- `PATCH /api/v1/field-comments/{comment_id}`로 관리자 검토와 분석 상태를 갱신한다.
- 일괄 검토, 원천 hash 감사, 오래된 NEW·근거 부족·보고서 원천 누락 작업함과 품질 지표 API를 제공한다.
- 첨부는 `POST /api/v1/field-comments/{comment_id}/attachments`와 목록 조회 API로 관리한다.
- AI 근거 후보와 외부 AI 질의 snapshot에는 관리자 검토 상태가 `ANALYZED`, `REVIEWED`, `SELECTED`인 FieldComment만 적격 원천으로 사용한다.
- 외부 AI 질의 시에는 작성자 계정·role, 연결 채널 멤버십과 활성 고객·현장 민감정보 정책도 다시 검사한다.

## Windows 구현

- Windows 앱은 `field_comments`와 `field_comment_attachments` 로컬 테이블을 사용한다.
- 현장 코멘트 입력, 조회, 첨부, 이력 기록은 로컬 SQLite에 누적된다.
- 테스트 중 생성된 코멘트와 첨부 산출물은 삭제하지 않는다.
