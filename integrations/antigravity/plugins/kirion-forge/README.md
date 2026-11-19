# KIRION Forge — Native Antigravity Plugin (`kirion-forge`)

Version: `1.0.0-r1` · Program: `FORGE-ANTIGRAVITY-SOFTWARE-FACTORY-R1` ([Issue #13](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/issues/13))

## Overview

`kirion-forge` packages the KIRION Forge autonomous software engineering factory into a single workspace-scoped Antigravity plugin bundle:

- **Manifest:** [plugin.json](plugin.json) (strictly validated against the Antigravity Language Server schema).
- **Always-On Rules:** [rules/AGENTS.md](rules/AGENTS.md) enforcing exact 40-char SHA authority, Second Brain / Forge crosswalk rules, persona role boundaries, and fail-closed destructive operation blocks.
- **Lifecycle Hooks:** [hooks.json](hooks.json) and [hooks/forge_guard.py](hooks/forge_guard.py) gating `PreToolUse` (`run_command`, `write_file`, `edit_file`) and `PostToolUse` (`run_command`).
- **Kirion Fleet Personas:** 10 specialized agent definitions under `agents/`.
- **Specialization Pack:** 16 engineering specialization skills under `skills/` (C# / ASP.NET Core / EF Core, PHP / Laravel / Eloquent, Concurrency, Database, API, Observability, Performance, Design Engineering, Test Engineering, DevSecOps) complementing the 16 core skills in `.agents/skills/`.

## Install, Discovery, and Uninstall Runbook

### 1. Workspace-Scoped Activation (Default — Zero Global Mutation)
This repository declares [../../../../.agents/plugins.json](../../../../.agents/plugins.json):

```json
{
  "entries": [
    {
      "path": "integrations/antigravity/plugins"
    }
  ]
}
```

When the repository is opened as an active workspace in Antigravity 2.0 or queried via the Language Server `GetAllPlugins` RPC, `kirion-forge` is automatically discovered with `isGlobal: false`.

### 2. Verification Command
Run the deterministic packaging and live Language Server discovery check from the repository root:

```bash
python -m integrations.antigravity.factory.cli verify-plugin
```

### 3. Clean Uninstall / Disable
- **UI Toggle:** Open `customization://kirion-forge` in the Antigravity Customizations page to disable or enable the plugin live without restarting.
- **Workspace Removal:** Remove `.agents/plugins.json` (or remove the `integrations/antigravity/plugins` entry) to unload the plugin from workspace discovery with zero global residue.
