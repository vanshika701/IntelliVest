import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiDelete, apiPatch } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { BellRing, Plus, Trash2, Power, PowerOff, TrendingUp, TrendingDown, Target } from 'lucide-react';
import { cn } from '../lib/utils';

const STOCK_UNIVERSE = [
  "RELIANCE.NS", "TCS.NS", "INFY.NS", "WIPRO.NS", "HDFCBANK.NS", 
  "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS",
  "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "MARUTI.NS", "TMPV.NS", 
  "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS", "LT.NS", "ULTRACEMCO.NS"
];

export function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [ticker, setTicker] = useState(STOCK_UNIVERSE[0]);
  const [condition, setCondition] = useState('above');
  const [targetPrice, setTargetPrice] = useState('');
  const [thresholdPct, setThresholdPct] = useState('5.0');
  
  useEffect(() => {
    loadAlerts();
  }, []);

  async function loadAlerts() {
    setLoading(true);
    try {
      const data = await apiGet<any[]>('/api/v1/alerts');
      setAlerts(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiPost('/api/v1/alerts', {
        ticker,
        condition,
        target_price: parseFloat(targetPrice),
        threshold_pct: parseFloat(thresholdPct)
      });
      setIsAddOpen(false);
      setTargetPrice('');
      await loadAlerts();
    } catch (e: any) {
      alert(e.message);
    }
  }

  async function handleToggle(id: string, currentState: boolean) {
    try {
      // Optimistic update
      setAlerts(alerts.map(a => a.id === id ? { ...a, is_active: !currentState, triggered: false } : a));
      await apiPatch(`/api/v1/alerts/${id}/toggle?is_active=${!currentState}`, {});
    } catch (e) {
      // Revert if failed
      await loadAlerts();
      console.error(e);
    }
  }

  async function handleRemove(id: string) {
    if (!confirm('Delete this alert?')) return;
    try {
      await apiDelete(`/api/v1/alerts/${id}`);
      setAlerts(alerts.filter(a => a.id !== id));
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      
      <div className="flex justify-between items-center bg-gradient-to-r from-[var(--color-brand-light)] to-transparent p-6 rounded-2xl border border-[var(--color-border-subtle)] relative overflow-hidden">
        <div className="relative z-10">
          <h2 className="text-xl font-bold text-[var(--color-text-primary)] flex items-center gap-2 mb-2">
            <BellRing className="w-5 h-5 text-[var(--color-brand)]"/> Intelligent Price Alerts
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-lg">
            Set proximity triggers for any stock. Our background jobs evaluate closing prices daily and highlight assets requiring your attention.
          </p>
        </div>
        <Button onClick={() => setIsAddOpen(true)} className="relative z-10 shrink-0 shadow-lg">
          <Plus className="w-4 h-4 mr-2" /> New Alert
        </Button>
      </div>

      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-[var(--color-text-muted)]">Loading rules...</div>
        ) : alerts.length === 0 ? (
          <div className="p-16 text-center">
            <Target className="w-12 h-12 text-[var(--color-border-strong)] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">No active rules</h3>
            <p className="text-[var(--color-text-secondary)] mb-6">Create a proximity alert to get notified when a stock hits your target.</p>
            <Button onClick={() => setIsAddOpen(true)} variant="outline">Set up alert</Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-[var(--color-background-tertiary)] bg-opacity-50 border-b border-[var(--color-border-subtle)]">
                <tr>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] w-1/4">Asset Target</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] w-1/4">Condition</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] w-1/4">Status</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)]">
                {alerts.map(alert => (
                  <tr key={alert.id} className={cn("transition-colors group", alert.triggered ? "bg-[var(--color-losses-light)] bg-opacity-20 hover:bg-opacity-30" : "hover:bg-[var(--color-background-tertiary)]")}>
                    <td className="px-6 py-4">
                      <div className="font-semibold text-base text-[var(--color-text-primary)] tracking-wide">{alert.ticker}</div>
                      <div className="text-xs text-[var(--color-text-muted)] mt-1 tracking-wider uppercase flex items-center gap-1">
                        Target <ArrowRight className="w-3 h-3"/> ₹{alert.target_price.toLocaleString()}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {alert.condition === 'above' && <span className="flex items-center gap-1.5 text-[var(--color-gains)] text-xs font-semibold px-2 py-1 rounded bg-[var(--color-gains-light)] border border-[rgba(16,185,129,0.2)]"><TrendingUp className="w-3.5 h-3.5"/> Crosses Above</span>}
                        {alert.condition === 'below' && <span className="flex items-center gap-1.5 text-[var(--color-losses)] text-xs font-semibold px-2 py-1 rounded bg-[var(--color-losses-light)] border border-[rgba(244,63,94,0.2)]"><TrendingDown className="w-3.5 h-3.5"/> Drops Below</span>}
                        {alert.condition === 'within_pct' && <span className="flex items-center gap-1.5 text-[var(--color-brand)] text-xs font-semibold px-2 py-1 rounded bg-[var(--color-brand-light)] border border-[rgba(99,102,241,0.2)]"><Target className="w-3.5 h-3.5"/> Within {alert.threshold_pct}%</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {alert.triggered ? (
                        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-losses)] bg-[var(--color-losses-light)] px-2.5 py-1 rounded-full w-max border border-[rgba(244,63,94,0.2)] shadow-[0_0_10px_rgba(244,63,94,0.3)]">
                          <span className="w-2 h-2 rounded-full bg-[var(--color-losses)] animate-pulse"></span>
                          TRIGGERED
                        </div>
                      ) : !alert.is_active ? (
                        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)] bg-[var(--color-background-tertiary)] px-2.5 py-1 rounded-full w-max">
                          <span className="w-2 h-2 rounded-full bg-[var(--color-text-muted)]"></span>
                          PAUSED
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] px-2.5 py-1 rounded-full w-max border border-[var(--color-border-strong)]">
                          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                          Monitoring...
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                       <div className="flex items-center justify-end gap-2">
                         <Button variant="ghost" size="sm" onClick={() => handleToggle(alert.id, alert.is_active)} className={cn("w-8 h-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity", alert.is_active ? "text-amber-500 hover:text-amber-400 hover:bg-amber-500/10" : "text-emerald-500 hover:text-emerald-400 hover:bg-emerald-500/10")}>
                           {alert.is_active ? <PowerOff className="w-4 h-4"/> : <Power className="w-4 h-4"/>}
                         </Button>
                         <Button variant="ghost" size="sm" onClick={() => handleRemove(alert.id)} className="text-[var(--color-losses)] hover:text-white hover:bg-[var(--color-losses)] w-8 h-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity">
                           <Trash2 className="w-4 h-4" />
                         </Button>
                       </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] p-6 rounded-xl w-full max-w-sm shadow-2xl">
            <h3 className="text-xl font-bold text-[var(--color-text-primary)] mb-5">Create Alert Rule</h3>
            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Target Asset</label>
                <select className="flex h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] text-[var(--color-text-primary)] [&>option]:bg-[var(--color-background-secondary)]" value={ticker} onChange={(e) => setTicker(e.target.value)}>
                  {STOCK_UNIVERSE.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Trigger Condition</label>
                <select className="flex h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] text-[var(--color-text-primary)] [&>option]:bg-[var(--color-background-secondary)]" value={condition} onChange={(e) => setCondition(e.target.value)}>
                  <option value="above">Price crosses above</option>
                  <option value="below">Price drops below</option>
                  <option value="within_pct">Price comes within % margin</option>
                </select>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Target Price (₹)</label>
                <Input required type="number" step="0.01" min="0.01" value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} placeholder="0.00" className="font-mono text-lg"/>
              </div>

              {condition === 'within_pct' && (
                <div>
                  <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Proximity Margin (%)</label>
                  <Input required type="number" step="0.1" min="0.1" max="50" value={thresholdPct} onChange={(e) => setThresholdPct(e.target.value)} placeholder="5.0"/>
                </div>
              )}
              
              <div className="flex gap-3 pt-4 border-t border-[var(--color-border-subtle)] mt-2">
                <Button type="button" variant="ghost" className="flex-1" onClick={() => setIsAddOpen(false)}>Cancel</Button>
                <Button type="submit" className="flex-1">Create Rule</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper icon component for inline use
function ArrowRight(props: any) {
  return <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>;
}
