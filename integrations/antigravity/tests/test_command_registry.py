import unittest

from integrations.antigravity.factory.authority import ALLOWED_TRANSITIONS
from integrations.antigravity.factory.command_registry import (
    ALIASES, COMMANDS, ROLES, STAGES, _aliases, describe_commands, propose_command,
)


class CommandRegistryTests(unittest.TestCase):
    def test_every_route_is_non_authoritative(self):
        for alias, name in ALIASES.items():
            for role in ROLES:
                for stage in STAGES:
                    with self.subTest(alias=alias, role=role, stage=stage):
                        result = propose_command(alias, observed_role=role, observed_stage=stage)
                        self.assertFalse(result["authority_granted"])
                        self.assertFalse(result["invoked"])
                        self.assertFalse(result["promotion_authorized"])
                        expected = role in COMMANDS[name].roles and stage in COMMANDS[name].stages
                        self.assertEqual(result["status"], "PROPOSED" if expected else "BLOCKED")
                        if expected and result["next_stage"] != stage:
                            self.assertIn(result["next_stage"], ALLOWED_TRANSITIONS[stage])

    def test_help_aliases_identical(self):
        args = dict(observed_role="Reviewer", observed_stage="READY")
        self.assertEqual(propose_command("/help.forge", **args), propose_command("/forge.help", **args))

    def test_no_implicit_command_or_argument_parsing(self):
        for alias in ("forge", "/FORGE", "/forge ", "/forge.verify --skip", "/forge;git push", None, []):
            self.assertEqual(propose_command(alias, observed_role="Code Writer", observed_stage="AUTHORIZED")["reason"],
                             "UNKNOWN_COMMAND")

    def test_invalid_observations_fail_closed(self):
        self.assertEqual(propose_command("/resume", observed_role=[], observed_stage="AUTHORIZED")["reason"],
                         "UNKNOWN_ROLE")
        self.assertEqual(propose_command("/resume", observed_role="Code Writer", observed_stage=None)["reason"],
                         "UNKNOWN_STAGE")

    def test_review_cannot_be_writer_self_acceptance(self):
        self.assertEqual(propose_command("/forge.review", observed_role="Code Writer", observed_stage="READY")["reason"],
                         "ROLE_NOT_ELIGIBLE")
        self.assertEqual(propose_command("/forge.accept", observed_role="Reviewer", observed_stage="UNDER_REVIEW")["reason"],
                         "ROLE_NOT_ELIGIBLE")

    def test_verification_and_delivery_not_read_only(self):
        self.assertEqual(propose_command("/forge.verify", observed_role="Reviewer", observed_stage="READY")["effect"],
                         "PROCESS_TEST")
        self.assertEqual(propose_command("/forge.deliver", observed_role="Maintainer", observed_stage="ACCEPTED")["effect"],
                         "REMOTE_EFFECT")

    def test_duplicate_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_COMMAND_ALIAS"):
            _aliases({"a": COMMANDS["help"], "b": COMMANDS["help"]})

    def test_catalog_is_detached(self):
        catalog = describe_commands()
        catalog[0]["aliases"].clear()
        self.assertIn("/forge", ALIASES)
