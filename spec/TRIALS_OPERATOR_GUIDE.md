# Trials Operator Guide

This guide is for the person who runs free trials and welcome credit from Desk. For the full behavior, read [Signups](../central/signups/SPEC.md).

## How a trial works

1. A customer signs up and gets a trial site. The site is free. It sleeps when nobody uses it.
2. The trial ends after **Trial Days**. Central stops the server.
3. **Trial Deletion Days** later, Central deletes the server and its data.
4. Central emails the team before the end, at the end, before deletion and at deletion.
5. If the team adds a payment method at any time, the trial becomes a paid site. Billing starts, and a stopped server starts again.

A team without a payment method can only have free trial sites. To create any other server, it must add a payment method.

## Before launch: check these settings

| Where | Field | Value |
|---|---|---|
| Billing Settings | Grant Welcome Credits | On |
| Billing Settings | Welcome Credit Amounts | USD 10, INR 1000 |
| Billing Settings | Validity (Days) | 60 |
| Billing Settings | Provision Teams as Trial | Off. This is for staging only. |
| Plan | Available on Trial | On for each active plan that signup may select. The cheapest eligible marked plan is selected. Its disk must fit the trial image. |
| Central Settings | Trial Days | 7 |
| Central Settings | Trial Deletion Days | 7 |
| Central Settings | Trial Notice Days | 2 |
| Central Settings | Trial Servers per Team | 3 |
| Central Settings | Require Payment Method for Servers | On |
| Central Settings | Trial Idle Shutdown (Minutes) | 10 |
| Region | FrappeMail Service | Enabled. Keep enough free mailboxes, because an empty pool stops new trials. |

A Product can have its own Trial Days and Trial Deletion Days. Leave them at 0 to use Central Settings.

A trial team gets the welcome credit only when it adds a card while a trial is still Active. A card after the trial ends brings the site back, but with no credit. A team without a trial gets the credit with its first card.

## Common tasks

| Task | What to do |
|---|---|
| Find trial sites | Open the **Site** list. Filter by **Trial State**. Blue is Active, orange is Ended, green is Converted, gray is Deleted. |
| Give a customer more time | Open the Site. Click **Trial > Extend Trial** and enter the days. An ended trial starts again. |
| End a trial now | Open the Site. Click **Trial > End Trial Now**. The server stops today. |
| Fix a failed trial step | The Site shows the error in red at the top. Click **Trial > Retry Trial Step**. If it fails again, open the Error Log named "Trial step failed". |
| Give a beta user credit | Open the **Team**. Click **Grant Credit**. Enter the amount in the team's currency, the days it is valid, and a note. The team gets no welcome credit after this. |
| Let a team create servers without a card, for a demo | Turn off **Require Payment Method for Servers** in Central Settings. Turn it on again after the demo. |
| See what trials cost | Open the **Trial Sites** report. It shows sites by product, month and state, with their cost. |
| See a team's trials | Open the Team. The **Site** link in Infrastructure lists its sites. |

## What the customer sees

| When | Customer sees |
|---|---|
| New Server page, no payment method | A note at the top: add a payment method to create servers and get the welcome credit. Create is off. **Add payment method** opens the payment dialog on the same page. |
| Onboarding, payment step | The welcome credit offer, that adding a card does not charge it, and an **Add payment method** button. It asks for billing details first when they are missing. |
| Trial ending, ended, deletion soon, deleted | An email and a notice in the **Trial** category. Customers can turn these off in their notification settings. |
| Site's in-app billing panel | The days left, the last day to add a card and get the credit, and that the site sleeps after Trial Idle Shutdown minutes without visitors. |
| Console resize dialog on a trial server | The same, with an **Add payment method** button. After the card, the plans. |
