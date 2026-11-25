import React, { useId, useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { CalendarCheck, KeyRound, LogIn, UserPlus } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { FieldError } from '../components/ui/FieldError';
import { Input } from '../components/ui/Input';
import { useAuth, type User } from '../AuthContext';
import { apiGet, apiPost, apiPut } from '../api/client';
import { validateBirthDate, validateEmail, validateName, validateNewPassword } from '../lib/validation';

// apiGet reads its Bearer token from localStorage — the token has to be
// written there before the /me call below, since AuthContext's login()
// (which normally does that write) isn't called until we already have
// the profile to hand it.
function storeTokenForApiClient(token: string) {
  localStorage.setItem('intellivest_token', token);
}

type Mode = 'login' | 'register' | 'reset' | 'birthdate';

const COPY = {
  login: { title: 'Sign in to your account', submit: 'Sign In', Icon: LogIn },
  register: { title: 'Create an account', submit: 'Create Account', Icon: UserPlus },
  reset: { title: 'Reset your password', submit: 'Reset Password', Icon: KeyRound },
  birthdate: { title: 'One more step', submit: 'Save', Icon: CalendarCheck },
} as const;

/** Today in local time, as the date input expects it. */
function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function Field({ label, error, ...props }: { label: string; error?: string | null } & React.InputHTMLAttributes<HTMLInputElement>) {
  const errorId = useId();
  return (
    <div>
      <label className="block">
        <span className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">{label}</span>
        <Input required aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} {...props} />
      </label>
      <FieldError id={errorId} message={error} />
    </div>
  );
}

