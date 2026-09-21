# DOCX Preview and Style Roles Implementation Plan

> **For agentic workers:** Implement this plan task-by-task in the current task, preserving all pre-existing worktree changes.

**Goal:** Make academic character-based indentation render in the PDF preview, give generated tables a uniform 0.5 pt grid, and expose paragraph settings for abstract and keyword rows without changing their inline layout.

**Architecture:** Keep the DOCX as the preview source. Emit a twip fallback alongside character-based indentation. Apply table borders during the existing DOCX post-processing pass. Make each metadata label a paragraph role for the full row and its content a character role; migrate existing saved role values into the new layout without changing label/content fonts.

**Tech Stack:** Python 3.12, Pydantic, python-docx, FastAPI; React, TypeScript, Vitest, Vite; LibreOffice for DOCX-to-PDF visual verification.

**Spec:** User-confirmed requirements and design in the current Codex task (2026-09-20).

## Global Constraints

- Preserve existing uncommitted changes in the worktree.
- Keep the visible metadata layout as one inline paragraph: “摘要：内容” and “关键词：内容”.
- Paragraph controls on the label role format the whole corresponding metadata paragraph; content roles format only their text runs.
- Table grid borders are single black lines, 0.5 pt (`w:sz="4"`).
- Use the existing Compose project name `doc-converter`; never run `down -v`.
- Add no dependencies.

## Review Focus

- Character indents must retain character semantics while a point fallback makes the academic-style PDF preview visibly indent only the first line; cover this in `tests/test_renderer.py` and a rendered-PDF check.
- A DOCX table must have outer and internal borders at 0.5 pt; cover all six grid edges in `tests/test_renderer.py`.
- Saved v3 label/content roles must retain both fonts and metadata paragraph geometry after migration; cover in `tests/test_style_library.py`.
- Legacy v2 `abstract` / `keywords` paragraph values must migrate to the new label paragraph roles while their text font remains on content roles; cover in `tests/test_style_library.py`.
- The editor must show paragraph controls for label roles and keep content roles font-only; cover in `frontend/src/StyleEditor.test.tsx`.

---

### Task 1: Render character-based indentation in LibreOffice previews

**Files:**
- Modify: `src/doc_converter/docx_styles.py`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: `ParagraphSpec` stores indentation magnitudes in points plus an explicit unit.
- Produces: Character-unit `w:ind` properties retain `firstLineChars` / `leftChars` / `rightChars` and also keep their equivalent twip attributes as fallbacks.

- [x] **Step 1: Add the failing DOCX regression test**

```python
def test_renderer_writes_character_indent_and_twip_fallback(tmp_path):
    # Build a paragraph style with 32 pt = two 16 pt characters.
    # Render it, read word/styles.xml, and assert firstLineChars="200"
    # and firstLine="640" are both present on DC_BodyParagraph.
```

- [x] **Step 2: Run the focused test and confirm it fails because `firstLine` is absent**

Run: `uv run pytest tests/test_renderer.py -k character_indent -q`
Expected: the character attribute is present, but the point-fallback assertion fails.

- [x] **Step 3: Keep the equivalent point attribute when writing character units**

```python
indent.set(qn(chars_attr), str(characters))
# Keep the point attribute already written by paragraph_format.
```

- [x] **Step 4: Re-run the focused test**

Run: `uv run pytest tests/test_renderer.py -k character_indent -q`
Expected: PASS, with both character and twip properties in the generated DOCX.

- [x] **Step 5: Verify the academic-style DOCX rendered to PDF**

Generated an academic-style sample with the application's LibreOffice conversion helper and inspected the rendered page: the first body line is indented, continuation lines return to the body margin, and the table grid is visible.

### Task 2: Add default 0.5 pt borders to generated tables

**Files:**
- Modify: `src/doc_converter/docx_postprocess.py`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: every top-level table produced by the current Pandoc renderer.
- Produces: table-level `top`, `bottom`, `left`, `right`, `insideH`, and `insideV` single borders at 0.5 pt.

- [x] **Step 1: Add a failing table-grid test**

```python
def test_renderer_adds_half_point_grid_borders(tmp_path):
    # Render a two-column Markdown table, inspect word/document.xml,
    # and assert all six table border edges are single, black, size 4.
```

