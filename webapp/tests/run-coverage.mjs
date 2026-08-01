import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import MCR from 'monocart-coverage-reports'
import istanbulCoverage from 'istanbul-lib-coverage'
import { buildCoverageSource, compiledDir, root } from './build-coverage-source.mjs'

const outputDir = path.join(root, 'coverage')
const rawDir = path.join(outputDir, 'tmp')
const productionFile = (filename) =>
  filename.startsWith(`${compiledDir}${path.sep}`) && filename.endsWith('.js')

const sourceByCompiledFile = await buildCoverageSource()
const intendedSources = new Set([...sourceByCompiledFile.values()].map((filename) => path.resolve(filename)))
fs.rmSync(outputDir, { force: true, recursive: true })
fs.mkdirSync(rawDir, { recursive: true })

const testFiles = fs.readdirSync(path.join(root, 'tests'))
  .filter((name) => name.endsWith('.test.mjs'))
  .sort()
  .map((name) => path.join('tests', name))

const result = spawnSync(process.execPath, [
  '--max-old-space-size=1536',
  '--loader', './tests/resolve-loader.mjs',
  '--experimental-test-module-mocks',
  '--test-concurrency=2',
  '--test',
  ...testFiles,
], {
  cwd: root,
  env: { ...process.env, NODE_V8_COVERAGE: rawDir },
  stdio: 'inherit',
})
if (result.status !== 0) process.exit(result.status ?? 1)

const report = new MCR.CoverageReport({
  all: {
    dir: compiledDir,
    filter: (filename) => productionFile(path.resolve(filename)),
  },
  baseDir: root,
  clean: true,
  entryFilter: (entry) => {
    if (!entry.url.startsWith('file:')) return false
    return productionFile(fileURLToPath(entry.url))
  },
  outputDir,
  reports: [['text', {}], ['json', {}]],
  sourceFilter: (sourcePath) => intendedSources.has(path.resolve(root, sourcePath)),
})

await report.addFromDir(rawDir)
await report.generate()

const coverageMap = istanbulCoverage.createCoverageMap(
  JSON.parse(fs.readFileSync(path.join(outputDir, 'coverage-final.json'), 'utf8')),
)
const coveredSources = new Set(coverageMap.files().map((filename) => path.resolve(filename)))
const missingSources = [...intendedSources].filter((filename) => !coveredSources.has(filename))
const unexpectedSources = [...coveredSources].filter((filename) => !intendedSources.has(filename))
if (missingSources.length || unexpectedSources.length) {
  for (const filename of missingSources) {
    console.error(`Coverage report omitted intended source: ${path.relative(root, filename)}`)
  }
  for (const filename of unexpectedSources) {
    console.error(`Coverage report included unexpected source: ${path.relative(root, filename)}`)
  }
  process.exit(1)
}

const summary = coverageMap.getCoverageSummary().toJSON()
let thresholdFailure = false
for (const metric of ['statements', 'branches', 'functions', 'lines']) {
  const { covered, total } = summary[metric]
  if (covered !== total) {
    console.error(`Coverage threshold for ${metric} was ${covered}/${total}; required exact coverage`)
    thresholdFailure = true
  }
}
if (thresholdFailure) process.exit(1)
