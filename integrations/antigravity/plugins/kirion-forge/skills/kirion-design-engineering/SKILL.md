---
name: kirion-design-engineering
description: Use this skill for WCAG 2.2 AA accessible frontend implementation, 320px-to-1440px responsive layout discipline, keyboard focus management, reduced-motion compliance, and truthful static-vs-live labeling.
---

# Kirion Design Engineering Specialization (`kirion-design-engineering`)

## 1. Versioned Official References
- W3C WCAG 2.2 AA Guidelines: `https://www.w3.org/TR/WCAG22/`
- MDN Accessible Rich Internet Applications (WAI-ARIA): `https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA`

## 2. Concrete Workflow
1. Build semantic HTML landmarks (`<header>`, `<nav>`, `<main>`, `<section>`, `<form>`, `<button>`) with explicit labels, visible `:focus-visible` outlines, and keyboard navigation order.
2. Verify layout responsiveness across `1440x900`, `1280x720`, `1024x768`, `768x1024`, `390x844`, and `320x568` viewports with zero unintended horizontal overflow (`overflow-x` / fixed pixel widths exceeding `100vw`).
3. Respect `@media (prefers-reduced-motion: reduce)` and provide explicit loading, empty, error, and permission-denied UI states.
4. When a contract authorizes a static showcase preview, label fictional data clearly and never claim simulated toggles are live authenticated sessions.

## 3. Canonical Example
```css
.container {
  width: 100%;
  max-width: 1200px;
  box-sizing: border-box;
  padding-inline: 1rem;
}
button:focus-visible, a:focus-visible, input:focus-visible {
  outline: 2px solid #0284c7;
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 4. Validation Commands
```bash
python -m unittest discover -s integrations/antigravity/tests -v
```

## 5. Misuse & Negative Cases
- **Negative Case 1 (320px Viewport Horizontal Overflow):** Setting `min-width: 480px` or fixed `width: 600px` on a card container (`UI-320PX-OVERFLOW`).
- **Negative Case 2 (Focus Removal):** Setting `outline: none` without a high-contrast `:focus-visible` replacement (`UI-KEYBOARD-FOCUS`).
- **Negative Case 3 (Simulated-as-Live Deception):** Presenting a hardcoded `localStorage` role switcher as "Backend RBAC Verified (`E5`)" (`UI-SIMULATED-LIVE-CLAIM`).

## 6. Tests & Qualification Evidence
- Verified in Benchmark C (`UI-320PX-OVERFLOW`, `UI-KEYBOARD-FOCUS`, `UI-SIMULATED-LIVE-CLAIM`).
