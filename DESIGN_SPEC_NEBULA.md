# SUDHARSHAN AI — PROJECT NEBULA DESIGN SPECIFICATION (`DESIGN_SPEC_NEBULA.md`)

**Design Authority**: Extracted from `taste-skill` v2.5.1 (`design-taste-frontend`) + Sudharshan AI Precision Obsidian & Solar Orange brand identity.  
**Product Classification**: `page-type: software` | `site-kind: software` | Local-First AI Ecosystem & OS.

---

## 1. Core Design Philosophy (Distilled from Taste Skill 2.5.1)
1. **Plain, Grounded Copy in a Voice of Its Own**: State plainly what Sudharshan AI does, show real product UI on every screen, and never use generic AI marketing hype or boilerplate.
2. **One Section per Screen & Equal Left/Right Edges**: Every landing section occupies a clean visual rhythm with strict max-width container alignment (`1180px`, `24px` horizontal gutters) and zero overlapping wordmarks or colliding grounds.
3. **Zero Captions Under Visuals & Zero Empty Grounds**: Visual frames, product UI mocks, and diagrams speak for themselves; attribution lives in one crisp footer line. Every viewport (`1440px`, `1024px`, `768px`, `390px`) renders cleanly.
4. **Real Product UI in `app-frame`**: Tech/software interfaces showcase genuine interactive product surfaces (live model router, real terminal commands, live feature registry explorer, client-side Web Crypto verifier, Native 1.5B parameter calculator) rather than abstract decoration.
5. **Restrained, Purposeful Micro-Interactions**: Linked cards lift `2px`, buttons step on hover and press on click, zero gimmicky tilt/carousels, and full `@media (prefers-reduced-motion: reduce)` compliance.
6. **Consistent Dark & Light Themes**: Primary **Precision Obsidian & Solar Orange** dark theme paired with a high-contrast **Warm Paper & Solar Orange** light theme toggle, both passing WCAG 2.1 AA (`>= 4.5:1` body text contrast).

## 2. Canonical Design Tokens (Shared Across Web, GTK4, Tkinter, PDF & PPTX)

| Token | Dark Theme (Default) | Light Theme | Usage |
| :--- | :--- | :--- | :--- |
| `--bg` (Obsidian / Paper) | `#0B0B0D` | `#F8F8FA` | Page & window canvas |
| `--surface` | `#141418` | `#FFFFFF` | Cards, panels, modals, HUD frames |
| `--surface-elevated` | `#1A1A20` | `#F1F2F6` | Hover panels, code blocks, active rows |
| `--hairline` | `#24242B` | `#E2E4EC` | 1px structural rules and borders |
| `--accent` (Solar Orange) | `#FF5A1F` | `#E04810` | Primary CTAs, active tabs, telemetry highlights |
| `--accent-secondary` (Signal Teal) | `#10B981` | `#059669` | Verified states, local-only badges, pass indicators |
| `--text` | `#F4F4F6` | `#111217` | Primary readable body & headings |
| `--muted` | `#A1A1AA` | `#525563` | Secondary metadata and labels |
| `--radius-container` | `10px` | `10px` | Cards, modals, panels |
| `--radius-input` | `8px` | `8px` | Inputs, selects, code boxes |
| `--radius-cta` | `9999px` | `9999px` | Primary pill action buttons |

## 3. Typography & Density Discipline
- **UI & Display Sans**: `Instrument Sans`, system-ui, sans-serif (tight `-0.03em` tracking on hero headlines).
- **Technical Monospace**: `DM Mono`, ui-monospace, monospace (used for telemetry, model weights, SHA-256 digests, CLI commands, and parameter tables).
- **Visual Density Dials**: Standard reading views use `VISUAL_DENSITY = 5`; engineering telemetry/registry views offer an explicit toggle to `VISUAL_DENSITY = 7` without card clutter.
