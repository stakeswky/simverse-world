import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { AppRoutes } from './App'
import { useGameStore } from './stores/gameStore'
import { checkOnboarding, getMe } from './services/api'

vi.mock('./pages/GamePage', () => ({
  GamePage: () => <main data-testid="game-page">Game World</main>,
}))

vi.mock('./pages/ForgePage', () => ({
  ForgePage: () => <main data-testid="forge-page">Forge</main>,
}))

vi.mock('./pages/OnboardingPage', () => ({
  OnboardingPage: () => <main data-testid="onboarding-page">Onboarding</main>,
}))

vi.mock('./pages/TownPage', () => ({
  TownPage: () => <main data-testid="town-page">Public Town</main>,
}))

vi.mock('./pages/WatchPage', () => ({
  WatchPage: () => <main data-testid="watch-page">Agent Viewer</main>,
}))

vi.mock('./pages/ChallengePage', () => ({
  ChallengePage: () => <main data-testid="challenge-page">WebMCP Challenge</main>,
}))

vi.mock('./pages/TodayPage', () => ({
  TodayPage: () => <main data-testid="today-page">Today</main>,
}))

vi.mock('./pages/AdminPage', () => ({
  AdminPage: () => <main data-testid="admin-page">Admin Console</main>,
}))

// HomeRoute (E2E-01) re-checks onboarding before rendering GamePage so a
// player landing on "/" directly (bookmark, closed tab, browser back) can't
// skip the resident picker. Stub the API call; individual tests override it.
vi.mock('./services/api', () => ({
  checkOnboarding: vi.fn(),
  getMe: vi.fn(),
}))

const user = {
  id: 'user-1',
  name: 'Resident',
  email: 'resident@example.com',
  avatar: null,
  soul_coin_balance: 0,
}

const adminUser = { ...user, is_admin: true }

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="route-location">{`${location.pathname}${location.search}${location.hash}`}</output>
}

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  useGameStore.setState({
    user: null,
    token: null,
    wsStatus: 'connected',
    achievementToast: null,
    pendingEncounter: null,
  })
  // Default: onboarding already completed, so existing authenticated-route
  // tests that don't care about onboarding keep seeing GamePage.
  vi.mocked(checkOnboarding).mockReset().mockResolvedValue({
    needs_onboarding: false,
    player_resident_id: 'resident-1',
  })
  vi.mocked(getMe).mockReset().mockResolvedValue({ ...user, is_admin: false })
  vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'false')
})

afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
  document.body.classList.remove('marketing-page-open', 'auth-page-open')
})

