# Copyright (c) 2026, frappe and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from central.api.integrations.github import get_connection_attempt, oauth_callback
from central.infrastructure.doctype.github_connection.github_connection import (
	GitHubConnection,
	GitHubConnectionAttempt,
	GitHubRepositoryNotGranted,
)
from central.infrastructure.doctype.pilot_credential.pilot_credential import PilotCredential
from central.tests.test_iam import ensure_user

INSTALLATION = {"installation_id": "101", "account": "octo", "account_type": "User"}
PRIVATE = {"repository_id": "11", "full_name": "octo/private-app"}
OTHER = {"repository_id": "12", "full_name": "octo/other-app"}


def make_team(name: str, owner: str) -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Team",
				"team_name": name,
				"owner_user": owner,
				"members": [{"user": owner, "role": "Owner", "status": "Active"}],
			}
		)
		.insert()
		.name
	)


class IntegrationTestGitHubConnection(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.owner = ensure_user("github.owner@example.test")
		self.team = make_team("GitHub Team", self.owner)
		PilotCredential.mint(team=self.team, pilot_credential_id="pilot-github")
		self.credential = frappe.get_doc("Pilot Credential", "pilot-github")

	def test_a_new_grant_replaces_the_old_one_and_bumps_the_version(self):
		first = GitHubConnection.grant(self.credential, INSTALLATION, [PRIVATE])
		second = GitHubConnection.grant(self.credential, INSTALLATION, [OTHER])

		self.assertEqual(first.name, second.name)
		self.assertEqual(second.version, 2)
		self.assertFalse(first.is_current(1))
		with self.assertRaises(GitHubRepositoryNotGranted):
			GitHubConnection.find_repository(self.credential, PRIVATE["full_name"])

	def test_a_repository_removed_on_github_is_no_longer_granted(self):
		GitHubConnection.grant(self.credential, INSTALLATION, [PRIVATE, OTHER])

		GitHubConnection.remove_repositories(INSTALLATION["installation_id"], {PRIVATE["repository_id"]})

		with self.assertRaises(GitHubRepositoryNotGranted):
			GitHubConnection.find_repository(self.credential, PRIVATE["full_name"])
		_, repository_id = GitHubConnection.find_repository(self.credential, "OCTO/other-app")
		self.assertEqual(repository_id, OTHER["repository_id"])

	def test_revoking_one_account_keeps_the_other_accounts(self):
		organization = {"installation_id": "202", "account": "octo-org", "account_type": "Organization"}
		GitHubConnection.grant(self.credential, INSTALLATION, [PRIVATE])
		GitHubConnection.grant(
			self.credential, organization, [{"repository_id": "21", "full_name": "octo-org/app"}]
		)

		GitHubConnection.revoke(self.credential, INSTALLATION["installation_id"])

		with self.assertRaises(GitHubRepositoryNotGranted):
			GitHubConnection.find_repository(self.credential, PRIVATE["full_name"])
		self.assertEqual(GitHubConnection.find_repository(self.credential, "octo-org/app")[1], "21")

	def test_only_a_console_user_of_the_team_can_open_the_attempt(self):
		outsider = ensure_user("github.outsider@example.test")
		make_team("Outsider Team", outsider)
		attempt = GitHubConnectionAttempt.start(self.credential, "https://bench.example.test/settings")

		with self.assertRaises(frappe.PermissionError):
			GitHubConnectionAttempt.load(attempt.attempt_id).bind(outsider)

		GitHubConnectionAttempt.load(attempt.attempt_id).bind(self.owner)
		with self.assertRaises(frappe.PermissionError):
			GitHubConnectionAttempt.load(attempt.attempt_id).bind(ensure_user("github.second@example.test"))
		attempt.finish()

	def test_an_expired_link_still_leads_back_to_the_server(self):
		attempt = GitHubConnectionAttempt.start(self.credential, "https://bench.example.test/settings")
		attempt.bind(self.owner)
		attempt.finish()

		oauth_callback(state=attempt.state, code="code")
		self.assertEqual(frappe.local.response["location"], f"/dashboard/github/connect/{attempt.attempt_id}")

		frappe.set_user(self.owner)
		self.assertEqual(
			get_connection_attempt(attempt.attempt_id),
			{"is_expired": True, "return_url": "https://bench.example.test/settings"},
		)
