import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const frontendDir = path.resolve(import.meta.dirname, '..')
const backendDir = path.resolve(frontendDir, '../backend')
const outputDir = path.join(frontendDir, 'backend-dist')
const workDir = path.join(frontendDir, '.backend-build')
const entryPoint = path.join(backendDir, 'src/harness_metrics/service.py')

mkdirSync(outputDir, { recursive: true })
mkdirSync(workDir, { recursive: true })

const executable = process.platform === 'win32' ? 'uv.exe' : 'uv'
const result = spawnSync(executable, [
  'run', '--project', backendDir, '--group', 'dev',
  'python', '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir',
  '--name', 'hubble-service',
  '--paths', path.join(backendDir, 'src'),
  '--distpath', outputDir,
  '--workpath', path.join(workDir, 'work'),
  '--specpath', workDir,
  entryPoint,
], { cwd: frontendDir, stdio: 'inherit' })

if (result.error) throw result.error
process.exit(result.status ?? 1)
