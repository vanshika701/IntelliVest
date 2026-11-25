import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import { AuthProvider } from './AuthContext'
import { LayoutProvider } from './LayoutContext'
import { AppShell } from './components/layout/AppShell'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { WatchlistPage } from './pages/WatchlistPage'
import { BudgetingPage } from './pages/BudgetingPage'
import { AlertsPage } from './pages/AlertsPage'
import { InstrumentPage } from './pages/InstrumentPage'
import { InvestmentsPage } from './pages/InvestmentsPage'
import { SearchPage } from './pages/SearchPage'
import { SectorsPage } from './pages/SectorsPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <LayoutProvider>
          <Routes>
            <Route path="/auth" element={<AuthPage />} />
            
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/watchlist" element={<WatchlistPage />} />
                <Route path="/budget" element={<BudgetingPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/instrument/:id" element={<InstrumentPage />} />
                <Route path="/investments" element={<InvestmentsPage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/sectors" element={<SectorsPage />} />
                
                {/* Fallback to dashboard */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Route>
            
          </Routes>
        </LayoutProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
