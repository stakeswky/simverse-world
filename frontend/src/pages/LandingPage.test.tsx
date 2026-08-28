import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { LandingPage } from './LandingPage'

afterEach(() => {
  cleanup()
  document.body.classList.remove('marketing-page-open')
})

describe('LandingPage', () => {
  it('leads with the Living Loop promise and preserves /today through login', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Simverse World' })).toBeInTheDocument()
    expect(screen.getByText('你离开后，小镇仍在生活；你回来后，每个选择都会留下痕迹。')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /看看今天发生了什么/ })).toHaveAttribute(
      'href',
      '/login?next=%2Ftoday',
    )
    expect(screen.getAllByRole('link', { name: /观看小镇实况|观察小镇/ })[0]).toHaveAttribute('href', '/town')
    expect(screen.getByRole('heading', { level: 2, name: /不是 NPC/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: /给一个名字/ })).toBeInTheDocument()
  })

  it('exposes an accessible mobile navigation toggle', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    const menuButton = screen.getByRole('button', { name: '打开导航菜单' })
    expect(menuButton).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(menuButton)
    expect(screen.getByRole('button', { name: '关闭导航菜单' })).toHaveAttribute('aria-expanded', 'true')
  })
})
