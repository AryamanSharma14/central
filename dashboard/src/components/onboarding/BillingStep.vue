<script setup lang="ts">
import { computed, ref } from 'vue'
import BillingProfileForm from '@/components/billing/BillingProfileForm.vue'
import { useBillingSetup } from '@/composables/useBillingSetup'

const form = ref<InstanceType<typeof BillingProfileForm> | null>(null)
const { welcomeCredit } = useBillingSetup()

defineExpose({
	canSubmit: true,
	submitLabel: 'Save billing details',
	saving: computed(() => form.value?.saving ?? false),
	submit: async () => (await form.value?.submit()) ?? false,
})
</script>

<template>
	<div class="space-y-4">
		<BillingProfileForm ref="form" />
		<p v-if="welcomeCredit" class="text-p-sm text-ink-gray-6">
			Add a payment method in Billing to get {{ welcomeCredit }}.
		</p>
	</div>
</template>
