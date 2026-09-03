import { spawnSync } from 'node:child_process'
import path from 'node:path'
import process from 'node:process'

if (process.platform !== 'darwin') {
  throw new Error('The macOS package must be built on macOS')
}

const frontendDir = path.resolve(import.meta.dirname, '..')
const builder = path.join(frontendDir, 'node_modules/.bin/electron-builder')
const appBundle = path.join(frontendDir, 'release/mac-arm64/Hubble.app')
const buildEnv = { ...process.env, CSC_IDENTITY_AUTO_DISCOVERY: 'false' }

function run(executable, args, env = process.env) {
  const result = spawnSync(executable, args, { cwd: frontendDir, stdio: 'inherit', env })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status ?? 1)
}

// Build without auto-selecting an unsuitable local certificate, then apply one
// consistent ad-hoc signature to the complete nested bundle. This keeps local
// builds launchable and verifiable; public releases still require Developer ID
// signing and notarization in the release pipeline.
run(builder, ['--mac', 'dir'], buildEnv)
run('codesign', ['--force', '--deep', '--sign', '-', appBundle])
run('codesign', ['--verify', '--deep', '--strict', '--verbose=2', appBundle])
run(builder, ['--mac', 'dmg', '--prepackaged', appBundle], buildEnv)
