<script setup lang="ts">
import { Badge, Button, Select, Spinner, Tooltip } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import { type Component, computed, ref, watch } from 'vue'
import { useAI } from '@/composables/useAI'
import { formatDateTime } from '@/lib/datetime'
import { getErrorMessage } from '@/lib/feedback'
import type { AIDialect } from '@/types/ai'
import LucideAudioLines from '~icons/lucide/audio-lines'
import LucideBinary from '~icons/lucide/binary'
import LucideCaptions from '~icons/lucide/captions'
import LucideCircleHelp from '~icons/lucide/circle-help'
import LucideFileText from '~icons/lucide/file-text'
import LucideImage from '~icons/lucide/image'
import LucideType from '~icons/lucide/type'
import LucideVideo from '~icons/lucide/video'

const dialectLabels: Record<AIDialect, string> = {
	openai: 'OpenAI',
	anthropic: 'Anthropic',
}
// Keyed by Grove's Modality names, which it sends lowercased. An unknown one falls
// back to a help icon.
const modalityIcons: Record<string, Component> = {
	text: LucideType,
	image: LucideImage,
	audio: LucideAudioLines,
	video: LucideVideo,
	file: LucideFileText,
	embeddings: LucideBinary,
	transcription: LucideCaptions,
}

function modalityLabel(modality: string): string {
	return modality.charAt(0).toUpperCase() + modality.slice(1)
}

const { ai, aiLoading, models, modelsLoading, modelsError, loadModels } =
	useAI()

const usage = computed(() => ai.value?.usage ?? null)
const spend = computed(() => ai.value?.spend ?? null)
// A free team is never charged: the spent card says so instead of hinting at caps.
const prepaid = computed(() => !!spend.value && !spend.value.is_free_user)
const spentPercent = computed(() => {
	const limit = spend.value?.spend_limit ?? 0
	return limit > 0 ? Math.min(((usage.value?.cost ?? 0) / limit) * 100, 100) : 0
})

// A model call often costs a fraction of a cent, so small amounts keep 4 places.
const usdPrecision = (value: number): number => (value > 0 && value < 1 ? 4 : 2)

// ── Available models, per geography ──
const geographies = computed(() => ai.value?.geographies ?? [])
const defaultGeography = computed(
	() =>
		geographies.value.find((g) => g.is_default)?.name ??
		geographies.value[0]?.name ??
		'',
)
const geography = ref('')
const geographyOptions = computed(() =>
	geographies.value.map((g) => ({ label: g.label, value: g.name })),
)
// The list follows the pick; the first pick is Grove's default once the page knows it.
watch(
	defaultGeography,
	(name) => {
		if (!geography.value && name) geography.value = name
	},
	{ immediate: true },
)
watch(
	geography,
	(name) => {
		if (name) loadModels(name)
	},
	{ immediate: true },
)

// The table starts short; the rest unfolds in place.
const SHOWN = 6
const showAll = ref(false)
const shownModels = computed(() =>
	showAll.value ? models.value : models.value.slice(0, SHOWN),
)
</script>