describe('public and authenticated routes', () => {
  it('shows the public landing page at / when logged out', async () => {
    renderRoute('/')
    expect(await screen.findByRole('heading', { level: 1, name: 'Simverse World' })).toBeInTheDocument()
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
  })

  it('shows the game at / when authenticated', async () => {
    useGameStore.setState({ user, token: 'token' })
    renderRoute('/')
    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
  })

  it('redirects authenticated /login visits back to the game', async () => {
    useGameStore.setState({ user, token: 'token' })
    renderRoute('/login')
    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '进入 Simverse' })).not.toBeInTheDocument()
    expect(checkOnboarding).toHaveBeenCalledWith('token')
  })

  it('shows the game at /play when authenticated', async () => {
    useGameStore.setState({ user, token: 'token' })
    renderRoute('/play')
    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
  })

  it('redirects /play to login when logged out', async () => {
    renderRoute('/play')
    expect(await screen.findByRole('heading', { name: '进入 Simverse' })).toBeInTheDocument()
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
  })

  it('redirects a logged-out /today visit to login with the complete return path', async () => {
    renderRoute('/today?entry=return#decision')

    expect(await screen.findByRole('heading', { name: '进入 Simverse' })).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      '/login?next=%2Ftoday%3Fentry%3Dreturn%23decision',
    )
    expect(screen.queryByTestId('today-page')).not.toBeInTheDocument()
  })

  it('exposes /town, /watch, and /challenge without a player login', async () => {
    const town = renderRoute('/town')
    expect(await screen.findByTestId('town-page')).toBeInTheDocument()
    town.unmount()

    renderRoute('/watch')
    expect(await screen.findByTestId('watch-page')).toBeInTheDocument()
    cleanup()

    renderRoute('/challenge')
    expect(await screen.findByTestId('challenge-page')).toBeInTheDocument()
  })

  it('normalizes trailing-slash spectator routes without mounting gameplay overlays', async () => {
    useGameStore.setState({
      user,
      token: 'token',
      wsStatus: 'reconnecting',
      achievementToast: { code: 'first', title: 'Hidden Achievement', reward_sc: 5 },
      pendingEncounter: { resident_slug: 'mei', resident_name: '梅', location_id: 'square', opener: '不应显示' },
    })

    const town = renderRoute('/town/')
    expect(await screen.findByTestId('town-page')).toBeInTheDocument()
    expect(screen.queryByText('连接已断开，正在重连…')).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden Achievement')).not.toBeInTheDocument()
    expect(screen.queryByText('不应显示')).not.toBeInTheDocument()
    town.unmount()

    renderRoute('/watch/')
    expect(await screen.findByTestId('watch-page')).toBeInTheDocument()
    expect(screen.queryByText('连接已断开，正在重连…')).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden Achievement')).not.toBeInTheDocument()
    expect(screen.queryByText('不应显示')).not.toBeInTheDocument()
    cleanup()

    renderRoute('/challenge/')
    expect(await screen.findByTestId('challenge-page')).toBeInTheDocument()
    expect(screen.queryByText('连接已断开，正在重连…')).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden Achievement')).not.toBeInTheDocument()
    expect(screen.queryByText('不应显示')).not.toBeInTheDocument()
  })

  it('does not mount authenticated gameplay overlays over spectator routes', async () => {
    useGameStore.setState({
      user,
      token: 'token',
      wsStatus: 'reconnecting',
      achievementToast: { code: 'first', title: 'Hidden Achievement', reward_sc: 5 },
    })
    renderRoute('/town')
    expect(await screen.findByTestId('town-page')).toBeInTheDocument()
    expect(screen.queryByText('连接已断开，正在重连…')).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden Achievement')).not.toBeInTheDocument()
  })

  it('shows encounter cards only on the authenticated game route', async () => {
    useGameStore.setState({
      user,
      token: 'token',
      pendingEncounter: { resident_slug: 'mei', resident_name: '梅', location_id: 'square', opener: '只在游戏里显示' },
    })

    const game = renderRoute('/')
    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.getByText('只在游戏里显示')).toBeInTheDocument()
    game.unmount()

    renderRoute('/forge')
    expect(await screen.findByTestId('forge-page')).toBeInTheDocument()
    expect(screen.queryByText('只在游戏里显示')).not.toBeInTheDocument()
  })

  it('does not leak gameplay overlays onto public pages', async () => {
    useGameStore.setState({
      wsStatus: 'reconnecting',
      achievementToast: { code: 'first', title: 'First Visit', reward_sc: 5 },
      pendingEncounter: { resident_slug: 'mei', resident_name: '梅', location_id: 'square', opener: '你好' },
    })
    renderRoute('/')
    await screen.findByRole('heading', { level: 1, name: 'Simverse World' })
    expect(screen.queryByText('连接已断开，正在重连…')).not.toBeInTheDocument()
    expect(screen.queryByText('First Visit')).not.toBeInTheDocument()
    expect(screen.queryByText('你好')).not.toBeInTheDocument()
  })
})

