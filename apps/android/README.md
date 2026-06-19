# Android App

Android 앱은 현재 활성 개발 대상이 아니다. 현장 테스트와 초기 배포는 WPF 또는 Avalonia 기반 설치형 클라이언트를 기준으로 진행한다.

## 보류 시 참고 책임

- 최신 문서 목록과 상세 조회
- HWP, Word, PowerPoint, Excel, PDF, DWG 등 문서 열람 또는 외부 뷰어 연계
- 문서 변경 알림 확인
- 현재 문서에 연결된 현장 코멘트, 작업 평가, 문제점 등록
- 정형 문구 선택 방식의 빠른 입력
- AI가 제공한 작업 전 주의 사항 확인

현장 사용자 단말기는 로컬 파일 감시와 문서 업로드를 수행하지 않는다.

## 보류 기준

- 언어: Kotlin
- 서버 연동: Python FastAPI 서버와 REST API로 통신
- 기본 문서 열람은 서버가 제공하는 파일/미리보기 API를 사용하고, 단말기 파일 동기화는 최소화한다.

## 디렉터리

- `src/main/kotlin/`: Android Kotlin 소스
- `src/main/res/`: Android 리소스
- `docs/`: Android 앱이 필요해질 때의 구현 메모와 화면 흐름
