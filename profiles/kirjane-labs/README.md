# Kirjane Labs — Organization-Specific Engineering Profile

This folder is a **Kirjane-specific policy overlay** for projects that the Kirjane technical authority explicitly brings under the standard. It is **not** a universal requirement for every project coordinated by KIRION Forge.

- [Engineering Stack Standard](ENGINEERING_STACK_STANDARD.md): C# / ASP.NET Core production-backend default, frontend choices, React/Vercel demo boundary, exceptions, verification and migration controls.
- [Project Stack Decision Template](PROJECT_STACK_DECISION.template.md): project-by-project architecture, risk, exception and release classification record.

## Integration point

For a **new Kirjane-controlled project**, the Maintainer should explicitly load the accepted version of the Engineering Stack Standard during project discovery/architecture. Complete the Stack Decision Template before delegating production implementation.

For an **existing Kirjane project**, first reconstruct its accepted SSOT architecture. Do not infer migration authorization from this profile.

For **non-Kirjane projects**, ignore this profile unless its technical authority has separately adopted it.

## Status

Policy and template remain **candidate-only** until accepted and promoted. An accepted profile is not mechanically enforced in other repositories until their own bootstrap, templates, reviews, and CI incorporate it.
