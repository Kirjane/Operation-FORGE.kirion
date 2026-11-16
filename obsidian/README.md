# KIRION Forge — Obsidian-only knowledge vault

The `KIRION-FORGE-VAULT` folder is a **real, local Markdown vault**, with a `00 HOME.md` map, 16 full pinned Skill Arsenal contracts, project-state routes, worker templates, governance and source provenance. Open the folder directly with Obsidian's **Open folder as vault**, then use Obsidian's built-in **Graph view**. No Notion, Graphify, Obsidian connector, paid account or community plugin is required.

**Source pins:** accepted Forge main `ac7285d7cd866b4728c28d64a7c145a6bc43f812`; Skill Arsenal PR #7 `eabbfbabdbb22d8684fb2c3d80767b8547852b83` was **CANDIDATE / OPEN / UNMERGED** at authoring. Re-read live GitHub before action. The note metadata is descriptive and does not grant merge/deployment authority.

## Regenerate and validate

Run in a local **full Git checkout** of `Kirch-Nairu/Operation-FORGE.kirion` with both pinned commits fetched:

```bash
python obsidian/scripts/build_vault.py --repo-root . --accepted-ref ac7285d7cd866b4728c28d64a7c145a6bc43f812 --candidate-ref eabbfbabdbb22d8684fb2c3d80767b8547852b83 --check
python -m unittest discover -s obsidian/tests -v
python obsidian/scripts/build_vault.py --repo-root . --accepted-ref ac7285d7cd866b4728c28d64a7c145a6bc43f812 --candidate-ref eabbfbabdbb22d8684fb2c3d80767b8547852b83 --zip obsidian/dist/KIRION-FORGE-VAULT.zip
```

The exporter verifies immutable Git commits and full source skill text; it validates all vault wiki links and provenance. ZIP creation uses deterministic ordering. It will not delete or overwrite anything in `_personal/`. Regenerate with explicit *new* refs only after verifying authority and lineage; no implicit latest or automatic adoption.

**Local preview alternative:** The separately delivered `KIRION-FORGE-OBSIDIAN-R2-PREVIEW.zip` is an offline, catalog-derived preview for a ChatGPT session without private Git checkout. It has a conspicuous `catalog-preview` label and summary notes; the Git branch contains **full canonical skill text**. Do not mistake the preview for an independently verified local Git archive.

## Scope and limitations

This repository deliverable is a derivative engineering reference. It does not install Agent Skills in ChatGPT, Codex or Antigravity, sync with GitHub unattended, or replace Forge project policy. Neither generic CI nor Markdown lint proves the Obsidian desktop UI; if no desktop is available report `OBSIDIAN_UI_NOT_RUN`.

Use [GitHub Issue #9](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/issues/9) for Maintainer state, and [Forge PR #7](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/pull/7) for the upstream candidate gate.
