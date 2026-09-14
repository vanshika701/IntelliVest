import React from 'react';
import { Menu, UserCircle } from 'lucide-react';
import { useAuth } from '../../AuthContext';
import { useLayout } from '../../LayoutContext';

export function Navbar() {
  const { user } = useAuth();
  const { sidebarOpen, setSidebarOpen, pageTitle } = useLayout();

  return (
    <nav className="fixed top-0 z-50 w-full border-b border-[var(--color-border-subtle)] bg-[var(--color-background-primary)] backdrop-blur-md">
      <div className="px-4 pr-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center justify-start flex-1">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="inline-flex items-center rounded-md p-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] mr-2 interactive-element"
            >
              <span className="sr-only">Open sidebar</span>
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center">
              <div className="h-8 w-8 rounded-lg bg-[var(--color-brand)] mr-3 flex items-center justify-center font-bold tracking-tighter text-white shadow-[0_0_15px_rgba(99,102,241,0.5)]">
                IV
              </div>
              <span className="self-center whitespace-nowrap text-lg font-semibold tracking-tight text-white hidden sm:block mr-8">
                IntelliVest<span className="text-[var(--color-brand)]">.ai</span>
              </span>
              
              <div className="h-6 w-px bg-[var(--color-border-strong)] mx-4 hidden sm:block"></div>
              
              <h1 className="text-[var(--color-text-primary)] font-medium text-sm sm:text-base tracking-wide flex items-center">
                {pageTitle}
              </h1>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Future: Marquee or Global Stock Search can go here */}
            
            <div className="flex items-center gap-3 bg-[var(--color-background-secondary)] px-3 py-1.5 rounded-full border border-[var(--color-border-subtle)]">
              <UserCircle className="h-5 w-5 text-[var(--color-text-secondary)]" />
              <div className="flex flex-col hidden sm:block">
                <span className="text-xs font-medium text-[var(--color-text-primary)] leading-none mb-1">
                  {user?.full_name || 'Loading...'}
                </span>
                <span className="text-[10px] text-[var(--color-text-muted)] leading-none">
                  {user?.email || ''}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
