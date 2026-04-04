import { Navigate } from 'react-router-dom'
import useAuthStore from '../store/authStore'
import LoadingVoid from '../components/ui/LoadingVoid'

/**
 * ProtectedRoute — Guards a route by auth state and role.
 *
 * Props:
 *   children     — the page component to render
 *   requiredRole — 'doctor' | 'patient' | undefined (any auth'd user)
 *
 * Behaviour:
 *   • isLoading  → shows <LoadingVoid />
 *   • not logged in → /auth
 *   • wrong role    → /auth
 *   • correct role  → renders children
 */
export default function ProtectedRoute({ children, requiredRole }) {
  const { user, role, isLoading } = useAuthStore()

  if (isLoading) {
    return <LoadingVoid text="verifying access..." />
  }

  if (!user) {
    return <Navigate to="/auth" replace />
  }

  if (requiredRole && role !== requiredRole) {
    return <Navigate to="/auth" replace />
  }

  return children
}
