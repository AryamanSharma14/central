import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

function load(path, dependencies = {}) {
	const source = readFileSync(new URL(path, import.meta.url), 'utf8')
	const exports = {}
	runInNewContext(
		typescript.transpileModule(source, {
			compilerOptions: { module: typescript.ModuleKind.CommonJS },
		}).outputText,
		{ exports, require: (name) => dependencies[name] },
	)
	return exports
}

const menu = load('../src/lib/serverMenu.ts', {
	'@/lib/clipboard': { copyToClipboard: async () => true },
	'@/lib/feedback': { reportError: () => {}, successToast: () => {} },
	'@/lib/status': load('../src/lib/status.ts'),
})

const allowed = {
	open: false,
	power: false,
	resize: false,
	snapshot: false,
	terminate: false,
	console: true,
}

function getConsoleRow(status) {
	const verbs = []
	const server = { resource_id: 'vm-1', status, pending_action: null }
	const row = menu
		.getServerMenuGroups(server, allowed, (verb) => verbs.push(verb), {
			isOnServerPage: true,
		})
		.flat()
		.find((option) => option.label === 'Web console')
	return { row, verbs }
}

test('web console offers SSH and TTY in a submenu', () => {
	const { row, verbs } = getConsoleRow('Running')

	assert.equal(row.disabled, false)
	assert.deepEqual(
		[...row.submenu].map((item) => item.label),
		['SSH session', 'Serial console (TTY)'],
	)

	for (const item of row.submenu) item.onClick()
	assert.deepEqual(verbs, ['ssh-console', 'tty-console'])
})

test('a flat list names each console mode and keeps the parent disabled state', () => {
	const { row } = getConsoleRow('Stopped')
	const items = menu.withSubmenuItems(row)

	assert.deepEqual(
		[...items].map((item) => [item.label, item.disabled]),
		[
			['Web console: SSH session', true],
			['Web console: Serial console (TTY)', true],
		],
	)
})
