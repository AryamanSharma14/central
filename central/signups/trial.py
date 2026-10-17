import frappe
from frappe import _
from frappe.utils import (
	add_days,
	date_diff,
	flt,
	fmt_money,
	formatdate,
	get_datetime,
	getdate,
	now_datetime,
	nowdate,
)

from central.infrastructure.doctype.resource_action.resource_action import PENDING_STATES, ResourceAction
from central.infrastructure.doctype.site.site import Site
from central.notification.engine import queue_event
from central.signups.funnel import capture_trial_event


def start_trial(site: Site) -> None:
	"""Start the trial clock on a new trial site, before it is saved. It does not wait for the
	customer to open the site, so an abandoned trial still ends. A team that already pays has no trial."""
	if site.trial_state or not site.is_trial():
		return

	if not site.get_creation_request().is_free_trial:
		site.trial_state = "Converted"
		return

	site.trial_state = "Active"
	site.trial_ends_on = add_days(nowdate(), get_trial_days(site.product, "trial_days"))


def convert_if_paid(site: Site) -> None:
	"""Convert a new trial site whose team added a payment method before Central recorded it."""
	if site.trial_state == "Active" and has_active_payment_method(site.team):
		convert_site(site)


def is_billing_deferred(server: str) -> bool:
	"""Whether the server runs a free trial site, so it has no subscription yet. Before Central
	records the site, the creation request says whether it is a free trial."""
	state = frappe.db.get_value("Site", {"server": server}, "trial_state")
	if state:
		return state in ("Active", "Ended", "Deleted")

	return bool(
		frappe.db.get_value("Resource Action", {"server": server, "action": "create"}, "is_free_trial")
	)


def is_free_trial_creation(team: str, resource_type: str) -> bool:
	"""Whether a creation request opens a free trial: a site, for a team that has never paid."""
	return resource_type == "Site" and not has_active_payment_method(team) and not has_paid_before(team)


def has_paid_before(team: str) -> bool:
	"""Whether the team ever had a subscription or a bill. Such a team buys its sites, even after
	its payment method lapses."""
	return bool(
		frappe.db.exists("Subscription", {"team": team})
		or frappe.db.exists("Invoice", {"team": team, "status": ["not in", ("Draft", "Cancelled")]})
	)


def convert_team(team: str) -> None:
	"""Turn the team's running trials into paid sites once it has an active payment method. An
	ended trial stays stopped until the customer keeps it, so a card never revives a site they left."""
	for name in frappe.get_all("Site", filters={"team": team, "trial_state": "Active"}, pluck="name"):
		convert_site(frappe.get_doc("Site", name, for_update=True))


def keep_site(site: Site) -> None:
	"""Convert an ended trial that the customer chose to keep, and start its server."""
	if site.trial_state != "Ended":
		frappe.throw(_("Only an ended trial can be kept."))
	if not has_active_payment_method(site.team):
		frappe.throw(_("Add a payment method to keep this site."))

	convert_site(site)


def convert_site(site: Site) -> None:
	"""Start billing the site's server, keep it awake, and start it again if the trial stopped it."""
	site.db_set({"trial_state": "Converted", "trial_error": None, **get_trial_cost(site)})
	capture_trial_event(
		"trial_converted", site.team, site.product, days_in_trial=date_diff(nowdate(), site.creation)
	)
	send_notice(site, "trial_converted", "converted")

	# A sleeping server is paid for like a running one. A stopped server gets its subscription
	# when the conversion job starts it.
	server = frappe.get_doc("Virtual Machine", site.server)
	if server.status in ("Running", "Paused"):
		server.ensure_subscription_enabled()

	enqueue_conversion(site)


def enqueue_conversion(site: Site) -> None:
	frappe.enqueue(
		finish_conversion,
		site=site.name,
		queue="long",
		enqueue_after_commit=True,
		job_id=f"trial-convert:{site.name}",
		deduplicate=True,
	)


def finish_conversion(site: str) -> None:
	"""Background job: turn idle sleep off on a converted trial's server, and start it when it is
	stopped. Safe to repeat, so the daily job sends it again after a failure."""
	from central.integrations.servers import convert_trial_server

	document = frappe.get_doc("Site", site)
	if document.trial_state != "Converted":
		return

	# A resize or a power action also changes the server's power; two jobs must not race on it.
	# The daily job sends the conversion again once that action is done.
	if frappe.db.exists(
		"Resource Action", {"resource_id": document.server, "status": ["in", PENDING_STATES]}
	):
		record_trial_error(
			site, _("Another action is running on this server. The conversion retries tomorrow.")
		)
		return

	is_stopped = frappe.db.get_value("Virtual Machine", document.server, "status") == "Stopped"
	try:
		convert_trial_server(document.server, start=is_stopped)
	# This worker boundary records every failure, and the daily job sends the conversion again.
	except Exception:
		frappe.db.rollback()
		record_trial_error(site, _("Central could not start this paid site's server. It retries tomorrow."))
		return

	document.db_set("trial_error", None)


