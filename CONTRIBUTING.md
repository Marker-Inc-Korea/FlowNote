# FlowNote 기여 안내

FlowNote는 현재 연구개발 프로토타입의 공개 후보를 정리하는 단계다. 외부 기여 접수와 권리 정책은 저장소 소유자가 별도로 정한다. 공개 Issue를 사용하기 전에도 실제 고객 정보, 운영 주소와 비밀값이 포함되지 않았는지 확인한다.

## 변경 원칙

- 제품 방향은 `docs/product-overview.md`, 전체 관계는 `docs/system-map.md`를 따른다.
- API·데이터·중요 설계 변경은 관련 기준 문서를 함께 갱신한다.
- 현장 코멘트 도메인은 `FieldComment`, `field_comments`, `field-comments` 명칭을 사용한다.
- Windows는 관리·문서 운영, Android는 현장 열람·짧은 기록 중심의 역할 분리를 유지한다.
- 실제 고객 자료, 운영 DB·로그, 자격 증명, 개인 경로와 생성 산출물을 커밋하지 않는다.
- 기존 시험 DB와 실패 기록은 삭제하지 않고 Git에서만 제외한다.

## 기본 검증

FastAPI:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

Windows WPF:

```powershell
dotnet test .\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
```

Android:

```bash
cd apps/android
./gradlew testDebugUnitTest assembleDebug lintDebug --warning-mode=fail
```

실행할 수 없는 검증은 통과로 표시하지 말고 환경과 미검증 범위를 변경 설명에 남긴다.

## 보안 문제

취약점과 자격 증명 노출 가능성은 공개 Issue에 쓰지 않고 [보안 정책](./SECURITY.md)의 비공개 제보 절차를 따른다.
