import { useEffect, useRef, useState } from 'react';
import { Bell, Menu, UserCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../AuthContext';
import { useLayout } from '../../LayoutContext';
import { apiGet } from '../../api/client';

interface Alert {
  id: string;
  ticker: string;
  condition: string;
  target_price: number;
  triggered: boolean;
}

export function Navbar() {
  const { user } = useAuth();
  const { sidebarOpen, setSidebarOpen, pageTitle } = useLayout();

  const [triggeredAlerts, setTriggeredAlerts] = useState<Alert[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const notificationsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function loadTriggeredAlerts() {
      try {
        const alerts = await apiGet<Alert[]>('/api/v1/alerts');
        setTriggeredAlerts(alerts.filter((a) => a.triggered));
      } catch {
        // Non-critical — the bell just stays empty if this fails.
      }
    }
    loadTriggeredAlerts();
    // Alerts are evaluated server-side every 5 minutes; polling a bit
    // more often than that keeps the bell reasonably fresh without
    // hammering the API.
    const interval = setInterval(loadTriggeredAlerts, 60_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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

            <div className="relative" ref={notificationsRef}>
              <button
                onClick={() => setShowNotifications((v) => !v)}
                className="relative inline-flex items-center rounded-md p-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] interactive-element"
              >
                <span className="sr-only">Notifications</span>
                <Bell className="h-5 w-5" />
                {triggeredAlerts.length > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-losses)] text-[10px] font-bold text-white">
                    {triggeredAlerts.length > 9 ? '9+' : triggeredAlerts.length}
                  </span>
                )}
              </button>

              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] shadow-2xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-[var(--color-border-subtle)]">
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      Triggered Alerts
                    </h3>
                  </div>
                  {triggeredAlerts.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
                      No triggered alerts right now.
                    </p>
                  ) : (
                    <ul className="max-h-72 overflow-y-auto divide-y divide-[var(--color-border-subtle)]">
                      {triggeredAlerts.map((alert) => (
                        <li key={alert.id} className="px-4 py-3 text-sm">
                          <span className="font-medium text-[var(--color-text-primary)]">{alert.ticker}</span>{' '}
                          <span className="text-[var(--color-text-secondary)]">
                            {alert.condition === 'above' ? 'crossed above' : alert.condition === 'below' ? 'dropped below' : 'is within range of'}{' '}
                            ₹{alert.target_price.toLocaleString()}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <Link
                    to="/alerts"
                    onClick={() => setShowNotifications(false)}
                    className="block px-4 py-3 text-center text-sm font-medium text-[var(--color-brand)] hover:bg-[var(--color-background-tertiary)] border-t border-[var(--color-border-subtle)]"
                  >
                    Manage alerts
                  </Link>
                </div>
              )}
            </div>

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
