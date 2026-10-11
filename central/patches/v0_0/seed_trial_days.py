import frappe


def execute() -> None:
	"""Store the trial length on the existing Central Settings, so no trial reads as 0 days."""
	for fieldname in ("trial_days", "trial_deletion_days"):
		if not frappe.db.get_single_value("Central Settings", fieldname):
			frappe.db.set_single_value("Central Settings", fieldname, 14)
