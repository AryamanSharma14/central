# Copyright (c) 2026, frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
import hashlib
import json
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

from central.iam import can
from central.infrastructure.doctype.pilot_credential.pilot_credential import PilotCredential


class GitHubRepositoryNotGranted(frappe.PermissionError):
	"""The Pilot has no active grant for this repository."""


class GitHubConnection(Document):
	"""A Pilot's grant to read selected repositories of one GitHub App installation."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from central.infrastructure.doctype.github_connection_repository.github_connection_repository import (
			GitHubConnectionRepository,
		)

		account: DF.Data | None
		account_type: DF.Literal["User", "Organization"]
		installation_id: DF.Data
		pilot_credential: DF.Link
		repositories: DF.Table[GitHubConnectionRepository]
		server: DF.Link | None
		status: DF.Literal["Active", "Disabled"]
		team: DF.Link
		version: DF.Int
	# end: auto-generated types

	@staticmethod
	def grant(credential: PilotCredential, installation: dict, repositories: list[dict]) -> GitHubConnection:
		"""Save the repositories one installation grants to a Pilot, replacing an earlier grant."""
		name = frappe.db.get_value(
			"GitHub Connection",
			{"pilot_credential": credential.name, "installation_id": installation["installation_id"]},
			for_update=True,
		)
		connection = (
			frappe.get_doc("GitHub Connection", name) if name else frappe.new_doc("GitHub Connection")
		)
		connection.update(
			{
				"team": credential.team,
				"server": credential.server,
				"pilot_credential": credential.name,
				"installation_id": installation["installation_id"],
				"account": installation["account"],
				"account_type": installation["account_type"],
				"status": "Active",
				"version": (connection.version or 0) + 1,
			}
		)
		connection.set(
			"repositories",
			[
				{"repository_id": repository["repository_id"], "full_name": repository["full_name"]}
				for repository in repositories
			],
		)
		connection.save(ignore_permissions=True)
		return connection

	@staticmethod
	def revoke(credential: PilotCredential, installation_id: str) -> None:
		"""Remove the grant of one installation from a Pilot."""
		name = frappe.db.get_value(
			"GitHub Connection",
			{"pilot_credential": credential.name, "installation_id": installation_id, "status": "Active"},
			for_update=True,
		)
		if name:
			frappe.get_doc("GitHub Connection", name).disable()

	@staticmethod
	def get_active(credential: PilotCredential) -> list[GitHubConnection]:
		names = frappe.get_all(
			"GitHub Connection",
			filters={"pilot_credential": credential.name, "status": "Active"},
			pluck="name",
			order_by="creation asc",
		)
		return [frappe.get_doc("GitHub Connection", name) for name in names]

	@staticmethod
	def find_repository(credential: PilotCredential, full_name: str) -> tuple[GitHubConnection, str]:
		"""The active connection that grants `full_name` to this Pilot, and the repository ID."""
		for connection in GitHubConnection.get_active(credential):
			for repository in connection.repositories:
				if repository.full_name.lower() == full_name.lower():
					return connection, repository.repository_id

		frappe.throw(
			_("Repository {0} is not granted to this server.").format(full_name), GitHubRepositoryNotGranted
		)

	def is_current(self, version: int) -> bool:
		"""Whether the grant is still active and unchanged since `version` was read."""
		status, current_version = frappe.db.get_value("GitHub Connection", self.name, ["status", "version"])
		return status == "Active" and current_version == version

	def disable(self) -> None:
		self.status = "Disabled"
		self.version += 1
		self.save(ignore_permissions=True)

	@staticmethod
	def disable_installation(installation_id: str) -> None:
		for connection in GitHubConnection._lock_active(installation_id):
			connection.disable()

	@staticmethod
	def remove_repositories(installation_id: str, repository_ids: set[str]) -> None:
		for connection in GitHubConnection._lock_active(installation_id):
			kept = [row for row in connection.repositories if row.repository_id not in repository_ids]
			if len(kept) < len(connection.repositories):
				connection.set("repositories", kept)
				connection.version += 1
				connection.save(ignore_permissions=True)

	@staticmethod
	def _lock_active(installation_id: str) -> list[GitHubConnection]:
		names = frappe.get_all(
			"GitHub Connection",
			filters={"installation_id": installation_id, "status": "Active"},
			pluck="name",
		)
		return [frappe.get_doc("GitHub Connection", name, for_update=True) for name in names]


ATTEMPT_TTL_SECONDS = 60 * 60
# The state and return URL outlive the attempt, so an expired link can still send the user back.
LINK_TTL_SECONDS = 24 * 60 * 60


class GitHubConnectionAttempt:
	"""A Pilot's request to connect GitHub, kept in Redis. The first user who opens it owns it."""

	def __init__(self, attempt_id: str, data: dict) -> None:
		self.attempt_id = attempt_id
		self.data = data

	@classmethod
	def start(cls, credential: PilotCredential, return_url: str) -> GitHubConnectionAttempt:
		attempt = cls(secrets.token_urlsafe(24), {"pilot_credential": credential.name})
		attempt.save()
		frappe.cache.set_value(
			cls._return_key(attempt.attempt_id), return_url, expires_in_sec=LINK_TTL_SECONDS
		)
		return attempt

	@classmethod
	def find(cls, attempt_id: str) -> GitHubConnectionAttempt | None:
		data = frappe.cache.get_value(cls._key(attempt_id))
		return cls(attempt_id, json.loads(data)) if data else None

	@classmethod
	def load(cls, attempt_id: str) -> GitHubConnectionAttempt:
		attempt = cls.find(attempt_id)
		if not attempt:
			frappe.throw(
				_("This link has expired. Open Git settings on your server and connect GitHub again."),
				frappe.DoesNotExistError,
			)
		return attempt

	@classmethod
	def find_attempt_id(cls, state: str) -> str | None:
		return frappe.cache.get_value(cls._state_key(state))

	@classmethod
	def find_return_url(cls, attempt_id: str) -> str | None:
		return frappe.cache.get_value(cls._return_key(attempt_id))

	@property
	def credential(self) -> PilotCredential:
		credential = frappe.get_doc("Pilot Credential", self.data["pilot_credential"])
		if credential.status != "Active":
			frappe.throw(_("This server can no longer connect GitHub."), frappe.PermissionError)
		return credential

	@property
	def state(self) -> str:
		return self.data["state"]

	@property
	def code_challenge(self) -> str:
		digest = hashlib.sha256(self.data["code_verifier"].encode()).digest()
		return base64.urlsafe_b64encode(digest).decode().rstrip("=")

	@property
	def code_verifier(self) -> str:
		return self.data["code_verifier"]

	@property
	def user_token(self) -> str | None:
		return decrypt(self.data["user_token"]) if self.data.get("user_token") else None

	def bind(self, user: str) -> PilotCredential:
		"""Bind the attempt to the first user with console access to the server."""
		credential = self.credential
		if not can(user, credential.team, "server:console", server=credential.server):
			frappe.throw(
				_("You can't connect GitHub to this server. Ask a team admin to review your access."),
				frappe.PermissionError,
			)

		if self.data.get("user") not in (None, user):
			frappe.throw(
				_("Another user already opened this GitHub connection link."), frappe.PermissionError
			)

		if not self.data.get("user"):
			self.data.update(
				{"user": user, "state": secrets.token_urlsafe(24), "code_verifier": secrets.token_urlsafe(48)}
			)
			self.save()
			frappe.cache.set_value(
				self._state_key(self.state), self.attempt_id, expires_in_sec=LINK_TTL_SECONDS
			)
		else:
			# Activity keeps the attempt alive during a long trip through GitHub.
			frappe.cache.expire_key(self._key(self.attempt_id), ATTEMPT_TTL_SECONDS)

		return credential

	def set_user_token(self, token: str) -> None:
		self.data["user_token"] = encrypt(token)
		self.save()

	def finish(self) -> None:
		frappe.cache.delete_value(self._key(self.attempt_id))

	def save(self) -> None:
		frappe.cache.set_value(
			self._key(self.attempt_id), json.dumps(self.data), expires_in_sec=ATTEMPT_TTL_SECONDS
		)

	@staticmethod
	def _key(attempt_id: str) -> str:
		return f"github:connection-attempt:{attempt_id}"

	@staticmethod
	def _state_key(state: str) -> str:
		return f"github:connection-state:{state}"

	@staticmethod
	def _return_key(attempt_id: str) -> str:
		return f"github:connection-return:{attempt_id}"


def on_doctype_update() -> None:
	frappe.db.add_unique("GitHub Connection", ["pilot_credential", "installation_id"])
