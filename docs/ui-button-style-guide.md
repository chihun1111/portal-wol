# UI Button Style Guide / 버튼 스타일 가이드

## 1. Design Tokens and Base Class / 디자인 토큰과 기본 클래스
- `.btn` is the canonical button foundation. It applies flex centering, shared padding, rounded corners, transitions, and neutral background defined by the theme tokens (`--color-button*`).
- Variants extend the base with semantic colors:
  - `.primary`: Accent gradient call-to-action.
  - `.secondary`: Subtle surface fill backed by `--color-button-secondary` and border emphasis.
  - `.ghost`: Transparent background, low-emphasis text (`--color-muted`) with a soft outline.
  - `.danger`: Destructive gradient for irreversible actions.
  - `.small`: Compact sizing for dense layouts.
- Combine `.btn` with optional modifiers to match the interaction weight. Custom refinements should be added through additional classes layered on top (e.g., `.btn portal-tabs__button`).

## 2. Component Usage Map / 컴포넌트 사용 매핑
| Component | Location | Applied Classes | Notes |
| --- | --- | --- | --- |
| LanguageToggle | `web/app/_components/LanguageToggle.tsx` | `btn language-toggle` | Pill-shaped toggle that inherits shared focus/hover behavior while preserving the locale badge look via `.language-toggle` overrides. |
| PortalDialog Close | `web/app/(management)/wol/_components/PortalDialog.tsx` | `btn secondary portal-dialog__close` | Uses the secondary fill for non-destructive dismissal with tighter padding defined in CSS. |
| Settings / Dialog Actions | Various (`TargetsCard`, `ConfirmDeleteModal`, etc.) | Existing `.btn` combinations | Review new variants here when adding or updating actions. |

## 3. Styling Overrides / 세부 스타일 조정
- When additional spacing, shape, or layout tweaks are necessary, author CSS selectors in `web/app/globals.css` using the combined class (e.g., `.btn.portal-menu-toggle`). This keeps the core system untouched while allowing per-component nuance.
- Ensure overrides remain theme-aware by referencing CSS custom properties instead of hard-coded colors.

## 4. Build & Static Asset Workflow / 빌드 및 정적 자산 워크플로
1. Modify source files under `web/` only. Never hand-edit the hashed bundle inside `app/static/_next/static/css` because builds regenerate those files with new fingerprints (e.g., `fe601308b2248cef.css`).
2. Run `bash scripts/build_frontend.sh [--skip-install]` to produce an updated Next.js static export in `web/out/`.
3. Sync the generated output into `app/static/` (the build script handles this copy) so FastAPI can serve the latest assets.
4. Restart the FastAPI process (`python -m app.main` or systemd service) to pick up the refreshed static files whenever hashes change.

## 5. Maintenance Checklist / 유지보수 체크리스트
- Document every new button variant in this guide and add its styling snippet to `web/app/globals.css`.
- Keep Korean translations for user-facing labels inside the localization dictionaries; only class names belong here.
- During code review, verify that new `<button>` or `<Link>` actions include `.btn` plus the appropriate modifier before merging.
- Re-run the frontend build after stylistic changes to confirm hashed assets update and commit the source diffs (not the regenerated static bundle unless a release build is required).
