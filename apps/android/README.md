# Android App

Android 앱은 Kotlin 기반 현장 사용자 단말기이다. UI는 WebView를 기본으로 사용한다.

## 예상 책임

- 최신 문서 목록과 상세 조회
- HWP, Word, PowerPoint, Excel, PDF, DWG 등 문서 열람 또는 외부 뷰어 연계
- 문서 변경 알림 확인
- 현재 문서에 연결된 현장 코멘트, 작업 평가, 문제점 등록
- 정형 문구 선택 방식의 빠른 입력
- AI가 제공한 작업 전 주의 사항 확인

현장 사용자 단말기는 로컬 파일 감시와 문서 업로드를 수행하지 않는다.

## 기술 기준

- 언어: Kotlin
- UI 표시: Android WebView
- 웹 UI와 네이티브 기능은 JavaScript bridge로 연동
- 기본 문서 열람은 서버 기반 웹 뷰어를 사용하고, 단말기 파일 동기화는 최소화한다.
