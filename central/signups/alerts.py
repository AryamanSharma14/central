import frappe

from central.billing.platform.alerts import notify_operators


def alert_operators(alert: str, doctype: str, name: str, team: str | None, detail: str) -> None:
	"""Tell the operators that a signup failed. It goes after commit, so a rolled-back failure sends
	nothing, and in a job, so a slow Raven post never holds the signup."""
	frappe.enqueue(
		notify_operators,
		queue="short",
		enqueue_after_commit=True,
		title=f"Signup failed: {alert}",
		alerts=[{"alert": alert, "doctype": doctype, "subject": name, "team": team, "detail": detail}],
	)
