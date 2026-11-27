import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  LineChart, 
  Wallet, 
  BellRing, 
  Bot,
  LogOut,
  Layers,
  PieChart,
  ShieldCheck
} from 'lucide-react';
import { blockchainApi } from '../../api/blockchain';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../AuthContext';
import { cn } from '../../lib/utils';
import { useLayout } from '../../LayoutContext';

export function Sidebar() {
  const { logout } = useAuth();
  const { sidebarOpen } = useLayout();
  // Phase 10: the vault link appears only when the server turns the feature on.
  const blockchain = useApi('blockchain-status', blockchainApi.status);

  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
    { icon: LineChart, label: 'Watchlist', path: '/watchlist' },
    { icon: Layers, label: 'Sectors', path: '/sectors' },
    { icon: PieChart, label: 'Portfolio plan', path: '/portfolio-plan' },
    { icon: Wallet, label: 'Budgeting', path: '/budget' },
    { icon: BellRing, label: 'Alerts', path: '/alerts' },
    ...(blockchain.data?.enabled ? [{ icon: ShieldCheck, label: 'AI vault', path: '/vault' }] : []),
    { icon: Bot, label: 'AI Advisor', path: '/ai', disabled: true },
  ];

  if (!sidebarOpen) return null;

  return (
    <aside className="fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] w-64 border-r border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] transition-transform sm:translate-x-0">
      <div className="flex h-full flex-col overflow-y-auto px-3 py-4">
        <div className="space-y-2">
          {navItems.map((item) => (
            <div key={item.path}>
              {item.disabled ? (
                <div className="flex items-center rounded-lg p-2 text-sm font-medium text-[var(--color-text-muted)] opacity-50 cursor-not-allowed group">
                  <item.icon className="h-5 w-5 mr-3 shrink-0" />
                  {item.label}
                  <span className="ml-auto text-[10px] uppercase tracking-wider bg-[var(--color-background-tertiary)] px-1.5 py-0.5 rounded">Soon</span>
                </div>
              ) : (
                <NavLink
                  to={item.path}
                  className={({ isActive }: { isActive: boolean }) =>
                    cn(
                      "flex items-center rounded-lg p-2 text-sm font-medium transition-colors interactive-element group",
                      isActive 
                        ? "bg-[var(--color-brand-light)] text-[var(--color-brand)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)]"
                    )
                  }
                >
                  <item.icon className="h-5 w-5 mr-3 shrink-0" />
                  {item.label}
                </NavLink>
              )}
            </div>
          ))}
        </div>

        <div className="mt-auto pt-4 border-t border-[var(--color-border-subtle)] space-y-2">
          <button
            onClick={logout}
            className="flex w-full items-center rounded-lg p-2 text-sm font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-losses-light)] hover:text-[var(--color-losses)] interactive-element group"
          >
            <LogOut className="h-5 w-5 mr-3 shrink-0" />
            Sign Out
          </button>
        </div>
      </div>
    </aside>
  );
}
