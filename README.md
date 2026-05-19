# FlowNote

FlowNote is planned as a multi-platform project for Windows, Android, and Web.

## Repository Structure

```text
FlowNote/
  apps/
    windows/       Windows desktop app
    android/       Android app
    web/           Web app
  packages/
    shared/        Shared domain logic, types, constants, and utilities
    ui/            Shared UI assets or design-system code when applicable
  services/
    api/           Optional backend/API service
  assets/          Shared images, icons, fonts, and brand assets
  docs/            Product notes, architecture, API docs, and decisions
  scripts/         Build, release, and development automation scripts
  .github/         GitHub workflows and repository templates
```

## Getting Started

Choose the implementation stack for each app before adding framework-specific files.

- Windows: WinUI, WPF, MAUI, Electron, Tauri, or another desktop stack
- Android: Kotlin/Jetpack Compose, Java/XML, Flutter, React Native, or MAUI
- Web: React, Next.js, Vue, Svelte, Angular, or another web stack
- Backend: Add only if the apps need shared sync, accounts, storage, or APIs

## Development Notes

- Keep platform-specific code inside `apps/`.
- Put reusable business logic in `packages/shared/`.
- Keep documentation in `docs/`.
- Add CI/CD workflows under `.github/workflows/` when the build stack is decided.
