import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

export function ProtectedRoute() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-background-primary)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 border-4 border-[var(--color-brand-light)] border-t-[var(--color-brand)] rounded-full animate-spin"></div>
          <p className="text-[var(--color-text-secondary)] font-medium text-sm">Initializing application...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/auth" replace />;
  }

  return <Outlet />;
}
