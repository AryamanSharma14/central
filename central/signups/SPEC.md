# Signups

## Purpose

The Signups module holds what a new customer gets: the [Product](doctype/product/SPEC.md) they sign up for, the free trial and the welcome credit. Operators start with the [Trials operator guide](../../spec/TRIALS_OPERATOR_GUIDE.md).

## Welcome credit

A Team gets the welcome credit when its first payment method becomes active, not at signup. The credit is granted once for each owner across all of the owner's Teams.

A Team with trial sites gets the credit only while one of its trials is Active. This rewards a card before the trial ends. A card after the trial ends still converts the site, but adds no credit. `get_welcome_credit_offer` returns `ends_on`, the earliest end date of the Team's Active trials, so the console and the site can name the last day.

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
| Trial Days | Central Settings, and Product | Days a trial site runs from when Central records it. A Product with 0 uses Central Settings. |
| Trial Deletion Days | Central Settings, and Product | Days a stopped trial site is kept before its server is terminated. A Product with 0 uses Central Settings. |
| Trial Notice Days | Central Settings | Days before the end date, and before the deletion date, that the warning email goes out. |

Example: Central Settings has Trial Days 14 and Trial Deletion Days 14. Product `raven` has Trial Days 30. A Raven trial runs 30 days, stops, and is terminated 14 days later.

### Operation

Central records the site when the region first reports its machine with an address, a few minutes after the request. The trial starts then. It does not wait for the customer to open the site, so a trial that the customer leaves also ends.

| Trial State | When | What Central does |
|---|---|---|
| Active | Central records the site and its Team has no active payment method | Sets Trial Ends On. |
| Converted | Central records the site and its Team already has an active payment method | Nothing. The site is not a trial. |
| Ended | Trial Ends On is reached | Stops the server and sets Trial Deletes On. |
| Deleted | Trial Deletes On is reached and the server is Terminated | Asks for a normal terminate action each day until the server is Terminated, then sets the state. |

The daily job `central.signups.trial.run_trials` moves each site. It sends each email once and records the last one in Trial Last Notice.

| Event | Sent |
|---|---|
| `trial_unopened` | Once, from the day after the site is ready, when nobody has opened it. Not sent when a warning is due. |
| `trial_expiring` | Trial Notice Days before Trial Ends On, and again on the last day. It names the welcome credit when the Team can still earn it, and says that the site sleeps when idle. |
| `trial_ended` | When the stop job has stopped the server, not when the trial ends |
| `trial_deletion_soon` | Trial Notice Days before Trial Deletes On |
| `trial_deleted` | When the server is terminated |
| `trial_converted` | When a payment method converts the trial |

A Product can add its own paragraph to each email and show its own logo and name. See [Product emails](doctype/product/SPEC.md#emails). These events are in the **Trial** notification category. A user can turn the email or the in-app notice for this category off in their notification settings. Each event goes to the Team members who hold `billing:view`.

A trial server usually sleeps when idle, and Atlas does not stop a sleeping VM. To end a trial, Central starts the server and then stops it. An explicit stop keeps the VM down, so traffic does not wake it.

### Limits

| Request | What Central checks |
|---|---|
| A trial site from the signup flow, Team without a payment method | The Team has fewer open trial sites (Active or Ended), pending site creations, and provisioned servers whose site Central has not recorded yet than Central Settings, Trial Servers per Team. No credit is needed. |
| Any other server | Credit covers the server's monthly rate, or the billing profile is complete and the Team has an active payment method or pays by Manual Checkout. Otherwise Central refuses with `PAYMENT_METHOD_REQUIRED`. With Central Settings, Require Payment Method for Servers off, a complete billing profile is enough. |
| Start an Ended trial's server | Refused. The Team must add a payment method, which converts the trial and starts the server. |
| Resize a trial server | Refused, because a trial server has no subscription. The console resize dialog and the in-app plan list ask for a payment method first. `get_composed_config` returns `trial`, and `billing_api.change_plan` refuses with "Add a payment method to change this site's plan." |

### Console

`central.billing.api.dashboard.account.get_billing_profile` returns `payment_method_required` and `welcome_credit` (`amount`, `currency`, `validity_days`, or null when the owner already had it). When a payment method is required, the New Server page shows a note and disables Create. Its **Add payment method** button opens the billing details dialog when they are missing, then the payment method dialog, on the same page. The welcome credit offer needs a billing currency, and the currency comes from the country (India pays in INR, every other country in USD). So the onboarding payment step asks for the billing country first and saves it to the billing profile. It fills India when the browser time zone is in India. It then names the welcome credit in that currency, says that adding a payment method does not charge it, and opens the same two dialogs, with the country already filled. On Billing, the main action for a new team is **Add card**. **Add credit** on the Wallet row tops up the prepaid wallet.

### Billing and conversion

A trial server has no subscription, so a trial creates no invoice. Before Central records the site, a server from the signup flow counts as a trial unless its Team already has an active payment method. The daily backfill of missing subscriptions skips these servers too.

When a payment method of the Team becomes active, every Active or Ended trial site of the Team becomes Converted:

1. Central records Trial Cost: the plan's monthly rate from the creation request, divided by 30, for each day since Central recorded the site.
2. A running or sleeping server gets its subscription now. A stopped server gets it when it starts. Until then, `get_composed_config` returns `starting`, and the console resize dialog says the server is starting on its paid plan and checks again.
3. A background job turns idle sleep off in Atlas, and starts the server when it is Stopped. When the team pays while the trial's stop job runs, the stop job queues this job again, so the server does not stay stopped. When a resize of the server is pending, the job writes a Trial Error and stops, because both jobs change the server's power. The daily job sends the conversion again.

A Deleted trial is not converted, because its server is gone. Its Trial Cost runs to Trial Ends On.

### In-app status

`central.billing.api.billing_api.get_billing_summary` returns `trial` for the site on the calling server: `state` (Active or Ended), `ends_on`, `days_left`, `deletes_on`, `credit` (the welcome credit offer, or null) and `sleeps_after_minutes` (Central Settings, Trial Idle Shutdown). It is null when the site has no open trial. The in-app billing panel shows it. On a server with several sites, the caller passes `site`, the Site's name. Without it, Central refuses the call.

### Desk

On a Site with an open trial, a System Manager has a **Trial** menu: **Extend Trial** adds days and starts an Ended trial again, **End Trial Now** ends an Active trial today, and **Retry Trial Step** runs today's step again after a Trial Error. On a Converted site, it sends the conversion job again. Each action leaves a comment on the Site. The **Trial Sites** report counts trial sites and their cost by product, month and state.

### Failure

When a stop, a terminate, or the conversion job fails, Central writes the reason in Trial Error on the Site and an Error Log, and the daily job tries again the next day. The daily job includes Converted sites that have a Trial Error. While a trial is Ended and its server is not Stopped, the daily job sends the stop again.
