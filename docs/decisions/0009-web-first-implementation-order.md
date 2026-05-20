# 0009. Web 우선 구현 단계

## 상태

Accepted

## 결정

FlowNote는 Web UI와 API를 1차로 구현한다.

구현 단계는 다음 순서를 따른다.

1. Web UI + API
2. Android Kotlin + WebView
3. Windows WPF + WebView2
4. 현장 코멘트/보고서 고도화
5. 검색/AI 조언

## 근거

Android와 Windows 앱은 하이브리드 앱 구조이다. 따라서 Web UI와 API 기능이 먼저 만들어지면, Android와 Windows는 같은 웹 화면을 WebView로 표시하고 필요한 네이티브 기능만 브릿지로 붙일 수 있다.

처음부터 Android와 Windows를 같이 만들면 API와 화면 요구사항이 안정되기 전에 중복 구현이 늘어난다.

## 결과

- 1차 MVP는 Web UI와 API 중심으로 정의한다.
- Android 앱은 2차 구현 대상으로 둔다.
- Windows 앱과 파일 감시는 3차 구현 대상으로 둔다.
- 브릿지는 Web UI에서 필요한 로컬 기능이 확정된 뒤 구현한다.
- Web UI는 WebView 환경을 고려해서 설계한다.
