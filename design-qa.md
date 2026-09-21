# Design QA

Final result: passed

## Reference and captures

- Design reference: `C:\Users\Lenovo\Downloads\ChatGPT Image 2026年9月20日 14_49_42.png`
- Candidate captures: streamed inline from the user's Chrome browser through CUA; the capture API did not persist them as local image files.
- Desktop page viewport: 2048 × 852 CSS px. Checked the empty state and the open settings drawer.
- Narrow page viewport: 390 × 844 CSS px. Checked the stacked workspace, fixed actions, and absence of horizontal overflow (`scrollWidth` matched the viewport). The settings drawer also opened by keyboard and exposed the expected dialog state.

## Checks

- Updated layout follows the reference's pale mint canvas, branded header, rounded two-panel workspace, green action buttons, and centered empty-preview illustration.
- Settings open as a bottom-up drawer with a dim backdrop; Escape, backdrop, close control, focus placement/restoration, and keyboard focus trapping are covered by tests.
- Successful generation replaces the editable workspace with `document.normalized.md`; subsequent generations use that normalized workspace content while leaving the original selected file unchanged.
- The DOCX fallback renderer is preloaded as soon as a source file is selected. Heading normalization covers Chinese chapter/section and official-document numbering, Arabic decimal levels, parenthesized numbers, and circled numbers, with hierarchy tests.
- Browser console: no errors during the rendered UI checks.
- Frontend tests: 19 passed across 3 files.
- Backend tests: 69 passed; two third-party deprecation warnings only.
- Production build: passed (`tsc -b` and Vite build).
- `git diff --check`: passed.

## Scope note

The frontend production bundle and generated image assets were built into `src/doc_converter/web`. Docker Compose was not rebuilt as part of this UI verification.