<template>
	<div class="min-h-0 flex-1 overflow-y-auto">
		<div class="mx-auto w-full max-w-3xl px-6 pb-8 pt-5">
			<div v-if="aiLoading && !ai" class="flex justify-center py-16">
				<Spinner class="size-5 text-ink-gray-5" />
			</div>

			<template v-else>
				<h2 class="text-base font-semibold text-ink-gray-8">This month</h2>

				<p class="mt-0.5 text-p-sm text-ink-gray-5">
					Across every key of the team, as of
					{{ usage?.as_of ? formatDateTime(usage.as_of) : 'the last count' }}.
				</p>

				<div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
					<NumberCard
						title="Spent"
						:value="usage?.cost ?? null"
						prefix="$"
						:precision="usdPrecision(usage?.cost ?? 0)"
					>
						<template #actions>
							<Tooltip
								:text="
									prepaid
										? `Your plan lets your keys spend $${(spend?.spend_limit ?? 0).toFixed(2)} a month; their caps add up to $${(spend?.capped ?? 0).toFixed(2)} of it. Usage is billed at the end of the month.`
										: 'This is a free team: usage is counted but never charged.'
								"
							>
								<lucide-circle-help
									class="size-4 text-ink-gray-5"
									aria-label="What the monthly limit is"
								/>
							</Tooltip>
						</template>
						<template v-if="prepaid" #caption>
							<div
								class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-3"
								role="progressbar"
								:aria-valuenow="Math.round(spentPercent)"
								aria-valuemin="0"
								aria-valuemax="100"
								aria-label="Share of the monthly limit spent"
							>
								<div
									class="h-full rounded-full bg-surface-gray-9"
									:style="{ width: `${spentPercent}%` }"
								/>
							</div>
							<span class="shrink-0 tabular-nums text-ink-gray-5">
								of ${{ (spend?.spend_limit ?? 0).toFixed(2) }}
							</span>
						</template>
					</NumberCard>
					<NumberCard title="Requests" :value="usage?.requests ?? null" />
					<NumberCard title="Tokens" :value="usage?.tokens ?? null">
						<template #actions>
							<Tooltip
								text="Prompt and completion tokens together, across every model and key."
							>
								<lucide-circle-help
									class="size-4 text-ink-gray-5"
									aria-label="What counts as a token"
								/>
							</Tooltip>
						</template>
					</NumberCard>
				</div>

				<div class="mt-8 border-t border-outline-gray-2 pt-8">
					<div class="flex items-center justify-between gap-4">
						<div class="min-w-0">
							<h2 class="text-base font-semibold text-ink-gray-8">
								Available models
							</h2>
							<p class="mt-0.5 text-p-sm text-ink-gray-5">
								What a key in this geography can call, what each model takes and
								gives, and the APIs it answers on.
							</p>
						</div>
						<Select
							v-if="geographyOptions.length"
							v-model="geography"
							:options="geographyOptions"
							side="bottom"
							align="end"
							aria-label="Geography"
							class="w-fit shrink-0"
						>
							<template #prefix>
								<span class="text-ink-gray-5">Geography</span>
							</template>
						</Select>
					</div>
				</div>

				<div
					v-if="modelsLoading && !models.length"
					class="flex justify-center py-8"
				>
					<Spinner class="size-5 text-ink-gray-5" />
				</div>

				<div
					v-else-if="modelsError && !models.length"
					class="mt-3 flex items-center justify-between gap-3 rounded-6 border border-outline-gray-2 p-5"
				>
					<p class="text-p-sm text-ink-gray-7">
						{{ getErrorMessage(modelsError, 'Models could not be loaded.') }}
					</p>
					<Button label="Try again" @click="loadModels(geography)" />
				</div>

				<table v-else-if="models.length" class="mt-3 w-full border-collapse">
					<thead>
						<tr
							class="border-b border-outline-gray-2 text-p-xs text-ink-gray-5"
						>
							<th scope="col" class="py-2 pr-3 text-left font-normal">
								Provider
							</th>
							<th scope="col" class="py-2 pr-3 text-left font-normal">Model</th>
							<th scope="col" class="py-2 pr-3 text-left font-normal">
								Model key
							</th>
							<th scope="col" class="py-2 pr-3 text-left font-normal">Input</th>
							<th scope="col" class="py-2 pr-3 text-left font-normal">
								Output
							</th>
							<th scope="col" class="py-2 text-right font-normal">API</th>
						</tr>
					</thead>

					<tbody class="divide-y divide-outline-gray-1">
						<tr v-for="model in shownModels" :key="model.name">
							<td class="py-3 pr-3 text-sm text-ink-gray-7">
								{{ model.provider }}
							</td>
							<td class="py-3 pr-3 text-sm font-medium text-ink-gray-9">
								{{ model.model_id }}
							</td>
							<td class="py-3 pr-3 font-mono text-xs text-ink-gray-6">
								{{ model.name }}
							</td>

							<td
								v-for="(modalities, side) in [model.input_modalities, model.output_modalities]"
								:key="side"
								class="py-3 pr-3"
							>
								<div class="flex items-center gap-1.5 text-ink-gray-6">
									<Tooltip
										v-for="modality in modalities"
										:key="modality"
										:text="modalityLabel(modality)"
									>
										<component
											:is="modalityIcons[modality] ?? LucideCircleHelp"
											class="size-4"
											role="img"
											:aria-label="modalityLabel(modality)"
										/>
									</Tooltip>
								</div>
							</td>

							<td class="py-3">
								<div class="flex justify-end gap-1.5">
									<Badge
										v-for="dialect in model.dialects"
										:key="dialect"
										:label="dialectLabels[dialect]"
									/>
								</div>
							</td>
						</tr>
					</tbody>
				</table>

				<p
					v-else
					class="mt-3 rounded-6 border border-outline-gray-2 p-8 text-center text-p-sm text-ink-gray-5"
				>
					No models in this geography yet
				</p>

				<Button
					v-if="models.length > SHOWN"
					class="-ml-2 mt-3"
					variant="ghost"
					:label="showAll ? 'Show fewer' : `Show all ${models.length}`"
					:icon-right="showAll ? 'lucide-chevron-up' : 'lucide-chevron-down'"
					@click="showAll = !showAll"
				/>
			</template>
		</div>
	</div>
</template>
