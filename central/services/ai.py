from __future__ import annotations

import frappe

from central.integrations.grove import GroveClient
from central.services.doctype.team_service.team_service import AI_SERVICE


def get_ai_service(team: str) -> str | None:
	"""The team's AI Team Service, None while AI is off for it."""
	return frappe.db.get_value("Team Service", {"team": team, "add_on_service": AI_SERVICE})


def enable(team: str) -> str:
	"""Turn AI on for a team. Safe to repeat. The record registers the team at Grove before it
	saves, so a refusal there leaves no row here."""
	# Two enables at once would both pass the check below; the team row serialises them.
	frappe.db.get_value("Team", team, "name", for_update=True)
	if name := get_ai_service(team):
		return name

	service = frappe.get_doc(
		{"doctype": "Team Service", "team": team, "add_on_service": AI_SERVICE, "status": "Active"}
	)
	# The route checked service:manage; Team Service is operator-only because it holds secrets.
	service.insert(ignore_permissions=True)
	return service.name


def register_team(team: str) -> dict:
	"""Register the team at Grove under the team id, then send the name of its tier and its
	standing. Grove keeps nothing else about the team."""
	client = GroveClient.from_settings()
	registered = client.provision_team(team) or {}
	client.update_team(team, **get_team_limits(team))
	return registered


def get_team_limits(team: str) -> dict:
	"""What Central tells Grove about the team: the name of its tier, whose key count, monthly
	spend limit and rate limits Grove holds (untiered: "", Grove's default tier), and whether its
	account is suspended. Every team is paid and gated at Grove."""
	from central.billing.catalog.entitlements import get_team_caps
	from central.billing.catalog.subscriptions import anchor_subscription

	anchor = anchor_subscription(team)
	return {
		"tier": get_team_caps(team).tier or "",
		"suspended": bool(anchor)
		and frappe.db.get_value("Subscription", anchor, "account_standing") == "Suspended",
	}


def sync_team(team: str) -> None:
	"""Send the team's limits and standing to Grove. A no-op while AI is off."""
	if get_ai_service(team):
		GroveClient.from_settings().update_team(team, **get_team_limits(team))


def on_tier_update(doc, method: str | None = None) -> None:
	"""Billing Profile and Subscription hook: a team's tier or standing moved, so Grove follows.
	A Billing Profile is named by its team."""
	fields = ("account_standing",) if doc.doctype == "Subscription" else ("trust_tier_level",)
	team = doc.team if doc.doctype == "Subscription" else doc.name
	if any(doc.has_value_changed(field) for field in fields) and get_ai_service(team):
		frappe.enqueue("central.services.ai.sync_team", team=team, enqueue_after_commit=True)


def on_level_update(doc, method: str | None = None) -> None:
	"""Trust Tier Level hook: a level's renamed tier reaches every AI team on it."""
	if not doc.has_value_changed("tier"):
		return
	teams = frappe.get_all("Billing Profile", filters={"trust_tier_level": doc.name}, pluck="name")
	for team in frappe.get_all(
		"Team Service", filters={"team": ("in", teams), "add_on_service": AI_SERVICE}, pluck="team"
	):
		frappe.enqueue("central.services.ai.sync_team", team=team, enqueue_after_commit=True)


def get_overview(team: str) -> dict:
	"""The team's AI at a glance: `spend` (this month's, and the keys' caps against the tier's
	spend limit), this month's `usage`, and the `geographies` a key may be minted in. What a key may call and how fast is the key's own: see `list_api_keys`."""
	client = GroveClient.from_settings()
	return {
		"spend": client.get_spend(team),
		"usage": get_month_usage(team),
		"geographies": client.list_geographies(),
	}


def get_month_usage(team: str) -> dict:
	"""This month's requests, tokens and cost, with the window and Grove's as-of time."""
	usage = GroveClient.from_settings().get_usage([team], period="This Month")
	return {
		**(usage.get(team) or {"requests": 0, "tokens": 0, "cost": 0}),
		"from_date": usage["from_date"],
		"to_date": usage["to_date"],
		"as_of": usage["as_of"],
	}


def get_models(geography: str | None = None) -> list[dict]:
	"""What a new key in `geography` (Grove's default when None) starts with: the published
	models of its default group, what each takes and gives, and the API surfaces it answers on."""
	return shape_models(GroveClient.from_settings().list_models(geography=geography))


def get_key_models(team: str, key: str) -> list[dict]:
	"""The models Grove lets one key call, as its geography serves them. Grove decides; Central
	only shows them."""
	return shape_models(GroveClient.from_settings().list_models(team, key))


def shape_models(rows: list[dict]) -> list[dict]:
	return [
		{
			"name": row["name"],
			"provider": row.get("provider"),
			"model_id": row.get("model_id"),
			"input_modalities": row.get("input_modalities", []),
			"output_modalities": row.get("output_modalities", []),
			"dialects": row["dialects"],
		}
		for row in rows
	]


def get_usage_report(team: str, period: str, key_hash: str | None = None) -> dict:
	"""What the team used over a period, or one key of theirs by `key_hash`: requests and cost,
	in total, per model, and per day for a chart. Grove does the sums and charged the cost."""
	usage = GroveClient.from_settings().get_usage([team], period=period, key_hash=key_hash)
	return {
		"period": period,
		"from_date": usage["from_date"],
		"to_date": usage["to_date"],
		"as_of": usage["as_of"],
		"totals": usage.get(team) or {"requests": 0, "tokens": 0, "cost": 0},
		"models": usage["model_summary"],
		"daily": get_every_day(usage),
	}


def get_every_day(usage: dict) -> list[dict]:
	"""Grove's per-day rows with the quiet days filled in: one row per day of the period and
	model, zeros where the model was not used, so a chart shows the whole period."""
	used = {(row["day"], row["model"]): row for row in usage["daily_summary"]}
	models = [row["model"] for row in usage["model_summary"]]
	days = frappe.utils.date_diff(usage["to_date"], usage["from_date"]) + 1

	return [
		used.get((day, model)) or {"day": day, "model": model, "requests": 0, "tokens": 0, "cost": 0}
		for day in (str(frappe.utils.add_days(usage["from_date"], offset)) for offset in range(days))
		for model in models
	]
