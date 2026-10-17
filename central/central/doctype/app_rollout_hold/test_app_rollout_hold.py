import frappe
from frappe.tests import IntegrationTestCase

from central.central.doctype.app_rollout_hold.app_rollout_hold import AppRolloutHold


def failing_row(commit: str, **changes) -> dict:
	return {
		"app": "erpnext",
		"to_commit": commit,
		"failed": 4,
		"total": 5,
		"error": "Migration failed",
		**changes,
	}


class IntegrationTestAppRolloutHold(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		frappe.db.delete("App Rollout Hold")

	def test_a_failing_release_is_held_with_its_counts_and_error(self):
		AppRolloutHold.hold_failing_releases([failing_row("abc")])

		hold = frappe.get_doc("App Rollout Hold", "abc")
		self.assertEqual(
			(hold.app, hold.failed, hold.total, hold.error), ("erpnext", 4, 5, "Migration failed")
		)
		self.assertEqual(AppRolloutHold.get_held_commits(), ["abc"])

	def test_the_same_release_is_held_once(self):
		AppRolloutHold.hold_failing_releases([failing_row("abc"), failing_row("abc")])
		AppRolloutHold.hold_failing_releases([failing_row("abc")])

		self.assertEqual(frappe.db.count("App Rollout Hold"), 1)

	def test_a_released_release_is_not_held_again(self):
		AppRolloutHold.hold_failing_releases([failing_row("abc")])
		frappe.db.set_value("App Rollout Hold", "abc", "released", 1)

		AppRolloutHold.hold_failing_releases([failing_row("abc")])

		self.assertEqual(AppRolloutHold.get_held_commits(), [])

	def test_a_bad_row_fails_the_alert_and_holds_nothing(self):
		no_error = failing_row("abc")
		del no_error["error"]
		bad_rows = (
			"abc",
			failing_row(""),
			failing_row("x" * 141),
			failing_row("abc", failed="4"),
			failing_row("abc", total=True),
			failing_row("abc", failed=6),
			failing_row("abc", failed=-1),
			failing_row("abc", error=["Migration failed"]),
			no_error,
		)
		for bad_row in bad_rows:
			with self.subTest(row=bad_row), self.assertRaises(frappe.ValidationError):
				AppRolloutHold.hold_failing_releases([failing_row("good"), bad_row])

		self.assertEqual(AppRolloutHold.get_held_commits(), [])

	def test_the_config_sends_the_held_commits(self):
		AppRolloutHold.hold_failing_releases([failing_row("abc")])

		self.assertEqual(frappe.get_doc("Central Settings").app_rollout()["held_commits"], ["abc"])
