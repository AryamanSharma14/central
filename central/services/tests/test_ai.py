# Copyright (c) 2026, frappe and Contributors
# See license.txt

from contextlib import contextmanager
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from central.integrations.grove import GroveClient, GroveUnavailable
from central.services import ai
from central.services.api import ai as api
from central.services.doctype.ai_settings import ai_settings

MINTED = {
	"name": "k1",
	"geography": "eu",
	"gateway_url": "https://eu.llm.frappe.cloud",
	"api_key": "gr_testsecret",
}
LIMITS = [{"metric": "requests", "window": "1m", "value": 20}]
LISTED = {
	"name": "k1",
	"title": "app",
	"status": "active",
	"creation": "2026-10-06 10:00:00",
	"revocable_at": "2026-10-06T10:30:00Z",
	"key_hash": "abc123",
	"masked": "gr_test…",
	"geography": "eu",
	"gateway_url": "https://eu.llm.frappe.cloud",
	"cap": 5.0,
	"spent": 1.25,
	"limits": LIMITS,
}
MODELS = [{"name": "acme/m", "provider": "acme", "model_id": "m", "dialects": ["openai"]}]
GEOGRAPHIES = [
	{"name": "eu", "label": "Europe", "endpoint": "https://eu.llm.frappe.cloud", "is_default": True}
]
EMPTY_USAGE = {
	"from_date": "2026-09-30",
	"to_date": "2026-09-30",
	"as_of": None,
	"model_summary": [],
	"daily_summary": [],
}


@contextmanager
def grove_replies(message):
	with patch("central.integrations.grove.requests.post") as post:
		post.return_value.status_code = 200
		post.return_value.json.return_value = {"message": message}
		yield post


def sent(post) -> tuple[str, dict]:
	return post.call_args.args[0].rsplit("/api/method/", 1)[1], post.call_args.kwargs["json"]


class TestGroveClientCalls(IntegrationTestCase):
	"""What the client puts on the wire. The argument names are Grove's `grove.api` signatures:
	Grove drops a name it does not know and rejects a wrong type."""

	def setUp(self):
		self.client = GroveClient("http://grove.localhost:8001", "control-key", "control-secret")

	def test_enroll_exchanges_the_bootstrap_secret_and_nothing_else(self):
		minted = {"api_key": "gr_key", "api_secret": "gr_sec"}
		with grove_replies(minted) as post:
			result = GroveClient.enroll("http://grove.localhost:8001", "bootstrap-xyz")

		self.assertEqual(
			sent(post),
			(
				"grove.api.create_control_client",
				{"email": f"central@{frappe.local.site}", "token": "bootstrap-xyz"},
			),
		)
		self.assertNotIn("headers", post.call_args.kwargs)
		self.assertEqual(result, minted)

	def test_a_team_is_registered_under_the_control_credential(self):
		with grove_replies({"team": "TEAM-1", "max_keys": 10}) as post:
			self.client.provision_team("TEAM-1", free=True)

		self.assertEqual(
			sent(post),
			("grove.api.provision_team", {"team": "TEAM-1", "free": True}),
		)
		self.assertEqual(
			post.call_args.kwargs["headers"], {"Authorization": "token control-key:control-secret"}
		)

	def test_keys_are_minted_listed_capped_and_revoked_by_team_and_name(self):
		with grove_replies(MINTED) as post:
			self.client.provision_key("TEAM-1", "n8n prod", "eu", 5)
		self.assertEqual(
			sent(post),
			("grove.api.provision_key", {"team": "TEAM-1", "title": "n8n prod", "geography": "eu", "cap": 5}),
		)

		with grove_replies([LISTED]) as post:
			self.client.list_keys("TEAM-1")
		self.assertEqual(sent(post), ("grove.api.keys", {"team": "TEAM-1"}))

		with grove_replies([LISTED]) as post:
			self.client.update_caps("TEAM-1", {"k1": 7.5})
		self.assertEqual(sent(post), ("grove.api.update_caps", {"team": "TEAM-1", "caps": {"k1": 7.5}}))

		with grove_replies("Revoked.") as post:
			self.client.revoke_key("TEAM-1", "k1")
		self.assertEqual(sent(post), ("grove.api.revoke_key", {"team": "TEAM-1", "key": "k1"}))

	def test_models_geographies_spend_and_usage_name_the_team(self):
		calls = [
			(
				lambda: self.client.list_models("TEAM-1", "k1"),
				("grove.api.available_models", {"team": "TEAM-1", "key": "k1", "geography": None}),
			),
			(
				lambda: self.client.list_models(geography="eu"),
				("grove.api.available_models", {"team": None, "key": None, "geography": "eu"}),
			),
			(lambda: self.client.list_geographies(), ("grove.api.geographies", {})),
			(lambda: self.client.get_spend("TEAM-1"), ("grove.api.spend", {"team": "TEAM-1"})),
			(
				lambda: self.client.get_usage(["TEAM-1"], period="Last 7 Days"),
				(
					"grove.api.usage",
					{"teams": ["TEAM-1"], "month": None, "period": "Last 7 Days", "key_hash": None},
				),
			),
			(
				lambda: self.client.update_team("TEAM-1", spend_limit=50),
				(
					"grove.api.update_team",
					{"team": "TEAM-1", "max_keys": None, "spend_limit": 50, "suspended": None},
				),
			),
		]
		for call, expected in calls:
			with grove_replies([]) as post:
				call()
			self.assertEqual(sent(post), expected)

	def test_a_grove_refusal_is_raised(self):
		with patch("central.integrations.grove.requests.post") as post:
			post.return_value.status_code = 403
			post.return_value.text = "Not permitted"
			with self.assertRaises(frappe.ValidationError) as refused:
				self.client.list_keys("TEAM-1")
		self.assertNotIsInstance(refused.exception, GroveUnavailable, "a refusal is not an outage")

	def test_a_grove_that_is_down_or_in_maintenance_is_unavailable(self):
		with patch("central.integrations.grove.requests.post", side_effect=requests.ConnectionError):
			with self.assertRaises(GroveUnavailable):
				self.client.list_keys("TEAM-1")
		for status in (502, 503, 504):
			with patch("central.integrations.grove.requests.post") as post:
				post.return_value.status_code = status
				with self.assertRaises(GroveUnavailable, msg=status):
					self.client.list_keys("TEAM-1")


