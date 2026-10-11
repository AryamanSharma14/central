<script setup lang="ts">
import { Button, Dropdown, Switch } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import SettingsSection from '@/components/common/SettingsSection.vue'
import CopyFirewallDialog from '@/components/servers/firewall/CopyFirewallDialog.vue'
import FirewallRuleDialog from '@/components/servers/firewall/FirewallRuleDialog.vue'
import FirewallRuleList from '@/components/servers/firewall/FirewallRuleList.vue'
import { useServerFirewall } from '@/composables/useServerFirewall'
import type { VirtualMachineRow } from '@/composables/useServers'
import { reportError, successToast } from '@/lib/feedback'
import {
	type Firewall,
	type FirewallChange,
	type FirewallRule,
	type FirewallRules,
	getFirewallTexts,
	PRESETS,
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

// Rule edits collect here until Save, so a swap such as "SSH from the office instead of
// anywhere" never applies half done.
const draft = ref<FirewallRules | null>(null)
watch(
	() => props.rules,
	(rules) => (draft.value = rules && clone(rules)),
	{ immediate: true },
)
const hasUnsavedRules = computed(
	() => JSON.stringify(draft.value) !== JSON.stringify(props.rules),
)

// The editor keeps its target after it closes, so the dialog does not change while it fades out.
const isEditorOpen = ref(false)
const editing = ref<{ direction: Direction; index: number | null }>({
	direction: 'inbound',
	index: null,
})
const editedRule = computed(() =>
	editing.value.index === null
		? null
		: (draft.value?.[editing.value.direction][editing.value.index] ?? null),
)

function openEditor(direction: Direction, index: number | null): void {
	editing.value = { direction, index }
	isEditorOpen.value = true
}

function saveRuleToDraft(rule: FirewallRule): void {
	if (!draft.value) return

	const rules = draft.value[editing.value.direction]
	if (editing.value.index === null) rules.push(rule)
	else rules.splice(editing.value.index, 1, rule)
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

	confirmIfRisky({
		change: { enabled },
		title: enabled ? 'Turn the firewall on' : 'Turn the firewall off',
		confirmLabel: enabled ? 'Turn on' : 'Turn off',
		success: enabled ? 'Firewall is on' : 'Firewall is off',
		warnings: getFirewallTexts(saved.value, { ...saved.value, enabled }),
	})
}

function saveDraftRules(): void {
	if (!saved.value || !draft.value) return

	confirmIfRisky({
		change: clone(draft.value),
		title: 'Save firewall rules',
		confirmLabel: 'Save rules',
		success: 'Firewall rules saved',
		warnings: getFirewallTexts(saved.value, {
			...saved.value,
			...draft.value,
		}),
	})
}

async function sendChange(action: FirewallAction): Promise<void> {
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
	successToast(action.success)
	emit('changed')
}

const isCopying = ref(false)

const menuOptions = computed(() => [
	{
		label: 'Use a preset',
		icon: 'lucide-list-checks',
		submenu: PRESETS.map((preset) => ({
			label: preset.label,
			onClick: () => (draft.value = clone(preset.rules)),
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
		description="Choose which traffic can reach this server and which traffic it can send."
	>
		<template v-if="canEdit && draft" #actions>
			<Dropdown :options="menuOptions" align="end">
				<Button
					variant="ghost"
					icon="lucide-ellipsis"
					label="Firewall options"
				/>
			</Dropdown>
		</template>

		<p v-if="!draft" class="text-p-sm text-ink-gray-5">
			The firewall appears after Central next reads this server from its region,
			within 10 minutes.
		</p>

		<template v-else>
			<Switch
				:model-value="isEnabled"
				:disabled="!canEdit || hasUnsavedRules || isSaving"
				label="Firewall"
				:description="
					hasUnsavedRules
						? 'Save or discard your rule changes first.'
						: isEnabled
							? 'Only traffic that a rule allows can pass.'
							: 'Every port is open. The rules below apply when you turn it on.'
				"
				class="rounded-6 bg-surface-gray-1 px-4 py-3"
				@update:model-value="toggleFirewall"
			/>

			<div
				v-if="canEdit && !draft.inbound.length && !draft.outbound.length"
				class="flex flex-wrap items-center gap-2"
			>
				<p class="text-p-sm text-ink-gray-6">Start from a preset:</p>
				<Button
					v-for="preset in PRESETS"
					:key="preset.label"
					size="sm"
					:label="preset.label"
					@click="draft = clone(preset.rules)"
				/>
			</div>

			<FirewallRuleList
				title="Incoming"
				address-header="Allowed from"
				:rules="draft.inbound"
				:empty-text="
					isEnabled ? 'No incoming traffic is allowed.' : 'No incoming rules.'
				"
				:can-edit="canEdit"
				@add="openEditor('inbound', null)"
				@edit="(index) => openEditor('inbound', index)"
				@remove="(index) => draft?.inbound.splice(index, 1)"
			/>

			<FirewallRuleList
				title="Outgoing"
				address-header="Allowed to"
				:rules="draft.outbound"
				:empty-text="
					isEnabled
						? 'The server cannot open any connection.'
						: 'No outgoing rules.'
				"
				:can-edit="canEdit"
				@add="openEditor('outbound', null)"
				@edit="(index) => openEditor('outbound', index)"
				@remove="(index) => draft?.outbound.splice(index, 1)"
			/>

			<p class="text-p-sm text-ink-gray-5">
				Your private network, VPN devices and ping are always allowed, so the
				web console keeps working.
			</p>

			<div
				v-if="hasUnsavedRules"
				class="sticky bottom-4 flex items-center justify-between gap-3 rounded-6 border border-outline-gray-2 bg-surface-elevation-2 py-2 pl-4 pr-2 shadow-lg"
			>
				<p class="text-sm text-ink-gray-7">Unsaved rule changes</p>
				<div class="flex gap-2">
					<Button
						label="Discard"
						:disabled="isSaving"
						@click="draft = rules && clone(rules)"
					/>
					<Button
						variant="solid"
						label="Save rules"
						:loading="isSaving && !riskyAction"
						@click="saveDraftRules"
					/>
				</div>
			</div>
		</template>

		<FirewallRuleDialog
			v-model:open="isEditorOpen"
			:direction="editing.direction"
			:rule="editedRule"
			:rules="draft?.[editing.direction] ?? []"
			@save="saveRuleToDraft"
		/>

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

		<CopyFirewallDialog
			v-if="saved"
			v-model:open="isCopying"
			:firewall="saved"
			:servers="servers"
		/>
	</SettingsSection>
</template>
