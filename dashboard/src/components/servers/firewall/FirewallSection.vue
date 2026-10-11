<script setup lang="ts">
import { Button, Dropdown, Switch } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import SettingsSection from '@/components/common/SettingsSection.vue'
import CopyFirewallDialog from '@/components/servers/firewall/CopyFirewallDialog.vue'
import FirewallRuleRow from '@/components/servers/firewall/FirewallRuleRow.vue'
import { useServerFirewall } from '@/composables/useServerFirewall'
import type { VirtualMachineRow } from '@/composables/useServers'
import { reportError, successToast } from '@/lib/feedback'
import {
	type Firewall,
	type FirewallChange,
	type FirewallRules,
	getFirewallTexts,
	getRulesError,
	getService,
	isSameRule,
	isSameRules,
	PRESETS,
	SERVICES,
} from '@/lib/firewall'

type Direction = keyof FirewallRules

interface Props {
	resourceId: string
	isEnabled: boolean
	/** Null until Central first reads the firewall from the region. */
	rules: FirewallRules | null
	canEdit: boolean
	/** The other servers of the team, for Copy to other servers. */
	servers: VirtualMachineRow[]
}

interface FirewallAction {
	change: FirewallChange
	title: string
	confirmLabel: string
	success: string
	warnings: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{ changed: [] }>()

// structuredClone refuses Vue's reactive objects, and the rules are plain JSON.
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))

const saved = computed<Firewall | null>(() =>
	props.rules ? { enabled: props.isEnabled, ...props.rules } : null,
)

// Rule edits collect here until Apply, so a swap such as "SSH from the office instead of
// anywhere" never applies half done.
const draft = ref<FirewallRules | null>(null)
const baseline = ref<FirewallRules | null>(null)
const removedIndices = ref<Record<Direction, number[]>>({
	inbound: [],
	outbound: [],
})
const effectiveDraft = computed<FirewallRules | null>(
	() =>
		draft.value && {
			inbound: draft.value.inbound.filter(
				(_, index) => !removedIndices.value.inbound.includes(index),
			),
			outbound: draft.value.outbound.filter(
				(_, index) => !removedIndices.value.outbound.includes(index),
			),
		},
)
const hasUnsavedRules = computed(
	() => JSON.stringify(effectiveDraft.value) !== JSON.stringify(baseline.value),
)
const pendingChanges = computed(() => {
	if (!baseline.value || !effectiveDraft.value) return 0
	return (['inbound', 'outbound'] as const).reduce((count, direction) => {
		const before = baseline.value![direction]
		const after = effectiveDraft.value![direction]
		const removed = before.filter(
			(rule) => !after.some((other) => isSameRule(rule, other)),
		).length
		const added = after.filter(
			(rule) => !before.some((other) => isSameRule(rule, other)),
		).length
		return count + Math.max(removed, added)
	}, 0)
})

const incomplete = ref<Record<string, boolean>>({})
const revision = ref(0)

function resetDraft(rules: FirewallRules | null): void {
	baseline.value = rules && clone(rules)
	draft.value = rules && clone(rules)
	removedIndices.value = { inbound: [], outbound: [] }
	incomplete.value = {}
	revision.value++
}

watch(
	[() => props.resourceId, () => props.rules],
	([resourceId, rules], previous) => {
		if (
			resourceId !== previous?.[0] ||
			(!hasUnsavedRules.value && !Object.values(incomplete.value).some(Boolean))
		)
			resetDraft(rules)
	},
	{ immediate: true },
)

function removeRule(direction: Direction, index: number): void {
	if (isSaving.value) return
	removedIndices.value[direction].push(index)
	incomplete.value[`${direction}:${index}`] = false
}

function undoRemoval(direction: Direction, index: number): void {
	removedIndices.value[direction] = removedIndices.value[direction].filter(
		(removed) => removed !== index,
	)
}

function usePreset(rules: FirewallRules): void {
	presetPreview.value = null
	draft.value = clone(rules)
	removedIndices.value = { inbound: [], outbound: [] }
	incomplete.value = {}
	revision.value++
}

const directions: Direction[] = ['inbound', 'outbound']
const staleDraft = computed(
	() =>
		!!baseline.value &&
		(!props.rules || !isSameRules(baseline.value, props.rules)),
)
const conflictMessage =
	'The saved firewall rules changed while you were editing. Reset all pending changes to load the latest rules before applying.'
