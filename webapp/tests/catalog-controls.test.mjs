import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

for (const [name, pagePath, basePath, addPath] of [
  ['product', '../src/app/products/page.tsx', '/products', '/products/new'],
  ['recipe', '../src/app/recipes/page.tsx', '/recipes', '/recipes/new'],
]) {
  test(`${name} catalog hides create and edit navigation from regular sessions`, async () => {
    const source = await readFile(new URL(pagePath, import.meta.url), 'utf8')

    assert.match(source, /const isStaff = session\?\.user\?\.isStaff === true/)
    assert.match(source, /rowHref=\{isStaff \? \(r\) =>/)
    assert.match(source, new RegExp(basePath.replace('/', '\\/')))
    assert.match(source, /addHref=\{isStaff \?/)
    assert.match(source, new RegExp(addPath.replaceAll('/', '\\/')))
  })
}
