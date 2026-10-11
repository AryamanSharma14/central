<script setup lang="ts">
import { Button, Combobox, FormControl, MultiSelect, Select } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import {
	ANYWHERE_IPV4,
	ANYWHERE_IPV6,
	type FirewallRule,
	getAddressLabel,
	getCidrError,
	getPortLabel,
	getService,
	isValidPortRange,
	SERVICES,
	toCidr,
} from '@/lib/firewall'

interface Props {
	rule: FirewallRule
	index: number
	incoming: boolean
	removed: boolean
	disabled: boolean
	options: string[]
}
const props = defineProps<Props>()
const emit = defineEmits<{
	update: [rule: FirewallRule]
	remove: []
	undo: []
	invalid: [invalid: boolean]
}>()
const adding = ref(false)
const address = ref('')
const addressError = ref('')
const portTouched = ref(false)
watch(
	[address, adding, () => props.rule.cidrs.length],
	() =>
		emit(
			'invalid',
			(adding.value || !props.rule.cidrs.length) && !!address.value.trim(),
		),
	{ flush: 'sync' },
)
const selectedService = ref(getService(props.rule).label)
const service = computed(
	() => SERVICES.find((item) => item.label === selectedService.value)!,
)
const anyone = computed(
	() =>
		props.rule.cidrs.includes(ANYWHERE_IPV4) &&
		props.rule.cidrs.includes(ANYWHERE_IPV6),
)
const portError = computed(() =>
	isValidPortRange(props.rule.ports)
		? ''
		: 'Use a port from 1 to 65535, or a range such as 8000-8100.',
)
const serviceOptions = SERVICES.map((item) => ({
	label: item.label,
	value: item.label,
}))
const addressOptions = computed(() =>
	[...new Set([...props.options, ...props.rule.cidrs])].map((value) => ({
		label: getAddressLabel(value),
		value,
	})),
)
function changeService(label: string): void {
	cancelAddress()
	const next = SERVICES.find((item) => item.label === label)!
	selectedService.value = label
	portTouched.value = false
	emit('update', {
		...props.rule,
		protocol: next.protocol,
		ports: next.ports ?? '',
		cidrs:
			[
				'SSH',
				'MariaDB',
				'PostgreSQL',
				'Redis',
				'Custom TCP',
				'Custom UDP',
			].includes(label) && anyone.value
				? []
				: props.rule.cidrs,
	})
}
function changeAccess(value: string): void {
	emit('update', {
		...props.rule,
		cidrs: value === 'anyone' ? [ANYWHERE_IPV4, ANYWHERE_IPV6] : [],
	})
	adding.value = value !== 'anyone'
	address.value = ''
	addressError.value = ''
	emit('invalid', false)
}
function addAddress(): void {
	addressError.value = getCidrError(address.value)
	const cidr = toCidr(address.value)
	if ([ANYWHERE_IPV4, ANYWHERE_IPV6].includes(cidr))
		addressError.value = 'Choose Anyone on the internet to allow all addresses.'
	if (addressError.value) return
	emit('update', {
		...props.rule,
		cidrs: [...new Set([...props.rule.cidrs, cidr])],
	})
	address.value = ''
	adding.value = false
	emit('invalid', false)
}
function cancelAddress(): void {
	adding.value = false
	address.value = ''
	addressError.value = ''
	emit('invalid', false)
}
</script>
<template>
	<div class="space-y-3 py-2">
		<div v-if="removed" class="rule-fields grid grid-cols-1 items-start gap-3">
			<div class="space-y-2">
				<p class="text-sm-medium text-ink-gray-7">{{ service.label }}</p>
				<p class="text-p-sm text-ink-gray-5">Removed on apply</p>
			</div>
			<p class="text-p-sm text-ink-gray-6">{{ getPortLabel(rule) }}</p>
			<div class="space-y-2">
				<p class="text-p-sm text-ink-gray-6">
					{{ anyone ? 'Anyone on the internet' : rule.cidrs.map(getAddressLabel).join(', ') }}
				</p>
				<p class="text-p-sm text-ink-gray-5">
					Nothing changes until you apply.
				</p>
			</div>
			<Button
				variant="ghost"
				:aria-label="`Keep ${service.label} rule`"
				:disabled="disabled"
				@click="emit('undo')"
				>Keep rule</Button
			>
		</div>
		<div v-else class="rule-fields grid grid-cols-1 items-start gap-3">
			<Combobox
				:model-value="service.label"
				:options="serviceOptions"
				:aria-label="`Service, rule ${index + 1}`"
				:disabled="disabled"
				size="md"
				class="w-full"
				@update:model-value="changeService"
			/>
			<FormControl
				:model-value="rule.ports"
				:aria-label="`Port, rule ${index + 1}`"
				:disabled="disabled || service.ports !== null"
				:error="portTouched ? portError : ''"
				@focus="portTouched = false"
				@blur="portTouched = true"
				:placeholder="service.ports === null ? 'All ports' : rule.protocol === 'icmp' ? 'Not needed' : 'All'"
				size="md"
				class="w-full"
				@update:model-value="(ports: string) => emit('update', { ...rule, ports })"
			/>
			<div class="min-w-0 space-y-3">
				<Select
					:model-value="anyone ? 'anyone' : 'specific'"
					class="w-full"
					:aria-label="incoming ? 'Allowed from' : 'Allowed to'"
					:options="[{ label: 'Anyone on the internet', value: 'anyone' }, { label: 'Specific addresses', value: 'specific' }]"
					:disabled="disabled"
					size="md"
					@update:model-value="changeAccess"
				/>
				<MultiSelect
					v-if="!anyone && rule.cidrs.length > 0"
					:model-value="rule.cidrs"
					:options="addressOptions"
					label="Allowed addresses"
					placeholder="Choose saved addresses"
					size="md"
					:disabled="disabled"
					empty-text="No matching saved addresses"
					class="w-full"
					@update:model-value="(cidrs: string[]) => emit('update', { ...rule, cidrs })"
				>
					<template #footer="{ clear, selectedOptions, setOpen }">
						<div
							class="flex justify-between gap-2 border-t border-outline-gray-1 px-2 py-1.5"
						>
							<Button
								v-if="selectedOptions.length"
								variant="ghost"
								size="sm"
								label="Clear all"
								@click="clear"
							/>
							<Button
								variant="ghost"
								size="sm"
								label="Add IP address"
								icon-left="lucide-plus"
								class="ml-auto"
								@click="setOpen(false); adding = true"
							/>
						</div>
					</template>
				</MultiSelect>
				<div v-if="!anyone && (adding || !rule.cidrs.length)" class="space-y-2">
					<FormControl
						v-model="address"
						label="IP address or range"
						:aria-label="`New IP address or range, rule ${index + 1}`"
						placeholder="203.0.113.7 or 203.0.113.0/24"
						:error="addressError"
						:disabled="disabled"
						size="md"
						@keydown.enter.prevent="addAddress"
					/>
					<p class="text-p-sm text-ink-gray-5">
						Only these addresses can
						{{ incoming ? 'connect to this service' : 'receive connections' }}.
					</p>
					<div class="flex gap-2">
						<Button
							label="Add IP address"
							:disabled="disabled || !address.trim()"
							@click="addAddress"
						/><Button
							v-if="rule.cidrs.length"
							variant="ghost"
							label="Cancel"
							:disabled="disabled"
							@click="cancelAddress"
						/>
					</div>
				</div>
				<p
					v-if="anyone && incoming && ['MariaDB', 'PostgreSQL', 'Redis', 'All traffic'].includes(service.label)"
					class="text-p-sm text-ink-amber-7"
				>
					This exposes {{ service.label }} to the public internet.
				</p>
			</div>
			<Button
				variant="ghost"
				icon="lucide-trash-2"
				size="md"
				:aria-label="`Remove ${service.label} rule`"
				:disabled="disabled"
				class="size-8 justify-self-start"
				@click="cancelAddress(); emit('remove')"
			/>
		</div>
	</div>
</template>

<style scoped>
@media (min-width: 560px) {
	.rule-fields {
		grid-template-columns: 148px 96px minmax(0, 1fr) 72px;
	}
}
</style>
