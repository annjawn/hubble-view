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
const uvEnv = { ...process.env, UV_PYTHON_PREFERENCE: 'only-managed', UV_PYTHON: '3.13' }
const install = spawnSync(executable, ['python', 'install', '3.13'], {
  cwd: backendDir, stdio: 'inherit', env: uvEnv,
})
if (install.error) throw install.error
if (install.status !== 0) process.exit(install.status ?? 1)

const result = spawnSync(executable, [
  'run', '--project', backendDir, '--group', 'dev',
  'python', '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir', '--noupx',
  '--name', 'hubble-service',
  '--paths', path.join(backendDir, 'src'),
  '--distpath', outputDir,
  '--workpath', path.join(workDir, 'work'),
  '--specpath', workDir,
  entryPoint,
], { cwd: frontendDir, stdio: 'inherit', env: uvEnv })

if (result.error) throw result.error
process.exit(result.status ?? 1)
