---
id: "forge.updating.from.github"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "ac7285d7cd866b4728c28d64a7c145a6bc43f812"
source_path: "AGENTS.md"
source_status: "ACCEPTED"
tags: [forge, source, sync]
---

# Updating from GitHub

The vault is derived from source. **GitHub is the only source of accepted engineering authority.**

1. Verify remote main, PR #7 and exact SHA and applicable review/promotion decisions.
2. Fetch the pinned commits into an authorized local Forge checkout.
3. Run the standard-library exporter at `obsidian/scripts/build_vault.py` with full `--accepted-ref`, `--candidate-ref` and `--repo-root` values.
4. Regenerate within an isolated output folder; use `--check` and the vault link/metadata tests.
5. Keep manual annotations under `_personal/` rather than changing generated notes.
6. Only move candidate content to accepted policy after observed GitHub source promotion and any separate project adoption authorization.
7. Verify Obsidian desktop navigation and built-in Graph on a real host; report `OBSIDIAN_UI_NOT_RUN` when unavailable.

[[Source Index]] · [[Exact SHA Ledger]] · [[Accepted vs Candidate]] · [[GitHub Source Truth]] · [[00 HOME]].
