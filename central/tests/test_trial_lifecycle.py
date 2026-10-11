from unittest.mock import Mock, patch

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from central.infrastructure.doctype.resource_action.resource_action import ResourceAction
from central.infrastructure.doctype.virtual_machine.virtual_machine import VirtualMachine
from central.integrations.servers import observe_server
from central.resource_actions import submit_command, validate_trial_site
from central.signups import credit, trial
from central.tests.test_sites import SiteOnAMachine


class TestTrialLifecycle(SiteOnAMachine):
	"""A trial site runs for its days, warns, stops, then is terminated."""

	def setUp(self):
		super().setUp()
		ResourceAction.queue(
			"create",
			self.team.name,
			self.region.name,
			self.server.name,
			server=self.server.name,
			resource_type="Site",
			request_key="request-" + frappe.generate_hash(length=8),
			request_payload={"image_tags": {"purpose": "pilot"}, "site": {"product": None}},
		)
		self.enroll()
		observe_server(self.server)
		self.notices = self.enterContext(patch("central.signups.trial.queue_event"))
		self.enterContext(patch.object(frappe.db, "commit"))
		self.enterContext(
			self.change_settings(
				"Central Settings", trial_days=14, trial_deletion_days=7, trial_notice_days=3
			)
		)

	def ready_site(self):
		self.site().record_ready()
		return self.site()

	def run_on(self, days_from_today: int):
		trial.advance_trial(self.site(), getdate(add_days(nowdate(), days_from_today)))
		return self.site()

	def sent_events(self) -> list[str]:
		return [call.args[1] for call in self.notices.call_args_list]

	def test_a_ready_trial_site_gets_its_end_date(self):
		site = self.ready_site()

		self.assertEqual(site.trial_state, "Active")
		self.assertEqual(getdate(site.trial_ends_on), getdate(add_days(nowdate(), 14)))

	def test_a_product_sets_its_own_trial_length(self):
		product = frappe.get_doc(
			{
				"doctype": "Product",
				"product_key": "raven-trial",
				"title": "Raven",
				"signup_app": "raven",
				"trial_days": 30,
			}
		).insert()

		self.assertEqual(trial.get_trial_days(product.name, "trial_days"), 30)
		self.assertEqual(trial.get_trial_days(product.name, "trial_deletion_days"), 7)

	def test_a_team_that_pays_has_no_trial(self):
		with patch("central.signups.trial.has_active_payment_method", return_value=True):
			site = self.ready_site()

		self.assertEqual(site.trial_state, "Converted")
		self.assertIsNone(site.trial_ends_on)

	def test_a_site_that_is_not_a_trial_has_no_trial_state(self):
		frappe.db.delete("Resource Action", {"server": self.server.name})

		self.assertFalse(self.ready_site().trial_state)

	def test_warnings_go_out_three_days_and_one_day_before_the_end_once_each(self):
		self.ready_site()
		for days in (11, 12, 13, 13):
			self.run_on(days)

		self.assertEqual(self.sent_events(), ["trial_expiring", "trial_expiring"])
		self.assertEqual(self.site().trial_last_notice, "last day")

	def test_the_end_date_stops_the_server_and_sets_the_deletion_date(self):
		self.ready_site()
		with patch("central.signups.trial.enqueue_stop") as enqueue_stop:
			site = self.run_on(14)

		self.assertEqual(site.trial_state, "Ended")
		self.assertEqual(getdate(site.trial_deletes_on), getdate(add_days(nowdate(), 21)))
		enqueue_stop.assert_called_once()
		self.assertEqual(self.sent_events(), ["trial_ended"])

	def test_the_deletion_date_terminates_the_server(self):
		self.ready_site()
		self.site().db_set({"trial_state": "Ended", "trial_deletes_on": nowdate()})

		site = self.run_on(0)

		self.assertEqual(site.trial_state, "Deleted")
		action = frappe.get_last_doc("Resource Action", {"server": self.server.name, "action": "terminate"})
		self.assertEqual(action.requested_by, "Administrator")
		self.assertEqual(self.sent_events(), ["trial_deleted"])

	def test_a_failed_stop_leaves_the_reason_on_the_site(self):
		self.ready_site()
		self.site().db_set("trial_state", "Ended")
		with (
			patch("central.integrations.servers.hold_server_stopped", side_effect=RuntimeError("down")),
			patch.object(frappe.db, "rollback"),
		):
			trial.stop_trial_server(self.site().name)

		self.assertIn("could not stop", self.site().trial_error)

	def test_a_converted_trial_is_not_stopped(self):
		self.ready_site()
		self.site().db_set("trial_state", "Converted")
		with patch("central.integrations.servers.hold_server_stopped") as hold_server_stopped:
			trial.stop_trial_server(self.site().name)

		hold_server_stopped.assert_not_called()

	def test_a_trial_server_has_no_subscription_until_it_converts(self):
		self.ready_site()
		self.assertTrue(trial.is_billing_deferred(self.server.name))

		self.site().db_set("trial_state", "Converted")
		self.assertFalse(trial.is_billing_deferred(self.server.name))

	def test_a_bought_server_is_billed_at_once(self):
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "resource_type", "Server")

		self.assertFalse(trial.is_billing_deferred(self.server.name))

	def test_an_active_payment_method_converts_the_team_trials(self):
		self.ready_site()
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "reserved_monthly_rate", 30)
		self.site().db_set({"trial_state": "Ended", "ready_at": add_days(now_datetime(), -3)})
		self.server.db_set("status", "Running")
		method = Mock(team=self.team.name, status="Active")
		method.get_doc_before_save.return_value = Mock(status="Pending Validation")

		with patch("central.signups.credit.grant_welcome_credits"):
			credit.on_payment_method_update(method)

		site = self.site()
		self.assertEqual(site.trial_state, "Converted")
		self.assertAlmostEqual(site.trial_cost, 3, places=1)
		VirtualMachine.ensure_subscription_enabled.assert_called()
		frappe.enqueue.assert_any_call(
			"central.integrations.servers.convert_trial_server",
			server=self.server.name,
			start=True,
			queue="long",
			enqueue_after_commit=True,
			job_id=f"trial-convert:{self.server.name}",
			deduplicate=True,
		)

	def test_an_ended_trial_cannot_be_started(self):
		self.ready_site()
		self.site().db_set("trial_state", "Ended")

		with self.assertRaisesRegex(frappe.ValidationError, "trial has ended"):
			submit_command("start", self.team.name, self.server.name)

	def test_a_team_has_a_limited_number_of_free_trial_sites(self):
		self.ready_site()

		with self.change_settings("Central Settings", trial_servers_per_team=1):
			with self.assertRaisesRegex(frappe.ValidationError, "at most 1 free trial"):
				validate_trial_site(self.team.name)

	def test_the_billing_panel_reads_the_open_trial_of_the_server(self):
		self.ready_site()

		status = trial.get_status(self.server.name)
		self.assertEqual(status["state"], "Active")
		self.assertEqual(status["days_left"], 14)
		self.assertIsNone(trial.get_status(self.server.name, site="other.example.test"))

		self.site().db_set("trial_state", "Converted")
		self.assertIsNone(trial.get_status(self.server.name))
