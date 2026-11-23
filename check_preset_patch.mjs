// Validate a DSH patch file that declares the TS800X agent preset.
//
// Run by sync_dsh_preset.ps1 before it writes the profile patch layer. It uses
// the installed harness itself instead of re-implementing its rules:
//   1. parse the file with @deepseek-ai/dsh-app-boot's patch parser
//      (`loadOptionalPatches`, the same call the plugin manager validates with),
//   2. validate each `@deepseek-ai/dsh-agent-preset` declaration against that
//      package's own Config schema,
//   3. check every plugin row against the installed dsh manifest, because a
//      preset row resolves its children from the installation scope -- a
//      package renamed upstream fails activation even though the YAML parses.
//
// Usage: DSH_ROOT=<dsh package dir> node check_preset_patch.mjs <patch-file>
// Exit: 0 valid, 1 invalid, 2 usage error, 3 validation unavailable (skipped).
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

const target = process.argv[2]
const dshRoot = process.env.DSH_ROOT
if (!target || !dshRoot) {
  console.error('[SKIP] usage: DSH_ROOT=<dsh package dir> node check_preset_patch.mjs <patch-file>')
  process.exit(3)
}

let boot
let AgentPreset
let dshManifest
try {
  boot = await import(pathToFileURL(join(dshRoot, 'node_modules', '@deepseek-ai', 'dsh-app-boot', 'lib', 'index.js')).href)
  AgentPreset = (await import(pathToFileURL(join(dshRoot, 'node_modules', '@deepseek-ai', 'dsh-agent-preset', 'lib', 'index.js')).href)).default
  dshManifest = JSON.parse(readFileSync(join(dshRoot, 'package.json'), 'utf8'))
} catch (error) {
  console.error(`[SKIP] harness modules are unavailable under ${dshRoot}: ${error.message}`)
  process.exit(3)
}

const installScope = new Set([
  ...Object.keys(dshManifest.dependencies ?? {}),
  ...Object.keys(dshManifest.peerDependencies ?? {}),
  ...Object.keys(dshManifest.devDependencies ?? {})
])

let patches
try {
  patches = boot.loadOptionalPatches('dsh', target)
} catch (error) {
  console.error(`[FAIL] patch parse: ${error.message}`)
  process.exit(1)
}
if (!Array.isArray(patches)) {
  console.error('[FAIL] patch list is not a YAML sequence')
  process.exit(1)
}
console.log(`[OK] parsed ${patches.length} patch entr${patches.length === 1 ? 'y' : 'ies'}`)

let presets = 0
let failures = 0
for (const entry of patches) {
  const rows = Array.isArray(entry?.insert) ? entry.insert : []
  for (const row of rows) {
    if (row?.name !== '@deepseek-ai/dsh-agent-preset') continue
    presets++
    let config
    try {
      config = AgentPreset.Config(row.config)
    } catch (error) {
      console.error(`[FAIL] row ${row?.id}: Config schema: ${error.message}`)
      failures++
      continue
    }
    console.log(`[OK] preset row ${row.id}: id=${config.id} name=${JSON.stringify(config.name)} order=${config.order} plugins=${config.plugins.length}`)
    const ids = new Set()
    for (const plugin of config.plugins) {
      if (typeof plugin?.name !== 'string') {
        console.error(`  [FAIL] plugin row without a name: ${JSON.stringify(plugin)}`)
        failures++
        continue
      }
      if (plugin.id !== undefined) {
        if (ids.has(plugin.id)) {
          console.error(`  [FAIL] duplicate plugin id inside the preset: ${plugin.id}`)
          failures++
        }
        ids.add(plugin.id)
      }
      if (plugin.name.startsWith('cordis:')) continue
      const pkg = plugin.name.startsWith('@')
        ? plugin.name.split('/').slice(0, 2).join('/')
        : plugin.name.split('/')[0]
      if (!installScope.has(pkg)) {
        console.error(`  [FAIL] plugin ${plugin.id}: ${pkg} is not an installation-scope package of dsh ${dshManifest.version}`)
        failures++
      }
    }
    console.log(`  [OK] ${config.plugins.length} plugin rows checked against the installation scope`)
  }
}

if (presets === 0) {
  console.error('[FAIL] no @deepseek-ai/dsh-agent-preset declaration found')
  process.exit(1)
}
if (failures > 0) {
  console.error(`[FAIL] ${failures} problem(s) in ${target}`)
  process.exit(1)
}
console.log(`[PASS] ${presets} preset declaration(s) valid`)
