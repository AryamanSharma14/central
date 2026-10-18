<script setup lang="ts">
import { Alert, Button, Dialog, TextInput } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useCapabilities } from '@/composables/useCapabilities'
import { useServerMapData } from '@/composables/useServerMapData'
import { useServers } from '@/composables/useServers'
import { useSession } from '@/composables/useSession'
import { getErrorMessage, successToast } from '@/lib/feedback'
import { plural } from '@/lib/format'

const { canPowerServer } = useCapabilities()
const { activeTeamLabel } = useSession()
const { servers } = useServerMapData()
const { runCommand } = useServers()

const running = computed(() =>
	servers.value.filter(
		(server) =>
			server.status === 'Running' &&
			(server.capabilities?.includes('server:power') ?? canPowerServer.value),
	),
)

const serverCount = computed(() => plural(running.value.length, 'server'))

const open = ref(false)
const confirmText = ref('')
const error = ref('')
const suspending = ref(false)

const confirmed = computed(
	() => confirmText.value.trim() === activeTeamLabel.value,
)

watch(open, (isOpen) => {
	if (!isOpen) return

	confirmText.value = ''
	error.value = ''
})

const suspendAll = async () => {
	suspending.value = true
	error.value = ''

	const results = await Promise.allSettled(
		running.value.map((server) =>
			runCommand('stop', server, { throwOnError: true }),
		),
	)

	suspending.value = false

	const failed = results.filter((result) => result.status === 'rejected')

	if (failed.length) {
		error.value = getErrorMessage(
			(failed[0] as PromiseRejectedResult).reason,
			`${plural(failed.length, 'server')} could not be stopped.`,
		)

		return
	}

	open.value = false
	successToast(`Stop requested for ${serverCount.value}`)
}
</script>

<template>
	<section
		aria-labelledby="suspend-heading"
		class="flex flex-wrap items-center gap-4 rounded-6 border border-outline-red-2 px-5 py-4"
	>
		<div class="min-w-0 flex-[1_1_20rem]">
			<h2 id="suspend-heading" class="text-base-semibold text-ink-gray-8">
				Stop all servers
			</h2>
			<p class="mt-0.5 text-p-sm text-ink-gray-5">
				<template v-if="running.length">
					Stops {{ serverCount }}. Sites will be unavailable. Data is retained,
					and you can restart the servers.
				</template>
				<template v-else>No servers are running.</template>
			</p>
		</div>
		<Button
			v-if="canPowerServer"
			theme="red"
			label="Stop all"
			:disabled="!running.length"
			@click="open = true"
		/>

		<Dialog
			v-model:open="open"
			:title="`Stop ${running.length === 1 ? 'your server' : `all ${serverCount}`}?`"
		>
			<template #default>
				<Alert v-if="error" class="mb-4" theme="red" :title="error" />
				<p class="text-p-base text-ink-gray-6">
					Sites on these servers will be unavailable until you restart them.
					Data, snapshots, and configuration are retained.
				</p>
				<TextInput
					v-model="confirmText"
					class="mt-4"
					autocomplete="off"
					:label="`Type ${activeTeamLabel} to confirm`"
					@keydown.enter="confirmed && suspendAll()"
				/>
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button label="Cancel" @click="open = false" />
					<Button
						variant="solid"
						theme="red"
						label="Stop servers"
						:disabled="!confirmed"
						:loading="suspending"
						@click="suspendAll"
					/>
				</div>
			</template>
		</Dialog>
	</section>
</template>
