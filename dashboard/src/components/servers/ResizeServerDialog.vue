<script setup lang="ts">
import {
	Alert,
	Button,
	Dialog,
	LoadingIndicator,
	Radio,
	RadioGroup,
	Skeleton,
	Tabs,
} from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed, toRef } from 'vue'
import PlanGroup from '@/components/servers/PlanGroup.vue'
import { useResizeServer } from '@/composables/useResizeServer'
import type { VirtualMachineRow } from '@/composables/useServers'
import { configSpecs } from '@/lib/composed'
import { money } from '@/lib/format'
import { formatGb } from '@/lib/units'

interface Props {
	server: VirtualMachineRow | null
}

const props = defineProps<Props>()
const model = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ resized: [] }>()

const {
	configCall,
	resizeCall,
	plansLoading,
	resizable,
	nothingToShow,
	resizeError,
	losesLockedRate,
	lock,
	hasTabs,
	activeTab,
	classTabs,
	currentDisk,
	currentPlanKey,
	groups,
	designableProfile,
	rateCard,
	available,
	currency,
	capacity,
	initialFor,
	selectedPlan,
	composedConfig,
	flatPresets,
	flatProfile,
	computeOnly,
	currentPrice,
	totalPrice,
	totalShape,
	selectionError,
	canConfirm,
	optionsError,
	reloadOptions,
	downtimeNote,
	changed,
	confirm,
} = useResizeServer(toRef(props, 'server'), model, {
	close: () => (model.value = false),
	resized: () => emit('resized'),
})

const open = computed({
	get: () => model.value,
	set: (value: boolean) => {
		if (!value && !resizeCall.loading) model.value = false
	},
})
</script>

<template>
	<Dialog v-model="open" title="Resize server" size="3xl">
		<template #default>
			<DialogDescription class="sr-only"
				>Choose CPU, memory and storage. Your files are kept.</DialogDescription
			>
			<!-- Keep the dialog stable while Central accepts the resize request. -->
			<div
				v-if="resizeCall.loading"
				class="flex flex-col items-center gap-3 py-10 text-center"
			>
				<LoadingIndicator class="h-6 w-6 text-ink-gray-5" />
				<p class="text-p-base font-medium text-ink-gray-8">Starting resize…</p>
				<p class="max-w-xs text-p-sm text-ink-gray-5">
					The reshape runs in the background. The server shows “Resizing” in the
					list and comes back on its own when it’s done.
				</p>
			</div>
			<div
				v-else-if="configCall.loading || plansLoading"
				class="space-y-4"
				aria-busy="true"
				aria-label="Loading resize options"
			>
				<div class="space-y-2">
					<Skeleton class="h-4 w-full rounded-4" />
					<Skeleton class="h-4 w-2/3 rounded-4" />
				</div>
				<div class="grid gap-3 sm:grid-cols-2">
					<Skeleton v-for="index in 2" :key="index" class="h-16 rounded-6" />
				</div>
				<div class="grid gap-3 sm:grid-cols-3">
					<Skeleton v-for="index in 6" :key="index" class="h-24 rounded-6" />
				</div>
			</div>
			<div v-else-if="optionsError" class="space-y-3">
				<Alert
					theme="red"
					title="Couldn't load resize options"
					:description="optionsError"
				/>
				<Button label="Retry" @click="reloadOptions" />
			</div>
			<p
				v-else-if="!resizable || nothingToShow"
				class="text-p-sm text-ink-gray-5"
			>
				This server can't be resized right now.
			</p>
			<div v-else class="space-y-4">
				<Alert v-if="resizeError" theme="red" :title="resizeError" />
				<Alert
					v-if="losesLockedRate && lock"
					theme="amber"
					title="Resizing will change your rate"
					:description="`You pay ${money(lock.locked_rate, lock.currency)}/mo for this size; it now lists at ${money(lock.list_rate, lock.currency)}/mo. Any resize is priced at today's rates, and the old rate doesn't come back, including if you resize to this size again later.`"
				/>

				<div class="space-y-2 text-p-sm text-ink-gray-7">
					<p>
						You can change CPU and memory only, or grow the disk too. Choosing a
						smaller CPU and memory size does not shrink your disk.
					</p>
					<p>
						Changing CPU or memory restarts the server and may take a few
						minutes. Increasing storage alone does not need a restart. Your
						files are kept.
					</p>
				</div>
				<RadioGroup v-model="computeOnly" label="Storage" padded>
					<Radio
						:value="true"
						:label="`Keep my ${formatGb(currentDisk)} GB disk`"
						description="Change CPU and memory. You can choose a smaller compute size."
					/>
					<Radio
						:value="false"
						label="Increase storage too"
						description="Use the selected plan's storage, or choose a custom size. Storage cannot shrink."
					/>
				</RadioGroup>
				<p class="text-p-sm text-ink-gray-6">
					Prices include all storage you keep. Increasing storage is permanent.
				</p>

				<Tabs v-if="hasTabs" v-model="activeTab" :tabs="classTabs">
					<template #tab-panel="{ tab }">
						<PlanGroup
							class="pt-4"
							:omit-disk="computeOnly"
							:min-disk="computeOnly ? undefined : currentDisk"
							:current-disk="currentDisk"
							:current-plan="currentPlanKey"
							:presets="groups[tab.value] ?? []"
							:profile="designableProfile(String(tab.value))"
							:rate-card="rateCard"
							:available="available ?? 0"
							:currency="currency ?? 'USD'"
							:capacity="capacity"
							:initial="initialFor(designableProfile(String(tab.value)))"
							v-model:selected-plan="selectedPlan"
							v-model:composed-config="composedConfig"
						/>
					</template>
				</Tabs>
				<PlanGroup
					v-else
					:omit-disk="computeOnly"
					:min-disk="computeOnly ? undefined : currentDisk"
					:current-disk="currentDisk"
					:current-plan="currentPlanKey"
					:presets="flatPresets"
					:profile="flatProfile"
					:rate-card="rateCard"
					:available="available ?? 0"
					:currency="currency ?? 'USD'"
					:capacity="capacity"
					:initial="initialFor(flatProfile)"
					v-model:selected-plan="selectedPlan"
					v-model:composed-config="composedConfig"
				/>
				<Alert v-if="selectionError" theme="red" :title="selectionError" />
				<div
					v-if="totalShape && changed"
					class="space-y-2 border-t border-outline-gray-2 pt-4"
					aria-live="polite"
				>
					<p class="text-sm-medium text-ink-gray-9">After resizing</p>
					<p class="text-p-sm text-ink-gray-7">{{ configSpecs(totalShape) }}</p>
					<p class="text-p-sm text-ink-gray-6">
						{{ downtimeNote }}
						Your files are kept.
					</p>
				</div>
			</div>
		</template>
		<template #actions>
			<div
				v-if="resizable && !resizeCall.loading"
				class="flex items-center justify-end gap-4"
			>
				<p v-if="totalPrice" class="text-p-sm text-ink-gray-6">
					{{ currentPrice }}
					<span
						class="lucide-arrow-right mx-1 inline-block size-3.5 align-[-2px]"
						aria-label="to"
					/>
					<span class="font-medium text-ink-gray-9">{{ totalPrice }}</span>
				</p>
				<Button
					variant="solid"
					label="Resize"
					:disabled="!canConfirm"
					@click="confirm"
				/>
			</div>
		</template>
	</Dialog>
</template>
