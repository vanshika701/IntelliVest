import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost, apiDelete } from '../api/client';
import { budgetApi, type BudgetMeta, type BudgetOverview } from '../api/budget';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { BudgetSetup } from '../components/budget/BudgetSetup';
import { EstimateVsActual, SpendingPie } from '../components/budget/SpendingPie';
import { ImproveBudget } from '../components/budget/ImproveBudget';
import { GoalsPanel } from '../components/budget/GoalsPanel';
import { Upload, Plus, Trash2, ArrowUpRight, ArrowDownRight, FileText, Download, SlidersHorizontal, AlertTriangle } from 'lucide-react';
import { cn } from '../lib/utils';
import { formatINR } from '../lib/format';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

type Tab = 'overview' | 'improve' | 'goals';
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'improve', label: 'Improve my budget' },
  { id: 'goals', label: 'Goals' },
];

export function BudgetingPage() {
  const [expenses, setExpenses] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [meta, setMeta] = useState<BudgetMeta | null>(null);
  const [overview, setOverview] = useState<BudgetOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('overview');
  const [setupOpen, setSetupOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [expenseType, setExpenseType] = useState('expense');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    budgetApi.meta().then(setMeta).catch(() => setMeta(null));
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [expData, sumData, ov] = await Promise.all([
        apiGet<any>('/api/v1/expenses?limit=100'),
        apiGet<any>('/api/v1/expenses/summary'),
        budgetApi.overview(),
      ]);
      setExpenses(expData.items);
      setSummary(sumData);
      setOverview(ov);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  const categoryName = (id: string) =>
    id === 'income' ? 'Income' : meta?.categories.find((c) => c.id === id)?.name ?? id;

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiPost('/api/v1/expenses', {
        amount: parseFloat(amount),
        description,
        // Income records get the "income" category server-side.
        ...(expenseType === 'expense' ? { category } : {}),
        expense_type: expenseType
      });
      setIsAddOpen(false);

      // Reset form
      setAmount('');
      setDescription('');
      setCategory('');
      setExpenseType('expense');

      await loadData();
    } catch (e: any) {
      alert(e.message);
    }
  }

  async function handleRemove(id: string) {
    if (!confirm('Delete this record?')) return;
    try {
      await apiDelete(`/api/v1/expenses/${id}`);
      await loadData();
    } catch (e) {
      console.error(e);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/expenses/upload-csv`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('intellivest_token')}`
        },
        body: formData
      });

      if (!res.ok) throw new Error('Upload failed');
      const result = await res.json();
      alert(`Imported ${result.imported} rows. Skipped ${result.skipped}. Errors: ${result.errors.length}\nRows without a recognised category were filed under "Other / Miscellaneous".`);
      await loadData();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  const hasProfile = overview?.has_profile ?? false;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div role="tablist" aria-label="Budget sections" className="flex gap-1 bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] rounded-lg p-1 overflow-x-auto max-w-full">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn('px-3 py-1.5 text-sm font-medium rounded-md whitespace-nowrap transition-colors',
                tab === t.id ? 'bg-[var(--color-background-tertiary)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]')}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto flex-wrap">
          {meta && (
            <Button variant="outline" className="h-9 text-xs" onClick={() => setSetupOpen(true)}>
              <SlidersHorizontal className="w-4 h-4 mr-2" /> {hasProfile ? 'Edit budget' : 'Set up budget'}
            </Button>
          )}
          {tab === 'overview' && (
            <>
              <a
                href={`${API_BASE_URL}/api/v1/expenses/sample-csv`}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                title="Download a sample CSV showing the columns the importer recognizes"
              >
                <Download className="w-3.5 h-3.5" /> Sample CSV
              </a>
              <Button variant="outline" className="flex-1 sm:flex-none h-9 text-xs" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                {uploading ? <div className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div> : <Upload className="w-4 h-4 mr-2" />}
                {uploading ? 'Uploading...' : 'Import CSV'}
              </Button>
              <input type="file" ref={fileInputRef} className="hidden" accept=".csv" onChange={handleFileUpload} />
              <Button className="flex-1 sm:flex-none h-9 text-xs" onClick={() => setIsAddOpen(true)}>
                <Plus className="w-4 h-4 mr-2" /> Add Log
              </Button>
            </>
          )}
        </div>
      </div>

      {!loading && meta && !hasProfile && (
        <div className="glass-card p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center gap-4 border-l-4 border-l-[var(--color-brand)]">
          <div className="flex-1">
            <h3 className="font-semibold text-[var(--color-text-primary)]">Set up your smart budget</h3>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1">
              Add your monthly income and a rough estimate per category to get overspend checks, the 50/30/20 breakdown and goal plans.
            </p>
          </div>
          <Button onClick={() => setSetupOpen(true)}>Get started</Button>
        </div>
      )}
      {overview?.profile_warnings.map((w) => (
        <p key={w} className="flex items-center gap-2 text-sm text-[#fab219]"><AlertTriangle className="w-4 h-4" /> {w}</p>
      ))}

      {loading || !overview ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-text-muted)]">Loading metrics...</div>
      ) : tab === 'improve' ? (
        meta && overview.analysis ? <ImproveBudget meta={meta} analysis={overview.analysis} /> : (
          <p className="text-[var(--color-text-muted)]">Set up your budget first to get recommendations.</p>
        )
      ) : tab === 'goals' ? (
        meta && <GoalsPanel meta={meta} refreshKey={refreshKey} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Summary Cards */}
          <div className="col-span-1 space-y-6">
            <div className="glass-card p-6 rounded-2xl border-l-4 border-l-[var(--color-gains)] group relative overflow-hidden">
               <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform"><ArrowDownRight className="w-32 h-32 text-[var(--color-gains)]"/></div>
               <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">Total Income</p>
               <h3 className="text-3xl font-bold text-[var(--color-gains)] tracking-tight">₹{(summary?.total_income || 0).toLocaleString('en-IN')}</h3>
            </div>
            <div className="glass-card p-6 rounded-2xl border-l-4 border-l-[var(--color-losses)] group relative overflow-hidden">
               <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform"><ArrowUpRight className="w-32 h-32 text-[var(--color-losses)]"/></div>
               <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">Total Expenses</p>
               <h3 className="text-3xl font-bold text-[var(--color-losses)] tracking-tight">₹{(summary?.total_expense || 0).toLocaleString('en-IN')}</h3>
            </div>
            {hasProfile && overview.profile && (
              <div className="glass-card p-5 rounded-2xl text-sm space-y-1">
                <div className="flex justify-between"><span className="text-[var(--color-text-secondary)]">Monthly income (budget)</span><span className="font-mono">{formatINR(overview.profile.monthly_income, 0)}</span></div>
                {overview.analysis && (
                  <div className="flex justify-between"><span className="text-[var(--color-text-secondary)]">Savings rate ({overview.analysis.basis})</span><span className="font-mono">{overview.analysis.savings_rate_pct ?? '—'}%</span></div>
                )}
              </div>
            )}

            {meta && (
              <SpendingPie categories={meta.categories} comparison={overview.comparison} hasActual={overview.actual.has_data} />
            )}
          </div>

          <div className="col-span-2 space-y-6">
            {hasProfile && <EstimateVsActual comparison={overview.comparison} hasActual={overview.actual.has_data} months={overview.actual.months} />}

            {/* Transaction List */}
            <div className="glass-card rounded-2xl flex flex-col h-[650px] overflow-hidden">
              <div className="px-6 py-5 border-b border-[var(--color-border-subtle)] flex justify-between items-center bg-[var(--color-background-tertiary)] bg-opacity-30">
                <h3 className="font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                  <FileText className="w-5 h-5 text-[var(--color-text-secondary)]"/> Recent Transactions
                </h3>
              </div>

              <div className="flex-1 overflow-y-auto">
                {expenses.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-[var(--color-text-muted)]">
                    <p>No transactions found.</p>
                    <p className="text-sm mt-2 font-medium">Click "Add Log" or "Import CSV" to start tracking.</p>
                  </div>
                ) : (
                  <ul className="divide-y divide-[var(--color-border-subtle)]">
                    {expenses.map(exp => (
                      <li key={exp.id} className="p-4 sm:px-6 hover:bg-[var(--color-background-tertiary)] transition-colors group flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className={cn("flex items-center justify-center w-10 h-10 rounded-full bg-opacity-15",
                            exp.expense_type === 'income' ? "bg-[var(--color-gains)] text-[var(--color-gains)]" : "bg-[var(--color-losses)] text-[var(--color-losses)]"
                          )}>
                            {exp.expense_type === 'income' ? <ArrowDownRight className="w-5 h-5"/> : <ArrowUpRight className="w-5 h-5"/>}
                          </div>
                          <div>
                            <p className="font-medium text-[var(--color-text-primary)]">{exp.description}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs bg-[var(--color-background-secondary)] border border-[var(--color-border-strong)] px-2 py-0.5 rounded text-[var(--color-text-secondary)]">{categoryName(exp.category)}</span>
                              <span className="text-xs text-[var(--color-text-muted)]">{new Date(exp.date).toLocaleDateString()}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-6">
                          <span className={cn("font-semibold whitespace-nowrap", exp.expense_type === 'income' ? "text-[var(--color-gains)]" : "text-[var(--color-text-primary)]")}>
                            {exp.expense_type === 'income' ? '+' : '-'} ₹{exp.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                          <button onClick={() => handleRemove(exp.id)} aria-label="Delete transaction" className="text-[var(--color-text-muted)] hover:text-[var(--color-losses)] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity p-2 -mr-2 rounded flex-shrink-0">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {setupOpen && meta && (
        <BudgetSetup
          meta={meta}
          initial={overview?.profile ?? null}
          onClose={() => setSetupOpen(false)}
          onSaved={() => { setSetupOpen(false); loadData(); }}
        />
      )}

      {/* Add Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] p-6 rounded-xl w-full max-w-sm shadow-2xl">
            <h3 className="text-xl font-bold text-[var(--color-text-primary)] mb-5">Add Transaction</h3>
            <form onSubmit={handleAdd} className="space-y-4">
              <div className="flex bg-[var(--color-background-tertiary)] rounded-md p-1 items-center justify-between border border-[var(--color-border-strong)]">
                <button type="button" onClick={() => setExpenseType('expense')} className={cn("flex-1 py-1.5 text-sm font-medium rounded-sm transition-colors", expenseType === 'expense' ? "bg-[var(--color-losses)] text-white shadow-sm" : "text-[var(--color-text-secondary)] hover:text-white")}>Expense</button>
                <button type="button" onClick={() => setExpenseType('income')} className={cn("flex-1 py-1.5 text-sm font-medium rounded-sm transition-colors", expenseType === 'income' ? "bg-[var(--color-gains)] text-white shadow-sm" : "text-[var(--color-text-secondary)] hover:text-white")}>Income</button>
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Amount (₹)</label>
                <Input required type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" autoFocus className="font-mono text-lg" />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Description</label>
                <Input required value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Grocery, Salary" />
              </div>

              {expenseType === 'expense' && (
                <div>
                  <label htmlFor="add-category" className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Category</label>
                  <select
                    id="add-category"
                    required
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-3 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
                  >
                    <option value="" disabled>Pick a category…</option>
                    {meta?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
              )}

              <div className="flex gap-3 pt-4 border-t border-[var(--color-border-subtle)] mt-2">
                <Button type="button" variant="ghost" className="flex-1" onClick={() => setIsAddOpen(false)}>Cancel</Button>
                <Button type="submit" className="flex-1">Save Log</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
