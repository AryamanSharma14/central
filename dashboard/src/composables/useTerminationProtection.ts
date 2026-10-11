import { useCall } from 'frappe-ui'
import { computed, type Ref } from 'vue'
import { API, method } from '@/api/methods'
import { useSession } from '@/composables/useSession'
import { reportError } from '@/lib/feedback'

/** Turns termination protection on or off for one server. */
export function useTerminationProtection(resourceId: Ref<string>) {
	const { activeTeam } = useSession()

	const protectionCall = useCall<
		null,
		{ team: string; resource_id: string; enabled: boolean }
	>({
		url: method(API.setTerminationProtection),
		method: 'POST',
		immediate: false,
	})

	async function setTerminationProtection(enabled: boolean): Promise<boolean> {
		if (!activeTeam.value) return false

		await protectionCall.submit({
			team: activeTeam.value,
			resource_id: resourceId.value,
			enabled,
		})
		if (protectionCall.error)
			reportError(protectionCall.error, {
				title: "Termination protection wasn't changed",
			})

		return !protectionCall.error
	}

	return {
		setTerminationProtection,
		isSavingProtection: computed(() => protectionCall.loading),
	}
}
