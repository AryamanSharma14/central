from collections.abc import Callable

import frappe
from frappe.utils.translations import _lt

from central.iam import user_has_operator_bypass
from central.signups.trial import OPEN_STATES, get_server_trial_state

SERVER_ACCESS_LOCKED = _lt(
	"Server access is not part of the free trial. Upgrade to use SSH, the console and Pilot."
)
SERVICE_ACCESS_LOCKED = _lt(
	"LLM and object storage are not part of the free trial. Upgrade to create keys and buckets."
)


def is_server_locked(server: str) -> bool:
	"""Whether the server runs an open trial, also one whose site Central has not recorded yet.
	Its owner then gets the site, but no server access."""
	return get_server_trial_state(server) in (*OPEN_STATES, "Pending")


def get_locked_servers(team: str) -> set[str]:
	"""The team's servers that run an open trial, also those whose site Central has not recorded yet."""
	return find_locked_servers(frappe.get_list, {"team": team})


def is_team_locked(team: str) -> bool:
	"""Whether the team runs an open trial. It then gets no LLM keys and no buckets, because they cost money."""
	return bool(find_locked_servers(frappe.get_all, {"team": team}))


def require_service_access(team: str) -> None:
	"""Refuse an LLM key or a bucket to a team on an open trial. Operators keep access."""
	if is_team_locked(team) and not user_has_operator_bypass():
		frappe.throw(str(SERVICE_ACCESS_LOCKED), frappe.PermissionError)


def get_locked_servers_among(servers: list[str]) -> set[str]:
	"""Which of `servers`, across teams, are locked. For a scheduled job, which reads as the system."""
	return find_locked_servers(frappe.get_all, {"server": ["in", servers]}) if servers else set()


def find_locked_servers(get: Callable, filters: dict) -> set[str]:
	sites = get("Site", filters=filters, fields=["server", "trial_state"])
	recorded = {site.server for site in sites}
	open_trials = {site.server for site in sites if site.trial_state in OPEN_STATES}
	free_trial_creations = get(
		"Resource Action",
		filters={"server": ["is", "set"], **filters, "action": "create", "is_free_trial": 1},
		pluck="server",
	)

	return open_trials | (set(free_trial_creations) - recorded)
