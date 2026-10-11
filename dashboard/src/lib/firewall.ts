export type FirewallProtocol = 'any' | 'tcp' | 'udp' | 'icmp'

/** One allow rule, in the form Atlas stores it. */
export interface FirewallRule {
	protocol: FirewallProtocol
	ports: string
	cidrs: string[]
}

/** The customer's rules. Central adds its own rules for the private network, VPN and ping. */
export interface FirewallRules {
	inbound: FirewallRule[]
	outbound: FirewallRule[]
}

export interface FirewallService {
	label: string
	protocol: FirewallProtocol
	/** The fixed port, or null when the person types one. */
	ports: string | null
}

export const ANYWHERE_IPV4 = '0.0.0.0/0'
export const ANYWHERE_IPV6 = '::/0'

export const SERVICES: FirewallService[] = [
	{ label: 'SSH', protocol: 'tcp', ports: '22' },
	{ label: 'HTTP', protocol: 'tcp', ports: '80' },
	{ label: 'HTTPS', protocol: 'tcp', ports: '443' },
	{ label: 'MariaDB', protocol: 'tcp', ports: '3306' },
	{ label: 'PostgreSQL', protocol: 'tcp', ports: '5432' },
	{ label: 'Redis', protocol: 'tcp', ports: '6379' },
	{ label: 'Ping', protocol: 'icmp', ports: '' },
	{ label: 'Custom TCP', protocol: 'tcp', ports: null },
	{ label: 'Custom UDP', protocol: 'udp', ports: null },
	{ label: 'All traffic', protocol: 'any', ports: '' },
]

/** The customer's firewall: its state and its rules. */
export type Firewall = FirewallRules & { enabled: boolean }

/** A change to a firewall. A field left out keeps its saved value. */
export type FirewallChange = Partial<Firewall>

const ANYWHERE = [ANYWHERE_IPV4, ANYWHERE_IPV6]
const ALL_OUTBOUND: FirewallRule[] = [
	{ protocol: 'any', ports: '', cidrs: ANYWHERE },
]
const allow = (...ports: string[]): FirewallRule[] =>
	ports.map((port) => ({ protocol: 'tcp', ports: port, cidrs: ANYWHERE }))

/** Starting rule sets. Each one lets the server reach the internet. */
export const PRESETS: { label: string; rules: FirewallRules }[] = [
	{
		label: 'Web server',
		rules: { inbound: allow('22', '80', '443'), outbound: ALL_OUTBOUND },
	},
	{
		label: 'SSH only',
		rules: { inbound: allow('22'), outbound: ALL_OUTBOUND },
	},
	{ label: 'Private only', rules: { inbound: [], outbound: ALL_OUTBOUND } },
]

export function getService(rule: FirewallRule): FirewallService {
	return (
		SERVICES.find(
			(service) =>
				service.protocol === rule.protocol && service.ports === rule.ports,
		) ??
		SERVICES.find(
			(service) => service.protocol === rule.protocol && service.ports === null,
		) ??
		SERVICES[SERVICES.length - 1]
	)
}

export function getPortLabel(rule: FirewallRule): string {
	if (rule.protocol === 'any') return 'All'
	if (rule.protocol === 'icmp') return 'ICMP'
	return `${rule.protocol.toUpperCase()} ${rule.ports || 'all'}`
}

export function getAddressLabel(cidr: string): string {
	if (cidr === ANYWHERE_IPV4) return 'Anywhere (IPv4)'
	if (cidr === ANYWHERE_IPV6) return 'Anywhere (IPv6)'
	return cidr
}

/** A single address becomes a one-address range, the form Atlas stores. */
export function toCidr(value: string): string {
	const address = value.trim()
	if (!address || address.includes('/')) return address
	return address.includes(':') ? `${address}/128` : `${address}/32`
}

/** Check an address before adding it; Central validates the complete change again. */
export function getCidrError(value: string): string {
	const cidr = toCidr(value)
	const [address, prefix, extra] = cidr.split('/')
	if (!address || !/^\d+$/.test(prefix ?? '') || extra !== undefined)
		return 'Enter an IP address or a range, such as 203.0.113.7 or 203.0.113.0/24.'

	const isIpv6 = address.includes(':')
	const width = isIpv6 ? 128 : 32
	const mask = Number(prefix)
	if (mask > width) return `The range prefix must be between 0 and ${width}.`
	if (String(mask) !== prefix)
		return 'Use a range prefix without leading zeros.'

	let bits: bigint
	if (isIpv6) {
		let canonical: string
		try {
			canonical = new URL(`http://[${address}]/`).hostname.slice(1, -1)
		} catch {
			return 'Enter a valid IPv6 address.'
		}
		if (canonical !== address)
			return `Use ${canonical}/${mask} for this address.`
		const [left, right] = canonical
			.split('::')
			.map((part) => (part ? part.split(':') : []))
		const groups = right
			? [...left, ...Array(8 - left.length - right.length).fill('0'), ...right]
			: left
		bits = BigInt(`0x${groups.map((part) => part.padStart(4, '0')).join('')}`)
	} else {
		const parts = address.split('.')
		if (
			parts.length !== 4 ||
			parts.some(
				(part) => !/^(0|[1-9]\d{0,2})$/.test(part) || Number(part) > 255,
			)
		)
			return 'Enter a valid IPv4 address.'
		bits = parts.reduce((result, part) => (result << 8n) + BigInt(part), 0n)
	}
	const hostMask = (1n << BigInt(width - mask)) - 1n
	if (bits & hostMask)
		return 'Use the network address for a range, such as 203.0.113.0/24.'
	return ''
}

export function isSameRule(a: FirewallRule, b: FirewallRule): boolean {
	return (
		a.protocol === b.protocol &&
		a.ports === b.ports &&
		[...a.cidrs].sort().join() === [...b.cidrs].sort().join()
	)
}

function opensSSH(rules: FirewallRule[]): boolean {
	return rules.some(
		(rule) =>
			rule.protocol === 'any' ||
			(rule.protocol === 'tcp' && (rule.ports === '22' || rule.ports === '')),
	)
}

/** What stops working when a firewall changes from `before` to `after`. */
export function getFirewallTexts(before: Firewall, after: Firewall): string[] {
	if (!after.enabled)
		return before.enabled ? ['Every port will be open to the internet.'] : []

	const warnings: string[] = []
	if (!opensSSH(after.inbound) && (!before.enabled || opensSSH(before.inbound)))
		warnings.push(
			'No rule allows SSH, so SSH connections will stop. The web console still works.',
		)
	if (!after.outbound.length && (!before.enabled || before.outbound.length))
		warnings.push(
			"No outgoing rule, so the server can't install updates or send email.",
		)
	return warnings
}
