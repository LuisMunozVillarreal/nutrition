import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const sourceRoot = path.join(root, 'src')
const metrics = ['statements', 'branches', 'functions', 'lines']

function walkSource(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(directory, entry.name)
    if (entry.isDirectory()) return walkSource(filename)
    return /\.(?:ts|tsx)$/.test(filename) && !filename.endsWith('.d.ts') ? [path.resolve(filename)] : []
  })
}

export default class ExactCoverageReporter {
  onCoverage(coverageMap) {
    const intendedFiles = new Set(walkSource(sourceRoot))
    const reportedFiles = new Set(coverageMap.files().map((filename) => path.resolve(filename)))
    const missingFiles = [...intendedFiles].filter((filename) => !reportedFiles.has(filename)).sort()
    const extraFiles = [...reportedFiles].filter((filename) => !intendedFiles.has(filename)).sort()

    const errors = [
      ...missingFiles.map((filename) => `Coverage report omitted intended source: ${path.relative(root, filename)}`),
      ...extraFiles.map((filename) => `Coverage report included unexpected source: ${path.relative(root, filename)}`),
    ]

    const summary = coverageMap.getCoverageSummary().toJSON()
    for (const metric of metrics) {
      const { covered, total } = summary[metric]
      if (covered !== total) {
        errors.push(`Exact coverage for ${metric} was ${covered}/${total}; required covered === total`)
      }
    }

    if (errors.length) throw new Error(errors.join('\n'))

    const totals = metrics.map((metric) => {
      const { covered, total } = summary[metric]
      return `${metric} ${covered}/${total}`
    }).join(', ')
    console.log(`Exact coverage verified for ${intendedFiles.size} source files: ${totals}`)
  }
}