- [x] **Step 2: Run the focused test and confirm generated tables lack the grid**

Run: `uv run pytest tests/test_renderer.py -k half_point_grid -q`
Expected: FAIL because the generated table is missing one or more border edges.

- [x] **Step 3: Apply the uniform border in the existing post-processing pass**

```python
for edge in ("top", "bottom", "left", "right", "insideH", "insideV"):
    # Set w:val="single", w:sz="4", and w:color="000000".
```

- [x] **Step 4: Re-run the focused table test**

Run: `uv run pytest tests/test_renderer.py -k half_point_grid -q`
Expected: PASS for all six edges.

### Task 3: Give abstract and keyword labels full paragraph-role controls

**Files:**
- Modify: `src/doc_converter/style_schema.py`
- Modify: `src/doc_converter/docx_postprocess.py`
- Modify: `frontend/src/StyleEditor.tsx`
- Modify: `README.md` if it documents the previous role mapping
- Test: `tests/test_style_library.py`
- Test: `tests/test_renderer.py`
- Test: `frontend/src/StyleEditor.test.tsx`

**Interfaces:**
- Consumes: current saved packs with label character roles and content paragraph roles, plus v2 legacy `abstract` / `keywords` roles.
- Produces: paragraph label roles carrying the complete paragraph layout and label font; character content roles carrying the content font. Existing role names and inline rendering remain stable.

- [x] **Step 1: Add failing migration tests for saved v3 and legacy v2 values**

```python
def test_style_pack_moves_metadata_paragraph_settings_to_label_roles():
    # Load a v3 pack with abstract-label as character and abstract-content
    # as paragraph; assert both fonts survive and paragraph values move to
    # abstract-label while abstract-content becomes character-only.
```

- [x] **Step 2: Run migration tests and confirm the role-type/layout assertions fail**

Run: `uv run pytest tests/test_style_library.py -k metadata -q`
Expected: FAIL because the current schema still makes labels character roles.

- [x] **Step 3: Implement the role swap and backward-compatible migration**

```python
# New defaults: abstract-label / keywords-label are paragraph roles;
# abstract-content / keywords-content are character roles.
# On old packs, move each content role's paragraph object to its label role.
```

- [x] **Step 4: Add a DOCX metadata-role integration test**

```python
def test_metadata_rows_use_label_paragraph_and_content_character_styles():
    # Render front matter; assert the paragraph style is DC_AbstractLabel
    # and the content run style is DC_AbstractContent.
```

- [x] **Step 5: Update the editor and its behavior test**

```tsx
expect(screen.getByLabelText('摘要标签对齐')).toBeInTheDocument()
expect(screen.queryByLabelText('摘要内容对齐')).not.toBeInTheDocument()
```

Run: `npm test -- --run src/StyleEditor.test.tsx`
Expected: PASS; the label exposes alignment, indentation, spacing, and line-spacing controls while content remains font-only.

- [x] **Step 6: Run focused backend tests**

Run: `uv run pytest tests/test_style_library.py tests/test_renderer.py -q`
Expected: PASS, including saved-style migration and rendered DOCX role assignments.

### Task 4: Full regression and rendered-app verification

**Files:**
- Validate: `tests/`, `frontend/src/`, generated DOCX/PDF, Compose service.

**Interfaces:**
- Consumes: all three implemented changes.
- Produces: verified backend/frontend suites, production build, and preview evidence where the local render service is available.

- [x] **Step 1: Run the complete backend and frontend test suites**

Run: `uv run pytest -q` and `npm test -- --run` from `frontend`.
Expected: all existing and new tests pass.

- [x] **Step 2: Build the frontend**

Run: `npm run build` from `frontend`.
Expected: TypeScript and Vite build succeed.

- [x] **Step 3: Exercise the real preview flow**

Generate and visually inspect a DOCX-to-PDF academic sample with a character-based body indent and Markdown table; verify the first-line indent, continuation-line alignment, and visible table grid. Frontend regression tests verify both labels expose paragraph controls while content roles remain font-only.

- [x] **Step 4: Rebuild and health-check Compose if the Docker engine is available**

Ran `docker compose -p doc-converter up --build -d`; verified the service is healthy at `http://127.0.0.1:8765/health` and retained the `doc-converter-data` volume.
