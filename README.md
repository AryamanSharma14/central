# Central

Central is the control plane for Frappe Cloud V2. It signs people in, decides what each team member can do, creates servers through Atlas, and bills each team. It is a Frappe app with a Vue console in `dashboard/`.

<img width="3080" height="1954" alt="CleanShot 2026-10-03 at 2 50 02 PM@2x" src="https://github.com/user-attachments/assets/7644da1f-ae09-42e3-9a5e-e0130b409995" />


Central does not run servers. [Atlas](https://github.com/frappe/atlas) runs the virtual machines in each region, [Pilot](https://github.com/frappe/pilot) runs the benches and sites on a server, and Cargo builds the server images. See [Integrations](spec/INTEGRATIONS.md) for the contracts.

## Requirements

Python 3.14, Node.js 24 with Yarn, MariaDB 11.8, Redis 6 or later, and [Pilot](https://github.com/frappe/pilot).

## Set up a local site

Run these commands from the bench root:

```bash
pilot get-app https://github.com/frappe/central.git --branch develop
pilot new-site central.localhost --admin-password admin
pilot install-app central.localhost central
pilot frappe --site central.localhost set-config developer_mode 1
NO_PROXY='*' pilot start
```

Open the console at `http://central.localhost:<http_port>/dashboard` and Desk at `/app`. The port is `http_port` in `bench.toml`. On macOS, `NO_PROXY='*'` stops the system proxy lookup from killing background workers.

Put gateway and integration keys in `sites/common_site_config.json`. Never commit them.

| Key | Needed for |
|---|---|
| `stripe_secret_key`, `stripe_publishable_key` | Stripe charges and top-ups |
| `razorpay_key_id`, `razorpay_key_secret` | Razorpay charges and top-ups |
| `entitlement_private_key` | Signed plan entitlements |
| `erpnext_url`, `erpnext_api_key`, `erpnext_api_secret` | Invoice sync to ERPNext |

To create servers, connect a Region to Atlas. See [Region](central/infrastructure/doctype/region/SPEC.md).

## Seed demo data

The demo seed creates ten teams with plans, subscriptions, and invoices. It deletes all billing data and all server records first. Run it only on a local site.

```bash
pilot frappe --site central.localhost execute central.billing.demo.demo_scenarios.seed
```

See the [billing demo](central/billing/demo/README.md) for the teams and logins.

## Develop the console

Run these commands from `apps/central`:

```bash
cd apps/central
yarn install
yarn dev
```

## Switch teams in the console

Open the team selector at the top of the sidebar and select a team. The console reloads the current section with that team's data. A server detail or creation page returns to Servers. A bucket detail page returns to Object Storage. Browser storage must be available to retain the selected team. The profile menu contains Theme with System, Light, and Dark options.

The selector shows full names in tooltips. Teams with the same name show their owner, or their unique team ID when the owner is the same. With more than six teams, use search to filter by name or identifier. The list scrolls while Create team stays available.

Use Enter or Space to open the selector. Use Up and Down to move between actions, Home and End to reach the first or last action, and Enter or Space to select. Tab reaches the search field and each action. Escape closes the selector and returns focus to its button.

Server usage opens with the last hour selected. You can select 24 hours, 7 days, 14 days, 30 days, or a custom window of up to 30 days. Switching tabs preserves the content alignment when a scrollbar is needed.

## Run checks and tests

The dashboard uses the installed Frappe UI typography tokens. Use `text-<size>-<weight>` for labels and headings, and `text-p-<size>` for paragraphs. These classes set size, weight, line height, and spacing together. Provider fallback initials use the same type scale at each avatar size.

Run the team session checks with `node --test dashboard/tests/team-session.test.mjs`. These checks verify team selection, section navigation, and browser storage failures without a running site.

Run presentation checks with `node --test dashboard/tests/team-labels.test.mjs`. These checks verify duplicate team names, full team identities, and readable permission labels.

Run the linters from `apps/central`:

```bash
../../env/bin/ruff check central
../../env/bin/ruff format central
python3 scripts/check_patches.py
pre-commit run --all-files
```

Run tests on a separate site with `allow_tests` set, because some billing tests commit their data:

```bash
pilot frappe --site central-test.localhost set-config allow_tests true
pilot frappe --site central-test.localhost run-tests --app central
```

See [`e2e/README.md`](e2e/README.md) for the Playwright suite.

Run the isolated server control checks with `yarn test:server-controls`. These checks render the resize and firewall components with mocked API responses. They do not change a server. Install the Playwright browser first, or set `PLAYWRIGHT_CHANNEL=chrome` to use an installed Chrome browser.

## Documentation

- [CLAUDE.md](CLAUDE.md): contributor and agent rules.
- [Specification router](spec/README.md): every module and cross-cutting specification.
- [Billing architecture](central/billing/ARCHITECTURE.md): the billing code map.

## License

[AGPL-3.0](license.txt)
