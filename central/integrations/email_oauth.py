"""Frappe Cloud's OAuth app at each mail provider, and the note that carries one mailbox sign-in."""

from typing import TypedDict
from urllib.parse import urlsplit

import frappe
import requests
from frappe import _
from frappe.utils import get_url
from oauthlib.oauth2 import WebApplicationClient

from central.infrastructure.doctype.site.site import get_server_hostnames

SETTINGS = "Email OAuth Settings"
CALLBACK_PATH = "/api/method/central.api.email_oauth.callback"
SITE_CALLBACK_PATH = "/api/method/frappe.integrations.frappe_providers.email_oauth.callback"
NOTE_TTL = 10 * 60


class Provider(TypedDict):
	authorize_url: str
	token_url: str
	scopes: list[str]
	authorize_params: dict[str, str]


# To add a provider: an entry here, `<key>_client_id` + `<key>_client_secret` on Email OAuth Settings, and CALLBACK_PATH as a Redirect URI in the provider's app. Nothing else in this file changes.
PROVIDERS: dict[str, Provider] = {
	"microsoft": {
		"authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
		"token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
		"scopes": [
			"offline_access",
			"https://outlook.office.com/IMAP.AccessAsUser.All",
			"https://outlook.office.com/SMTP.Send",
			"openid",
			"email",
			"profile",
		],
		"authorize_params": {"prompt": "select_account"},
	},
}


def start_sign_in(
	provider: str, state: str, code_challenge: str, return_url: str, team: str, server: str | None
) -> dict:
	"""Remember where to send the browser back, and return the provider's sign-in link."""
	config, client_id = get_provider(provider)
	check_return_url(return_url, team, server)

	frappe.cache.set_value(
		note_key(state),
		{"return_url": return_url, "team": team, "server": server},
		expires_in_sec=NOTE_TTL,
	)

	authorize_url = WebApplicationClient(client_id).prepare_request_uri(
		config["authorize_url"],
		redirect_uri=get_url(CALLBACK_PATH),
		scope=" ".join(config["scopes"]),
		state=state,
		code_challenge=code_challenge,
		code_challenge_method="S256",
		**config["authorize_params"],
	)
	# the site saves these scopes on its Connected App, so it keeps no list of its own
	return {"authorize_url": authorize_url, "client_id": client_id, "scopes": config["scopes"]}


def check_return_url(return_url: str, team: str, server: str | None) -> None:
	url = urlsplit(return_url)
	schemes = ("https", "http") if frappe.conf.developer_mode else ("https",)
	if (
		url.scheme in schemes
		and "@" not in url.netloc
		and "\\" not in return_url
		and url.path == SITE_CALLBACK_PATH
		and url.hostname in get_server_hostnames(team, server)
	):
		return
	frappe.throw(
		_("Return URL must be the email callback on one of this server's sites"), frappe.PermissionError
	)


def get_sign_in(state: str | None) -> dict | None:
	return frappe.cache.get_value(note_key(state)) if state else None


def mark_login_sent(state: str, note: dict) -> None:
	frappe.cache.set_value(note_key(state), {**note, "login_sent": True}, expires_in_sec=NOTE_TTL)


def forget_sign_in(state: str) -> None:
	frappe.cache.delete_value(note_key(state))


def note_key(state: str) -> str:
	return f"email_oauth:{state}"


def exchange_token(provider: str, grant_type: str, **params: str | None) -> dict:
	"""Swap a code or refresh token at the provider with Frappe Cloud's app secret."""
	config, client_id = get_provider(provider)
	if grant_type not in ("authorization_code", "refresh_token"):
		frappe.throw(_("Unsupported grant type"))

	data = {
		**params,
		"grant_type": grant_type,
		"client_id": client_id,
		"client_secret": frappe.get_single(SETTINGS).get_password(f"{provider}_client_secret"),
	}
	if grant_type == "authorization_code":
		data["redirect_uri"] = get_url(CALLBACK_PATH)

	response = requests.post(config["token_url"], data={k: v for k, v in data.items() if v}, timeout=30)
	token = response.json()
	if not response.ok:
		# Pilot keeps only this text, so the site can still tell invalid_grant apart (standard OAuth error code)
		frappe.throw(token.get("error") or _("The mail provider refused the token request"))
	return token


def get_provider(provider: str) -> tuple[Provider, str]:
	config = PROVIDERS.get(provider)
	client_id = config and frappe.db.get_single_value(SETTINGS, f"{provider}_client_id")
	if not client_id:
		frappe.throw(_("Sign in with {0} isn't available right now").format(provider))
	return config, client_id
