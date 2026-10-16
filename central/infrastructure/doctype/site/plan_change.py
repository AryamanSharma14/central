import hmac
from typing import Self
from urllib.parse import urlencode, urlsplit

import frappe
from frappe import _
from frappe.utils import get_datetime, get_url, now_datetime
from frappe.utils.verified_command import get_signed_params

from central.infrastructure.doctype.resource_action.resource_action import ResourceAction
from central.infrastructure.doctype.site.site import Site
from central.integrations.pilot import is_site_reachable

# Resource Action status -> the step the waiting page shows.
STEPS = {
	"Queued": "saving",
	"Dispatching": "saving",
	"Sent": "moving",
	"In Progress": "moving",
	"Uncertain": "moving",
	"Succeeded": "starting",
	"Failed": "failed",
	"Timed Out": "failed",
}


class PlanChange:
	"""A site's plan change, followed on a public page. The site's own users have no Central
	account, so a signed link is the only access to it."""

	def __init__(self, site: Site, action: ResourceAction):
		self.site = site
		self.action = action

	@classmethod
	def from_signed_link(cls, action: str, site: str, signature: str) -> Self:
		"""Open a plan change from its link. A wrong signature, or an action that does not
		resize the site's server, reads as an invalid link."""
		params = urlencode({"action": action, "site": site})
		expected = get_signed_params(params).removeprefix(f"{params}&_signature=")
		if not hmac.compare_digest(expected, signature):
			frappe.throw(_("This link is not valid."), frappe.PermissionError)

		action_doc = frappe.get_doc("Resource Action", action)
		site_doc = frappe.get_doc("Site", site)
		if action_doc.action != "resize" or action_doc.resource_id != site_doc.server:
			frappe.throw(_("This link is not valid."), frappe.PermissionError)

		return cls(site_doc, action_doc)

	@property
	def url(self) -> str:
		params = get_signed_params({"action": self.action.name, "site": self.site.name})
		return get_url(f"/upgrading?{params}")

	def get_progress(self) -> dict:
		"""What the waiting page shows. The site is ready only once it answers again."""
		step = STEPS.get(self.action.status, "saving")
		if step == "starting" and is_site_reachable(self.site.primary_url):
			step = "ready"

		configuration = self.action.get_resize_configuration()
		# The server keeps its old plan and size until the resize lands, so the page can show both.
		server = frappe.db.get_value(
			"Virtual Machine",
			self.site.server,
			["plan", "vcpus", "memory_megabytes", "disk_gigabytes"],
			as_dict=True,
		)
		return {
			"step": step,
			"site": urlsplit(self.site.primary_url).hostname,
			"site_url": self.site.primary_url,
			"plan": frappe.db.get_value("Plan", configuration.plan, "title") if configuration.plan else None,
			"current_plan": frappe.db.get_value("Plan", server.plan, "title") if server.plan else None,
			"shape": configuration.shape.model_dump(),
			"current_shape": {key: server[key] for key in ("vcpus", "memory_megabytes", "disk_gigabytes")},
			"region": frappe.db.get_value(
				"Region", self.action.region, ["display_name", "latitude", "longitude"], as_dict=True
			),
			"elapsed_seconds": int((now_datetime() - get_datetime(self.action.creation)).total_seconds()),
			"error": self.action.error_message if step == "failed" else None,
		}
