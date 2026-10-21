# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt
"""Object storage is billed by the GB-month, from a daily reading of each team's buckets.

One storage subscription bills every bucket a team holds in a region. Each day adds
that day's share of the month (GB held / days in the month) to the month's usage, keyed
by the day so a second run the same day adds nothing. At month end the usage is the
average GB held, which the invoice prices at the current per-GB rate. GB here is the
GiB Cargo counts and caps in.
"""

import calendar
from collections import defaultdict

import frappe

from central.billing.doctype.billing_profile.billing_profile import get_team_currency
from central.billing.revenue.metering import ingest_rollup

BYTES_PER_GIB = 1024**3
RESOURCE_TYPE = "Storage"


def record_storage_usage(today=None) -> dict:
	"""Daily: add today's share of the month to every storage subscription's usage."""
	today = frappe.utils.getdate(today)
	recorded, failed = 0, 0
	for subscription, buckets in _buckets_by_subscription().items():
		try:
			frappe.db.savepoint("storage_usage")
			record_subscription_usage(subscription, buckets, today)
			recorded += 1
		except Exception:
			# One unreachable region must not stop the others; the readiness audit flags the gap.
			frappe.db.rollback(save_point="storage_usage")
			frappe.log_error(title=f"Storage usage for {subscription} was not recorded")
			failed += 1
	return {"recorded": recorded, "failed": failed}


def record_subscription_usage(subscription: str, buckets: list, today) -> str | None:
	"""Read what the subscription's buckets hold and add today's share to its month."""
	gib = sum(frappe.utils.flt(bucket.get_usage().get("used_bytes")) for bucket in buckets) / BYTES_PER_GIB
	sub = frappe.db.get_value(
		"Subscription", subscription, ["team", "cluster", "service_subject"], as_dict=True
	)
	days = calendar.monthrange(today.year, today.month)[1]
	start = today.replace(day=1)
	return ingest_rollup(
		{
			"idempotency_key": f"storage::{sub.service_subject}::{start:%Y-%m}",
			"resource_id": sub.service_subject,
			"resource_type": RESOURCE_TYPE,
			"meter_type": "Gauge",
			"team": sub.team,
			"cluster": sub.cluster,
			"currency": get_team_currency(sub.team),
			"period_start": start,
			"period_end": today.replace(day=days),
			"quantity": gib / days,
			"unit": "GB",
			"sequence": today.day,
		}
	)


def _buckets_by_subscription() -> dict[str, list]:
	"""Every live bucket, grouped by the storage subscription that bills it."""
	from central.services.doctype.team_service.team_service import STORAGE_SERVICE

	grouped = defaultdict(list)
	for name in frappe.get_all(
		"Team Service",
		filters={"add_on_service": STORAGE_SERVICE, "status": "Active", "subscription": ["is", "set"]},
		pluck="name",
	):
		bucket = frappe.get_doc("Team Service", name)
		grouped[bucket.subscription].append(bucket)
	return grouped
