import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useGameStore } from './stores/gameStore'
import { LoginPage } from './pages/LoginPage'
import { GamePage } from './pages/GamePage'
import { ForgePage } from './pages/ForgePage'
import { ProfilePage } from './pages/ProfilePage'
import { OnboardingPage } from './pages/OnboardingPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useGameStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/onboarding" element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>} />
        <Route path="/" element={<ProtectedRoute><GamePage /></ProtectedRoute>} />
        <Route path="/forge" element={<ProtectedRoute><ForgePage /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
