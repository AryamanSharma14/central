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

### Failure

When a stop or a terminate fails, Central writes the reason in Trial Error on the Site and an Error Log, and the daily job tries again the next day. While a trial is Ended and its server is not Stopped, the daily job sends the stop again.
