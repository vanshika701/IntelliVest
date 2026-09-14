import React, { createContext, useContext, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface LayoutContextType {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  pageTitle: string;
  setPageTitle: (title: string) => void;
}

const LayoutContext = createContext<LayoutContextType | undefined>(undefined);

export function LayoutProvider({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [pageTitle, setPageTitle] = useState('Dashboard');
  const location = useLocation();

  useEffect(() => {
    // Determine page title based on path
    const path = location.pathname;
    if (path.includes('watchlist')) setPageTitle('Watchlist & Markets');
    else if (path.includes('budget')) setPageTitle('Budgeting & Expenses');
    else if (path.includes('alerts')) setPageTitle('Price Alerts');
    else if (path.includes('ai')) setPageTitle('AI Insights');
    else setPageTitle('Dashboard');
  }, [location]);

  return (
    <LayoutContext.Provider value={{ sidebarOpen, setSidebarOpen, pageTitle, setPageTitle }}>
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayout() {
  const context = useContext(LayoutContext);
  if (context === undefined) {
    throw new Error('useLayout must be used within a LayoutProvider');
  }
  return context;
}
