import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiDelete, apiPatch } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Plus, Trash2, Edit2, TrendingUp, TrendingDown, Search, X } from 'lucide-react';
import { cn } from '../lib/utils';

// Starter universe defined in backend constants
const STOCK_UNIVERSE = [
  "RELIANCE.NS", "TCS.NS", "INFY.NS", "WIPRO.NS", "HDFCBANK.NS",
  "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS",
  "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "MARUTI.NS", "TMPV.NS",
  "SUNPHARMA.NS", "TITAN.NS", "ASIANPAINT.NS", "LT.NS", "ULTRACEMCO.NS"
];

const PRIORITIES = ['high', 'medium', 'low'] as const;
type Priority = (typeof PRIORITIES)[number];

const PRIORITY_STYLES: Record<Priority, string> = {
  high: 'text-[var(--color-losses)] bg-[var(--color-losses-light)]',
  medium: 'text-[var(--color-brand)] bg-[var(--color-brand-light)]',
  low: 'text-[var(--color-text-secondary)] bg-[var(--color-background-tertiary)]',
};

interface WatchlistItem {
  id: string;
  ticker: string;
  notes: string;
  rationale: string;
  priority: Priority;
  latest_price: number | null;
  previous_close: number | null;
  change_pct: number | null;
}

export function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Add modal state
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [useCustomTicker, setUseCustomTicker] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState(STOCK_UNIVERSE[0]);
  const [customTicker, setCustomTicker] = useState('');
  const [newPriority, setNewPriority] = useState<Priority>('medium');
  const [newRationale, setNewRationale] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  // Edit modal state (notes + rationale + priority together)
  const [editingItem, setEditingItem] = useState<WatchlistItem | null>(null);
  const [editNotes, setEditNotes] = useState('');
  const [editRationale, setEditRationale] = useState('');
  const [editPriority, setEditPriority] = useState<Priority>('medium');

  useEffect(() => {
    loadWatchlist();
  }, []);

  async function loadWatchlist() {
    try {
      const data = await apiGet<WatchlistItem[]>('/api/v1/watchlist');
      setWatchlist(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const ticker = (useCustomTicker ? customTicker : selectedTicker).trim().toUpperCase();
    if (!ticker) return;

    setIsAdding(true);
    try {
      await apiPost('/api/v1/watchlist', {
        ticker,
        priority: newPriority,
        rationale: newRationale,
      });
      setIsAddOpen(false);
      setCustomTicker('');
      setNewRationale('');
      setNewPriority('medium');
      setUseCustomTicker(false);
      await loadWatchlist();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setIsAdding(false);
    }
  }

  async function handleRemove(id: string) {
    if (!confirm('Remove this stock from watchlist?')) return;
    try {
      await apiDelete(`/api/v1/watchlist/${id}`);
      setWatchlist(watchlist.filter(item => item.id !== id));
    } catch (e) {
      console.error(e);
    }
  }

  function openEditModal(item: WatchlistItem) {
    setEditingItem(item);
    setEditNotes(item.notes || '');
    setEditRationale(item.rationale || '');
    setEditPriority(item.priority || 'medium');
  }

  async function saveEdit() {
    if (!editingItem) return;
    try {
      await apiPatch(`/api/v1/watchlist/${editingItem.id}`, {
        notes: editNotes,
        rationale: editRationale,
        priority: editPriority,
      });
      setWatchlist(watchlist.map(item =>
        item.id === editingItem.id
          ? { ...item, notes: editNotes, rationale: editRationale, priority: editPriority }
          : item
      ));
      setEditingItem(null);
    } catch (e) {
      console.error(e);
    }
  }

  const filteredWatchlist = watchlist.filter(item =>
    item.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (item.notes && item.notes.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" />
          <Input
            placeholder="Search watchlist or notes..."
            className="pl-9 bg-[var(--color-background-secondary)]"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <Button onClick={() => setIsAddOpen(true)} className="w-full sm:w-auto">
          <Plus className="w-4 h-4 mr-2" /> Add Stock
        </Button>
      </div>

      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-[var(--color-text-muted)] flex flex-col items-center">
             <div className="h-8 w-8 border-2 border-[var(--color-border-strong)] border-t-[var(--color-brand)] rounded-full animate-spin mb-4"></div>
             Loading market data...
          </div>
        ) : filteredWatchlist.length === 0 ? (
          <div className="p-16 text-center">
            <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">No stocks found</h3>
            <p className="text-[var(--color-text-secondary)] mb-6">Your watchlist is empty or no items match your search.</p>
            <Button onClick={() => setIsAddOpen(true)} variant="outline">Browse Stocks</Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-[var(--color-background-tertiary)] bg-opacity-50">
                <tr>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)]">Ticker</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] text-right">Latest Price</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] text-right">Day Change</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)]">Notes &amp; Rationale</th>
                  <th className="px-6 py-4 font-medium text-[var(--color-text-secondary)] text-right">Options</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)]">
                {filteredWatchlist.map((item) => {
                  const isUp = (item.change_pct || 0) >= 0;
                  return (
                    <tr key={item.id} className="hover:bg-[var(--color-background-tertiary)] transition-colors group">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-base text-[var(--color-text-primary)]">{item.ticker}</div>
                        <span className={cn("inline-block mt-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded", PRIORITY_STYLES[item.priority])}>
                          {item.priority} priority
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-medium text-base text-[var(--color-text-primary)]">
                          {item.latest_price ? `₹${item.latest_price.toFixed(2)}` : '--'}
                        </div>
                        <div className="text-xs text-[var(--color-text-muted)] mt-1">
                          {item.previous_close ? `Prev: ₹${item.previous_close.toFixed(2)}` : ''}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {item.change_pct !== null && item.change_pct !== undefined ? (
                          <span className={cn("inline-flex items-center gap-1.5 font-medium px-2.5 py-1 rounded-md bg-opacity-15",
                            isUp ? "text-[var(--color-gains)] bg-[var(--color-gains)]" : "text-[var(--color-losses)] bg-[var(--color-losses)]"
                          )}>
                            {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                            {Math.abs(item.change_pct).toFixed(2)}%
                          </span>
                        ) : (
                          <span className="text-[var(--color-text-muted)] text-sm">Awaiting sync</span>
                        )}
                      </td>
                      <td className="px-6 py-4 max-w-xs">
                        <div className="flex items-center gap-2 cursor-pointer group/note" onClick={() => openEditModal(item)}>
                          <div className="min-w-0">
                            <p className={cn("text-sm truncate", item.notes ? "text-[var(--color-text-primary)]" : "text-[var(--color-text-muted)] italic")}>
                              {item.notes || 'Add notes...'}
                            </p>
                            {item.rationale && (
                              <p className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">{item.rationale}</p>
                            )}
                          </div>
                          <Edit2 className="w-3.5 h-3.5 shrink-0 text-[var(--color-text-muted)] opacity-0 group-hover/note:opacity-100 transition-opacity" />
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Button variant="ghost" size="sm" onClick={() => handleRemove(item.id)} className="text-[var(--color-losses)] hover:text-white hover:bg-[var(--color-losses)] w-8 h-8 p-0 ml-auto">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4 animate-in fade-in duration-200">
          <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] p-6 rounded-xl w-full max-w-sm shadow-2xl">
            <h3 className="text-xl font-bold text-[var(--color-text-primary)] mb-4">Add to Watchlist</h3>
            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
                    {useCustomTicker ? 'Custom Ticker' : 'Select Ticker'}
                  </label>
                  <button
                    type="button"
                    onClick={() => setUseCustomTicker(!useCustomTicker)}
                    className="text-xs font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]"
                  >
                    {useCustomTicker ? 'Choose from list' : 'Enter custom ticker'}
                  </button>
                </div>
                {useCustomTicker ? (
                  <Input
                    required
                    value={customTicker}
                    onChange={(e) => setCustomTicker(e.target.value)}
                    placeholder="e.g. ZOMATO.NS"
                    className="uppercase"
                  />
                ) : (
                  <select
                    className="flex h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] text-[var(--color-text-primary)] [&>option]:bg-[var(--color-background-secondary)]"
                    value={selectedTicker}
                    onChange={(e) => setSelectedTicker(e.target.value)}
                  >
                    {STOCK_UNIVERSE.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Priority</label>
                <div className="flex bg-[var(--color-background-tertiary)] rounded-md p-1 border border-[var(--color-border-strong)]">
                  {PRIORITIES.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setNewPriority(p)}
                      className={cn(
                        "flex-1 py-1.5 text-xs font-medium rounded-sm capitalize transition-colors",
                        newPriority === p ? "bg-[var(--color-brand)] text-white shadow-sm" : "text-[var(--color-text-secondary)] hover:text-white"
                      )}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                  Investment Rationale <span className="text-[var(--color-text-muted)] font-normal">(optional)</span>
                </label>
                <textarea
                  value={newRationale}
                  onChange={(e) => setNewRationale(e.target.value)}
                  placeholder="Why are you tracking this stock?"
                  rows={2}
                  className="flex w-full rounded-md border border-[var(--color-border-strong)] bg-transparent px-3 py-2 text-sm placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] text-[var(--color-text-primary)] resize-none"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <Button type="button" variant="ghost" className="flex-1" onClick={() => setIsAddOpen(false)}>Cancel</Button>
                <Button type="submit" className="flex-1" disabled={isAdding}>
                  {isAdding ? 'Adding...' : 'Add Stock'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal (notes, rationale, priority) */}
      {editingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4 animate-in fade-in duration-200">
          <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] p-6 rounded-xl w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-[var(--color-text-primary)]">Edit {editingItem.ticker}</h3>
              <button onClick={() => setEditingItem(null)} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Priority</label>
                <div className="flex bg-[var(--color-background-tertiary)] rounded-md p-1 border border-[var(--color-border-strong)]">
                  {PRIORITIES.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setEditPriority(p)}
                      className={cn(
                        "flex-1 py-1.5 text-xs font-medium rounded-sm capitalize transition-colors",
                        editPriority === p ? "bg-[var(--color-brand)] text-white shadow-sm" : "text-[var(--color-text-secondary)] hover:text-white"
                      )}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Notes</label>
                <Input autoFocus value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Quick note..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Investment Rationale</label>
                <textarea
                  value={editRationale}
                  onChange={(e) => setEditRationale(e.target.value)}
                  rows={3}
                  className="flex w-full rounded-md border border-[var(--color-border-strong)] bg-transparent px-3 py-2 text-sm placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] text-[var(--color-text-primary)] resize-none"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Button type="button" variant="ghost" className="flex-1" onClick={() => setEditingItem(null)}>Cancel</Button>
                <Button type="button" className="flex-1" onClick={saveEdit}>Save</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