def get_trial_cost(site: Site, until=None) -> dict:
	"""The plan's monthly rate for the days the trial ran, from its creation request. The trial
	starts when Central records the site."""
	request = site.get_creation_request()
	if not request:
		return {}

	days = (get_datetime(until or now_datetime()) - get_datetime(site.creation)).total_seconds() / 86400
	cost = flt(request.reserved_monthly_rate) * max(days, 0) / 30
	currency = frappe.parse_json(request.request_payload or "{}").get("currency")
	return {"trial_cost": cost, "trial_currency": currency}


def has_active_payment_method(team: str) -> bool:
	return bool(frappe.db.exists("Payment Method", {"team": team, "status": "Active"}))


def get_trial_days(product: str | None, fieldname: str) -> int:
	"""The product's `trial_days` or `trial_deletion_days`, or the Central Settings default for 0."""
	days = frappe.db.get_value("Product", product, fieldname) if product else 0
	return days or frappe.get_cached_value("Central Settings", "Central Settings", fieldname)


def get_status(server: str, site: str | None = None) -> dict | None:
	"""The open trial of the site on `server`, for the in-app billing panel, or None.
	A server with several sites must name one."""
	from central.signups.credit import get_welcome_credit_offer

	filters = {"server": server, "name": site} if site else {"server": server}
	sites = frappe.get_all(
		"Site", filters=filters, fields=["team", "trial_state", "trial_ends_on", "trial_deletes_on"]
	)
	if len(sites) > 1:
		frappe.throw(_("This server has several sites. Name the site whose trial to show."))
	if not sites or sites[0].trial_state not in ("Active", "Ended"):
		return None

	trial = sites[0]
	return {
		"state": trial.trial_state,
		"can_keep": trial.trial_state == "Ended" and has_active_payment_method(trial.team),
		"ends_on": trial.trial_ends_on,
		"days_left": max(date_diff(trial.trial_ends_on, nowdate()), 0),
		"deletes_on": trial.trial_deletes_on,
		"credit": get_welcome_credit_offer(trial.team),
		"sleeps_after_minutes": get_sleep_minutes(),
	}


def is_conversion_starting(server: str) -> bool:
	"""Whether the server's trial converted but its server has no subscription yet, because the
	conversion job is still starting it."""
	site = frappe.db.get_value("Site", {"server": server, "trial_state": "Converted"}, "team")
	return bool(site) and not frappe.db.exists("Subscription", {"server_id": server, "team": site})


def get_sleep_minutes() -> int:
	"""Idle minutes before a trial server sleeps, so the customer is told the real number."""
	return frappe.get_cached_value("Central Settings", "Central Settings", "trial_idle_shutdown_minutes")


def run_trials() -> None:
	"""Daily job: warn before a trial ends, stop it on its end date, terminate it on its deletion
	date, and finish a conversion that failed."""
	today = getdate(nowdate())
	open_trials = frappe.get_all("Site", filters={"trial_state": ["in", ("Active", "Ended")]}, pluck="name")
	failed_conversions = frappe.get_all(
		"Site", filters={"trial_state": "Converted", "trial_error": ["is", "set"]}, pluck="name"
	)
	for name in open_trials + failed_conversions:
		try:
			advance_trial(frappe.get_doc("Site", name, for_update=True), today)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- keep each site's step if a later one fails
		except Exception:
			frappe.db.rollback()
			record_trial_error(name, _("The daily trial job failed. It retries tomorrow."))
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- leave the reason where the operator looks


def advance_trial(site: Site, today) -> None:
	notice_days = frappe.get_cached_value("Central Settings", "Central Settings", "trial_notice_days")
	if site.trial_state == "Converted":
		enqueue_conversion(site)
	elif site.trial_state == "Active":
		advance_active_trial(site, today, notice_days)
	else:
		advance_ended_trial(site, today, notice_days)


