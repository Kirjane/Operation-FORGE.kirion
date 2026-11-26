# Visual system engineering
Sources V1–V3 in [register](provenance.md); no universal palette, font, radius, density or framework.

## V1 — Semantic visual language (MUST)
Choose brand primitives from approved assets, then role tokens, then component recipes. A raw color is not a semantic role. Separate canvas, surface, raised/recessed, text primary/secondary, boundary, focus, brand fill, on-fill ink, brand link ink, disabled/selected/hover and status foreground/background/border. Map each appearance and interaction state; define high contrast/forced-color behavior where supported. Shared tokens may be generated into native or web formats when multiple surfaces share approved identity; platform adaptations must be traceable. Do not silently change brand authority: create a parity table of logo, color, type, icon and state differences, request decision for intentional divergence.

Illustrative (values deliberately symbolic):
```css
:root {
  --action-fill: var(--approved-solid-accent);
  --action-ink: var(--approved-on-accent);
  --link-ink: var(--approved-text-accent);
  --surface-panel: var(--approved-panel);
}
.action { background: var(--action-fill); color: var(--action-ink); }
.link { color: var(--link-ink); text-decoration: underline; }
```
SHOULD use a restrained elevation hierarchy in dark themes, differentiate input wells from overlay surfaces, and reserve high saturation for intent. Verify actual composited contrast, not only nominal token hex; measure hover, disabled meaning, link and focus on each background. A flat theme may use borders and spacing rather than four literal layers. Native light-dark() and color-scheme MAY simplify theme implementation when supported, with tested fallback. Theme change must reach rendered controls and overlays.

## V2 — Composition, typography, craft (SHOULD)
Establish a layout grid with flexible content tracks, consistent gutters, intentional alignment and spacing scale (e.g. 4/8 increments; not mandatory). Start with content hierarchy: one readable page title, primary work region, secondary details, supporting controls. Align labels, field edges, table headers and numeric columns. Use optical alignment for icons; avoid boxes around every group; divide by spacing or a quiet rule when adequate. Balance density against scanning and motor effort. Use a display typeface only where it adds personality; use legible body type for long rows/inputs, tabular figures for comparison, mono for identifiers if useful. Load licensed fonts sparingly with fallbacks, check real language glyphs, numeral widths, wrap and zoom. Do not shrink text to rescue a broken layout.

Make a specimen: title, paragraph, dense row, primary/secondary/destructive actions, filter, form validation, status, card, empty state, modal/drawer, mobile header and actual icon/logo. Demonstrate populated, long-content and loading/error states in each supported theme. Review the rhythm, whitespace and hierarchy before scaling. Reuse primitives by semantic function rather than forcing a single Card on everything. Design intentionally distinct surfaces: command center, register, creation form, preview, POS and editorial pages.

## V3 — Predictable style ownership (MUST)
Establish predictable cascade and one source of token/primitive definitions. Tailwind layers or ordinary scoped CSS/modules can both satisfy this. Do not hijack global utility semantics or add chronological override files to conceal unresolved consumers. Before deleting shared styles enumerate route, dynamic import and class consumers; migrate together or keep explicit bridges. Verify order independence (visit routes in different orders), computed styles, dark/forced-color and secondary pages. Scoped compatibility overrides or reduced-motion/print exceptions MAY be justified and documented. No framework change merely to match donor.
 
Acceptance: specimen and live screens demonstrate intended identity, consistent rhythm, readable typography, meaningful accent/semantic states and measured contrast; no accidental style drift, unresolved consumers or visual regressions; brand divergence disclosed. See [pattern catalog](patterns/catalog.md).
