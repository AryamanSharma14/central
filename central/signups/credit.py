import frappe
from frappe import _

from central.billing.payments.provisioning import grant_welcome_credits
from central.billing.revenue.credits import grant_promotional_credits
from central.signups.trial import convert_team


def on_payment_method_update(doc, method: str | None = None) -> None:
	"""Grant the welcome credit and convert the team's trials when its payment method becomes active. A gateway
	creates every method as Pending Validation, so activation is always a status change."""
	before = doc.get_doc_before_save()
	if doc.status != "Active" or not before or before.status == "Active":
		return

	grant_welcome_credits(doc.team)
	convert_team(doc.team)


@frappe.whitelist(methods=["POST"])
def grant_credit(team: str, amount: float, validity_days: int, note: str) -> dict:
	"""Operator action: grant promotional credit, such as a beta credit, to `team` now.

	It counts as the owner's welcome credit, so the team gets no welcome credit later."""
	frappe.only_for("System Manager")
	if amount <= 0 or validity_days <= 0:
		frappe.throw(_("Enter a positive amount and a positive validity."))

	currency = frappe.db.get_value("Billing Profile", team, "currency")
	if not currency:
		frappe.throw(_("Team {0} has no billing currency yet.").format(team))

	expires_on = frappe.utils.add_days(frappe.utils.nowdate(), validity_days)
	return grant_promotional_credits(team, amount, currency, note=note, expires_on=expires_on)
