import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiGet } from './api/client';

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
        // We temporarily intercept the global fetch to add the token just for this check
        // Real implementation should update the api client to always include this token
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1/auth/me`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        if (res.ok) {
          const userData = await res.json();
          setUser(userData);
        } else {
          // Token invalid or expired
          setToken(null);
          localStorage.removeItem('intellivest_token');
        }
      } catch (e) {
        console.error("Failed to load user profile", e);
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
