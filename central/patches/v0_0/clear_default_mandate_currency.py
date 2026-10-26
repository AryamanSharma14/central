import frappe


def execute():
	"""Clear the mandate currency a card without a mandate got from the old INR default."""
	method = frappe.qb.DocType("Payment Method")
	(
		frappe.qb.update(method)
		.set(method.mandate_currency, None)
		.where(method.mandate_currency.isnotnull())
		.where(frappe.query_builder.functions.IfNull(method.mandate_max_amount, 0) == 0)
	).run()
