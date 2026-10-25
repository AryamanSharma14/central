import frappe

from central.billing.platform.alerts import notify_operators


def alert_operators(alert: str, doctype: str, name: str, team: str | None, detail: str) -> None:
	"""Tell the operators that a signup failed. It goes after commit, so a rolled-back failure sends
	nothing, and in a job, so a slow Raven post never holds the signup."""
	frappe.enqueue(
		send_alert,
		queue="short",
		enqueue_after_commit=True,
		alert=alert,
		doctype=doctype,
		name=name,
		team=team,
		detail=detail,
	)


def send_alert(alert: str, doctype: str, name: str, team: str | None, detail: str) -> None:
	"""Background job: post one signup alert to the operator alert channel in Billing Settings."""
	notify_operators(
		f"Signup failed: {alert}",
		[{"alert": alert, "doctype": doctype, "subject": name, "team": team, "detail": detail}],
	)