class TestAI(IntegrationTestCase):
	def setUp(self):
		team = frappe.get_all(
			"Team", filters={"owner_user": ("is", "set")}, fields=["name", "owner_user"], limit=1
		)
		if not team:
			self.skipTest("Needs a Team with an owner on the site.")
		self.team, self.owner = team[0].name, team[0].owner_user

		settings = frappe.get_single("AI Settings")
		settings.update(
			{
				"base_url": "http://grove.localhost:8001",
				"control_api_key": "control-key",
				"control_api_secret": "control-secret",
			}
		)
		settings.save()
		frappe.db.delete("Team Service", {"add_on_service": "ai"})
		self.addCleanup(frappe.set_user, "Administrator")

	def enabled(self):
		with (
			patch.object(GroveClient, "provision_team", return_value={"team": self.team, "max_keys": 10}),
			patch.object(GroveClient, "update_team"),
		):
			return ai.enable(self.team)

	def test_enabling_registers_the_team_as_free_at_its_alert_address(self):
		frappe.set_user(self.owner)
		with (
			patch.object(
				GroveClient, "provision_team", return_value={"team": self.team, "max_keys": 10}
			) as provision_team,
			patch.object(GroveClient, "update_team") as update_team,
		):
			name = api.enable_ai(self.team)["name"]
			self.assertEqual(api.enable_ai(self.team)["name"], name)

		provision_team.assert_called_once_with(self.team, free=True)
		# The tier's limits and the standing go with it, so the first key has room for a cap.
		update_team.assert_called_once_with(self.team, **ai.get_team_limits(self.team))
		service = frappe.get_doc("Team Service", name)
		# Prepaid at Grove, and each key calls its own geography: no subscription, no region,
		# no endpoint on the row.
		self.assertEqual(
			(service.status, service.subscription, service.region, service.endpoint_url),
			("Active", None, None, None),
		)

	def test_a_grove_refusal_leaves_ai_off(self):
		with patch.object(GroveClient, "provision_team", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				ai.enable(self.team)

		self.assertIsNone(ai.get_ai_service(self.team))

	def test_a_team_has_one_ai_service(self):
		self.enabled()
		duplicate = frappe.get_doc(
			{"doctype": "Team Service", "team": self.team, "add_on_service": "ai", "status": "Active"}
		)
		# Refused before Grove is dialled.
		with patch.object(GroveClient, "provision_team") as provision_team:
			with self.assertRaises(frappe.ValidationError):
				duplicate.insert()
		provision_team.assert_not_called()

	def test_storage_still_needs_a_region(self):
		storage = frappe.get_doc(
			{"doctype": "Team Service", "team": self.team, "add_on_service": "storage", "status": "Active"}
		)
		storage.subscription = "any"
		with self.assertRaises(frappe.MandatoryError):
			storage.validate()

	def test_the_page_says_grove_is_unavailable_instead_of_failing(self):
		self.enabled()
		with patch.object(GroveClient, "get_spend", side_effect=GroveUnavailable):
			self.assertEqual(api.get_ai(self.team), {"enabled": True, "unavailable": True})

	def test_ai_off_answers_with_nothing_and_refuses_the_rest(self):
		self.assertEqual(api.get_ai(self.team), {"enabled": False})
		with self.assertRaises(frappe.ValidationError):
			api.list_api_keys(self.team)

	def test_the_overview_carries_spend_this_months_usage_and_the_geographies(self):
		self.enabled()
		spend = {
			"spent": 7.5, "month_spent": 7.5, "capped": 20.0, "spend_limit": 50.0,
			"max_keys": 10, "suspended": False, "is_free_user": False,
		}
		month = {**EMPTY_USAGE, self.team: {"requests": 6, "tokens": 900, "cost": 7.5}}
		with (
			patch.object(GroveClient, "get_spend", return_value=spend),
			patch.object(GroveClient, "get_usage", return_value=month) as get_usage,
			patch.object(GroveClient, "list_geographies", return_value=GEOGRAPHIES),
		):
			first = api.get_ai(self.team)

		self.assertEqual(first["spend"], spend)
		self.assertEqual(first["usage"]["tokens"], 900)
		self.assertEqual(first["usage"]["to_date"], EMPTY_USAGE["to_date"])
		self.assertEqual(first["geographies"], GEOGRAPHIES)
		self.assertEqual(get_usage.call_args.kwargs["period"], "This Month")

	def test_a_key_is_minted_in_a_geography_with_a_cap_and_its_secret_is_returned_once(self):
		self.enabled()
		with (
			patch.object(GroveClient, "provision_key", return_value=MINTED) as provision_key,
			patch.object(GroveClient, "list_models", return_value=MODELS) as list_models,
		):
			created = api.create_api_key(self.team, " app ", "eu", "5")
		provision_key.assert_called_once_with(self.team, "app", "eu", 5.0)
		list_models.assert_called_once_with(self.team, "k1")
		self.assertEqual(
			(created["api_key"], created["geography"], created["gateway_url"]),
			(MINTED["api_key"], "eu", MINTED["gateway_url"]),
		)
		self.assertEqual(created["models"][0]["name"], "acme/m")

		with patch.object(GroveClient, "list_keys", return_value=[LISTED]):
			[listed] = api.list_api_keys(self.team)
		self.assertNotIn("key_hash", listed)
		self.assertEqual(
			(listed["masked"], listed["geography"], listed["cap"], listed["spent"], listed["limits"]),
			(LISTED["masked"], "eu", 5.0, 1.25, LIMITS),
		)
		# So the console can hold Revoke back instead of asking Grove and being refused.
		self.assertEqual(listed["revocable_at"], LISTED["revocable_at"])

		with patch.object(GroveClient, "update_caps", return_value=[{**LISTED, "cap": 7.5}]) as update_caps:
			self.assertEqual(api.set_api_key_caps(self.team, {"k1": "7.5"})[0]["cap"], 7.5)
		update_caps.assert_called_once_with(self.team, {"k1": 7.5})

		with patch.object(GroveClient, "revoke_key") as revoke_key:
			api.revoke_api_key(self.team, "k1")
		revoke_key.assert_called_once_with(self.team, "k1")

	def test_a_geographys_models_are_read_from_grove(self):
		self.enabled()
		with patch.object(GroveClient, "list_models", return_value=MODELS) as list_models:
			[model] = api.get_models(self.team, "eu")
			api.get_models(self.team, "")
		self.assertEqual(
			[call.kwargs for call in list_models.call_args_list], [{"geography": "eu"}, {"geography": None}]
		)
		self.assertEqual((model["name"], model["provider"], model["model_id"]), ("acme/m", "acme", "m"))

	def test_usage_of_one_key_sends_its_hash_and_an_unknown_key_is_refused(self):
		self.enabled()
		with (
			patch.object(GroveClient, "list_keys", return_value=[LISTED]),
			patch.object(GroveClient, "get_usage", return_value=EMPTY_USAGE) as get_usage,
		):
			report = api.get_usage(self.team, key="k1")
			self.assertEqual(get_usage.call_args.kwargs["key_hash"], "abc123")
			with self.assertRaises(frappe.DoesNotExistError):
				api.get_usage(self.team, key="someone-elses")

		self.assertEqual(report["totals"], {"requests": 0, "tokens": 0, "cost": 0})

	def test_usage_fills_the_quiet_days_for_every_model(self):
		self.enabled()
		usage = {
			"from_date": "2026-09-28",
			"to_date": "2026-09-29",
			"as_of": "2026-09-29T10:00:00Z",
			"model_summary": [{"model": "m-big", "requests": 2, "tokens": 300, "cost": 1.0}],
			"daily_summary": [
				{"day": "2026-09-29", "model": "m-big", "requests": 2, "tokens": 300, "cost": 1.0}
			],
			self.team: {"requests": 2, "tokens": 300, "cost": 1.0},
		}
		with patch.object(GroveClient, "get_usage", return_value=usage):
			report = api.get_usage(self.team, period="Last 30 Days")

		self.assertEqual(report["totals"], {"requests": 2, "tokens": 300, "cost": 1.0})
		self.assertEqual(
			report["daily"],
			[
				{"day": "2026-09-28", "model": "m-big", "requests": 0, "tokens": 0, "cost": 0},
				{"day": "2026-09-29", "model": "m-big", "requests": 2, "tokens": 300, "cost": 1.0},
			],
		)

	def test_the_teams_limits_are_its_tiers_and_its_standing(self):
		caps = frappe._dict(max_ai_keys=4, max_ai_spend=50)
		with (
			patch("central.billing.catalog.entitlements.get_team_caps", return_value=caps),
			patch("central.billing.catalog.subscriptions.anchor_subscription", return_value=None),
		):
			self.assertEqual(ai.get_team_limits(self.team), {"max_keys": 4, "spend_limit": 50, "suspended": False})
			# Untiered: Grove keeps its own key count.
			caps.max_ai_keys = 0
			self.assertIsNone(ai.get_team_limits(self.team)["max_keys"])

	def test_a_tier_or_standing_change_is_sent_to_grove_only_when_ai_is_on(self):
		profile = frappe._dict(doctype="Billing Profile", name=self.team, has_value_changed=lambda field: field == "trust_tier_level")
		standing = frappe._dict(doctype="Subscription", team=self.team, has_value_changed=lambda field: field == "account_standing")
		unchanged = frappe._dict(doctype="Subscription", team=self.team, has_value_changed=lambda field: False)
		with patch.object(frappe, "enqueue") as enqueue:
			ai.on_tier_update(profile)
			enqueue.assert_not_called()
			self.enabled()
			for doc in (profile, standing, unchanged):
				ai.on_tier_update(doc)

		self.assertEqual(enqueue.call_count, 2)
		enqueue.assert_called_with("central.services.ai.sync_team", team=self.team, enqueue_after_commit=True)

	def test_enroll_pops_the_secret_from_the_request_and_keeps_the_credential(self):
		minted = {"api_key": "gr_key", "api_secret": "gr_sec"}
		frappe.local.form_dict["bootstrap_secret"] = "bootstrap-xyz"
		with patch.object(GroveClient, "enroll", return_value=minted) as enroll:
			ai_settings.enroll()

		enroll.assert_called_once_with("http://grove.localhost:8001", "bootstrap-xyz")
		self.assertNotIn("bootstrap_secret", frappe.local.form_dict)
		settings = frappe.get_single("AI Settings")
		self.assertEqual(settings.control_api_key, "gr_key")
		self.assertEqual(settings.get_password("control_api_secret"), "gr_sec")
		with self.assertRaises(frappe.ValidationError):
			ai_settings.enroll()

	def test_rotation_asks_grove_for_a_new_secret_under_the_current_one(self):
		with patch.object(
			GroveClient, "rotate_control_key", return_value={"api_key": "k", "api_secret": "s2"}
		):
			ai_settings.rotate_credential()

		self.assertEqual(frappe.get_single("AI Settings").get_password("control_api_secret"), "s2")
