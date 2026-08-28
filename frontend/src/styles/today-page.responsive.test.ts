/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/styles/today-page.css'), 'utf8')

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{[^}]*\\}`, 'm'))?.[0] ?? ''
}

function mediaSlice(query: string): string {
  const start = css.indexOf(query)
  if (start < 0) return ''
  const next = css.indexOf('@media', start + query.length)
  return css.slice(start, next < 0 ? css.length : next)
}

describe('today-page.css responsive and accessibility contract', () => {
  it('owns a viewport scroll root without permitting page-level horizontal overflow', () => {
    const root = rule('.today-page')
    const shell = rule('.today-page__shell')

    expect(root).toMatch(/height:\s*100dvh/)
    expect(root).toMatch(/overflow-y:\s*auto/)
    expect(root).toMatch(/overflow-x:\s*hidden/)
    expect(root).toMatch(/-webkit-overflow-scrolling:\s*touch/)
    expect(shell).toMatch(/width:\s*min\([^;]*100%[^;]*\)/)
    expect(shell).toMatch(/max-width:\s*100%/)
    expect(shell).toMatch(/min-width:\s*0/)
  })

  it('has a 320px-safe mobile tier that stacks content and choice cards', () => {
    const mobile = mediaSlice('@media (max-width: 760px)')

    expect(mobile).not.toBe('')
    expect(mobile).toMatch(/\.today-page__main\s*\{[^}]*grid-template-columns:\s*1fr/)
    expect(mobile).toMatch(/\.today-choice-grid\s*\{[^}]*grid-template-columns:\s*1fr/)
    expect(mobile).toMatch(/\.today-page__shell\s*\{[^}]*padding(?:-right|-left)?:\s*(?:1[0-6]|[0-9])px/)
    expect(css).toMatch(/\.today-page[^}]*overflow-wrap:\s*anywhere/)
  })

  it('provides visible keyboard focus without relying on color alone', () => {
    expect(css).toMatch(/\.today-page[^,{]*:focus-visible\s*\{/)
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*(?!none)/)
    expect(css).toMatch(/\.today-choice[^}]*:has\([^)]*:checked[^)]*\)/)
  })

  it('disables non-essential motion for reduced-motion users', () => {
    const reduced = mediaSlice('@media (prefers-reduced-motion: reduce)')

    expect(reduced).not.toBe('')
    expect(reduced).toMatch(/\.today-page \*/)
    expect(reduced).toMatch(/animation-duration:\s*0\.01ms|animation:\s*none/)
    expect(reduced).toMatch(/transition-duration:\s*0\.01ms|transition:\s*none/)
    expect(reduced).toMatch(/scroll-behavior:\s*auto/)
  })
})
