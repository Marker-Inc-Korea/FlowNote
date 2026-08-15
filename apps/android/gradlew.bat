@echo off
set APP_HOME=%~dp0
set GRADLE_VERSION=9.5.1
set GRADLE_SHA256=bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f
set GRADLE_USER_HOME=%APP_HOME%\.gradle
set DIST_DIR=%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin\gradle-%GRADLE_VERSION%
set DIST_ZIP=%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin\gradle-%GRADLE_VERSION%-bin.zip
set DIST_URL=https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip

if not exist "%DIST_DIR%\bin\gradle.bat" (
  mkdir "%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin" 2>nul
  if not exist "%DIST_ZIP%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%DIST_URL%' -OutFile '%DIST_ZIP%'"
  )
  call :verify_distribution
  if errorlevel 1 exit /b 1
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force '%DIST_ZIP%' '%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin'"
 ) else if exist "%DIST_ZIP%" (
  call :verify_distribution
  if errorlevel 1 exit /b 1
)

call "%DIST_DIR%\bin\gradle.bat" %*
exit /b %errorlevel%

:verify_distribution
set ACTUAL_SHA256=
for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%DIST_ZIP%').Hash.ToLowerInvariant()"') do set ACTUAL_SHA256=%%H
if /i not "%ACTUAL_SHA256%"=="%GRADLE_SHA256%" (
  echo Gradle distribution SHA-256 verification failed: %DIST_ZIP% 1>&2
  echo Expected: %GRADLE_SHA256% 1>&2
  echo Actual:   %ACTUAL_SHA256% 1>&2
  exit /b 1
)
exit /b 0
