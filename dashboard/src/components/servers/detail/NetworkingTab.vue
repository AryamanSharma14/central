<script setup lang="ts">
import { Badge, Button, Skeleton } from 'frappe-ui'
import { computed } from 'vue'
import CopyableValue from '@/components/common/CopyableValue.vue'
import {
	createListViewQuery,
	ListView,
	type ListViewColumn,
} from '@/components/common/list-view'
import SettingsSection from '@/components/common/SettingsSection.vue'
import FirewallSection from '@/components/servers/firewall/FirewallSection.vue'
import { useServerHostnames } from '@/composables/useServerHostnames'
import type { VirtualMachineRow } from '@/composables/useServers'
import type { ServerOverview } from '@/types/servers'

interface Props {
	server: VirtualMachineRow
	overview: ServerOverview
	/** The viewer holds server:network on this server. */
	canManageNetwork: boolean
	/** The other servers of the team, for copying firewall rules. */
	servers: VirtualMachineRow[]
}

const props = defineProps<Props>()
const emit = defineEmits<{ changed: [] }>()

const { hostnames, loading, error } = useServerHostnames(
	computed(() => props.server),
)

interface Address {
	label: string
	value: string
	reach: string
}

const addresses = computed(() =>
	[
		{
			label: 'Public IPv6',
			value: props.overview.server.public_ipv6,
			reach: 'Anyone on the internet',
		},
		{
			label: 'Public IPv4',
			value: props.overview.server.public_ipv4,
			reach: 'Anyone on the internet',
		},
		{
			label: 'Private IPv6',
			value: props.overview.server.ipv6_address,
			reach: 'Your servers in this region',
		},
	].filter((row): row is Address => !!row.value),
)

const addressQuery = createListViewQuery()
const addressColumns: ListViewColumn<Address>[] = [
	{ accessorKey: 'label', header: 'Type', size: 120, enableSorting: false },
	{ accessorKey: 'value', header: 'Address', size: 260, enableSorting: false },
	{
		accessorKey: 'reach',
		header: 'Reachable by',
		size: 220,
		enableSorting: false,
	},
]
</script>

<template>
	<div class="divide-y divide-outline-gray-1">
		<SettingsSection title="Addresses" help="Click an address to copy it.">
			<ListView
				v-if="addresses.length"
				:query="addressQuery"
				:rows="addresses"
				:columns="addressColumns"
				:row-key="(row) => row.label"
				:paginated="false"
				:show-count="false"
				item-label="address"
			>
				<template #value="{ row }">
					<CopyableValue :value="row.value" :label="`${row.label} address`" />
				</template>
			</ListView>

			<p v-else class="text-p-sm text-ink-gray-5">
				This server has no address yet. It gets one when it finishes setting up.
			</p>
		</SettingsSection>

		<FirewallSection
			:resource-id="overview.server.resource_id"
			:is-enabled="!!overview.server.is_firewall_enabled"
			:rules="overview.server.firewall_rules"
			:can-edit="canManageNetwork"
			:servers="servers"
			@changed="emit('changed')"
		/>

		<SettingsSection
			title="Domains"
			help="Site and custom domains that point to this server."
		>
			<div v-if="loading" class="space-y-2" aria-busy="true">
				<Skeleton class="h-9 rounded-4" />
				<Skeleton class="h-9 w-2/3 rounded-4" />
			</div>

			<p v-else-if="error" class="text-p-sm text-ink-gray-5">{{ error }}</p>

			<p v-else-if="!hostnames.length" class="text-p-sm text-ink-gray-5">
				No site or custom domain points to this server.
			</p>

			<ul v-else class="divide-y divide-outline-gray-1">
				<li
					v-for="entry in hostnames"
					:key="entry.hostname"
					class="flex items-center gap-3 py-2 first:pt-0 last:pb-0"
				>
					<span
						class="lucide-globe size-4 shrink-0 text-ink-gray-5"
						aria-hidden="true"
					/>

					<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
						{{ entry.hostname }}
					</span>

					<Badge :label="entry.kind" />

					<Button
						variant="ghost"
						icon="lucide-arrow-up-right"
						:label="`Open ${entry.hostname}`"
						tooltip="Open"
						:link="`https://${entry.hostname}`"
					/>
				</li>
			</ul>
		</SettingsSection>
	</div>
</template>
