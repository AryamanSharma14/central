import frappe
from frappe import _
from frappe.utils import add_days, date_diff, formatdate, getdate, nowdate

from central.infrastructure.doctype.resource_action.resource_action import ResourceAction
from central.infrastructure.doctype.site.site import Site
from central.notification.engine import queue_event


def start_trial(site: Site) -> None:
	"""Start the trial clock when a trial site is first ready. A team that already pays has no trial."""
	if site.trial_state or not site.is_trial():
		return

	if has_active_payment_method(site.team):
		site.db_set("trial_state", "Converted")
		return

	ends_on = add_days(nowdate(), get_trial_days(site.product, "trial_days"))
	site.db_set({"trial_state": "Active", "trial_ends_on": ends_on})


def has_active_payment_method(team: str) -> bool:
	return bool(frappe.db.exists("Payment Method", {"team": team, "status": "Active"}))


def get_trial_days(product: str | None, fieldname: str) -> int:
	"""The product's `trial_days` or `trial_deletion_days`, or the Central Settings default for 0."""
	days = frappe.db.get_value("Product", product, fieldname) if product else 0
	return days or frappe.get_cached_value("Central Settings", "Central Settings", fieldname)


def run_trials() -> None:
	"""Daily job: warn before a trial ends, stop it on its end date, and terminate it on its deletion date."""
	today = getdate(nowdate())
	for name in frappe.get_all("Site", filters={"trial_state": ["in", ("Active", "Ended")]}, pluck="name"):
		try:
			advance_trial(frappe.get_doc("Site", name, for_update=True), today)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- keep each site's step if a later one fails
		except Exception:
			frappe.db.rollback()
			record_trial_error(name, _("The daily trial job failed. It retries tomorrow."))
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- leave the reason where the operator looks


def advance_trial(site: Site, today) -> None:
	notice_days = frappe.get_cached_value("Central Settings", "Central Settings", "trial_notice_days")
	if site.trial_state == "Active":
		days_left = date_diff(site.trial_ends_on, today)
		if days_left <= 0:
			end_trial(site, today)
		elif days_left <= notice_days:
			# A second warning goes out on the last day.
			send_notice(site, "trial_expiring", "last day" if days_left == 1 else "ending")
		return

	days_left = date_diff(site.trial_deletes_on, today)
	if days_left <= 0:
		delete_trial(site)
	elif frappe.db.get_value("Virtual Machine", site.server, "status") != "Stopped":
		enqueue_stop(site)
	if 0 < days_left <= notice_days:
		send_notice(site, "trial_deletion_soon", "deletion")


def end_trial(site: Site, today) -> None:
	"""Stop the trial's server and set the day it is terminated."""
	deletes_on = add_days(today, get_trial_days(site.product, "trial_deletion_days"))
	site.db_set({"trial_state": "Ended", "trial_deletes_on": deletes_on, "trial_error": None})
	enqueue_stop(site)
	send_notice(site, "trial_ended", "ended")


def enqueue_stop(site: Site) -> None:
	frappe.enqueue(
		stop_trial_server,
		site=site.name,
		queue="long",
		enqueue_after_commit=True,
		job_id=f"trial-stop:{site.name}",
		deduplicate=True,
	)


def stop_trial_server(site: str) -> None:
	"""Background job: stop an ended trial's server, unless the team paid in the meantime."""
	from central.integrations.servers import hold_server_stopped

	document = frappe.get_doc("Site", site)
	if document.trial_state != "Ended":
		return

	try:
		hold_server_stopped(frappe.get_doc("Virtual Machine", document.server))
	# This worker boundary records every failure, and the daily job sends the stop again.
	except Exception:
		frappe.db.rollback()
		record_trial_error(site, _("Central could not stop this trial's server. It retries tomorrow."))
		return

	document.db_set("trial_error", None)


def delete_trial(site: Site) -> None:
	"""Terminate the ended trial's server through the normal terminate action."""
	server = frappe.get_doc("Virtual Machine", site.server)
	if server.status != "Terminated" and not ResourceAction.get_pending(server.name, "terminate"):
		ResourceAction.queue(
			"terminate",
			server.team,
			server.region,
			server.title or server.name,
			server=server.name,
			remote_vm_id=server.atlas_vm_id,
			requested_by="Administrator",
		)

	site.db_set({"trial_state": "Deleted", "trial_error": None})
	send_notice(site, "trial_deleted", "deleted")


def send_notice(site: Site, event_type: str, notice: str) -> None:
	if site.trial_last_notice == notice:
		return

	queue_event(
		site.team,
		event_type,
		context=get_notice_context(site),
		reference_doctype="Site",
		reference_name=site.name,
	)
	site.db_set("trial_last_notice", notice)


def get_notice_context(site: Site) -> dict:
	product = frappe.db.get_value("Product", site.product, "title") if site.product else None
	return {
		"address": site.rename_target if site.subdomain else site.name,
		"product": product or "Frappe Cloud",
		"ends_on": formatdate(site.trial_ends_on),
		"deletes_on": formatdate(site.trial_deletes_on) if site.trial_deletes_on else "",
		"days_left": date_diff(site.trial_ends_on, nowdate()),
	}


def record_trial_error(site: str, reason: str) -> None:
	frappe.log_error(title="Trial step failed", reference_doctype="Site", reference_name=site)
	frappe.db.set_value("Site", site, "trial_error", reason)
