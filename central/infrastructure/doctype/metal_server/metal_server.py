# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from typing import Literal

import frappe
from frappe.model.document import Document


class MetalServer(Document):
	"""A bare metal server and how to reach it."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bmc_password: DF.Password | None
		bmc_url: DF.Data | None
		bmc_username: DF.Password | None
		cost_per_month_inr: DF.Currency
		disk_gib: DF.Int
		memory_gib: DF.Int
		os: DF.Data | None
		private_ipv4: DF.Data | None
		public_ipv4: DF.Data | None
		region: DF.Link
		root_password: DF.Password | None
		root_username: DF.Password | None
		status: DF.Literal["Active", "Archived"]
		vcpus: DF.Int
		vendor: DF.Data
	# end: auto-generated types

	@frappe.whitelist(methods=["POST"])
	def get_credentials(self, kind: Literal["root", "bmc"]) -> dict[str, str | None]:
		"""Return the root or BMC login to a system user with System Manager."""
		frappe.only_for("System Manager")

		return {
			"username": self.get_password(f"{kind}_username", raise_exception=False),
			"password": self.get_password(f"{kind}_password", raise_exception=False),
		}
