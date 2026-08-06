import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

const readSource = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('authenticated mobile pages expose an accessible home bar and closable navigation drawer', async () => {
  const [shellSource, sidebarSource, styles] = await Promise.all([
    readSource('../src/components/AppShell.tsx'),
    readSource('../src/components/Sidebar.tsx'),
    readSource('../src/app/globals.css'),
  ])

  assert.match(shellSource, /<Sidebar \/>/)
  assert.match(shellSource, /<main className="main-content p-6 md:p-10" tabIndex=\{-1\}>/)
  assert.match(sidebarSource, /className="mobile-header"/)
  assert.match(sidebarSource, /href="\/"/)
  assert.match(sidebarSource, /aria-label="Go to dashboard"/)
  assert.match(sidebarSource, /aria-label="Open navigation menu"/)
  assert.match(sidebarSource, /aria-expanded=\{menuOpen\}/)
  assert.match(sidebarSource, /aria-controls="primary-navigation"/)
  assert.match(sidebarSource, /event\.key === 'Escape'/)
  assert.match(sidebarSource, /event\.key === 'Tab'/)
  assert.match(sidebarSource, /drawerRef\.current!\.querySelectorAll/)
  assert.match(sidebarSource, /menuButtonRef\.current\?\.focus\(\)/)
  assert.match(sidebarSource, /window\.matchMedia\('\(max-width: 768px\)'\)/)
  assert.match(sidebarSource, /if \(!menuOpen \|\| !authenticated\) return/)
  assert.match(sidebarSource, /mainContent\?\.setAttribute\('inert', ''\)/)
  assert.match(sidebarSource, /mobileHeader\?\.setAttribute\('inert', ''\)/)
  assert.match(sidebarSource, /focusMainContent\(\)/)
  assert.match(sidebarSource, /className=\{`sidebar-overlay \$\{menuOpen \? 'open' : ''\}`\}/)

  assert.match(sidebarSource, /id="primary-navigation"/)
  assert.match(sidebarSource, /aria-label="Primary navigation"/)
  assert.match(sidebarSource, /className=\{`sidebar \$\{menuOpen \? 'open' : ''\}`\}/)
  assert.match(sidebarSource, /aria-label="Close navigation menu"/)
  assert.match(sidebarSource, /onClick=\{closeMenu\}/)

  assert.match(styles, /\.mobile-header,[\s\S]*\.sidebar-overlay\s*\{[^}]*display:\s*none/s)
  assert.match(styles, /@media \(max-width: 768px\)[\s\S]*\.mobile-header\s*\{[^}]*display:\s*flex/s)
  assert.match(styles, /\.sidebar\.open\s*\{[^}]*transform:\s*translateX\(0\)/s)
  assert.match(styles, /\.sidebar-overlay\.open\s*\{[^}]*display:\s*block/s)
  assert.match(styles, /\.main-content\s*\{[^}]*padding-top:/s)
})

test('mobile navigation has a browser-level Cypress acceptance scenario', async () => {
  const [feature, steps] = await Promise.all([
    readSource('../cypress/e2e/measurements.feature'),
    readSource('../cypress/support/step_definitions/measurements.ts'),
  ])

  assert.match(feature, /Scenario: Navigate away from measurements on a phone/)
  assert.match(feature, /When I open the mobile navigation/)
  assert.match(feature, /When I close the mobile navigation with Escape/)
  assert.match(feature, /Then the mobile menu button should have focus/)
  assert.match(feature, /And I choose Plans from the mobile navigation/)
  assert.match(feature, /Then I should be on the plans page with the mobile navigation closed/)
  assert.match(steps, /cy\.viewport\(375, 667\)/)
  assert.match(steps, /aria-expanded.*true/)
  assert.match(steps, /trigger\("keydown", \{ key: "Escape" \}\)/)
  assert.match(steps, /and\("be\.focused"\)/)
  assert.match(steps, /cy\.get\("\.main-content"\)\.should\("be\.focused"\)/)
})
