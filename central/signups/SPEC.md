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
