import frappe
from frappe.utils.translations import _lt

from central.signups.trial import OPEN_STATES, get_server_trial_state

SERVER_ACCESS_LOCKED = _lt(
	"Server access is not part of the free trial. Upgrade to use SSH, the console and Pilot."
)


def is_server_locked(server: str) -> bool:
	"""Whether the server runs an open trial, also one whose site Central has not recorded yet.
	Its owner then gets the site, but no server access."""
	return get_server_trial_state(server) in (*OPEN_STATES, "Pending")


def get_locked_servers(team: str) -> set[str]:
	"""The team's servers that run an open trial, also those whose site Central has not recorded yet."""
	sites = frappe.get_list("Site", filters={"team": team}, fields=["server", "trial_state"])
	recorded = {site.server for site in sites}
	open_trials = {site.server for site in sites if site.trial_state in OPEN_STATES}
	free_trial_creations = frappe.get_list(
		"Resource Action",
		filters={"team": team, "action": "create", "is_free_trial": 1, "server": ["is", "set"]},
		pluck="server",
	)

	return open_trials | (set(free_trial_creations) - recorded)
