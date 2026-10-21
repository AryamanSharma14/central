# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""The audit repair patch leaves each finding in a state the guards accept."""

from unittest.mock import patch

import frappe

from central.billing.revenue import credits
from central.billing.tests.utils import BillingTestCase as IntegrationTestCase
from central.billing.tests.utils import complete_billing_profile, ensure_team, ensure_trust_tier_level
from central.patches.v0_0 import repair_billing_audit_findings as repair

TEAM = "team-audit-repair"


class TestRepairBillingAuditFindings(IntegrationTestCase):
	def setUp(self):
		ensure_team(TEAM)
		complete_billing_profile(TEAM)
		frappe.db.delete("Tax Profile", {"team": TEAM})

	def test_staging_team_becomes_internal(self):
		frappe.db.set_value("Team", TEAM, "is_staging_trial", 1)
		with patch("central.billing.settings.provision_teams_as_trial", return_value=False):
			repair.mark_staging_teams_internal()
		self.assertTrue(frappe.db.get_value("Tax Profile", TEAM, "is_internal"))
		self.assertFalse(frappe.db.get_value("Team", TEAM, "is_staging_trial"))

	def test_staging_team_is_kept_on_a_staging_site(self):
		frappe.db.set_value("Team", TEAM, "is_staging_trial", 1)
		self.addCleanup(frappe.db.set_value, "Team", TEAM, "is_staging_trial", 0)
		with patch("central.billing.settings.provision_teams_as_trial", return_value=True):
			repair.mark_staging_teams_internal()
		self.assertTrue(frappe.db.get_value("Team", TEAM, "is_staging_trial"))

	def test_india_team_never_invoiced_goes_back_to_inr(self):
		frappe.db.set_value("Billing Profile", TEAM, "currency", "USD")
		repair.match_currency_to_country()
		self.assertEqual(frappe.db.get_value("Billing Profile", TEAM, "currency"), "INR")

	def test_tier_set_by_hand_is_pinned_without_its_dead_cap(self):
		ensure_trust_tier_level("t-entry")
		frappe.db.set_value("Trust Tier Level", "t-entry", "is_default", 1)
		self.addCleanup(frappe.db.set_value, "Trust Tier Level", "t-entry", "is_default", 0)
		level = ensure_trust_tier_level("t-elite")
		frappe.db.set_value(
			"Billing Profile",
			TEAM,
			{"trust_tier_level": level, "manual_override": 0, "override_max_spend": 1000000},
		)
		repair.pin_tiers_set_by_hand()
		profile = frappe.db.get_value(
			"Billing Profile",
			TEAM,
			["manual_override", "override_max_spend", "promotion_basis"],
			as_dict=True,
		)
		self.assertEqual((profile.manual_override, profile.override_max_spend), (1, 0))
		self.assertTrue(profile.promotion_basis)

	def test_unexplained_wallet_balance_is_booked_and_moves_again(self):
		credits.grant_promotional_credits(TEAM, 100, "INR")
		frappe.db.set_value("Credit Wallet", credits.wallet_name(TEAM, "INR"), "balance", 2600)

		repair.book_wallet_balances_missing_from_the_ledger()

		credits.apply_credit(TEAM, 50, "INR", reference_type="Invoice", reference_name="INV-1")
		self.assertEqual(credits.get_balance(TEAM, "INR")["balance"], 2550)
