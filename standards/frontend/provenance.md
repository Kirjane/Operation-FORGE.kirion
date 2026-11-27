# Empirical source and decision register
Authority [issue](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31) and [activation](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31#issuecomment-7184179763). Both complete 40-answer reports retrieved, read in ranges. OT = [ONE TALIBON + skill extraction](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31#issuecomment-7184052579); SC = [Salryn Cafe web/Android](https://github.com/Kirjane/Operation-FORGE.kirion/issues/31#issuecomment-7184055728). Both are operator reports posted by Engineer; shared session knowledge is not independent corroboration. S = author inspected pinned source; R = reported source/runtime/feedback, not independently reproduced; I = engineering synthesis or proposed acceptance; U = unavailable/not run. Q references are answer numbers; rules are normative candidates by authority and synthesis, not empirical certainty.

## Source pins
OT donor [7afabad](https://github.com/Kirjane/one-talibon-isolated-frontend-rewrite/tree/7afabade1fd651c2950f70006b8213ae8b7c61da); canonical [796afd3f](https://github.com/Project-Intra-Smithy/ONE-TALIBON-intra.office.system-STABLE-v1-10-18-2026/tree/796afd3f26a5f196f02cdc2e0cf6760d880463ea) (TransactionLiveQuery fetch returned 404; no independent canonical inspection). SC [87b08c84](https://github.com/Kirjane/Dev-Salryn-Cafe/tree/87b08c8463c26d12b516bc196bfb130b59679347), [26a301dc](https://github.com/Kirjane/Dev-Salryn-Cafe/tree/26a301dc4e244f39e8639ba684c8e4f6c4fb142e), Android [ad5d9dc6](https://github.com/Kirjane/Dev-Android-Salryn-Cafe/tree/ad5d9dc6f99418cb377e5bf9b68d72835f5cf71c). F = Forge [4b9fcad](https://github.com/Kirjane/Operation-FORGE.kirion/tree/4b9fcad291ba74400b282288d22014274f210f63).
S samples: OT resources/css/tokens.css blob a3602ec7c5ab9c846b4569cd677e1a1ff578097e; resources/js/components/ui/Dialog.tsx ec4176648d4fa10963f0b4d86e7109d9ba54ede7 (native component inspected in part). SC apps/cafe-web/src/cashier/main.tsx 21e9a18fdc11eb637ae846afa902b5450f5ff8d7 (full); src/r3/styles/r3-design-system.css adee3953782d47d4aa57848051818574dc56d575 (lines 1–105); src/r3/live/durableIntent.ts 0fee63f3a10cf398b3a5f3796eae6dbc950d6161 (lines 1–180, partial). These support existence/design shape only, not claimed historical measurements or complete correctness. Other cited source paths and intermediate SHAs are report-derived; short refs are as reported, not resolved full hashes. Raw local artifacts, license/QA data, screenshots and historical logs not retrieved; no client data copied.

## Rule traceability
Each row maps failure/correction and source to domain rule; applicability, tradeoffs, counterexamples and acceptance in linked domains and [patterns](patterns/catalog.md).

| Rule | Observed problem → correction; project and ref | Evidence ceiling / basis |
|---|---|---|
| D1 | OT Q1,5,28 baseline 4655487 banner-heavy civic UI → domain audit; SC Q3,25,28 #44 actual install rejected → operator-first C1/R3 | R; F planning hub S; design brief I |
| D2 | OT Q2,4 CP1–4 mockups → tokens; SC Q2 c743db87 ISO primitives → live slice | R, S token samples; reference comparison I |
| D3 | OT Q8,28 7afabad and SC Q3,8 #44 developer copy → task language; OT Q10 row density | R; no raw captures; critique I |
| V1 | OT Q3,7,27 2235e27→670894d dark fill/link; SC Q3,39 87b08c84 brand drift | S tokens current shape; R failure/contrast; parity I |
| V2 | OT Q6,10 670894d compact header/figures; SC Q6 87b08c84 CSS hierarchy | S CSS excerpt; R outcomes |
| V3 | OT Q3,12,13 2235e27→a2105b2 orphan CSS; canonical additive M4; SC Q22 no Tailwind | R; I cascade invariants |
| I1 | OT Q3,7,26 36592a8 split→drawer; Q26–27 a2105b2 reset | S partial Dialog; R behavior; I presenter selection |
| I2 | OT Q9 670894d motion/reduced motion; SC Q9 87b08c84 microtransitions | R; F design skill S; motion quality I |
| I3 | OT Q7,26 c5e1480 DateInput; SC Q6,9 87b08c84 touch/busy | R/S CSS target values; no physical proof |
| A1 | SC Q3,12,34 5197d742 wrong retail/unmounted→87b08c84 real routing; OT Q12,33 alias divergence | S SC entry, R history; I launcher test |
| A2 | SC Q3,10,12 #44 global failure, 04c4dc5d refresh unmount→retain; Q12 oversized modules | R; F Component Boundary/State Ownership S |
| A3 | OT Q13,30 donor purge vs M4 compatibility; SC Q13 c743db87→d89a09ba incremental promotion | R, S SC router; I migration criteria |
| P1 | OT Q14,27 785c6ed7 repeated transition→allowedActions; SC Q3,14 04c4dc5d→87b08c84 typed normalizers and idempotency | R; OT canonical fetch U; F trust S |
| P2 | OT Q15 f100a74a demo storage removed; SC Q7,14,29 87b08c84 redaction/zero and license | R; F Loading/Empty and Session S |
| P3 | SC Q7,12,14,29 d89a09ba/30d80db9 intent identity and retry fidelity vs OT Q15 canonical prohibition | S partial v2 shape/lease, R runtime; I security/expiry and non-atomic lease limitation |
| P4 | SC Q12,33 Android ad5d9dc6 baseline storage mismatch; OT Q3,15 f100a74a tile/bytes boundary | R; platform runtime U |
| R1 | OT Q3,7,26 36592a8 1280 cards/table; SC Q6,10 87b08c84 flexible grid and mobile | R; F profile S; breakpoints contextual |
| R2 | OT Q31,33 geometry, SC Q31,35 token/axe limited scope | R; F design skill/profile S; WCAG baseline |
| W1 | OT Q19–30 CP sequence/feedback, SC Q25–30 wrong target→live slices | R; F planning S; I workflow |
| E1 | OT Q32,35 donor vs M4, SC Q15,31–35 fixture/dist/host/release/hardware | R; I evidence ladder, not client PASS |
| E2 | OT Q33,34 wrong key/dialog/dead tests; SC Q33 real restore/keystore failures | R; S entry and partial intent; I discriminating oracle |

F exact inspected sources: frontend skill, design engineering skill, frontend_web profile, ENGINEERING_PROFILES, UX_FRONTEND_PLANNING_HUB, both Antigravity personas, all 15 frontend mesh files, policy.py lines 250–285. See [skill ledger](skill-adoption.md) and [W5](w5-integration.md). No client runtime tests, historical reproduction, external skill license validation or independent review executed. Pattern confidence can be revised on new evidence without rewriting reported history.
