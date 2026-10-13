import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

const require = createRequire(import.meta.url)
const source = readFileSync(
	new URL('../src/composables/useSession.ts', import.meta.url),
	'utf8',
)
const compiled = typescript.transpileModule(source, {
	compilerOptions: { module: typescript.ModuleKind.CommonJS },
}).outputText
const storageKey = 'central.console.activeTeam'

function startSession(pathname, storage, storageBlocked = false) {
	const navigations = []
	const exports = {}
	const roster = [
		{ name: 'team-a', label: 'Acme' },
		{ name: 'team-b', label: 'Pied Piper' },
	]
	const localStorage = {
		getItem: (key) => storage.get(key) ?? null,
		setItem(key, value) {
			if (storageBlocked) throw new Error('Storage blocked')
			storage.set(key, value)
		},
		removeItem: (key) => storage.delete(key),
	}
	const dependencies = {
		vue: require('vue'),
		'@/api/methods': { API: { myTeams: 'my_teams' }, method: (value) => value },
		'frappe-ui': {
			useCall(options) {
				options.onSuccess(roster)
				return { data: roster, promise: Promise.resolve(), reload() {} }
			},
		},
	}
	runInNewContext(compiled, {
		exports,
		require: (name) => dependencies[name],
		localStorage,
		window: {
			location: {
				pathname,
				reload: () => navigations.push('reload'),
				replace: (path) => navigations.push(path),
			},
		},
	})
	return { session: exports.useSession(), navigations }
}

test('switching preserves a section and boots with the new team before reads start', () => {
	for (const path of [
		'/dashboard/llm',
		'/dashboard/billing/invoices',
		'/dashboard/team/members',
		'/dashboard/servers/snapshots',
	]) {
		const storage = new Map([[storageKey, 'team-a']])
		const { session, navigations } = startSession(path, storage)
		session.setActiveTeam('team-b')
		assert.deepEqual(navigations, ['reload'])
		assert.equal(storage.get(storageKey), 'team-b')
		// The departing document never pairs team B's identity with team A's data.
		assert.equal(session.activeTeam.value, 'team-a')
		const nextDocument = startSession(path, storage)
		assert.equal(nextDocument.session.activeTeam.value, 'team-b')
		assert.equal(nextDocument.session.activeTeamLabel.value, 'Pied Piper')
	}
})

test('resource pages return to their section when the selected team changes', () => {
	for (const [path, destination] of [
		['/dashboard/servers/vm-a/access', '/dashboard/servers'],
		['/dashboard/servers/new', '/dashboard/servers'],
		['/dashboard/object-storage/bucket-a', '/dashboard/object-storage'],
	]) {
		const storage = new Map([[storageKey, 'team-a']])
		const { session, navigations } = startSession(path, storage)
		session.setActiveTeam('team-b')
		assert.deepEqual(navigations, [destination])
	}
})

test('a storage failure keeps the existing team and prevents navigation', () => {
	const storage = new Map([[storageKey, 'team-a']])
	const { session, navigations } = startSession('/dashboard/llm', storage, true)
	assert.throws(
		() => session.setActiveTeam('team-b'),
		/Could not save the selected team/,
	)
	assert.equal(session.activeTeam.value, 'team-a')
	assert.equal(storage.get(storageKey), 'team-a')
	assert.deepEqual(navigations, [])
})
