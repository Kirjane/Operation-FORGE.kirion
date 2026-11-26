"""Focused Lane B source-policy and declaration regressions; no live dispatch."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from integrations.antigravity.factory.authority import AuthorityError
from integrations.antigravity.factory.mission_contract import contract_digest
from integrations.antigravity.factory.policy import (
    PolicyViolationError, assert_paths_within_ownership, assert_frontend_actor_binding,
)
from integrations.antigravity.tests.test_mission_contract import make_contract, historical_packet

ROOT = Path(__file__).resolve().parents[3]
LUCIEN = "Antigravity-Lucien"
IRIS = "Antigravity-Iris"


def writer(persona=LUCIEN, owned=None, excluded=None, canonical=False):
    packet = make_contract()
    owned = owned or ["src/components"]
    packet.update(assigned_persona=persona, formal_role="Code Writer",
                  allowed_operations=["READ", "WRITE_OWNED"],
                  owned_paths=owned, excluded_paths=excluded or ["docs/private"])
    if canonical:
        packet.update(repo_id=1377058358, repo_name="Kirjane/Operation-FORGE.kirion")
        packet["source_authorities"][0].update(repository_id=packet["repo_id"],
                                               repository_name=packet["repo_name"])
    packet["authority"]["grant_scope"] = ["READ", "WRITE_OWNED"]
    packet["required_capabilities"].append({
        "capability_id": "scoped_worktree_write", "operation": "WRITE_OWNED",
        "scope": owned, "environment": "fixture", "independence_required": False,
    })
    return packet


def binding(packet, provider=None, actor=None):
    persona = packet["assigned_persona"]
    provider = provider or ("github" if persona == LUCIEN else "native")
    actor = actor or ("359299805" if provider == "github" else "native:fixture-iris")
    observation = {"persona": persona, "formal_role": packet["formal_role"],
                   "actor_id": actor, "worker_id": "fixture-worker",
                   "host_id": "fixture-host", "identity_provider": provider}
    grant = dict(observation, contract_sha256=contract_digest(packet),
                 revision=packet["revision"])
    return {"trusted_grant": grant, "observed_actor": observation}


class FrontendRoleTests(unittest.TestCase):
    def test_both_implement_full_ui(self):
        paths = ["apps/cafe-web/src/r3/Workspace.tsx", "apps/cafe-web/src/r3/layout.css",
                 "apps/cafe-web/src/api/hostClient.ts", "apps/cafe-web/assets/logo.svg",
                 "tests/frontend/checkout.spec.ts", "resources/views/records.blade.php",
                 "Views/Records/Index.cshtml", "android/app/src/main/ui/Checkout.kt"]
        for persona in (LUCIEN, IRIS):
            packet = writer(persona, owned=["apps/cafe-web/src", "apps/cafe-web/assets",
                          "tests/frontend", "resources/views", "Views", "android/app/src/main/ui"])
            with self.subTest(persona=persona):
                self.assertEqual(assert_paths_within_ownership(packet, paths, **binding(packet)), paths)

    def test_denied_backend_and_scope_even_with_valid_grant(self):
        for persona in (LUCIEN, IRIS):
            packet = writer(persona, owned=["src/components", "src/pages", "src/routes",
                                           "src/features", "tests/frontend", "backend",
                                           "resources/views", "src/ui"])
            kwargs = binding(packet)
            for path in ("backend/payment.ts", "src/components/server/ledger.ts",
                         "src/components/security/authorize.ts", "src/pages/api/payment.ts",
                         "src/routes/route.ts", "src/features/billing.server.ts",
                         "src/ui/package.json", "src/ui/.env", "src/ui/AGENTS.md",
                         "src/components/../other.tsx", "src/components/x.tsx:ads",
                         "src/components/x.sh", "src/components/x.py", "src/components2/x.tsx",
                         "resources/views/Controller.php", "tests/frontend/scripts/run.js"):
                with self.subTest(persona=persona, path=path), self.assertRaises(AuthorityError):
                    assert_paths_within_ownership(packet, [path], **kwargs)

    def test_broad_scope_exclusion_and_missing_binding(self):
        for persona in (LUCIEN, IRIS):
            packet = writer(persona, owned=["src"])
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(packet, ["src/components/A.tsx"], **binding(packet))
            packet = writer(persona, excluded=["src/components/private"])
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(packet, ["src/components/private/A.tsx"], **binding(packet))
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(packet, ["src/components/A.tsx"])
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(packet, ["src/components/A.tsx"], require_write_operation=False)

    def test_identity_spoof_and_contract_drift(self):
        packet = writer()
        for provider, actor in (("github", "339001004"), ("github", "335897759"),
                                ("native", "359299805"), ("other", "359299805")):
            with self.subTest(provider=provider, actor=actor), self.assertRaises(PolicyViolationError):
                assert_frontend_actor_binding(packet, **binding(packet, provider, actor))
        for key in ("actor_id", "worker_id", "host_id", "identity_provider", "persona", "formal_role"):
            kwargs = binding(packet)
            kwargs["observed_actor"][key] = "different"
            with self.subTest(key=key), self.assertRaises(PolicyViolationError):
                assert_frontend_actor_binding(packet, **kwargs)
        stale = binding(packet)
        changed = copy.deepcopy(packet)
        changed["objective"]["statement"] = "Different objective"
        with self.assertRaises(PolicyViolationError):
            assert_frontend_actor_binding(changed, **stale)
        iris = writer(IRIS)
        with self.assertRaises(PolicyViolationError):
            assert_frontend_actor_binding(iris, **binding(iris, "github", "359299805"))

    def test_paused_review_and_legacy(self):
        for persona in (LUCIEN, IRIS):
            packet = writer(persona)
            for fields in ({"work_mode": "PAUSED"}, {"formal_role": "Reviewer"},
                           {"allowed_operations": ["READ"]}):
                with self.subTest(persona=persona, fields=fields), self.assertRaises(PolicyViolationError):
                    assert_paths_within_ownership(dict(packet, **fields), ["src/components/A.tsx"],
                                                  require_write_operation=False)
        legacy = historical_packet()
        legacy.update(assigned_persona=LUCIEN, formal_role="Code Writer",
                      allowed_operations=["READ", "WRITE_OWNED"], owned_paths=["docs/adr", "src/components"])
        self.assertEqual(assert_paths_within_ownership(legacy, ["docs/adr/old.md"]), ["docs/adr/old.md"])
        for persona in (LUCIEN, IRIS):
            legacy["assigned_persona"] = persona
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(legacy, ["src/components/A.tsx"])

    def test_canonical_authorship_and_separate_architecture(self):
        path = "standards/frontend/README.md"
        packet = writer(owned=["standards/frontend"], canonical=True)
        self.assertEqual(assert_paths_within_ownership(packet, [path], **binding(packet)), [path])
        for persona in (IRIS, "Antigravity-Jane"):
            other = writer(persona, owned=["standards/frontend"], canonical=True)
            with self.assertRaises(PolicyViolationError):
                assert_paths_within_ownership(other, [path], **binding(other))
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(packet, [path], **binding(packet, "native", "native:fixture-lucien"))
        wrong_repo = writer(owned=["standards/frontend"])
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(wrong_repo, [path], **binding(wrong_repo))
        adr = writer(owned=["docs/adr"])
        self.assertEqual(assert_paths_within_ownership(adr, ["docs/adr/Decision.md"], **binding(adr)),
                         ["docs/adr/Decision.md"])
        iris = writer(IRIS, owned=["docs/adr"])
        with self.assertRaises(PolicyViolationError):
            assert_paths_within_ownership(iris, ["docs/adr/Decision.md"], **binding(iris))

    def test_declaration_matches_profile_and_existing_sources(self):
        profile = json.loads((ROOT / "integrations/antigravity/profiles/frontend_web.json").read_text(encoding="utf-8"))
        declaration = json.loads((ROOT / profile["frontend_standard"]["declaration_path"]).read_text(encoding="utf-8"))
        self.assertEqual(set(declaration["personas"]), {LUCIEN, IRIS})
        self.assertEqual(profile["eligible_frontend_personas"], declaration["personas"])
        self.assertEqual(profile["frontend_standard"]["entrypoint"], declaration["entrypoint"])
        self.assertEqual(set(declaration["selection_order"]), set(declaration["domains"]))
        self.assertEqual(declaration["required_domains"], ["evidence"])
        self.assertTrue(profile["frontend_standard"]["required"])
        self.assertEqual(declaration["rules"]["unknown_domain"], "DENY")
        self.assertEqual(declaration["rules"]["receipt"], "verified_consumption_only")
        for path in [declaration["entrypoint"], *[p for paths in declaration["domains"].values() for p in paths]]:
            self.assertTrue(path.startswith("standards/frontend/"))
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
