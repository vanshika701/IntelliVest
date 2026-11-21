import { useEffect, useState } from 'react';
import { Newspaper, BellRing, TrendingUp, TrendingDown, Clock, ArrowRight, LineChart } from 'lucide-react';
import { apiGet } from '../api/client';
import { cn } from '../lib/utils';
import { Link } from 'react-router-dom';

interface DashboardData {
  watchlist: any[];
  budget_summary: {
    total_income: number;
    total_expense: number;
    net: number;
    by_category: Record<string, number>;
  };
  active_alerts: any[];
  triggered_alerts: any[];
  recent_news: any[];
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await apiGet<DashboardData>('/api/v1/dashboard');
        setData(result);
      } catch (e) {
        console.error('Failed to load dashboard', e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 border-2 border-[var(--color-border-strong)] border-t-[var(--color-brand)] rounded-full animate-spin"></div>
          <p className="text-[var(--color-text-secondary)] text-sm">Aggregating insights...</p>
        </div>
      </div>
    );
  }

  const { watchlist = [], budget_summary, active_alerts = [], triggered_alerts = [], recent_news = [] } = data || {};

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out">
      
      {/* Top Value Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-card p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-6 opacity-10 transform translate-x-4 -translate-y-4 group-hover:scale-110 transition-transform duration-500">
             <TrendingUp className="w-24 h-24 text-[var(--color-gains)]" />
          </div>
          <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">Total Savings (Net)</p>
          <div className="flex items-end gap-3 mb-2">
            <h3 className={cn("text-3xl font-bold tracking-tight", (budget_summary?.net || 0) >= 0 ? "text-[var(--color-text-primary)]" : "text-[var(--color-losses)]")}>
              ₹{(budget_summary?.net || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </h3>
          </div>
          <div className="h-10 text-xs text-[var(--color-text-muted)] mt-4 border-t border-[var(--color-border-subtle)] pt-3 flex items-center justify-between">
            <span>Income: ₹{(budget_summary?.total_income || 0).toLocaleString()}</span>
            <span>Expenses: ₹{(budget_summary?.total_expense || 0).toLocaleString()}</span>
          </div>
        </div>

        <div className="glass-card p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-6 opacity-10 transform translate-x-4 -translate-y-4 group-hover:scale-110 transition-transform duration-500">
             <BellRing className="w-24 h-24 text-[var(--color-brand)]" />
          </div>
          <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">Price Alerts</p>
          <div className="flex items-end gap-3 mb-2">
            <h3 className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)]">
              {active_alerts.length + triggered_alerts.length}
            </h3>
            <span className="text-sm font-medium text-[var(--color-text-muted)] pb-1 mb-0.5">active</span>
          </div>
          <div className="h-10 mt-4 border-t border-[var(--color-border-subtle)] pt-3 flex items-center">
            {triggered_alerts.length > 0 ? (
              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--color-losses-light)] text-[var(--color-losses)] text-xs font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-losses)] animate-pulse"></span>
                {triggered_alerts.length} Action Required
              </span>
            ) : (
              <span className="text-xs text-[var(--color-text-muted)]">No triggered alerts</span>
            )}
          </div>
        </div>
        
        {/* Placeholder for future ML Insight */}
        <div className="glass-card p-6 rounded-2xl relative overflow-hidden group bg-gradient-to-br from-[var(--color-background-secondary)] to-[rgba(99,102,241,0.05)] border-[rgba(99,102,241,0.2)]">
          <p className="text-sm font-medium text-[var(--color-brand)] mb-1 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[var(--color-brand)]"></span>
            AI Portfolio Health
          </p>
          <div className="flex items-center justify-center h-[72px]">
             <span className="text-[var(--color-text-muted)] text-sm italic">Connecting ML Pipeline (Phase 8)...</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Watchlist Quick View */}
        <div className="glass-card rounded-2xl col-span-2 flex flex-col">
          <div className="p-5 border-b border-[var(--color-border-subtle)] flex items-center justify-between">
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Watchlist Overview</h3>
            <Link to="/watchlist" className="text-sm font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)] flex items-center gap-1">
              View all <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <div className="p-0 flex-1 overflow-auto">
            {watchlist.length === 0 ? (
              <div className="flex h-full min-h-[200px] flex-col items-center justify-center text-[var(--color-text-muted)] px-6 text-center">
                <LineChart className="w-10 h-10 mb-3 opacity-20" />
                <p className="text-sm">Your watchlist is empty.</p>
                <p className="text-xs mt-1">Add stocks to track their daily price movements.</p>
              </div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border-subtle)] bg-[var(--color-background-tertiary)] bg-opacity-30">
                    <th className="px-5 py-3 font-medium text-[var(--color-text-secondary)]">Ticker</th>
                    <th className="px-5 py-3 font-medium text-[var(--color-text-secondary)] text-right">Latest Price</th>
                    <th className="px-5 py-3 font-medium text-[var(--color-text-secondary)] text-right">Change</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border-subtle)]">
                  {watchlist.slice(0, 5).map((item) => {
                    const isUp = (item.change_pct || 0) >= 0;
                    return (
                      <tr key={item.id} className="hover:bg-[var(--color-background-tertiary)] transition-colors">
                        <td className="px-5 py-3.5">
                          <div className="font-semibold text-[var(--color-text-primary)] tracking-wide">{item.ticker}</div>
                          {item.notes && <div className="text-xs text-[var(--color-text-muted)] truncate max-w-[150px] mt-0.5">{item.notes}</div>}
                        </td>
                        <td className="px-5 py-3.5 text-right font-medium text-[var(--color-text-primary)]">
                          {item.latest_price ? `₹${item.latest_price.toFixed(2)}` : '—'}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          {item.change_pct !== null && item.change_pct !== undefined ? (
                            <span className={cn("inline-flex items-center gap-1 font-medium bg-opacity-15 px-2 py-0.5 rounded", 
                              isUp ? "text-[var(--color-gains)] bg-[var(--color-gains)]" : "text-[var(--color-losses)] bg-[var(--color-losses)]"
                            )}>
                              {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                              {Math.abs(item.change_pct).toFixed(2)}%
                            </span>
                          ) : (
                            <span className="text-[var(--color-text-muted)] text-xs">Waiting for data</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Recent News */}
        <div className="glass-card rounded-2xl flex flex-col h-[400px]">
           <div className="p-5 border-b border-[var(--color-border-subtle)] flex items-center gap-2">
             <Newspaper className="w-5 h-5 text-[var(--color-text-secondary)]" />
             <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Market News</h3>
           </div>
           <div className="p-0 flex-1 overflow-y-auto">
             {recent_news.length === 0 ? (
               <div className="flex h-full flex-col items-center justify-center text-[var(--color-text-muted)] px-6 text-center">
                 <p className="text-sm">No recent news ingested.</p>
               </div>
             ) : (
               <div className="divide-y divide-[var(--color-border-subtle)]">
                 {recent_news.slice(0, 5).map((news, idx) => (
                   <a 
                     key={idx} 
                     href={news.url} 
                     target="_blank" 
                     rel="noreferrer"
                     className="block p-4 hover:bg-[var(--color-background-tertiary)] transition-colors group"
                   >
                     <div className="flex items-center gap-2 mb-2">
                       <span className="text-[10px] uppercase font-bold text-[var(--color-brand)] bg-[var(--color-brand-light)] px-1.5 py-0.5 rounded">
                         {news.tickers[0]}
                       </span>
                       <span className="text-xs text-[var(--color-text-muted)] flex items-center gap-1">
                         <Clock className="w-3 h-3" /> 
                         {new Date(news.published_at).toLocaleDateString()}
                       </span>
                     </div>
                     <h4 className="text-sm font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-brand)] transition-colors line-clamp-2 leading-snug">
                       {news.title}
                     </h4>
                     <p className="text-xs text-[var(--color-text-secondary)] mt-1.5 line-clamp-2">{news.source}</p>
                   </a>
                 ))}
               </div>
             )}
           </div>
        </div>

      </div>
    </div>
  );
}
