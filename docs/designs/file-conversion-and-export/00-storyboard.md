# Storyboard — File Conversion & Report Export

Feature: (1) **Report download control** offering Word (`.docx`) + Markdown
(`.md`); (2) **Upload accepts `.docx`** (converted to Markdown via markitdown
before ingest; `.pdf` already works). Two UI touchpoints, mapped below.

Source-of-truth scope: this is a **third-party repo (MiroFish)**, not a
dev-methodology project. No `/mockup-parity` validator consumes these tags
downstream; parity attributes are included for skill-compliance and to make
"what + where" unambiguous, not for an automated gate.

## Component tokens (Gate 11 — lifted from real components)

| Token | Value | Source |
|---|---|---|
| Font (sans) | `'Space Grotesk','Noto Sans SC',system-ui` | ReportView.vue:227 |
| Font (mono) | `'JetBrains Mono',monospace` | ReportView.vue:250,297 |
| Surface | `#FFF` | ReportView.vue:225,238 |
| Border | `#EAEAEA` (header), `#E5E7EB`/`#F3F4F6` (cards) | ReportView.vue:233 / Step4Report |
| Ink / muted | `#000` / `#666` / `#999` | ReportView.vue:271,299,319 |
| Accent (status) | `#FF9800` processing · `#4CAF50` completed | ReportView.vue:329-330 |
| App header height | `60px` | ReportView.vue:232 |
| Report tag | black pill, 11px, white text | Step4Report.vue:11 `.report-tag` |
| Primary button | dark fill, white text, 8px radius (base for download btn) | Step4Report.vue:131 `.next-step-btn` |

## Provenance (Gate 1 — classes lifted verbatim)

| Class | From |
|---|---|
| `.main-view`, `.app-header`, `.brand`, `.view-switcher`, `.switch-btn`, `.header-right`, `.workflow-step`, `.status-indicator`, `.dot`, `.content-area`, `.panel-wrapper` | ReportView.vue |
| `.report-panel`, `.left-panel.report-style`, `.report-content-wrapper`, `.report-header-block`, `.report-meta`, `.report-tag`, `.report-id`, `.main-title`, `.sub-title`, `.header-divider`, `.sections-list`, `.report-section-item`, `.section-header-row`, `.section-number`, `.section-title`, `.next-step-btn` | Step4Report.vue |
| `.console-box`, `.console-section`, `.console-header`, `.console-label`, `.console-meta`, `.upload-zone`, `.upload-placeholder`, `.upload-icon`, `.upload-title`, `.upload-hint`, `.file-list`, `.file-item` | Home.vue |
| **NEW** `.report-download`, `.report-download__btn`, `.report-download__menu`, `.report-download__item` | **introduced by this feature** (styled from the primary-button + card tokens above) |

## States (Gate 2 — golden path)

| # | slug | Tier | entry-point | Entry / Action / Result |
|---|---|---|---|---|
| 1 | `report-complete-resting` | A | none | On the report page, report finished. Download button visible at the header's top-right, menu closed. (Shows the affordance at rest — Gate 4a for state 2.) |
| 2 | `report-download-menu-open` | A | report-complete-resting | User clicks **Download ▾** → a 2-item menu opens: **Word (.docx)** and **Markdown (.md)**. |
| 3 | `upload-docx-accepted` | A | none | On the start page, the upload console shows supported formats **PDF, DOCX, MD, TXT** and a just-dropped `.docx` file accepted in the list (PDF + MD shown too). |

## Variant exemptions

- **Gate 9 (dark mode): EXEMPT — light-only because** MiroFish ships no dark
  theme; `ReportView.vue` and all components hardcode `#FFF` surfaces and there
  is no `prefers-color-scheme` rule anywhere in `frontend/src`.
- **Gate 10 (mobile): EXEMPT — desktop-only because** the app is desktop-first
  (fixed 60px header + two-panel graph/report view-switcher); there is no mobile
  layout for these screens to re-author against.

## Accessibility (Gate 8)

- Download control is a real `<button>` with `aria-haspopup="menu"` /
  `aria-expanded`; menu uses `role="menu"` + `role="menuitem"`.
- One `:focus-visible` state captured on the Word menu item (state 2).
