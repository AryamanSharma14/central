from unittest.mock import patch

import frappe

from central.billing.platform.alerts import notify_operators
from central.signups import trial
from central.tests.test_trial_lifecycle import TrialOnAMachine


class TestSignupAlerts(TrialOnAMachine):
	"""A failed signup reaches the operators once, through the operator alert channel."""

	def setUp(self):
		super().setUp()
		self.enqueue = self.enterContext(patch("central.signups.alerts.frappe.enqueue"))

	def creation(self):
		return frappe.get_doc("Resource Action", {"server": self.server.name, "resource_type": "Site"})

	def sent(self) -> list[dict]:
		return [
			{
				**call.kwargs["alerts"][0],
				"title": call.kwargs["title"],
				"after_commit": call.kwargs["enqueue_after_commit"],
			}
			for call in self.enqueue.call_args_list
			if call.args == (notify_operators,)
		]

	def test_a_failed_site_creation_alerts_once(self):
		envelope = {
			"code": "REGION_AT_CAPACITY",
			"message": "The region is full.",
			"remediation": "",
			"retriable": False,
		}
		action = self.creation()
		action.transition("Failed", envelope=envelope)
		action.transition("Failed", envelope=envelope)

		[alert] = self.sent()
		self.assertEqual(alert["alert"], "site creation failed")
		self.assertEqual(alert["title"], "Signup failed: site creation failed")
		self.assertEqual((alert["doctype"], alert["subject"]), ("Resource Action", action.name))
		self.assertEqual(alert["detail"], "REGION_AT_CAPACITY: The region is full.")
		self.assertTrue(alert["after_commit"])

	def test_an_uncertain_site_creation_alerts(self):
		self.creation().transition("Uncertain")

		self.assertEqual(self.sent()[0]["alert"], "site creation uncertain")

	def test_a_failed_trial_step_alerts(self):
		trial.Trial(self.site()).record_error("Could not stop the server.")

		[alert] = self.sent()
		self.assertEqual((alert["alert"], alert["subject"]), ("trial step failed", self.site().name))
		self.assertEqual(alert["team"], self.team.name)
