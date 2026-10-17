from unittest.mock import Mock, patch

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from central.infrastructure.doctype.resource_action.resource_action import ResourceAction
from central.infrastructure.doctype.site.site import Site
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
			is_free_trial=1,
			request_key="request-" + frappe.generate_hash(length=8),
			request_payload={"image_tags": {"purpose": "pilot"}, "site": {"product": None}},
		)
		self.enroll()
		self.enterContext(
			patch("central.integrations.pilot.rename_admin_domain", return_value={"task_id": "task-1"})
		)
		observe_server(self.server)
		self.notices = self.enterContext(patch("central.signups.trial.queue_event"))
		self.funnel = self.enterContext(patch("central.signups.trial.capture_trial_event"))
		self.enterContext(patch.object(frappe.db, "commit"))
		self.enterContext(
			self.change_settings(
				"Central Settings", trial_days=14, trial_deletion_days=7, trial_notice_days=3
			)
		)

	def record_site_again(self):
		frappe.db.delete("Site", {"server": self.server.name})
		Site.create_once_addressable(self.server.name)
		return self.site()

	def run_on(self, days_from_today: int):
		trial.advance_trial(self.site(), getdate(add_days(nowdate(), days_from_today)))
		return self.site()

	def sent_events(self) -> list[str]:
		return [call.args[1] for call in self.notices.call_args_list]

	def funnel_events(self) -> list[str]:
		return [call.args[0] for call in self.funnel.call_args_list]

	def test_a_new_trial_site_gets_its_end_date_before_it_is_ready(self):
		site = self.site()

		self.assertIsNone(site.ready_at)
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

	def test_the_patch_starts_a_trial_site_recorded_before_trials_started_on_insert(self):
		from central.patches.v0_0 import start_unready_trials

		self.site().db_set({"trial_state": "", "trial_ends_on": None})
		start_unready_trials.execute()

		site = self.site()
		self.assertEqual(site.trial_state, "Active")
		self.assertEqual(getdate(site.trial_ends_on), getdate(add_days(nowdate(), 14)))

	def test_the_patch_leaves_a_site_from_before_trials_that_was_opened(self):
		from central.patches.v0_0 import start_unready_trials

		self.site().db_set({"trial_state": "", "trial_ends_on": None, "claimed_at": now_datetime()})
		start_unready_trials.execute()

		self.assertFalse(self.site().trial_state)

	def test_a_team_that_pays_has_no_trial(self):
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "is_free_trial", 0)
		site = self.record_site_again()

		self.assertEqual(site.trial_state, "Converted")
		self.assertIsNone(site.trial_ends_on)

	def test_a_team_that_has_paid_before_gets_no_free_trial(self):
		invoice = frappe.get_doc({"doctype": "Invoice", "team": self.team.name, "status": "Draft"})
		invoice.db_insert()
		self.assertTrue(trial.is_free_trial_creation(self.team.name, "Site"))

		invoice.db_set("status", "Overdue")
		self.assertFalse(trial.is_free_trial_creation(self.team.name, "Site"))

	def test_a_team_with_a_subscription_gets_no_free_trial(self):
		frappe.get_doc({"doctype": "Subscription", "team": self.team.name}).db_insert()

		self.assertFalse(trial.is_free_trial_creation(self.team.name, "Site"))

	def test_a_card_cancelled_before_the_site_is_recorded_keeps_the_server_paid(self):
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "is_free_trial", 0)
		with patch("central.signups.trial.has_active_payment_method", return_value=False):
			site = self.record_site_again()

		self.assertEqual(site.trial_state, "Converted")
		self.assertFalse(trial.is_billing_deferred(self.server.name))

	def test_a_card_added_before_the_site_is_recorded_converts_it_on_record(self):
		self.server.db_set("status", "Running")
		with patch("central.signups.trial.has_active_payment_method", return_value=True):
			site = self.record_site_again()

		self.assertEqual(site.trial_state, "Converted")
		self.assertEqual(self.sent_events(), ["trial_converted"])
		self.assert_conversion_queued()

	def test_the_patch_marks_creations_that_started_a_trial(self):
		from central.patches.v0_0 import set_free_trial_on_creations

		frappe.db.set_value("Resource Action", {"server": self.server.name}, "is_free_trial", 0)
		set_free_trial_on_creations.execute()

		self.assertEqual(
			frappe.db.get_value("Resource Action", {"server": self.server.name}, "is_free_trial"), 1
		)

	def test_a_site_that_is_not_a_trial_has_no_trial_state(self):
		frappe.db.delete("Resource Action", {"server": self.server.name})

		self.assertFalse(self.record_site_again().trial_state)

	def test_warnings_go_out_three_days_and_one_day_before_the_end_once_each(self):
		for days in (11, 12, 13, 13):
			self.run_on(days)

		self.assertEqual(self.sent_events(), ["trial_expiring", "trial_expiring"])
		self.assertEqual(self.site().trial_last_notice, "last day")

	def test_a_ready_site_that_nobody_opened_gets_one_reminder_the_next_day(self):
		self.site().db_set("ready_at", now_datetime())
		self.run_on(0)
		self.run_on(1)
		self.run_on(2)

		self.assertEqual(self.sent_events(), ["trial_unopened"])

	def test_an_opened_site_gets_no_reminder(self):
		self.site().db_set({"ready_at": now_datetime(), "claimed_at": now_datetime()})
		self.run_on(1)

		self.assertEqual(self.sent_events(), [])

	def test_the_end_date_stops_the_server_and_sets_the_deletion_date(self):
		with patch("central.signups.trial.enqueue_stop") as enqueue_stop:
			site = self.run_on(14)

		self.assertEqual(site.trial_state, "Ended")
		self.assertEqual(getdate(site.trial_deletes_on), getdate(add_days(nowdate(), 21)))
		enqueue_stop.assert_called_once()
		self.assertEqual(self.sent_events(), [])
		self.assertEqual(self.funnel_events(), ["trial_ended"])

	def test_the_team_hears_the_trial_ended_once_the_server_is_stopped(self):
		self.site().db_set("trial_state", "Ended")
		with patch("central.integrations.servers.hold_server_stopped"):
			trial.stop_trial_server(self.site().name)

		self.assertEqual(self.sent_events(), ["trial_ended"])

	def test_the_deletion_date_terminates_the_server_and_deletes_the_site_once_it_is_gone(self):
		self.site().db_set({"trial_state": "Ended", "trial_deletes_on": nowdate()})

		site = self.run_on(0)

		self.assertEqual(site.trial_state, "Ended")
		action = frappe.get_last_doc("Resource Action", {"server": self.server.name, "action": "terminate"})
		self.assertEqual(action.requested_by, "Administrator")
		self.assertEqual(self.sent_events(), [])

		frappe.db.set_value("Virtual Machine", self.server.name, "status", "Terminated")
		site = self.run_on(0)

		self.assertEqual(site.trial_state, "Deleted")
		self.assertEqual(self.sent_events(), ["trial_deleted"])
		self.assertEqual(self.funnel_events(), ["trial_deleted"])

	def test_a_refused_termination_stays_selectable_and_is_asked_again(self):
		self.site().db_set({"trial_state": "Ended", "trial_deletes_on": nowdate()})
		self.run_on(0)
		frappe.db.set_value(
			"Resource Action",
			{"server": self.server.name, "action": "terminate"},
			"status",
			"Failed",
		)

		site = self.run_on(0)

		self.assertEqual(site.trial_state, "Ended")
		self.assertIn("did not terminate", site.trial_error)
		self.assertEqual(
			frappe.db.count("Resource Action", {"server": self.server.name, "action": "terminate"}), 2
		)

	def test_a_failed_stop_leaves_the_reason_on_the_site(self):
		self.site().db_set("trial_state", "Ended")
		with (
			patch("central.integrations.servers.hold_server_stopped", side_effect=RuntimeError("down")),
			patch.object(frappe.db, "rollback"),
		):
			trial.stop_trial_server(self.site().name)

		self.assertIn("could not stop", self.site().trial_error)
		self.assertEqual(self.sent_events(), [])

	def test_a_converted_trial_is_not_stopped(self):
		self.site().db_set("trial_state", "Converted")
		with patch("central.integrations.servers.hold_server_stopped") as hold_server_stopped:
			trial.stop_trial_server(self.site().name)

		hold_server_stopped.assert_not_called()

	def test_a_trial_server_has_no_subscription_until_it_converts(self):
		self.assertTrue(trial.is_billing_deferred(self.server.name))

		self.site().db_set("trial_state", "Converted")
		self.assertFalse(trial.is_billing_deferred(self.server.name))

	def test_a_bought_server_is_billed_at_once(self):
		frappe.db.set_value(
			"Resource Action",
			{"server": self.server.name},
			{
				"resource_type": "Server",
				"is_free_trial": 0,
				"request_payload": '{"image_tags": {"purpose": "pilot"}}',
			},
		)
		self.record_site_again()

		self.assertFalse(trial.is_billing_deferred(self.server.name))

	def test_an_active_payment_method_converts_the_team_trials(self):
		frappe.db.set_value("Resource Action", {"server": self.server.name}, "reserved_monthly_rate", 30)
		frappe.db.set_value(
			"Site", self.site().name, "creation", add_days(now_datetime(), -3), update_modified=False
		)
		self.server.db_set("status", "Running")
		method = Mock(team=self.team.name, status="Active")
		method.get_doc_before_save.return_value = Mock(status="Pending Validation")

		with patch("central.signups.credit.grant_welcome_credits"):
			credit.on_payment_method_update(method)

		site = self.site()
		self.assertEqual(site.trial_state, "Converted")
		self.assertAlmostEqual(site.trial_cost, 3, places=1)
		self.funnel.assert_called_once_with("trial_converted", self.team.name, None, days_in_trial=3)
		self.assertEqual(self.sent_events(), ["trial_converted"])
		VirtualMachine.ensure_subscription_enabled.assert_called()
		self.assert_conversion_queued()

	def test_a_payment_method_leaves_an_ended_trial_stopped(self):
		self.site().db_set("trial_state", "Ended")
		method = Mock(team=self.team.name, status="Active")
		method.get_doc_before_save.return_value = Mock(status="Pending Validation")

		with patch("central.signups.credit.grant_welcome_credits"):
			credit.on_payment_method_update(method)

		self.assertEqual(self.site().trial_state, "Ended")
		with patch("central.signups.trial.has_active_payment_method", return_value=True):
			self.assertTrue(trial.get_status(self.server.name)["can_keep"])

	def test_keeping_an_ended_trial_converts_it_and_starts_its_server(self):
		from central.api.servers import keep_trial_site

		self.site().db_set("trial_state", "Ended")
		with patch("central.signups.trial.has_active_payment_method", return_value=True):
			keep_trial_site(self.team.name, self.server.resource_id)

		self.assertEqual(self.site().trial_state, "Converted")
		self.assert_conversion_queued()

	def test_an_ended_trial_is_kept_only_with_a_payment_method(self):
		from central.api.servers import keep_trial_site

		self.site().db_set("trial_state", "Ended")
		self.assertFalse(trial.get_status(self.server.name)["can_keep"])
		with self.assertRaisesRegex(frappe.ValidationError, "Add a payment method"):
			keep_trial_site(self.team.name, self.server.resource_id)

		self.assertEqual(self.site().trial_state, "Ended")

	def test_only_a_billing_manager_keeps_a_trial(self):
		from central.api.servers import keep_trial_site

		self.site().db_set("trial_state", "Ended")
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			keep_trial_site(self.team.name, self.server.resource_id)

	def test_a_sleeping_server_is_subscribed_when_its_trial_converts(self):
		self.server.db_set("status", "Paused")
		VirtualMachine.ensure_subscription_enabled.reset_mock()

		trial.convert_site(self.site())

		VirtualMachine.ensure_subscription_enabled.assert_called_once()

	def test_resize_options_say_a_converted_server_is_still_starting(self):
		from central.billing.api.dashboard.catalog import get_composed_config

		self.site().db_set("trial_state", "Converted")

		config = get_composed_config(self.server.name, self.team.name)

		self.assertTrue(config["starting"])
		self.assertIsNone(config["trial"])

	def assert_conversion_queued(self):
		frappe.enqueue.assert_any_call(
			trial.finish_conversion,
			site=self.site().name,
			queue="long",
			enqueue_after_commit=True,
			job_id=f"trial-convert:{self.site().name}",
			deduplicate=True,
		)

	def test_a_converted_server_that_the_trial_stopped_starts_again(self):
		self.site().db_set("trial_state", "Converted")
		self.server.db_set("status", "Stopped")
		with patch("central.integrations.servers.convert_trial_server") as convert_trial_server:
			trial.finish_conversion(self.site().name)

		convert_trial_server.assert_called_once_with(self.server.name, start=True)

	def test_the_in_app_trial_status_carries_the_credit_offer_and_the_idle_minutes(self):
		"""The site's billing tab reads these fields; their names are the contract with Pilot."""
		status = trial.get_status(self.server.name)

		self.assertEqual(
			set(status),
			{"state", "can_keep", "ends_on", "days_left", "deletes_on", "credit", "sleeps_after_minutes"},
		)
		self.assertEqual(status["sleeps_after_minutes"], trial.get_sleep_minutes())

	def test_resize_options_say_the_trial_blocks_a_resize(self):
		from central.billing.api.dashboard.catalog import get_composed_config

		config = get_composed_config(self.server.name, self.team.name)

		self.assertFalse(config["resizable"])
		self.assertEqual(config["trial"]["state"], "Active")

	def test_a_pending_action_defers_the_conversion_to_the_daily_job(self):
		"""Any pending action on the server, not only a resize, defers it with a reason to retry."""
		self.site().db_set("trial_state", "Converted")
		for action in ("resize", "restart"):
			pending = ResourceAction.queue(
				action, self.team.name, self.region.name, "pending", server=self.server.name
			)
			with patch("central.integrations.servers.convert_trial_server") as convert_trial_server:
				trial.finish_conversion(self.site().name)

			convert_trial_server.assert_not_called()
			self.assertIn("Another action is running", self.site().trial_error)
			pending.db_set("status", "Succeeded")

	def test_a_failed_conversion_leaves_the_reason_and_the_daily_job_retries_it(self):
		self.site().db_set("trial_state", "Converted")
		with (
			patch("central.integrations.servers.convert_trial_server", side_effect=RuntimeError("down")),
			patch.object(frappe.db, "rollback"),
		):
			trial.finish_conversion(self.site().name)

		self.assertIn("could not start", self.site().trial_error)

		frappe.enqueue.reset_mock()
		trial.run_trials()
		self.assert_conversion_queued()

	def test_a_team_that_pays_during_the_stop_gets_its_server_back(self):
		self.site().db_set("trial_state", "Ended")

		def pay_during_stop(server):
			self.site().db_set("trial_state", "Converted")

		with patch("central.integrations.servers.hold_server_stopped", side_effect=pay_during_stop):
			trial.stop_trial_server(self.site().name)

		self.assert_conversion_queued()
		self.assertEqual(self.sent_events(), [])

	def test_an_ended_trial_cannot_be_started(self):
		self.site().db_set("trial_state", "Ended")

		with self.assertRaisesRegex(frappe.ValidationError, "Add a payment method"):
			submit_command("start", self.team.name, self.server.name)
		with (
			patch("central.resource_actions.has_active_payment_method", return_value=True),
			self.assertRaisesRegex(frappe.ValidationError, "Keep this site"),
		):
			submit_command("start", self.team.name, self.server.name)

	def test_a_team_has_a_limited_number_of_free_trial_sites(self):

		with self.change_settings("Central Settings", trial_servers_per_team=1):
			with self.assertRaisesRegex(frappe.ValidationError, "at most 1 free trial"):
				validate_trial_site(self.team.name)

	def test_a_server_whose_site_is_not_recorded_yet_still_counts_toward_the_limit(self):
		frappe.db.delete("Site", {"server": self.server.name})

		with self.change_settings("Central Settings", trial_servers_per_team=1):
			with self.assertRaisesRegex(frappe.ValidationError, "at most 1 free trial"):
				validate_trial_site(self.team.name)

	def test_the_billing_panel_reads_the_open_trial_of_the_server(self):

		status = trial.get_status(self.server.name)
		self.assertEqual(status["state"], "Active")
		self.assertEqual(status["days_left"], 14)
		self.assertIsNone(trial.get_status(self.server.name, site="other.example.test"))

		self.site().db_set("trial_state", "Converted")
		self.assertIsNone(trial.get_status(self.server.name))

	def test_an_operator_extends_an_ended_trial_and_its_server_starts(self):
		self.site().db_set(
			{"trial_state": "Ended", "trial_ends_on": nowdate(), "trial_deletes_on": nowdate()}
		)

		self.site().extend_trial(7)

		site = self.site()
		self.assertEqual(site.trial_state, "Active")
		self.assertEqual(getdate(site.trial_ends_on), getdate(add_days(nowdate(), 7)))
		self.assertIsNone(site.trial_deletes_on)
		self.assertTrue(frappe.db.exists("Resource Action", {"server": self.server.name, "action": "start"}))

	def test_an_operator_ends_an_active_trial_now(self):
		with patch("central.signups.trial.enqueue_stop"):
			self.site().end_trial_now()

		self.assertEqual(self.site().trial_state, "Ended")

	def test_only_an_operator_changes_a_trial(self):
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			self.site().extend_trial(7)
