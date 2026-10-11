<script setup lang="ts">
import { Alert, Checkbox, Dialog, FormControl } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import {
	ANYWHERE_IPV4,
	ANYWHERE_IPV6,
	type FirewallRule,
	getService,
	isSameRule,
	SERVICES,
	toCidr,
} from '@/lib/firewall'

interface Props {
	/** 'inbound' rules allow traffic from a source, 'outbound' rules to a destination. */
	direction: 'inbound' | 'outbound'
	/** The rule to edit, or null to add one. */
	rule: FirewallRule | null
	/** The other rules in the same list, so a duplicate is refused before saving. */
	rules: FirewallRule[]
}

const props = defineProps<Props>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ save: [rule: FirewallRule] }>()

const serviceLabel = ref('SSH')
const ports = ref('')
const anywhereIpv4 = ref(true)
const anywhereIpv6 = ref(true)
const otherRanges = ref('')

watch(open, (isOpen) => {
	if (!isOpen) return

	const rule = props.rule
	serviceLabel.value = rule ? getService(rule).label : getUnusedService()
	ports.value = rule?.ports ?? ''
	anywhereIpv4.value = rule ? rule.cidrs.includes(ANYWHERE_IPV4) : true
	anywhereIpv6.value = rule ? rule.cidrs.includes(ANYWHERE_IPV6) : true
	otherRanges.value = (rule?.cidrs ?? [])
		.filter((cidr) => cidr !== ANYWHERE_IPV4 && cidr !== ANYWHERE_IPV6)
		.join(', ')
})

// A new rule starts on a web service the list lacks, never on a database open to anyone.
function getUnusedService(): string {
	const defaults =
		props.direction === 'inbound' ? ['SSH', 'HTTP', 'HTTPS'] : ['All traffic']
	const allowed = props.rules.map((rule) => getService(rule).label)
	return defaults.find((label) => !allowed.includes(label)) ?? 'Custom TCP'
}

const service = computed(
	() =>
		SERVICES.find((item) => item.label === serviceLabel.value) ?? SERVICES[0],
)
const isCustom = computed(() => service.value.ports === null)
const target = computed(() => (props.direction === 'inbound' ? 'from' : 'to'))

const draft = computed<FirewallRule>(() => ({
	protocol: service.value.protocol,
	ports: isCustom.value ? ports.value.trim() : (service.value.ports ?? ''),
	cidrs: [
		...(anywhereIpv4.value ? [ANYWHERE_IPV4] : []),
		...(anywhereIpv6.value ? [ANYWHERE_IPV6] : []),
		...otherRanges.value
			.split(/[\s,]+/)
			.map(toCidr)
			.filter(Boolean),
	],
}))

const portError = computed(() => {
	if (!isCustom.value || !ports.value.trim()) return ''
	const match = /^([1-9]\d*)(?:-([1-9]\d*))?$/.exec(ports.value.trim())
	if (!match)
		return 'Enter one port, such as 8000, or one range, such as 8000-8100.'
	const [start, end] = [Number(match[1]), Number(match[2] ?? match[1])]
	return start <= end && end <= 65535
		? ''
		: 'Ports go from 1 to 65535, with the smaller number first.'
})

// Checked only while open: an added rule is in `rules` while the dialog fades out.
const isDuplicate = computed(
	() =>
		open.value &&
		props.rules.some(
			(rule) => rule !== props.rule && isSameRule(rule, draft.value),
		),
)

const canSave = computed(
	() =>
		draft.value.cidrs.length > 0 &&
		!portError.value &&
		!isDuplicate.value &&
		(!isCustom.value || !!ports.value.trim()),
)

function save(): void {
	if (!canSave.value) return

	emit('save', draft.value)
	open.value = false
}
</script>

<template>
	<Dialog
		v-model="open"
		:title="rule ? 'Edit rule' : 'Add rule'"
		:actions="[
			{
				label: rule ? 'Save' : 'Add rule',
				variant: 'solid',
				disabled: !canSave,
				onClick: save,
			},
		]"
	>
		<template #default>
			<div class="space-y-4">
				<Alert
					v-if="isDuplicate"
					theme="red"
					title="This rule already exists."
				/>

				<FormControl
					v-model="serviceLabel"
					type="select"
					label="Service"
					:options="SERVICES.map((item) => ({ label: item.label, value: item.label }))"
				/>

				<FormControl
					v-if="isCustom"
					v-model="ports"
					label="Port"
					placeholder="8000 or 8000-8100"
					:error="portError"
				/>

				<div class="flex flex-col gap-2">
					<p class="text-xs text-ink-gray-5">Allow {{ target }}</p>
					<Checkbox v-model="anywhereIpv4" label="Anywhere (IPv4)" />
					<Checkbox v-model="anywhereIpv6" label="Anywhere (IPv6)" />
				</div>

				<FormControl
					v-model="otherRanges"
					label="Other addresses"
					placeholder="198.51.100.7, 203.0.113.0/24"
					description="Separate addresses with commas. A range uses CIDR notation."
				/>
			</div>
		</template>
	</Dialog>
</template>