describe('admin route authorization', () => {
  it('sends a logged-out visitor to login with /admin as the return destination', async () => {
    renderRoute('/admin')

    expect(await screen.findByRole('heading', { name: '进入 Simverse' })).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/login?next=%2Fadmin')
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
  })

  it('keeps a stale cached admin candidate on /admin until live identity confirms access', async () => {
    let resolveIdentity!: (value: typeof adminUser) => void
    vi.mocked(getMe).mockReturnValue(new Promise((resolve) => { resolveIdentity = resolve }))
    useGameStore.setState({ user: { ...user, is_admin: false }, token: 'admin-token' })

    renderRoute('/admin')

    expect(screen.getByText('加载中…')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()

    resolveIdentity(adminUser)

    expect(await screen.findByTestId('admin-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
    expect(useGameStore.getState().user?.is_admin).toBe(true)
    expect(getMe).toHaveBeenCalledWith('admin-token')
  })

  it('recovers an admin session when the cached user record is missing', async () => {
    vi.mocked(getMe).mockResolvedValue(adminUser)
    useGameStore.setState({ user: null, token: 'admin-token' })

    renderRoute('/admin')

    expect(await screen.findByTestId('admin-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
  })

  it('shows a fail-closed permission page for a confirmed non-admin without navigating to /play', async () => {
    vi.mocked(getMe).mockResolvedValue({ ...user, is_admin: false })
    useGameStore.setState({ user: adminUser, token: 'resident-token' })

    renderRoute('/admin')

    expect(await screen.findByRole('heading', { name: '没有后台管理权限' })).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
  })

  it('keeps network verification failures on a retryable safe page', async () => {
    vi.mocked(getMe)
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(adminUser)
    useGameStore.setState({ user: adminUser, token: 'admin-token' })

    renderRoute('/admin')

    expect(await screen.findByRole('heading', { name: '暂时无法验证后台权限' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新验证' })).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新验证' }))
    expect(await screen.findByTestId('admin-page')).toBeInTheDocument()
    expect(getMe).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
  })

  it('returns an expired session to login while retaining /admin', async () => {
    vi.mocked(getMe).mockImplementation(async () => {
      useGameStore.getState().logout()
      throw new Error('Session expired')
    })
    useGameStore.setState({ user: adminUser, token: 'expired-token' })

    renderRoute('/admin')

    expect(await screen.findByRole('heading', { name: '进入 Simverse' })).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/login?next=%2Fadmin')
  })

  it('honors an authenticated login return destination and revalidates admin access', async () => {
    vi.mocked(getMe).mockResolvedValue(adminUser)
    useGameStore.setState({ user: { ...user, is_admin: false }, token: 'admin-token' })

    renderRoute('/login?next=%2Fadmin')

    expect(await screen.findByTestId('admin-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/admin')
  })
})

// E2E-01: landing directly on "/" (bookmark, closed tab, browser back) used
// to skip onboarding entirely because HomeRoute never asked. It now re-runs
// the same checkOnboarding call the /onboarding route makes.
describe('HomeRoute onboarding gate', () => {
  it('redirects to /onboarding when the backend says onboarding is needed', async () => {
    vi.mocked(checkOnboarding).mockResolvedValue({ needs_onboarding: true, player_resident_id: null })
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('onboarding-page')).toBeInTheDocument()
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
    expect(checkOnboarding).toHaveBeenCalledWith('token')
  })

  it('renders the game when the backend says onboarding is already done', async () => {
    vi.mocked(checkOnboarding).mockResolvedValue({ needs_onboarding: false, player_resident_id: 'resident-1' })
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.queryByTestId('onboarding-page')).not.toBeInTheDocument()
  })

  it('fails open into the game when the onboarding check errors', async () => {
    vi.mocked(checkOnboarding).mockRejectedValue(new Error('network error'))
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    // Must not strand the player on the loading fallback just because the
    // network call failed — fail open rather than fail closed.
    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.queryByTestId('onboarding-page')).not.toBeInTheDocument()
  })

  it('does not flash the game before the onboarding check resolves', async () => {
    let resolveCheck!: (v: { needs_onboarding: boolean; player_resident_id: string | null }) => void
    vi.mocked(checkOnboarding).mockReturnValue(
      new Promise((resolve) => { resolveCheck = resolve })
    )
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    // While the check is in flight, neither the game nor onboarding should render.
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('onboarding-page')).not.toBeInTheDocument()

    resolveCheck({ needs_onboarding: true, player_resident_id: null })

    expect(await screen.findByTestId('onboarding-page')).toBeInTheDocument()
  })

  it('keeps the legacy game home when the Living Loop entry flag is off', async () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'false')
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.queryByTestId('today-page')).not.toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/')
  })

  it('routes an onboarded authenticated user from / to /today when the entry flag is on', async () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'true')
    vi.mocked(checkOnboarding).mockResolvedValue({
      needs_onboarding: false,
      player_resident_id: 'resident-1',
    })
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('today-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/today')
    expect(screen.queryByTestId('game-page')).not.toBeInTheDocument()
  })

  it('preserves /today through onboarding when the entry flag is on', async () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'true')
    vi.mocked(checkOnboarding).mockResolvedValue({
      needs_onboarding: true,
      player_resident_id: null,
    })
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('onboarding-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      '/onboarding?next=%2Ftoday',
    )
    expect(screen.queryByTestId('today-page')).not.toBeInTheDocument()
  })

  it('guards a direct authenticated /today visit with onboarding and preserves its return path', async () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'true')
    vi.mocked(checkOnboarding).mockResolvedValue({
      needs_onboarding: true,
      player_resident_id: null,
    })
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/today')

    expect(await screen.findByTestId('onboarding-page')).toBeInTheDocument()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      '/onboarding?next=%2Ftoday',
    )
  })

  it('fails open to the legacy game when the onboarding check fails with the entry flag on', async () => {
    vi.stubEnv('VITE_LIVING_LOOP_P0_ENABLED', 'true')
    vi.mocked(checkOnboarding).mockRejectedValue(new Error('network down'))
    useGameStore.setState({ user, token: 'token' })

    renderRoute('/')

    expect(await screen.findByTestId('game-page')).toBeInTheDocument()
    expect(screen.queryByTestId('today-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('onboarding-page')).not.toBeInTheDocument()
  })
})
