<script setup lang="ts">
import { Button } from 'frappe-ui'
import EmptyState from '@/components/common/EmptyState.vue'
import { useSession } from '@/composables/useSession'

const { activeTeamLabel } = useSession()
</script>

<template>
	<div class="p-6">
		<EmptyState
			icon="lucide-circle-pause"
			:title="`${activeTeamLabel} is suspended`"
			description="Frappe Cloud support suspended this team, so its members cannot open it. Its data is kept. Switch to another team, or contact support to find out why."
		>
			<template #action>
				<Button
					label="Contact support"
					href="https://support.frappe.io"
					icon-right="lucide-external-link"
				/>
			</template>
		</EmptyState>
	</div>
</template>
