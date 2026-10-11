# Signups

## Purpose

The Signups module holds what a new customer gets: the [Product](doctype/product/SPEC.md) they sign up for and the welcome credit.

## Welcome credit

A Team gets the welcome credit when its first payment method becomes active, not at signup. The credit is granted once for each owner across all of the owner's Teams.

| Billing Settings field | Value on a new install |
|---|---|
| Grant Welcome Credits | On |
| Welcome Credit Amounts | 10 USD, 1000 INR |
| Validity (Days) | 60 |

A new install seeds these values once. Change them on an existing site in Billing Settings. A currency with no amount gets no credit. A staging trial team (Billing Settings, Provision Teams as Trial) still gets its credit at signup, because it runs servers on credit before it has a payment method.

### Operator credit

A System Manager can grant credit from the **Grant Credit** action on a Team, for example 100 USD to a beta user. The operator sets the amount in the Team's billing currency, the validity in days and a note. The credit is available at once. It counts as the owner's welcome credit, so the Team gets no welcome credit later.

## Trials

A trial site is a site from the signup flow, with or without a Product. It runs free for a set number of days. The trial state is on the Site, in the **Trial** section.

### Configuration

| Field | Where | Meaning |
|---|---|---|
| Trial Days | Central Settings, and Product | Days a trial site runs from when it is first ready. A Product with 0 uses Central Settings. |
| Trial Deletion Days | Central Settings, and Product | Days a stopped trial site is kept before its server is terminated. A Product with 0 uses Central Settings. |
| Trial Notice Days | Central Settings | Days before the end date, and before the deletion date, that the warning email goes out. |

Example: Central Settings has Trial Days 14 and Trial Deletion Days 14. Product `raven` has Trial Days 30. A Raven trial runs 30 days, stops, and is terminated 14 days later.

### Operation

| Trial State | When | What Central does |
|---|---|---|
| Active | The site is first ready and its Team has no active payment method | Sets Trial Ends On. |
| Converted | The site is first ready and its Team already has an active payment method | Nothing. The site is not a trial. |
| Ended | Trial Ends On is reached | Stops the server and sets Trial Deletes On. |
| Deleted | Trial Deletes On is reached | Terminates the server with a normal terminate action. |

The daily job `central.signups.trial.run_trials` moves each site. It sends each email once and records the last one in Trial Last Notice.

| Event | Sent |
|---|---|
| `trial_expiring` | Trial Notice Days before Trial Ends On, and again on the last day |
| `trial_ended` | When the server is stopped |
| `trial_deletion_soon` | Trial Notice Days before Trial Deletes On |
| `trial_deleted` | When the server is terminated |

These events are in the **Trial** notification category. A user can turn the email or the in-app notice for this category off in their notification settings. Each event goes to the Team members who hold `billing:view`.

A trial server usually sleeps when idle, and Atlas does not stop a sleeping VM. To end a trial, Central starts the server and then stops it. An explicit stop keeps the VM down, so traffic does not wake it.

### Limits

| Request | What Central checks |
|---|---|
| A trial site from the signup flow, Team without a payment method | The Team has fewer open trial sites (Active or Ended) and pending site creations than Central Settings, Trial Servers per Team. No credit is needed. |
| Any other server | Credit covers the server's monthly rate, or the billing profile is complete and the Team has an active payment method or pays by Manual Checkout. Otherwise Central refuses with `PAYMENT_METHOD_REQUIRED`. With Central Settings, Require Payment Method for Servers off, a complete billing profile is enough. |
| Start an Ended trial's server | Refused. The Team must add a payment method, which converts the trial and starts the server. |

### Console

`central.billing.api.dashboard.account.get_billing_profile` returns `payment_method_required` and `welcome_credit` (`amount`, `currency`, `validity_days`, or null when the owner already had it). When a payment method is required, the New Server page shows a note with a link to Billing and disables Create. The onboarding billing step says that servers need a payment method, and names the welcome credit.

### Billing and conversion

A trial server has no subscription, so a trial creates no invoice. Before the site is ready, a server from the signup flow counts as a trial unless its Team already has an active payment method. The daily backfill of missing subscriptions skips these servers too.

When a payment method of the Team becomes active, every Active or Ended trial site of the Team becomes Converted:

1. Central records Trial Cost: the plan's monthly rate from the creation request, divided by 30, for each day since the site was ready.
2. A running server gets its subscription now. A stopped server gets it when it starts.
3. A background job turns idle sleep off in Atlas, and starts the server if the trial had stopped it.

A Deleted trial is not converted, because its server is gone. Its Trial Cost runs to Trial Ends On.

### In-app status

`central.billing.api.billing_api.get_billing_summary` returns `trial` for the site on the calling server: `state` (Active or Ended), `ends_on`, `days_left` and `deletes_on`. It is null when the site has no open trial. The in-app billing panel shows it. On a server with several sites, the caller passes `site`, the Site's name. Without it, Central refuses the call.

### Failure

When a stop or a terminate fails, Central writes the reason in Trial Error on the Site and an Error Log, and the daily job tries again the next day. While a trial is Ended and its server is not Stopped, the daily job sends the stop again.
