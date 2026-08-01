import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

export const root = path.resolve(import.meta.dirname, '..')
export const sourceDir = path.join(root, 'src')
export const compiledDir = path.join(root, '.coverage-src')

const walk = (directory) => fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
  const filename = path.join(directory, entry.name)
  return entry.isDirectory() ? walk(filename) : [filename]
})

export async function buildCoverageSource() {
  fs.rmSync(compiledDir, { force: true, recursive: true })
  const sourceFiles = walk(sourceDir)
    .filter((filename) => /\.(?:ts|tsx)$/.test(filename) && !filename.endsWith('.d.ts'))
    .sort()
  const sourceByCompiledFile = new Map()

  for (const sourceFile of sourceFiles) {
    const relative = path.relative(sourceDir, sourceFile).replace(/\.(?:ts|tsx)$/, '.js')
    const compiledFile = path.join(compiledDir, relative)
    if (sourceByCompiledFile.has(compiledFile)) {
      throw new Error(`Coverage source collision for ${relative}`)
    }
    const transformed = await esbuild.transform(fs.readFileSync(sourceFile, 'utf8'), {
      format: 'esm',
      jsx: 'automatic',
      loader: sourceFile.endsWith('.tsx') ? 'tsx' : 'ts',
      sourcefile: sourceFile,
      sourcemap: 'inline',
      target: 'node22',
    })
    fs.mkdirSync(path.dirname(compiledFile), { recursive: true })
    fs.writeFileSync(compiledFile, transformed.code)
    sourceByCompiledFile.set(compiledFile, sourceFile)
  }

  return sourceByCompiledFile
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildCoverageSource()
}
