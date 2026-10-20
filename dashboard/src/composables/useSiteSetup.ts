import { dayjsLocal } from 'frappe-ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { API } from '@/api/methods'
import { useTrialOnboarding } from '@/composables/useTrialOnboarding'
import { frappeErrorMessage, methodUrl, postFrappe } from '@/lib/auth'
import type {
	SetupPhase,
	TrialOnboardingStatus,
	TrialSiteState,
} from '@/types/api'

/** What the waiting page shows: Central's phase, or the two states only the page knows. */
export type SetupStage = SetupPhase | 'arrived' | 'delayed'

const POLL_MS = 1000
// A new Pilot accepts Central seconds after it finishes its bootstrap, so the
// first retries come fast. The schedule still gives up after about 2 minutes.
const LOGIN_RETRY_DELAYS_MS = [
	1000, 1000, 1000, 2000, 2000, 2000, 2000, 5000, 5000, 10000, 10000, 15000,
	15000, 15000, 15000, 20000,
]
const SIGN_IN_FAILED =
	'Your site is up, but we could not sign you in automatically.'

/** Follows a new trial site until it answers, then signs the customer in and leaves. */
export function useSiteSetup() {
	const { readStatus } = useTrialOnboarding()
	const status = ref<TrialOnboardingStatus | null>(null)
	const error = ref('')
	const loginUrl = ref<string | null>(null)
	const now = ref(Date.now())
	let timer: ReturnType<typeof setTimeout> | undefined
	let clock: ReturnType<typeof setInterval> | undefined
	let loginRetryIndex = 0

	const site = computed(() => status.value?.site ?? null)
	const journey = computed(() => status.value?.journey ?? null)
	const isFailed = computed(
		() =>
			journey.value?.phase === 'failed' ||
			Boolean(status.value?.creation?.error),
	)
	const failure = computed(() => status.value?.creation?.error?.message ?? '')
	const secondsWaited = computed(() => {
		const started = journey.value?.started_at
		return started ? (now.value - dayjsLocal(started).valueOf()) / 1000 : 0
	})
	const secondsLeft = computed(() => {
		const eta = journey.value?.eta_seconds
		return eta ? Math.round(eta - secondsWaited.value) : null
	})

	const stage = computed<SetupStage>(() => {
		if (loginUrl.value) return 'arrived'
		if (isFailed.value) return 'failed'
		const phase = journey.value?.phase ?? 'booking'
		const eta = journey.value?.eta_seconds
		// Past twice the usual wait, the page says so instead of counting below zero.
		if (phase !== 'signing' && eta && secondsWaited.value > eta * 2)
			return 'delayed'
		return phase
	})

	async function poll() {
		try {
			status.value = await readStatus()
			if (site.value?.ready) return claim()
			if (isFailed.value) return
		} catch (exception) {
			error.value = frappeErrorMessage(
				exception,
				'Lost track of your site. Refresh to retry.',
			)
			return
		}
		timer = setTimeout(poll, POLL_MS)
	}

	// Ready means the site answered. Claiming hands back a way in and schedules the
	// customer's name behind the response. A new Pilot can reject Central authentication
	// briefly, so only that state is retried without starting the rename.
	async function claim() {
		try {
			const claimed = await postFrappe<TrialSiteState>(
				methodUrl(API.claimSite),
				{ name: site.value!.name },
			)
			if (claimed.login_pending) return retryClaim()
			if (!claimed.login_url) {
				error.value = SIGN_IN_FAILED
				return
			}
			arrive(claimed.login_url)
		} catch (exception) {
			error.value = frappeErrorMessage(exception, SIGN_IN_FAILED)
		}
	}

	function retryClaim() {
		const retryDelay = LOGIN_RETRY_DELAYS_MS[loginRetryIndex]
		if (retryDelay === undefined) {
			error.value = SIGN_IN_FAILED
			return
		}
		loginRetryIndex += 1
		timer = setTimeout(claim, retryDelay)
	}

	function arrive(url: string) {
		loginUrl.value = url
		// Long enough to read "Arrived", short enough that nobody waits on it.
		timer = setTimeout(() => window.location.assign(url), 1200)
	}

	function openSite() {
		if (site.value?.url) window.location.assign(site.value.url)
	}

	onMounted(() => {
		clock = setInterval(() => (now.value = Date.now()), 1000)
		poll()
	})
	onUnmounted(() => {
		clearTimeout(timer)
		clearInterval(clock)
	})

	return {
		site,
		journey,
		stage,
		secondsLeft,
		failure,
		error,
		openSite,
	}
}
