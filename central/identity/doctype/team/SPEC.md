# Team

## Network identity

Each Team has one permanent numeric tenant ID for Atlas network isolation. The Team name remains the customer-facing label.

## Allocation

Central assigns the ID when it inserts a Team. It replaces any caller-supplied value. IDs range from 1 to 4294967295. Zero belongs to infrastructure.

The Framework naming series `TENANT-ID` serializes allocation in the Team transaction. A rolled-back allocation can be reused. A committed allocation is never decremented, including after Team deletion.

Schema setup creates the series before concurrent customer requests. It advances past preserved IDs without lowering the existing counter. Gaps are valid.

The field uses Int with length 20 to store the full range. The controller adds the database uniqueness constraint after legacy zero values are filled.

## Changes and access

The tenant ID is read-only in Desk. Saving a Team cannot change its tenant ID, including as an operator. Renaming the Team label preserves it.

Existing Team permissions still apply to reads and writes. A tenant ID does not grant authority. Regional callers must resolve authorization through Central IAM.

## Migration

Pause Team creation and resource mutations during the migration. Run the registered `backfill_team_tenant_ids` patch after model sync.

The patch checks preserved IDs for range and duplicates before assigning missing IDs. It retains Team names, memberships, and billing references.

If an unassigned Team owns a non-terminated Virtual Machine or Site, the patch stops with a readable error. Verify regional ownership and restore the mapping before retrying. Do not infer ownership from a display name.

The patch can run again without changing assigned IDs. It calls the controller schema hook to install the uniqueness constraint after the backfill.

For a fresh installation, schema setup creates the empty series and the uniqueness constraint. No backfill is needed.

## Validation

Run `central.tests.test_team_tenant_id` through Pilot. Tests cover caller input, immutability, database uniqueness, full-range storage, concurrent allocation, counter preservation, and migration checks.

Run the existing IAM tests to check that Team capability rules still apply. No capability or permission bypass is added by tenant allocation.

Run `central.tests.test_team_archive` for status changes, archive checks and impersonation.

## Status

A Team is `Active`, `Suspended` or `Archived`. IAM resolves grants only for an `Active` team, so members of a suspended or archived team lose access at once. Only a System Manager can change the status in Desk. A team member cannot change it by saving the Team. The only exception is `Team.archive`.

## Archive

The owner archives a team from the console (Settings > Team > Archive). A System Manager uses **Archive Team** on the Team form. Both call `central.api.teams.archive_team`, which needs `team:delete`. Central does not delete a team for a customer. It keeps every record for billing and audit.

`central.identity.doctype.team.archive.get_archive_checks` lists what must be true first. `central.api.teams.get_team_archive_checks` returns the same list to the console, with the credit balances that archiving forfeits. The console shows each failed check with a link to the page that fixes it, and warns about the credit.

| Check | Passes when | Console link |
|---|---|---|
| `servers` | Every Virtual Machine of the team is `Terminated`. | Servers |
| `snapshots` | No enabled snapshot Subscription remains. | Snapshots |
| `buckets` | No enabled bucket or service Subscription remains. | Object storage |
| `add_ons` | No other enabled Subscription without a server remains, such as a public address. | Billing |
| `invoices` | No Billable Invoice is `Open` or `Overdue`, and no `Draft` remains from a closed month. | Invoices |
| `final_bill` | The current month's Draft has no charges, or the team has an active Payment Method to collect them. | Billing |

When the checks pass, archiving does these steps in order:

1. It stops the team's AI keys at Grove. Each live key gets a cap of 0, so it spends nothing. Keys past their `revocable_at` time are revoked. A Grove failure stops the archive, and the team stays Active.
2. It revokes pending invitations.
3. It sets the status to `Archived` and adds a comment that names the user.
4. It sends the `team_archived` email to the owner.

The month-end run collects the current month's Draft with the card on file. To restore a team, a System Manager uses **Restore Team** on the Team form (`central.api.teams.restore_team`). Restoring does not bring back revoked AI keys. The Team list shows Active in green, Suspended in orange and Archived in gray.

## Impersonation

A System Manager uses **Impersonate Team Owner** on the Team form to see the console as the customer sees it. The operator must enter a reason. `central.api.teams.impersonate_team_owner` adds a comment on the team with the operator and the reason, and returns `/dashboard/servers?view_as=<team>`. It sends no email by default. When the operator selects **Email the owner**, it sends the `team_impersonated` notification email to the owner, and the comment records it. The email does not include the reason. The console keeps `view_as` for the browser tab only, passes it to `my_teams`, and shows a banner with an **Exit** button. `my_teams` adds the team only for a System Manager. The operator acts with the operator bypass, so every action of the owner is available and changes apply to the team.
