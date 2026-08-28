import { BrowserRouter, Routes, Route, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { Suspense, lazy, useEffect, useState } from 'react'
import { useGameStore } from './stores/gameStore'
import { LoginPage } from './pages/LoginPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'
import { AdminAccessState } from './components/admin/AdminAccessState'
import { AchievementToast } from './components/AchievementToast'
import { ConnectionBanner } from './components/ConnectionBanner'
import { EncounterCard } from './components/EncounterCard'
import { ErrorBoundary } from './components/ErrorBoundary'
import { checkOnboarding, getMe, type MeResponse } from './services/api'
import { loginPath, safeAuthReturnTo } from './services/authReturnTo'

// Heavy pages are code-split so the login/first-load bundle stays lean:
// GamePage pulls in Phaser (~1.4MB), ProfilePage pulls in @uiw/react-md-editor
// (via ResidentEditor), AdminPage pulls in the whole admin panel tree. These
// pages use named exports, so adapt them to the default export React.lazy wants.
const GamePage = lazy(() => import('./pages/GamePage').then((m) => ({ default: m.GamePage })))
const LandingPage = lazy(() => import('./pages/LandingPage').then((m) => ({ default: m.LandingPage })))
const ForgePage = lazy(() => import('./pages/ForgePage').then((m) => ({ default: m.ForgePage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then((m) => ({ default: m.OnboardingPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })))
const GraphPage = lazy(() => import('./pages/GraphPage').then((m) => ({ default: m.GraphPage })))
const SeasonsPage = lazy(() => import('./pages/SeasonsPage').then((m) => ({ default: m.SeasonsPage })))
const DebatesPage = lazy(() => import('./pages/DebatesPage').then((m) => ({ default: m.DebatesPage })))
const CapsulesPage = lazy(() => import('./pages/CapsulesPage').then((m) => ({ default: m.CapsulesPage })))
const TownPage = lazy(() => import('./pages/TownPage').then((m) => ({ default: m.TownPage })))
const WatchPage = lazy(() => import('./pages/WatchPage').then((m) => ({ default: m.WatchPage })))
const ChallengePage = lazy(() => import('./pages/ChallengePage').then((m) => ({ default: m.ChallengePage })))

function normalizePathname(pathname: string): string {
  if (pathname === '/') return pathname
  return pathname.replace(/\/+$/, '') || '/'
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useGameStore((s) => s.token)
  const { pathname, search, hash } = useLocation()
  if (!token) return <Navigate to={loginPath(`${pathname}${search}${hash}`)} replace />
  return <>{children}</>
}

function AdminRoute() {
  const token = useGameStore((s) => s.token)
  const setAuth = useGameStore((s) => s.setAuth)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{
    token: string
    attempt: number
    user?: MeResponse
    error?: string
  } | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false

    getMe(token)
      .then((user) => {
        if (cancelled || useGameStore.getState().token !== token) return
        setAuth(user, token)
        setResult({ token, attempt, user })
      })
      .catch((reason: unknown) => {
        if (cancelled || useGameStore.getState().token !== token) return
        setResult({
          token,
          attempt,
          error: reason instanceof Error ? reason.message : '无法验证后台权限',
        })
      })

    return () => {
      cancelled = true
    }
  }, [attempt, setAuth, token])

  if (!token || result?.token !== token || result.attempt !== attempt) return <PageFallback />
  if (result.error) {
    return <AdminAccessState kind="verification_error" onRetry={() => setAttempt((value) => value + 1)} />
  }
  if (!result.user?.is_admin) return <AdminAccessState kind="forbidden" />
  return <AdminPage />
}

// Landing directly on "/" (bookmark, closed tab, browser back) skips the
// /login and /onboarding routes' checkOnboarding call entirely, so a player
// who never picked a resident would fall straight into GamePage with the
// default skin (E2E-01). Re-run the same check here before rendering the
// game. Network failures fail OPEN (render GamePage) rather than stranding
// an otherwise-fine player on a spinner.
function HomeRoute() {
  const token = useGameStore((s) => s.token)
  // "Checking" is derived, not stored: the check for the current token is in
  // flight exactly while `checked.token` doesn't match it, so a token change
  // shows the spinner again without any synchronous setState in the effect.
  const [checked, setChecked] = useState<{ token: string; needsOnboarding: boolean } | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    checkOnboarding(token)
      .then((result) => {
        if (!cancelled) setChecked({ token, needsOnboarding: result.needs_onboarding })
      })
      .catch(() => {
        if (!cancelled) setChecked({ token, needsOnboarding: false })
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (!token) return <LandingPage />
  if (checked?.token !== token) return <PageFallback />
  if (checked.needsOnboarding) return <Navigate to="/onboarding" replace />
  return <GamePage />
}

function LoginRoute() {
  const token = useGameStore((s) => s.token)
  const [params] = useSearchParams()
  const requestedNext = params.get('next')
  // Preserve the old authenticated /login -> / behavior when no explicit
  // destination exists, because HomeRoute performs the onboarding check.
  const next = requestedNext ? safeAuthReturnTo(requestedNext, '/') : '/'
  return token ? <Navigate to={next} replace /> : <LoginPage />
}

function PageFallback() {
  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-muted)',
        background: 'var(--bg-page)',
      }}
    >
      加载中…
    </div>
  )
}

function AuthenticatedOverlays() {
  const token = useGameStore((state) => state.token)
  const { pathname } = useLocation()
  const normalizedPath = normalizePathname(pathname)
  if (
    !token
    || normalizedPath === '/login'
    || normalizedPath === '/auth/callback'
    || normalizedPath === '/town'
    || normalizedPath === '/watch'
    || normalizedPath === '/challenge'
  ) return null

  return (
    <>
      <ConnectionBanner />
      <AchievementToast />
      {(normalizedPath === '/' || normalizedPath === '/play') && <EncounterCard />}
    </>
  )
}

export function AppRoutes() {
  return (
    <>
      <AuthenticatedOverlays />
      <ErrorBoundary>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/login" element={<LoginRoute />} />
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            <Route path="/town" element={<TownPage />} />
            <Route path="/watch" element={<WatchPage />} />
            <Route path="/challenge" element={<ChallengePage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/" element={<HomeRoute />} />
            {/* The game also lives at /play — many entry points (landing CTA,
                onboarding redirect, Admin/Forge/ErrorBoundary) navigate here.
                Without this route React Router matches nothing → blank screen. */}
            <Route path="/play" element={<ProtectedRoute><GamePage /></ProtectedRoute>} />
            <Route path="/forge" element={<ProtectedRoute><ForgePage /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute><AdminRoute /></ProtectedRoute>} />
            <Route path="/graph" element={<ProtectedRoute><GraphPage /></ProtectedRoute>} />
            <Route path="/seasons" element={<ProtectedRoute><SeasonsPage /></ProtectedRoute>} />
            <Route path="/debates" element={<ProtectedRoute><DebatesPage /></ProtectedRoute>} />
            <Route path="/capsules" element={<ProtectedRoute><CapsulesPage /></ProtectedRoute>} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
