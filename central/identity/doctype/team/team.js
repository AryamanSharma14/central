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
		}
	},
});

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
