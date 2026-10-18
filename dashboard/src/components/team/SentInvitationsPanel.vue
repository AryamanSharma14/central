<script setup lang="ts">
import { Badge, Button } from 'frappe-ui'
import { computed, ref } from 'vue'
import {
	createListViewQuery,
	ListView,
	type ListViewColumn,
	type ListViewFilter,
} from '@/components/common/list-view'
import InvitationRowActions from '@/components/team/InvitationRowActions.vue'
import InviteMemberDialog from '@/components/team/InviteMemberDialog.vue'
import { useCapabilities } from '@/composables/useCapabilities'
import { useTeamInvitations } from '@/composables/useTeamInvitations'
import { useTeamRoles } from '@/composables/useTeamRoles'
import { formatDate } from '@/lib/format'
import { invitationStatusTheme } from '@/lib/status'
import type { InvitationRow } from '@/types/api'

const { invitations, loading, error, busy, reload, resend, revoke } =
	useTeamInvitations()
const { canManageMembers } = useCapabilities()
const { roleLabel } = useTeamRoles()

const query = ref(
	createListViewQuery({
		pageSize: 20,
		sort: { key: 'creation', direction: 'desc' },
	}),
)
const inviteOpen = ref(false)

const filters: ListViewFilter[] = [
	{
		key: 'status',
		label: 'Status',
		options: ['Pending', 'Accepted', 'Expired', 'Revoked', 'Declined'].map(
			(v) => ({ label: v, value: v }),
		),
	},
]

const columns = computed<ListViewColumn<InvitationRow>[]>(() => [
	{ key: 'email', label: 'Email', sortable: true },
	{
		key: 'role',
		label: 'Role',
		value: (invitation) => roleLabel(invitation.role),
		sortable: true,
	},
	{ key: 'status', label: 'Status' },
	{
		key: 'expires',
		label: 'Expires',
		value: (invitation) => formatDate(invitation.expires_on) || '-',
		sortable: true,
	},
	{ key: 'actions', label: '', width: '2.5rem', align: 'end' },
])

function getInvitationKey(invitation: InvitationRow): string {
	return invitation.name
}
</script>

<template>
	<ListView
		class="min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6"
		v-model:query="query"
		:rows="invitations"
		:columns="columns"
		:row-key="getInvitationKey"
		:loading="loading"
		:error="error"
		:filters="filters"
		searchable
		search-placeholder="Search invitations..."
		item-label="invitation"
		:empty-state="{ title: 'No invitations', description: 'Invitations you send to this team will appear here.' }"
		@retry="reload"
	>
		<template v-if="canManageMembers" #toolbar>
			<Button
				variant="solid"
				label="Invite"
				icon-left="lucide-user-plus"
				@click="inviteOpen = true"
			/>
		</template>

		<template #email="{ row }">
			<span class="truncate text-sm-medium">{{ row.email }}</span>
		</template>

		<template #status="{ row }">
			<Badge :theme="invitationStatusTheme(row.status)" :label="row.status" />
		</template>

		<template #actions="{ row }">
			<InvitationRowActions
				:invitation="row"
				:can-manage="canManageMembers"
				:busy="busy === row.name"
				@resend="resend"
				@revoke="revoke"
			/>
		</template>
	</ListView>

	<InviteMemberDialog v-model:open="inviteOpen" @invited="reload" />
</template>
