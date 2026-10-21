# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""An internal team's invoices are rated for the record and waived, never collected."""

import frappe

from central.billing.ingester import customer
from central.billing.report.internal_usage_and_waivers import internal_usage_and_waivers as report
from central.billing.revenue import credits, invoicing
from central.billing.tests.utils import BillingTestCase as IntegrationTestCase
from central.billing.tests.utils import add_segment, make_billing_subscription, make_plan

TEAM = "team-internal-waiver"
CLUSTER = "ap-south-1"
PLAN = "bundle-internal-waiver"


def _mark_internal(reason="Platform team's own servers"):
	values = {"doctype": "Tax Profile", "team": TEAM, "output_tax_type": "GST", "output_tax_rate": 18}
	doc = (
		frappe.get_doc("Tax Profile", TEAM)
		if frappe.db.exists("Tax Profile", TEAM)
		else frappe.get_doc(values)
	)
	doc.is_internal = 1
	doc.internal_reason = reason
	doc.save(ignore_permissions=True)
	return doc


class TestInternalTeams(IntegrationTestCase):
	def setUp(self):
		make_plan(PLAN)
		sub = make_billing_subscription(TEAM, CLUSTER, PLAN, billing_cycle="Monthly")
		add_segment(sub, "Created", 1000, "2026-06-01 00:00:00")
		frappe.db.delete("Tax Profile", {"team": TEAM})
		frappe.db.delete("Billing Event", {"team": TEAM})
		self.invoice = invoicing.generate_draft_invoice(sub, "2026-06-01", "2026-06-30")

	def test_marking_internal_needs_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			_mark_internal(reason="")

	def test_marking_internal_is_logged(self):
		_mark_internal()
		events = frappe.get_all("Billing Event", filters={"team": TEAM}, pluck="event_type")
		self.assertEqual(events, ["Internal Team Marked"])

	def test_invoice_is_waived_untaxed_without_drawing_credits(self):
		_mark_internal()
		credits.grant_promotional_credits(TEAM, 500, "INR", note="Welcome credits")

		result = invoicing.open_and_collect(self.invoice)

		invoice = frappe.get_doc("Invoice", self.invoice)
		self.assertEqual(result["status"], "Waived")
		self.assertEqual(
			(invoice.status, invoice.output_tax_amount, invoice.credit_applied), ("Waived", 0, 0)
		)
		self.assertEqual(credits.get_balance(TEAM, "INR")["balance"], 500)

	def test_internal_team_is_not_sent_to_accounting(self):
		_mark_internal()
		profile = frappe._dict(
			team=TEAM, currency="INR", legal_name="Us", address_line1="1", city="Pune", country="India"
		)
		self.assertFalse(customer._should_sync(profile))

	def test_report_shows_usage_and_waived_amount(self):
		_mark_internal()
		invoicing.open_and_collect(self.invoice)

		_, rows, _ = report.execute({"team": TEAM})

		self.assertEqual([(r["invoice"], r["waived"]) for r in rows], [(self.invoice, 1000)])
