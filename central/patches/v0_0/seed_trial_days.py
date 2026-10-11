import frappe


def execute() -> None:
	"""Store the trial days on the existing Central Settings, so none reads as 0."""
	defaults = {"trial_days": 14, "trial_deletion_days": 14, "trial_notice_days": 3}
	for fieldname, days in defaults.items():
		if not frappe.db.get_single_value("Central Settings", fieldname):
			frappe.db.set_single_value("Central Settings", fieldname, days)