const validation = computed(() => {
	if (staleDraft.value) return conflictMessage
	if (Object.values(incomplete.value).some(Boolean))
		return 'Add or cancel the address you are typing.'
	if (!effectiveDraft.value) return ''
	return (
		getRulesError(effectiveDraft.value.inbound) ||
		getRulesError(effectiveDraft.value.outbound)
	)
})
function addRule(direction: Direction): void {
	if (!draft.value) return
	const used =
		effectiveDraft.value?.[direction].map((rule) => getService(rule).label) ??
		[]
	const service =
		SERVICES.find(
			(item) =>
				(direction === 'inbound'
					? ['HTTPS', 'HTTP', 'SSH']
					: ['All traffic']
				).includes(item.label) && !used.includes(item.label),
		) ?? SERVICES.find((item) => item.label === 'Custom TCP')!
	draft.value[direction].push({
		protocol: service.protocol,
		ports: service.ports ?? '',
		cidrs: ['SSH', 'Custom TCP', 'Custom UDP'].includes(service.label)
			? []
			: ['0.0.0.0/0', '::/0'],
	})
}

const { updateFirewall, isSaving } = useServerFirewall()
const riskyAction = ref<FirewallAction | null>(null)
const sendError = ref('')

// A change that cuts access asks first. A safe one applies at once.
function confirmIfRisky(action: FirewallAction): void {
	if (action.warnings.length) {
		sendError.value = ''
		riskyAction.value = action
	} else sendChange(action)
}

function toggleFirewall(enabled: boolean): void {
	if (!saved.value) return

	const change =
		enabled && !saved.value.inbound.length && !saved.value.outbound.length
			? { enabled, ...clone(PRESETS[0].rules) }
			: { enabled }
	confirmIfRisky({
		change,
		title: enabled ? 'Turn the firewall on' : 'Turn the firewall off',
		confirmLabel: enabled ? 'Turn on' : 'Turn off',
		success: enabled ? 'Firewall is on' : 'Firewall is off',
		warnings: getFirewallTexts(saved.value, { ...saved.value, ...change }),
	})
}

function saveDraftRules(): void {
	if (
		!saved.value ||
		!effectiveDraft.value ||
		!hasUnsavedRules.value ||
		validation.value
	)
		return

	confirmIfRisky({
		change: clone(effectiveDraft.value),
		title: 'Apply firewall changes',
		confirmLabel: 'Apply changes',
		success: 'Firewall rules saved',
		warnings: getFirewallTexts(saved.value, {
			...saved.value,
			...effectiveDraft.value,
		}),
	})
}

async function sendChange(action: FirewallAction): Promise<void> {
	if (action.change.inbound && staleDraft.value) {
		sendError.value = conflictMessage
		return
	}
	const error = (await updateFirewall([props.resourceId], action.change))[
		props.resourceId
	]
	if (error && riskyAction.value) {
		sendError.value = error
		return
	}
	if (error) {
		reportError(error, { title: "The firewall wasn't changed" })
		return
	}

	riskyAction.value = null
	if (action.change.inbound && action.change.outbound)
		resetDraft({
			inbound: action.change.inbound,
			outbound: action.change.outbound,
		})
	successToast(action.success)
	emit('changed')
}

const isCopying = ref(false)

const presetPreview = ref<(typeof PRESETS)[number] | null>(null)
const resetPreview = ref<boolean | null>(null)
const menuOptions = computed(() => [
	...(hasUnsavedRules.value
		? [
				{
					label: 'Reset all pending changes',
					icon: 'lucide-rotate-ccw',
					onClick: () => (resetPreview.value = true),
				},
			]
		: []),
	{
		label: 'Use a preset',
		disabled: !props.isEnabled,
		icon: 'lucide-list-checks',
		submenu: PRESETS.map((preset) => ({
			label: preset.label,
			onClick: () => (presetPreview.value = preset),
		})),
	},
	...(props.servers.length
		? [
				{
					label: 'Copy to other servers',
					icon: 'lucide-copy',
					onClick: () => (isCopying.value = true),
				},
			]
		: []),
])
</script>

