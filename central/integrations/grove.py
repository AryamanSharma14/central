from __future__ import annotations

import frappe
import requests
from frappe import _

# Connect, read: a dashboard call must not hang on a Grove that is down.
TIMEOUT = (30, 90)
# What a Grove that is down or in maintenance answers; Frappe's maintenance mode is a 503.
UNAVAILABLE = (502, 503, 504)


class GroveUnavailable(frappe.ValidationError):
	"""Grove cannot be reached or is in maintenance. Its gateways keep serving keys meanwhile."""

	http_status_code = 503


class GroveClient:
	"""Calls Grove's control API (`grove.api`) as Central. A team is one Central Team at Grove,
	named by the team id, under the key count, monthly spend limit and rate limits of its tier,
	which Grove holds; each of its keys carries its own geography, models, rate limits and monthly cap. Grove owns the keys;
	Central never proxies inference."""

	def __init__(self, base_url: str, api_key: str, api_secret: str):
		self.base_url = base_url
		self.headers = {"Authorization": f"token {api_key}:{api_secret}"}

	@classmethod
	def from_settings(cls) -> GroveClient:
		settings = frappe.get_cached_doc("AI Settings")
		if not settings.base_url or not settings.control_api_key:
			frappe.throw(_("AI is not set up: enroll Central at Grove in AI Settings."))
		return cls(settings.base_url, settings.control_api_key, settings.get_password("control_api_secret"))

	@staticmethod
	def enroll(base_url: str, bootstrap_secret: str) -> dict:
		"""Mint Central's own control user and key at Grove. The shared secret is the only auth."""
		body = {"email": f"central@{frappe.local.site}", "token": bootstrap_secret}
		response = requests.post(
			f"{base_url}/api/method/grove.api.control.create_control_client", json=body, timeout=TIMEOUT
		)
		return read(response)

	def rotate_control_key(self) -> dict:
		"""A new secret for Central's own control user; the old one stops at once."""
		return self.call("grove.api.control.create_control_client_key")

	def provision_team(self, team: str) -> dict:
		"""Register `team` by its id; Grove keeps nothing else about who it is. Grove upserts
		by `team`; `update_team` sets everything else. → `team` and `max_keys`."""
		return self.call("grove.api.teams.provision_team", team=team)

	def update_team(self, team: str, suspended: bool | None = None, tier: str | None = None) -> dict:
		"""The name of the team's `tier` at Grove ("" for none: Grove's default tier), whose key
		count, monthly spend limit and rate limits Grove holds, and whether it is `suspended`,
		each kept at Grove when None. → the team and the limits in force for it."""
		return self.call("grove.api.teams.update_team", team=team, suspended=suspended, tier=tier)

	def provision_key(
		self, team: str, title: str, geography: str | None = None, cap: float | None = None
	) -> dict:
		"""Mint a key in `geography` (Grove's default when None) with `cap` USD to spend a month
		(0 when None: refused until it gets one): its `name`, `geography`, `gateway_url` and
		`api_key`. The secret is never sent again."""
		return self.call("grove.api.keys.provision_key", team=team, title=title, geography=geography, cap=cap)

	def update_caps(self, team: str, caps: dict[str, float]) -> list[dict]:
		"""Set several keys' monthly caps at once, {key: USD}; Grove saves all or none. → the keys
		as `list_keys` lists them."""
		return self.call("grove.api.keys.update_caps", team=team, caps=caps) or []

	def list_keys(self, team: str) -> list[dict]:
		return self.call("grove.api.keys.keys", team=team) or []

	def revoke_key(self, team: str, key: str) -> None:
		self.call("grove.api.keys.revoke_key", team=team, key=key)

	def list_models(
		self, team: str | None = None, key: str | None = None, geography: str | None = None
	) -> list[dict]:
		"""What a new key in `geography` (Grove's default when None) starts with: the published
		models of its default group. With `team` and `key`, what that one key may call."""
		return self.call("grove.api.catalog.available_models", team=team, key=key, geography=geography) or []

	def list_geographies(self) -> list[dict]:
		"""Where a key may be minted: `name`, `label`, `endpoint`, `is_default`."""
		return self.call("grove.api.catalog.geographies") or []

	def get_spend(self, team: str) -> dict:
		"""As of Grove's last pull, in USD: `spent`, `month_spent`, `capped` (Σ live caps)
		against `spend_limit`; and `max_keys`, `suspended`."""
		return self.call("grove.api.usage.spend", team=team)

	def get_usage(
		self,
		teams: list[str],
		month: str | None = None,
		period: str | None = None,
		key_hash: str | None = None,
		pulled_after: str | None = None,
		pulled_until: str | None = None,
	) -> dict:
		"""Requests and cost per team and model over a UTC `month` or `period`, or, for an invoice,
		over a landing window: what Grove pulled between `pulled_after` and `pulled_until` (RFC 3339
		UTC, until exclusive) whatever day it was served on. Central converts its own invoice period
		to UTC before asking."""
		return self.call(
			"grove.api.usage.usage",
			teams=teams,
			month=month,
			period=period,
			key_hash=key_hash,
			pulled_after=pulled_after,
			pulled_until=pulled_until,
		)

	def call(self, method: str, **body) -> dict | list:
		try:
			response = requests.post(
				f"{self.base_url}/api/method/{method}", json=body, headers=self.headers, timeout=TIMEOUT
			)
		except (requests.ConnectionError, requests.Timeout) as e:
			raise GroveUnavailable(_("Grove can't be reached right now.")) from e
		return read(response)


def read(response: requests.Response) -> dict | list:
	if response.status_code in UNAVAILABLE:
		raise GroveUnavailable(_("Grove is unavailable ({0}).").format(response.status_code))
	if response.status_code >= 400:
		frappe.throw(_("Grove request failed ({0}): {1}").format(response.status_code, response.text[:200]))
	return response.json().get("message", {})
