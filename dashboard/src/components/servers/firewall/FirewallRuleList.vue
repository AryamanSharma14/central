<script setup lang="ts">
import { Badge, Button } from 'frappe-ui'
import { computed } from 'vue'
import {
	createListViewQuery,
	ListView,
	type ListViewColumn,
} from '@/components/common/list-view'
import RowActionsMenu from '@/components/common/RowActionsMenu.vue'
import {
	type FirewallRule,
	getAddressLabel,
	getPortLabel,
	getService,
} from '@/lib/firewall'

interface Props {
	title: string
	rules: FirewallRule[]
	emptyText: string
	/** Incoming rules name their source; outgoing rules name their destination. */
	addressHeader: string
	canEdit: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
	add: []
	edit: [index: number]
	remove: [index: number]
}>()

const query = createListViewQuery()

const columns = computed<ListViewColumn<FirewallRule>[]>(() => [
	{
		id: 'service',
		header: 'Service',
		accessorFn: (rule) => getService(rule).label,
		size: 120,
		enableSorting: false,
	},
	{
		id: 'port',
		header: 'Port',
		accessorFn: getPortLabel,
		size: 100,
		enableSorting: false,
	},
	{
		id: 'addresses',
		header: props.addressHeader,
		size: 400,
		enableSorting: false,
	},
	...(props.canEdit
		? [
				{
					id: 'actions',
					header: '',
					size: 48,
					enableSorting: false,
					meta: { align: 'end' as const },
				},
			]
		: []),
])

// Each rule appears once in a list, so its fields identify it.
const getRuleKey = (rule: FirewallRule): string =>
	`${rule.protocol}:${rule.ports}:${rule.cidrs.join(',')}`

function getRuleActions(rule: FirewallRule) {
	const index = props.rules.indexOf(rule)
	return [
		{
			label: 'Edit',
			icon: 'lucide-pencil',
			onClick: () => emit('edit', index),
		},
		{
			label: 'Remove',
			icon: 'lucide-trash-2',
			onClick: () => emit('remove', index),
		},
	]
}
</script>

<template>
	<div class="space-y-2">
		<div class="flex items-center justify-between gap-3">
			<h3 class="text-sm-medium text-ink-gray-7">{{ title }}</h3>
			<Button
				v-if="canEdit"
				size="sm"
				icon-left="lucide-plus"
				label="Add rule"
				@click="emit('add')"
			/>
		</div>

		<ListView
			:query="query"
			:rows="rules"
			:columns="columns"
			:row-key="getRuleKey"
			:paginated="false"
			:show-count="false"
			item-label="rule"
			:empty-state="{ title: emptyText }"
		>
			<template #addresses="{ row }">
				<div class="flex min-w-0 flex-wrap gap-1">
					<Badge
						v-for="cidr in row.cidrs"
						:key="cidr"
						:label="getAddressLabel(cidr)"
					/>
				</div>
			</template>

			<template #actions="{ row }">
				<RowActionsMenu
					:options="getRuleActions(row)"
					:label="`Rule options for ${getService(row).label}`"
					icon="lucide-ellipsis"
				/>
			</template>
		</ListView>
	</div>
</template>
