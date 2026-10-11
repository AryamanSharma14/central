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
