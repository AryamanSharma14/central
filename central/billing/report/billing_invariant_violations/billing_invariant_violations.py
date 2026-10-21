# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Billing Invariant Violations — the money facts that no longer add up.

Every row is a place where two independent derivations of the same number disagree:
a wallet whose balance is not its ledger, an invoice whose subtotal is not its lines,
a payment we believe we captured with no attempt behind it.

**An empty report is the success case.** This is the one report you want blank.

It also lists the readiness checks (`platform.readiness`): data the next billing run
would bill wrongly or not at all. The Summary view shows one row per check.

It recomputes live with the same functions the daily audit and hourly alerts run, so
what the jobs assert and what a human reads can never drift apart. Nothing is stored,
so there is no snapshot to go stale.

Amounts are split per currency: INR and USD never share a column or a total
(report/_currency.split_currency_columns).
"""

import frappe
from frappe import _

from central.billing.platform import invariants, readiness
from central.billing.report._currency import split_currency_columns

KINDS = {"Money": invariants.CHECKS, "Readiness": readiness.CHECKS}


def _registries(kind: str | None) -> dict:
	return {k: v for k, v in KINDS.items() if not kind or k == kind}


def _title(check: str) -> str:
	return next(registry[check][0] for registry in KINDS.values() if check in registry)


def _kind(check: str) -> str:
	return next(name for name, registry in KINDS.items() if check in registry)


def _violations(filters: dict) -> list:
	only = filters.get("check") or None
	found = []
	for registry in _registries(filters.get("kind")).values():
		if not only or only in registry:
			found.extend(invariants.audit(only=only, checks=registry))
	if filters.get("team"):
		found = [v for v in found if v.team == filters["team"]]
	return found


def execute(filters: dict | None = None):
	filters = filters or {}
	violations = _violations(filters)
	if filters.get("view") == "Summary":
		return _summary(violations)

	rows = [
		{
			"check": v.check,
			"title": _title(v.check),
			"team": v.team,
			"subject_doctype": v.subject_doctype,
			"subject": v.subject,
			"currency": v.currency,
			"expected": v.expected,
			"actual": v.actual,
			"drift": v.drift,
			"detail": v.detail,
		}
		for v in violations
	]

	# Splits expected/actual/drift into one column per currency when the run spans more
	# than one, and drops the standalone currency column. Mutates `rows` in place.
	columns = split_currency_columns(_columns(), rows, ("expected", "actual", "drift"))
	return columns, rows, _message(rows), _chart(violations)


def _summary(violations: list):
	"""One row per check: how many violations, across how many teams."""
	rows = []
	for registry in KINDS.values():
		for check, (title, _fn) in registry.items():
			hits = [v for v in violations if v.check == check]
			rows.append(
				{
					"check": check,
					"kind": _kind(check),
					"title": title,
					"violations": len(hits),
					"teams": len({v.team for v in hits if v.team}),
					"example": hits[0].detail if hits else "",
				}
			)
	rows.sort(key=lambda row: (-row["violations"], row["check"]))
	columns = [
		{"label": _("Check"), "fieldname": "check", "fieldtype": "Data", "width": 70},
		{"label": _("Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 100},
		{"label": _("What it asserts"), "fieldname": "title", "fieldtype": "Data", "width": 280},
		{"label": _("Violations"), "fieldname": "violations", "fieldtype": "Int", "width": 100},
		{"label": _("Teams"), "fieldname": "teams", "fieldtype": "Int", "width": 80},
		{"label": _("Example"), "fieldname": "example", "fieldtype": "Data", "width": 460},
	]
	return columns, rows, _message(violations), _chart(violations)


def _message(rows: list) -> str:
	if not rows:
		return _("✅ Every money invariant and readiness check holds. This report is meant to be empty.")
	return _(
		"⚠️ {0} violation(s). Money checks are numbers the system derives two ways and gets two "
		"answers for; readiness checks are data the next billing run would bill wrongly. Worst drift first."
	).format(len(rows))


def _chart(violations: list) -> dict | None:
	if not violations:
		return None
	counts: dict[str, int] = {}
	for v in violations:
		counts[v.check] = counts.get(v.check, 0) + 1
	labels = sorted(counts)
	return {
		"data": {
			"labels": [f"{k} — {_title(k)}" for k in labels],
			"datasets": [{"name": _("Violations"), "values": [counts[k] for k in labels]}],
		},
		"type": "bar",
	}


def _columns() -> list[dict]:
	return [
		{"label": _("Check"), "fieldname": "check", "fieldtype": "Data", "width": 70},
		{"label": _("Invariant"), "fieldname": "title", "fieldtype": "Data", "width": 240},
		{"label": _("Team"), "fieldname": "team", "fieldtype": "Link", "options": "Team", "width": 150},
		{
			"label": _("Subject"),
			"fieldname": "subject",
			"fieldtype": "Dynamic Link",
			"options": "subject_doctype",
			"width": 170,
		},
		{"label": _("Type"), "fieldname": "subject_doctype", "fieldtype": "Data", "width": 130},
		# expected / actual / drift are expanded per currency by split_currency_columns,
		# which drops this column when it does — INR and USD never share a total.
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
		},
		{"label": _("Expected"), "fieldname": "expected", "fieldtype": "Currency", "width": 120},
		{"label": _("Actual"), "fieldname": "actual", "fieldtype": "Currency", "width": 120},
		{"label": _("Drift"), "fieldname": "drift", "fieldtype": "Currency", "width": 120},
		{"label": _("What broke"), "fieldname": "detail", "fieldtype": "Data", "width": 420},
	]
