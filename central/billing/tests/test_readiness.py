# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""The readiness checks find what the next billing run would get wrong, before it runs."""

from unittest.mock import patch

import frappe

from central.billing.platform import alerts, invariants, readiness
from central.billing.report.billing_invariant_violations import billing_invariant_violations as report
from central.billing.tests.utils import BillingTestCase as IntegrationTestCase
from central.billing.tests.utils import (
	add_segment,
	clear_team_tier,
	complete_billing_profile,
	make_billing_subscription,
	make_plan,
	set_team_tier,
)

TEAM = "team-readiness"
CLUSTER = "ap-south-1"
PLAN = "bundle-readiness"


def _found(check: str, team: str = TEAM) -> list:
	return [v for v in invariants.audit(only=check, checks=readiness.CHECKS) if v.team == team]


class TestReadiness(IntegrationTestCase):
	def setUp(self):
		make_plan(PLAN)
		self.subscription = make_billing_subscription(TEAM, CLUSTER, PLAN, billing_cycle="Monthly")
		add_segment(self.subscription, "Created", 1000, "2026-06-01 00:00:00")
		frappe.db.set_value("Subscription", self.subscription, "enabled", 1)
		complete_billing_profile(TEAM)
		set_team_tier(TEAM, max_spend=5000)
		self.addCleanup(clear_team_tier, TEAM)

	def test_india_billed_in_usd_is_found(self):
		frappe.db.set_value("Billing Profile", TEAM, "currency", "USD")
		self.assertEqual(len(_found("B1")), 1)

	def test_spend_over_the_tier_cap_is_found(self):
		set_team_tier(TEAM, max_spend=500)
		[violation] = _found("T1")
		self.assertEqual((violation.expected, violation.actual), (500, 1000))

	def test_internal_team_is_not_held_to_its_tier(self):
		set_team_tier(TEAM, max_spend=500)
		frappe.get_doc(
			{"doctype": "Tax Profile", "team": TEAM, "is_internal": 1, "internal_reason": "Our own team"}
		).insert(ignore_permissions=True)
		self.assertEqual(_found("T1"), [])

	def test_unpriced_subscription_is_found(self):
		add_segment(self.subscription, "Plan Changed", 0, "2026-06-02 00:00:00")
		self.assertEqual(len(_found("S1")), 1)

	def test_team_with_no_way_to_pay_is_found(self):
		[violation] = _found("W1")
		self.assertEqual((violation.expected, violation.actual), (1000, 0))

	def test_team_on_manual_checkout_can_pay(self):
		frappe.db.set_value("Billing Profile", TEAM, "collection_mode", "Manual Checkout")
		self.assertEqual(_found("W1"), [])

	def test_staging_trial_outside_staging_is_found(self):
		frappe.db.set_value("Team", TEAM, "is_staging_trial", 1)
		self.addCleanup(frappe.db.set_value, "Team", TEAM, "is_staging_trial", 0)
		with patch.object(readiness.settings, "provision_teams_as_trial", return_value=False):
			self.assertEqual(len(_found("X1")), 1)

	def test_summary_has_a_row_per_check(self):
		_, rows, _, _ = report.execute({"view": "Summary", "team": TEAM})
		checks = {row["check"]: row for row in rows}
		self.assertEqual(set(checks), set(invariants.CHECKS) | set(readiness.CHECKS))
		self.assertEqual(checks["W1"]["violations"], 1)

	def test_readiness_gaps_reach_the_operator_alerts(self):
		gaps = [a for a in alerts.readiness_gaps() if a["team"] == TEAM]
		self.assertIn("readiness", {a["alert"] for a in gaps})
