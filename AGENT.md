# Agent Instructions

## Project

FlowNote is a multi-platform application project for Windows, Android, and Web.

## Repository Layout

- `apps/windows/`: Windows desktop app
- `apps/android/`: Android app
- `apps/web/`: Web app
- `packages/shared/`: Shared domain logic, types, constants, and utilities
- `packages/ui/`: Shared UI resources or design-system code
- `services/api/`: Optional backend/API service
- `assets/`: Shared images, icons, fonts, and brand assets
- `docs/`: Product, architecture, and API documentation
- `scripts/`: Development, build, and release scripts

## Working Rules

- Keep platform-specific code inside the matching `apps/` directory.
- Put reusable logic in `packages/shared/`.
- Add backend code only under `services/`.
- Keep documentation in `docs/`.
- Do not add framework-specific scaffolding until the stack for that app is chosen.
- Do not commit build outputs, dependency folders, secrets, local settings, or generated temporary files.
- Prefer small, focused commits with clear Korean commit messages.

## Before Committing

- Check `git status`.
- Review changed files.
- Run relevant build or test commands after each platform stack is introduced.
