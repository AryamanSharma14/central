<script setup lang="ts">
import { computed, ref } from 'vue'
import PaymentMethodFlow from '@/components/billing/PaymentMethodFlow.vue'
import { useBillingSetup } from '@/composables/useBillingSetup'

const { welcomeCredit } = useBillingSetup()
const flow = ref<InstanceType<typeof PaymentMethodFlow> | null>(null)
const hasMethod = ref(false)

defineExpose({
	canSubmit: true,
	submitLabel: computed(() =>
		hasMethod.value ? 'Continue' : 'Add payment method',
	),
	saving: false,
	submit: async () => {
		if (hasMethod.value) return true
		flow.value?.start()
		return false
	},
})
</script>

<template>
	<div class="space-y-4">
		<div
			v-if="hasMethod"
			class="flex items-center gap-3 rounded-6 bg-surface-gray-2 px-4 py-3"
			role="status"
		>
			<span
				class="lucide-circle-check size-4 shrink-0 text-ink-green-3"
				aria-hidden="true"
			/>
			<p class="text-p-sm-medium text-ink-gray-9">
				Payment method added.
				{{ welcomeCredit ? 'Your credit is in your wallet.' : '' }}
			</p>
		</div>
		<div
			v-else-if="welcomeCredit"
			class="flex items-center gap-3 rounded-6 bg-surface-gray-2 px-4 py-3"
		>
			<span
				class="lucide-gift size-4 shrink-0 text-ink-gray-8"
				aria-hidden="true"
			/>
			<p class="text-p-sm-medium text-ink-gray-9">
				Add a payment method and get {{ welcomeCredit }}.
			</p>
		</div>

		<ul class="space-y-3 text-p-sm text-ink-gray-7">
			<li class="flex items-start gap-3">
				<span
					class="lucide-credit-card mt-0.5 size-4 shrink-0 text-ink-gray-5"
					aria-hidden="true"
				/>
				Adding a card does not charge it. We charge it for your monthly bill,
				after any credit is used.
			</li>
			<li class="flex items-start gap-3">
				<span
					class="lucide-server mt-0.5 size-4 shrink-0 text-ink-gray-5"
					aria-hidden="true"
				/>
				You need a payment method to create servers.
			</li>
		</ul>

		<PaymentMethodFlow ref="flow" @done="hasMethod = true" />
	</div>
</template>
