<script setup lang="ts">
import { Alert, Button } from 'frappe-ui'
import { computed, ref } from 'vue'
import AddMethodDialog from '@/components/AddMethodDialog.vue'
import EditBillingProfileDialog from '@/components/billing/EditBillingProfileDialog.vue'
import { useBillingSetup } from '@/composables/useBillingSetup'
import { formatDate, plural } from '@/lib/format'
import type { ServerTrial } from '@/types/billing'

interface Props {
	trial: ServerTrial
	checking: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ check: [] }>()

const { requireSetup, setupDialogOpen, welcomeCredit } = useBillingSetup()
const showAddMethod = ref(false)
// A new card is confirmed by the gateway first, so the trial can stay open for a moment.
const methodAdded = ref(false)

const title = computed(() =>
	props.trial.state === 'Ended'
		? 'Your free trial has ended'
		: `Your free trial ends in ${plural(props.trial.days_left, 'day')}`,
)

const description = computed(() =>
	props.trial.state === 'Ended' && props.trial.deletes_on
		? `This site is stopped. Add a payment method before ${formatDate(props.trial.deletes_on)} to keep it and choose a plan.`
		: 'Add a payment method to keep this site and choose a bigger plan.',
)

function addMethod(): void {
	if (requireSetup()) showAddMethod.value = true
}

function onMethodAdded(): void {
	methodAdded.value = true
	emit('check')
}
</script>

<template>
	<div class="space-y-4">
		<Alert
			:theme="trial.state === 'Ended' ? 'red' : 'blue'"
			:title="title"
			:description="description"
		/>

		<ul class="space-y-1.5 text-p-sm text-ink-gray-7">
			<li v-if="welcomeCredit">You get {{ welcomeCredit }} when you add it.</li>
			<li>
				After the credit is used, we charge this card for your monthly bill.
			</li>
			<li>Your site and its data stay as they are.</li>
		</ul>

		<p v-if="methodAdded" class="text-p-sm text-ink-gray-6" aria-live="polite">
			We are confirming your payment method. This can take a minute.
		</p>

		<div class="flex justify-end gap-2">
			<Button
				v-if="methodAdded"
				label="Check again"
				:loading="checking"
				@click="emit('check')"
			/>
			<Button
				v-else
				variant="solid"
				icon-left="lucide-credit-card"
				label="Add payment method"
				@click="addMethod"
			/>
		</div>

		<AddMethodDialog v-model="showAddMethod" @done="onMethodAdded" />
		<EditBillingProfileDialog v-model="setupDialogOpen" />
	</div>
</template>
