import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { useLayout } from '../../LayoutContext';
import { cn } from '../../lib/utils';

export function AppShell() {
  const { sidebarOpen } = useLayout();

  return (
    <div className="min-h-screen bg-[var(--color-background-primary)]">
      <Navbar />
      <Sidebar />
      <main
        className={cn(
          "pt-16 transition-all duration-300 ease-in-out",
          sidebarOpen ? "sm:ml-64" : "ml-0"
        )}
      >
        <div className="p-4 sm:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
