import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useGameStore } from './stores/gameStore'
import { LoginPage } from './pages/LoginPage'
import { GamePage } from './pages/GamePage'

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
        <Route path="/" element={<ProtectedRoute><GamePage /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
