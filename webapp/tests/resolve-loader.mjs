import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(import.meta.dirname, '..')
const sourceDir = path.join(root, 'src')
const compiledDir = path.join(root, '.coverage-src')

const compiledForSource = (sourceFile) => path.join(
  compiledDir,
  path.relative(sourceDir, sourceFile).replace(/\.(?:ts|tsx)$/, '.js'),
)

const findSource = (base) => ['.ts', '.tsx', '.js', '.jsx']
  .map((extension) => `${base}${extension}`)
  .find(fs.existsSync)

const compiledUrl = (sourceFile) => ({
  url: pathToFileURL(compiledForSource(sourceFile)).href,
  shortCircuit: true,
})

export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'next/navigation') return nextResolve('next/navigation.js', context)
  if (specifier === 'next/link') return nextResolve('next/link.js', context)
  if (specifier === 'next/font/google') return nextResolve('next/font/google/index.js', context)
  if (specifier.endsWith('.css')) return { url: 'coverage:css', shortCircuit: true }

  if (specifier.startsWith('@/')) {
    const sourceFile = findSource(path.join(sourceDir, specifier.slice(2)))
    if (sourceFile) return compiledUrl(sourceFile)
  }

  if (context.parentURL?.startsWith(pathToFileURL(compiledDir).href)) {
    const parentFile = fileURLToPath(context.parentURL)
    const resolved = path.resolve(path.dirname(parentFile), specifier)
    const compiledFile = path.extname(resolved) ? resolved.replace(/\.(?:ts|tsx)$/, '.js') : `${resolved}.js`
    if (fs.existsSync(compiledFile)) {
      return { url: pathToFileURL(compiledFile).href, shortCircuit: true }
    }
  }

  if ((specifier.startsWith('./') || specifier.startsWith('../')) && context.parentURL?.startsWith('file:')) {
    const resolved = fileURLToPath(new URL(specifier, context.parentURL))
    if (resolved.startsWith(sourceDir)) {
      const sourceFile = /\.(?:ts|tsx)$/.test(resolved) ? resolved : findSource(resolved)
      if (sourceFile) return compiledUrl(sourceFile)
    }
  }

  return nextResolve(specifier, context)
}

export async function load(url, context, nextLoad) {
  if (url === 'coverage:css') {
    return { format: 'module', source: 'export default {}', shortCircuit: true }
  }
  if (url.startsWith(pathToFileURL(compiledDir).href)) {
    return { format: 'module', source: fs.readFileSync(fileURLToPath(url), 'utf8'), shortCircuit: true }
  }
  return nextLoad(url, context)
}
