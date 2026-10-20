<script lang="ts">
export type PaymentNetwork = 'visa' | 'mastercard' | 'rupay' | 'diners' | 'upi'
</script>

<script setup lang="ts">
import diners from '@/assets/payments/diners.svg?raw'
import mastercard from '@/assets/payments/mastercard.svg?raw'
import rupay from '@/assets/payments/rupay.svg?raw'
import upi from '@/assets/payments/upi.svg?raw'
import visa from '@/assets/payments/visa.svg?raw'

defineProps<{ network: PaymentNetwork }>()

// Inlined, not an img: the wordmarks use dark:fill, and an image cannot see
// data-theme. Diners stays filled as drawn, because its mark is a white disc.
const marks: Record<
	PaymentNetwork,
	{ svg: string; label: string; height: string }
> = {
	visa: { svg: visa, label: 'Visa', height: '[&>svg]:h-3' },
	mastercard: {
		svg: mastercard,
		label: 'Mastercard',
		height: '[&>svg]:h-[18px]',
	},
	// The y descender and the circle both hang below the label's body, so the
	// marks sit a pixel or two above the line the row centers.
	rupay: {
		svg: rupay,
		label: 'RuPay',
		height: '[&>svg]:h-[13px] -translate-y-px',
	},
	diners: {
		svg: diners,
		label: 'Diners Club',
		height: '[&>svg]:h-4 -translate-y-[2px]',
	},
	upi: { svg: upi, label: 'UPI', height: '[&>svg]:h-[13px]' },
}
</script>

<template>
	<span
		class="inline-flex shrink-0 items-center [&>svg]:w-auto"
		:class="marks[network].height"
		role="img"
		:aria-label="marks[network].label"
		v-html="marks[network].svg"
	/>
</template>