<template>
	<SettingsSection
		title="Firewall"
		help="The region filters traffic before it reaches the server."
		description="Choose who can connect and which connections the server can open. Your private network, VPN devices and ping stay allowed, so the web console keeps working."
	>
		<template #actions>
			<div class="flex items-center gap-3">
				<Switch
					v-if="draft"
					:model-value="isEnabled"
					:disabled="!canEdit || hasUnsavedRules || isSaving"
					@update:model-value="toggleFirewall"
				>
					<template #label><span class="sr-only">Firewall</span></template>
				</Switch>
				<Dropdown
					v-if="canEdit && draft && !isSaving"
					:options="menuOptions"
					align="end"
				>
					<Button
						variant="ghost"
						icon="lucide-ellipsis"
						label="Firewall options"
					/>
				</Dropdown>
			</div>
		</template>

		<p v-if="!draft" class="text-p-sm text-ink-gray-5">
			The firewall appears after Central next reads this server from its region,
			within 10 minutes.
		</p>

		<template v-else>
			<template v-if="isEnabled">
				<div v-for="direction in directions" :key="direction" class="space-y-1">
					<div class="flex items-center justify-between gap-3">
						<h3 class="text-sm-medium text-ink-gray-7">
							{{ direction === 'inbound' ? 'Incoming' : 'Outgoing' }}
						</h3>
						<Button
							v-if="canEdit"
							size="sm"
							icon-left="lucide-plus"
							label="Add rule"
							:disabled="isSaving"
							@click="addRule(direction)"
						/>
					</div>
					<div
						v-if="draft[direction].length"
						class="rule-headers gap-3 pt-2 text-p-sm text-ink-gray-5"
						aria-hidden="true"
					>
						<span>Service</span><span>Port</span
						><span
							>{{ direction === 'inbound' ? 'Allowed from' : 'Allowed to' }}</span
						><span />
					</div>
					<FirewallRuleRow
						v-for="(rule, index) in draft[direction]"
						:key="`${revision}:${index}`"
						:rule="rule"
						:index="index"
						:incoming="direction === 'inbound'"
						:removed="removedIndices[direction].includes(index)"
						:disabled="!canEdit || isSaving"
						:options="effectiveDraft?.[direction].flatMap((item) => item.cidrs).filter((cidr) => !['0.0.0.0/0', '::/0'].includes(cidr)) ?? []"
						@update="draft[direction][index] = $event"
						@remove="removeRule(direction, index)"
						@undo="undoRemoval(direction, index)"
						@invalid="incomplete[`${direction}:${index}`] = $event"
					/>
					<p
						v-if="!effectiveDraft?.[direction].length"
						class="py-2 text-p-sm text-ink-gray-6"
					>
						{{ hasUnsavedRules ? 'After applying, no public' : 'No public' }}
						{{ direction === 'inbound' ? 'incoming' : 'outgoing' }}
						connections
						{{ hasUnsavedRules ? 'will be allowed.' : 'are allowed.' }}
					</p>
				</div>
			</template>
			<p v-else class="text-p-sm text-ink-gray-6">
				{{ draft.inbound.length || draft.outbound.length ? 'Turn on to use your saved rules.' : 'Turn on to allow SSH, HTTP and HTTPS, with all outgoing connections allowed.' }}
				You can edit the rules after enabling.
			</p>

			<p v-if="validation" class="text-p-sm text-ink-gray-5">
				{{ validation }}
			</p>
			<div
				v-if="canEdit && (hasUnsavedRules || removedIndices.inbound.length || removedIndices.outbound.length)"
				class="flex flex-wrap items-center justify-between gap-3 pt-2"
			>
				<p class="text-p-sm text-ink-gray-6" role="status">
					{{ pendingChanges ? `${pendingChanges} ${pendingChanges === 1 ? 'change' : 'changes'} pending` : 'No changes to apply' }}
				</p>
				<div class="flex gap-2">
					<Button
						variant="solid"
						label="Apply changes"
						:disabled="!hasUnsavedRules || !!validation"
						:loading="isSaving && !riskyAction"
						@click="saveDraftRules"
					/>
				</div>
			</div>
		</template>

		<ConfirmDialog
			v-model:target="riskyAction"
			:title="riskyAction?.title ?? ''"
			:confirm-label="riskyAction?.confirmLabel"
			:loading="isSaving"
			:error="sendError"
			@confirm="sendChange"
		>
			<ul class="space-y-2 text-p-sm text-ink-gray-7">
				<li v-for="warning in riskyAction?.warnings" :key="warning">
					{{ warning }}
				</li>
			</ul>
		</ConfirmDialog>

		<ConfirmDialog
			v-model:target="presetPreview"
			:title="`Use ${presetPreview?.label ?? ''} preset?`"
			confirm-label="Use preset"
			@confirm="(preset) => usePreset(preset.rules)"
		>
			<p class="text-p-sm text-ink-gray-7">
				{{ presetPreview?.label === 'Private only' ? 'Block public incoming connections. Allow all outgoing connections.' : presetPreview?.label === 'SSH only' ? 'Allow SSH from the internet and all outgoing connections.' : 'Allow SSH, HTTP and HTTPS from the internet and all outgoing connections.' }}
				This replaces your pending draft. Review it before applying.
			</p>
		</ConfirmDialog>
		<ConfirmDialog
			v-model:target="resetPreview"
			title="Reset all pending changes?"
			confirm-label="Reset changes"
			@confirm="resetDraft(rules); resetPreview = null"
		>
			<p class="text-p-sm text-ink-gray-7">
				Restore all saved rules. This clears every pending edit and removal.
			</p>
		</ConfirmDialog>
		<CopyFirewallDialog
			v-if="saved"
			v-model:open="isCopying"
			:firewall="saved"
			:servers="servers"
		/>
	</SettingsSection>
</template>

<style scoped>
.rule-headers {
	display: none;
}
@media (min-width: 560px) {
	.rule-headers {
		display: grid;
		grid-template-columns: 148px 96px minmax(0, 1fr) 72px;
	}
}
</style>
