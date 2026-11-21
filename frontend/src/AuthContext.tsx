import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiGet, ApiError } from './api/client';

export interface User {
  id: string;
  email: string;
  full_name: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('intellivest_token'));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadUser() {
      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        // apiGet already attaches the token from localStorage (see
        // api/client.ts's getDefaultHeaders) — no need to duplicate that
        // here with a manual fetch + Authorization header.
        const userData = await apiGet<User>('/api/v1/auth/me');
        setUser(userData);
      } catch (e) {
        if (e instanceof ApiError) {
          // Token invalid or expired — clear it so ProtectedRoute
          // redirects to /auth instead of retrying forever.
          setToken(null);
          localStorage.removeItem('intellivest_token');
        } else {
          // A network hiccup isn't proof the token is bad — don't log
          // the user out just because a request failed to go through.
          console.error('Failed to load user profile', e);
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadUser();
  }, [token]);

  const login = (newToken: string, userProfile: User) => {
    setToken(newToken);
    setUser(userProfile);
    localStorage.setItem('intellivest_token', newToken);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('intellivest_token');
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