export function AuthPage() {
  const [formMode, setFormMode] = useState<'login' | 'register' | 'reset'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fullName, setFullName] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);

  const { user, token, login, logout, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();

  if (authLoading) return null;
  if (user?.has_date_of_birth) {
    return <Navigate to="/dashboard" replace />;
  }
  // Accounts made before sign-up asked for a date of birth add it here.
  const mode: Mode = user ? 'birthdate' : formMode;
  const { title, submit, Icon } = COPY[mode];

  const choosesPassword = mode === 'register' || mode === 'reset';
  const errors: Record<string, string | null> = {
    name: mode === 'register' ? validateName(fullName) : null,
    email: mode !== 'birthdate' ? validateEmail(email) : null,
    birthDate: mode !== 'login' ? validateBirthDate(birthDate, todayIso()) : null,
    password: choosesPassword ? validateNewPassword(password) : mode === 'login' && !password ? 'Enter your password' : null,
    confirm: mode === 'reset' && password !== confirm ? "The passwords don't match." : null,
  };
  /** Errors show once the user has filled in and left the field, or tried to submit. */
  const check = (field: string) => ({
    error: submitted || touched[field] ? errors[field] : null,
    onBlur: (e: React.FocusEvent<HTMLInputElement>) => {
      if (e.target.value) setTouched((prev) => ({ ...prev, [field]: true }));
    },
  });

  const switchTo = (next: typeof formMode) => {
    setFormMode(next);
    setError('');
    setNotice('');
    setPassword('');
    setConfirm('');
    setBirthDate('');
    setTouched({});
    setSubmitted(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setSubmitted(true);
    if (Object.values(errors).some(Boolean)) return;
    const cleanEmail = email.trim();
    setIsLoading(true);

    try {
      if (mode === 'birthdate') {
        await apiPut<void>('/api/v1/auth/date-of-birth', { date_of_birth: birthDate });
        login(token!, { ...user!, has_date_of_birth: true });
        navigate('/dashboard');
        return;
      }
      if (mode === 'reset') {
        await apiPost<void>('/api/v1/auth/reset-password', { email: cleanEmail, date_of_birth: birthDate, new_password: password });
        switchTo('login');
        setNotice('Password changed. Sign in with your new password.');
        return;
      }
      if (mode === 'register') {
        await apiPost('/api/v1/auth/register', { email: cleanEmail, password, full_name: fullName.trim(), date_of_birth: birthDate });
        // Fall through to log them in immediately after registration.
      }

      const data = await apiPost<{ access_token: string }>('/api/v1/auth/login', { email: cleanEmail, password });
      storeTokenForApiClient(data.access_token);
      const userProfile = await apiGet<User>('/api/v1/auth/me');
      login(data.access_token, userProfile);
      setBirthDate('');
      setSubmitted(false);
      if (userProfile.has_date_of_birth) navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  const linkClass = 'font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)] transition-colors';

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-background-primary)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8 glass-card p-8 sm:p-10 relative overflow-hidden">
        {/* Decorative background glow */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-[var(--color-brand)] rounded-full mix-blend-screen filter blur-[80px] opacity-20"></div>
        <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-[var(--color-gains)] rounded-full mix-blend-screen filter blur-[80px] opacity-10"></div>

        <div className="relative text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-[var(--color-brand)] flex items-center justify-center font-bold text-2xl tracking-tighter text-white shadow-[0_0_20px_rgba(99,102,241,0.6)] mb-6">
            IV
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)]">{title}</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            {mode === 'birthdate' ? (
              'Add your date of birth so you can reset your password if you forget it. It can only be set once.'
            ) : mode === 'reset' ? (
              'Enter the date of birth you signed up with.'
            ) : (
              <>
                {mode === 'login' ? 'Or ' : 'Already have an account? '}
                <button type="button" onClick={() => switchTo(mode === 'login' ? 'register' : 'login')} className={linkClass}>
                  {mode === 'login' ? 'create a new account' : 'sign in instead'}
                </button>
              </>
            )}
          </p>
        </div>

        <form className="mt-8 space-y-6 relative" noValidate onSubmit={handleSubmit}>
          {error && (
            <div role="alert" className="rounded-md bg-[var(--color-losses-light)] border border-[rgba(244,63,94,0.2)] p-4 text-sm text-[var(--color-losses)]">
              {error}
            </div>
          )}
          {notice && (
            <div role="status" className="rounded-md bg-[var(--color-background-tertiary)] border border-[var(--color-border-strong)] p-4 text-sm text-[var(--color-gains)]">
              {notice}
            </div>
          )}

          <div className="space-y-4">
            {mode === 'register' && (
              <Field {...check('name')} label="Full Name" maxLength={120} type="text" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="John Doe" />
            )}
            {mode !== 'birthdate' && (
              <Field {...check('email')} label="Email address" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            )}
            {mode !== 'login' && (
              <Field {...check('birthDate')} label="Date of birth" type="date" autoComplete="bday" min="1900-01-01" max={todayIso()} value={birthDate} onChange={(e) => setBirthDate(e.target.value)} className="[color-scheme:dark]" />
            )}
            {mode !== 'birthdate' && (
              <div>
                <Field
                  {...check('password')}
                  label={mode === 'reset' ? 'New password' : 'Password'}
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
                {mode === 'login' && (
                  <div className="mt-2 text-right text-sm">
                    <button type="button" onClick={() => switchTo('reset')} className={linkClass}>
                      Forgot password?
                    </button>
                  </div>
                )}
              </div>
            )}
            {mode === 'reset' && (
              <Field {...check('confirm')} label="Confirm new password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="••••••••" />
            )}
          </div>

          <Button type="submit" className="w-full h-11 text-base font-medium" disabled={isLoading}>
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
                Processing...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Icon className="h-5 w-5" /> {submit}
              </span>
            )}
          </Button>

          {(mode === 'reset' || mode === 'birthdate') && (
            <div className="text-center text-sm">
              <button type="button" onClick={() => (mode === 'reset' ? switchTo('login') : logout())} className={linkClass}>
                {mode === 'reset' ? 'Back to sign in' : 'Sign out'}
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
