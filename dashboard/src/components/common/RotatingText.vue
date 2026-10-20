<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'

interface RotatingTextProps {
	lines: string[]
	intervalMs?: number
}

const props = withDefaults(defineProps<RotatingTextProps>(), {
	intervalMs: 2600,
})

// Holds on the last line instead of looping, so the text never seems to start over.
const index = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

watch(
	() => props.lines.join('\n'),
	() => {
		clearInterval(timer)
		index.value = 0
		timer = setInterval(() => {
			if (index.value < props.lines.length - 1) index.value += 1
			else clearInterval(timer)
		}, props.intervalMs)
	},
	{ immediate: true },
)
onUnmounted(() => clearInterval(timer))
</script>

<template>
	<p class="relative h-6" aria-live="polite">
		<Transition
			enter-active-class="transition duration-300 ease-out"
			enter-from-class="translate-y-1.5 opacity-0 blur-[2px]"
			leave-active-class="absolute inset-x-0 transition duration-200 ease-in"
			leave-to-class="-translate-y-1.5 opacity-0 blur-[2px]"
		>
			<span v-if="lines.length" :key="lines[index]" class="block truncate">
				{{ lines[index] }}
			</span>
		</Transition>
	</p>
</template>
