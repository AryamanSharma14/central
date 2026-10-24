frappe.ui.form.on("Team", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Invite Member"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Invite Member"),
				fields: [
					{ fieldname: "email", fieldtype: "Data", label: __("Email"), reqd: 1 },
					{
						fieldname: "role",
						fieldtype: "Link",
						label: __("Team Role"),
						options: "Team Role",
						reqd: 1,
					},
				],
				primary_action_label: __("Invite"),
				primary_action(values) {
					frappe
						.call("central.api.teams.invite_team_member", { team: frm.doc.name, ...values })
						.then(() => {
							dialog.hide();
							frappe.show_alert({
								message: __("Invitation created"),
								indicator: "green",
							});
						});
				},
			});
			dialog.show();
		});

		if (frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Grant Credit"), () => grant_credit(frm));
			frm.add_custom_button(__("Impersonate Team Owner"), () => impersonate_team_owner(frm));
			if (frm.doc.status === "Active") {
				frm.add_custom_button(__("Archive Team"), () => archive_team(frm));
			}
			if (frm.doc.status === "Archived") {
				frm.add_custom_button(__("Restore Team"), () => restore_team(frm));
			}
		}
	},
});

function impersonate_team_owner(frm) {
	frappe.prompt(
		[
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
				description: __("Recorded on the team for staff. The owner does not see it."),
			},
			{
				fieldname: "notify_owner",
				fieldtype: "Check",
				label: __("Email the owner"),
				default: 0,
				description: __("Tell the owner that support opened their team."),
			},
		],
		async ({ reason, notify_owner }) => {
			const response = await frappe.call({
				method: "central.api.teams.impersonate_team_owner",
				args: { team: frm.doc.name, reason, notify_owner },
				freeze: true,
			});
			window.location.assign(response.message.url);
		},
		__("Impersonate Team Owner"),
		__("Open console"),
	);
}

function restore_team(frm) {
	frappe.confirm(
		__("Restore {0}? Its members can open it again. Its AI keys stay revoked.", [frm.doc.team_name]),
		async () => {
			await frappe.call({
				method: "central.api.teams.restore_team",
				args: { team: frm.doc.name },
				freeze: true,
			});
			frappe.show_alert({ message: __("Team restored"), indicator: "green" }, 5);
			frm.reload_doc();
		},
	);
}

function archive_team(frm) {
	frappe.confirm(
		__("Archive {0}? Every member loses access. The records stay.", [frm.doc.team_name]),
		async () => {
			await frappe.call({
				method: "central.api.teams.archive_team",
				args: { team: frm.doc.name },
				freeze: true,
				freeze_message: __("Archiving…"),
			});
			frappe.show_alert({ message: __("Team archived"), indicator: "orange" }, 5);
			frm.reload_doc();
		},
	);
}

function grant_credit(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Grant Credit"),
		fields: [
			{ fieldname: "amount", fieldtype: "Float", label: __("Amount"), reqd: 1,
				description: __("In the team's billing currency.") },
			{ fieldname: "validity_days", fieldtype: "Int", label: __("Validity (Days)"), reqd: 1, default: 60 },
			{ fieldname: "note", fieldtype: "Data", label: __("Note"), reqd: 1, default: __("Beta credit") },
		],
		primary_action_label: __("Grant"),
		primary_action(values) {
			frappe.confirm(
				__("Grant {0} credit to {1}? It replaces the welcome credit.", [values.amount, frm.doc.team_name]),
				() =>
					frappe
						.call("central.signups.credit.grant_credit", { team: frm.doc.name, ...values })
						.then(() => {
							dialog.hide();
							frappe.show_alert({ message: __("Credit granted"), indicator: "green" });
						}),
			);
		},
	});
	dialog.show();
}
