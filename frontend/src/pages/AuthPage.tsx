import React, { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { LogIn, UserPlus } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { useAuth, type User } from '../AuthContext';
import { apiGet, apiPost } from '../api/client';

// apiGet reads its Bearer token from localStorage — the token has to be
// written there before the /me call below, since AuthContext's login()
// (which normally does that write) isn't called until we already have
// the profile to hand it.
function storeTokenForApiClient(token: string) {
  localStorage.setItem('intellivest_token', token);
}

export function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const { user, login } = useAuth();
  const navigate = useNavigate();

  // Redirect if already logged in
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (!isLogin) {
        await apiPost('/api/v1/auth/register', { email, password, full_name: fullName });
        // Fall through to log them in immediately after registration.
      }

      const data = await apiPost<{ access_token: string }>('/api/v1/auth/login', { email, password });
      storeTokenForApiClient(data.access_token);
      const userProfile = await apiGet<User>('/api/v1/auth/me');
      login(data.access_token, userProfile);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-background-primary)] px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8 glass-card p-8 sm:p-10 relative overflow-hidden">
        {/* Decorative background glow */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-[var(--color-brand)] rounded-full mix-blend-screen filter blur-[80px] opacity-20"></div>
        <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-[var(--color-gains)] rounded-full mix-blend-screen filter blur-[80px] opacity-10"></div>
        
        <div className="relative text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-[var(--color-brand)] flex items-center justify-center font-bold text-2xl tracking-tighter text-white shadow-[0_0_20px_rgba(99,102,241,0.6)] mb-6">
            IV
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)]">
            {isLogin ? 'Sign in to your account' : 'Create an account'}
          </h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            {isLogin ? 'Or ' : 'Already have an account? '}
            <button
              onClick={() => {
                setIsLogin(!isLogin);
                setError('');
              }}
              className="font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)] transition-colors"
            >
              {isLogin ? 'create a new account' : 'sign in instead'}
            </button>
          </p>
        </div>

        <form className="mt-8 space-y-6 relative" onSubmit={handleSubmit}>
          {error && (
            <div className="rounded-md bg-[var(--color-losses-light)] border border-[rgba(244,63,94,0.2)] p-4 text-sm text-[var(--color-losses)]">
              {error}
            </div>
          )}

          <div className="space-y-4">
            {!isLogin && (
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  Full Name
                </label>
                <Input
                  required
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="John Doe"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                Email address
              </label>
              <Input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                Password
              </label>
              <Input
                required
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                minLength={8}
              />
            </div>
          </div>

          <Button type="submit" className="w-full h-11 text-base font-medium" disabled={isLoading}>
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
                Processing...
              </span>
            ) : isLogin ? (
              <span className="flex items-center gap-2">
                <LogIn className="h-5 w-5" /> Sign In
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <UserPlus className="h-5 w-5" /> Create Account
              </span>
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
