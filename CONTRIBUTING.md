# FlowNote 기여 안내

FlowNote는 현재 연구개발 프로토타입의 공개 후보를 정리하는 단계다. 외부 기여 접수와 권리 정책은 저장소 소유자가 별도로 정한다. 공개 Issue를 사용하기 전에도 실제 고객 정보, 운영 주소와 비밀값이 포함되지 않았는지 확인한다.

버그와 개선 제안은 저장소의 Issue 양식을 사용한다. 보안 취약점은 Issue에 올리지 않고 [보안 정책](./SECURITY.md)의 비공개 제보 절차를 따른다. Dependabot은 Python, NuGet, Gradle과 GitHub Actions 의존성을 매월 점검하지만 자동 병합하지 않는다.

## 변경 원칙

- 제품 방향은 `docs/product-overview.md`, 전체 관계는 `docs/system-map.md`를 따른다.
- API·데이터·중요 설계 변경은 관련 기준 문서를 함께 갱신한다.
- 현장 코멘트 도메인은 `FieldComment`, `field_comments`, `field-comments` 명칭을 사용한다.
- Windows는 관리·문서 운영, Android는 현장 열람·짧은 기록 중심의 역할 분리를 유지한다.
- 실제 고객 자료, 운영 DB·로그, 자격 증명, 개인 경로와 생성 산출물을 커밋하지 않는다.
- 기존 시험 DB와 실패 기록은 삭제하지 않고 Git에서만 제외한다.

## 기본 검증

처음 환경을 준비하는 방법은 [처음 실행하기](./docs/getting-started.md)를 따른다. 이 과정에서 생성한 `.env`, SQLite, storage와 빌드 산출물은 커밋하지 않는다.

공개 제외 파일과 문서 상대 링크:

```bash
python3 scripts/check_public_tree.py
```

FastAPI:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests ..\..\scripts\bootstrap_local_evaluation.py ..\..\scripts\test_bootstrap_local_evaluation.py ..\..\scripts\check_public_tree.py
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