def advance_active_trial(site: Site, today, notice_days: int) -> None:
	days_left = date_diff(site.trial_ends_on, today)
	if days_left <= 0:
		end_trial(site, today)
	elif days_left <= notice_days:
		# A second warning goes out on the last day.
		send_notice(site, "trial_expiring", "last day" if days_left == 1 else "ending")
	elif site.ready_at and not site.claimed_at and getdate(site.ready_at) < today:
		# One reminder, from the day after the site is ready, to a team that has not opened it.
		send_notice(site, "trial_unopened", "unopened")


def advance_ended_trial(site: Site, today, notice_days: int) -> None:
	days_left = date_diff(site.trial_deletes_on, today)
	if days_left <= 0:
		delete_trial(site)
	elif frappe.db.get_value("Virtual Machine", site.server, "status") != "Stopped":
		enqueue_stop(site)
	if 0 < days_left <= notice_days:
		send_notice(site, "trial_deletion_soon", "deletion")


def extend_trial(site: Site, days: int) -> None:
	"""Give a trial `days` more from today, or from its end date when that is later. An ended
	trial runs again and its server starts."""
	if site.trial_state not in ("Active", "Ended"):
		frappe.throw(_("Only an active or ended trial can be extended."))
	if days <= 0:
		frappe.throw(_("Enter a positive number of days."))

	ends_on = add_days(max(getdate(site.trial_ends_on), getdate(nowdate())), days)
	was_ended = site.trial_state == "Ended"
	site.db_set(
		{
			"trial_state": "Active",
			"trial_ends_on": ends_on,
			"trial_deletes_on": None,
			"trial_last_notice": None,
			"trial_error": None,
		}
	)
	if was_ended:
		queue_server_action(site, "start")


def end_trial(site: Site, today) -> None:
	"""Stop the trial's server and set the day it is terminated. The stop job tells the team."""
	deletes_on = add_days(today, get_trial_days(site.product, "trial_deletion_days"))
	site.db_set({"trial_state": "Ended", "trial_deletes_on": deletes_on, "trial_error": None})
	capture_trial_event("trial_ended", site.team, site.product)
	enqueue_stop(site)


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
	"""Background job: stop an ended trial's server, unless the team paid in the meantime. The
	team hears that the trial ended only once the server is stopped."""
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

	# The team can pay while the stop runs. Its server must then run again.
	if document.reload().trial_state == "Converted":
		enqueue_conversion(document)
		return

	document.db_set("trial_error", None)
	send_notice(document, "trial_ended", "ended")


def delete_trial(site: Site) -> None:
	"""Terminate the ended trial's server. The site is Deleted once the server is Terminated.
	Until then the daily job asks again, so a refused terminate is not lost."""
	if frappe.db.get_value("Virtual Machine", site.server, "status") != "Terminated":
		if frappe.db.exists(
			"Resource Action",
			{"resource_id": site.server, "action": "terminate", "status": ["in", ("Failed", "Timed Out")]},
		):
			site.db_set(
				"trial_error", _("Atlas did not terminate this trial's server. Central asks again tomorrow.")
			)
		queue_server_action(site, "terminate")
		return

	site.db_set({"trial_state": "Deleted", "trial_error": None, **get_trial_cost(site, site.trial_ends_on)})
	capture_trial_event("trial_deleted", site.team, site.product)
	send_notice(site, "trial_deleted", "deleted")


def queue_server_action(site: Site, action: str) -> None:
	"""Run a start or terminate on the trial's server through the normal action, as the system."""
	server = frappe.get_doc("Virtual Machine", site.server)
	if ResourceAction.get_pending(server.name, action):
		return

	ResourceAction.queue(
		action,
		server.team,
		server.region,
		server.title or server.name,
		server=server.name,
		remote_vm_id=server.atlas_vm_id,
		requested_by="Administrator",
	)


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
	from central.signups.credit import get_welcome_credit_offer

	product = frappe.db.get_value("Product", site.product, "title") if site.product else None
	credit = get_welcome_credit_offer(site.team)
	return {
		"address": site.rename_target if site.subdomain else site.name,
		"product": product or "Frappe Cloud",
		"ends_on": formatdate(site.trial_ends_on),
		"deletes_on": formatdate(site.trial_deletes_on) if site.trial_deletes_on else "",
		"days_left": date_diff(site.trial_ends_on, nowdate()),
		"credit": fmt_money(credit["amount"], currency=credit["currency"]) if credit else "",
		"sleeps_after_minutes": get_sleep_minutes(),
	}


def record_trial_error(site: str, reason: str) -> None:
	frappe.log_error(title="Trial step failed", reference_doctype="Site", reference_name=site)
	frappe.db.set_value("Site", site, "trial_error", reason)
