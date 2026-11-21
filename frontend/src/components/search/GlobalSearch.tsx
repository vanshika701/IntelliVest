import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Search, X } from 'lucide-react'
import { instrumentsApi, type InstrumentSearchResult } from '../../api/instruments'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { cn } from '../../lib/utils'
import { Skeleton } from '../ui/Skeleton'
import { TypeTag } from '../ui/TypeTag'

export const MIN_QUERY_LENGTH = 2
export const SEARCH_DEBOUNCE_MS = 300

type Status = 'idle' | 'loading' | 'success' | 'error'

interface SearchResponseState {
  query: string
  status: 'success' | 'error'
  results: InstrumentSearchResult[]
  partial: boolean
}

/** Instrument search for the navbar: an inline field on sm+ screens, an
 * icon that expands into a full-width field on mobile. Implements the
 * WAI-ARIA combobox pattern (listbox popup, aria-activedescendant). */
export function GlobalSearch() {
  const navigate = useNavigate()
  const listboxId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [mobileExpanded, setMobileExpanded] = useState(false)
  const [response, setResponse] = useState<SearchResponseState | null>(null)
  const [activeIndex, setActiveIndex] = useState(-1)

  const debouncedQuery = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS)
  const tooShort = debouncedQuery.length < MIN_QUERY_LENGTH

  useEffect(() => {
    if (tooShort) return
    const controller = new AbortController()
    instrumentsApi
      .search(debouncedQuery, controller.signal)
      .then((data) => {
        setResponse({ query: debouncedQuery, status: 'success', results: data.results, partial: data.partial })
        setActiveIndex(data.results.length ? 0 : -1)
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setResponse({ query: debouncedQuery, status: 'error', results: [], partial: false })
      })
    return () => controller.abort()
  }, [debouncedQuery, tooShort])

  // Status is derived: a response only counts if it answers the current query.
  const current = response?.query === debouncedQuery ? response : null
  const status: Status = tooShort ? 'idle' : current ? current.status : 'loading'
  const results = current?.results ?? []
  const partial = current?.partial ?? false

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
        setMobileExpanded(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    if (mobileExpanded) inputRef.current?.focus()
  }, [mobileExpanded])

  function close() {
    setOpen(false)
    setMobileExpanded(false)
  }

  function select(result: InstrumentSearchResult) {
    setQuery('')
    close()
    inputRef.current?.blur()
    navigate(`/instrument/${encodeURIComponent(result.id)}`)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      if (open) setOpen(false)
      else close()
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      if (!results.length) return
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((i) => (i + step + results.length) % results.length)
      return
    }
    if (event.key === 'Enter' && open && status === 'success') {
      const choice = results[activeIndex] ?? results[0]
      if (choice) {
        event.preventDefault()
        select(choice)
      }
    }
  }

  // Waiting for the debounce counts as loading, so typing never flashes "no results".
  const pending = !tooShort && (status === 'loading' || debouncedQuery !== query.trim())
  const showPanel = open && query.trim().length > 0
  const activeId = activeIndex >= 0 && results[activeIndex] ? `${listboxId}-option-${activeIndex}` : undefined

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setMobileExpanded(true)}
        className={cn(
          'inline-flex items-center rounded-md p-2 text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] sm:hidden',
          mobileExpanded && 'hidden',
        )}
        aria-label="Search stocks and funds"
      >
        <Search className="h-5 w-5" />
      </button>

      <div
        className={cn(
          mobileExpanded
            ? 'fixed inset-x-0 top-0 z-[60] flex h-16 items-center gap-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-background-primary)] px-3'
            : 'hidden',
          'sm:relative sm:inset-auto sm:z-auto sm:block sm:h-auto sm:border-0 sm:bg-transparent sm:p-0',
        )}
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            role="combobox"
            aria-label="Search stocks, mutual funds and ETFs"
            aria-expanded={showPanel}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={showPanel ? activeId : undefined}
            placeholder="Search stocks, funds, ETFs…"
            autoComplete="off"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            className="h-9 w-full rounded-full border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] pl-9 pr-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] sm:w-64 lg:w-80 [&::-webkit-search-cancel-button]:hidden"
          />
        </div>
        {mobileExpanded && (
          <button
            type="button"
            onClick={close}
            className="rounded-md p-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] sm:hidden"
            aria-label="Close search"
          >
            <X className="h-5 w-5" />
          </button>
        )}

        {showPanel && (
          <div className="absolute left-3 right-3 top-full mt-1 overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] shadow-2xl sm:left-auto sm:right-0 sm:mt-2 sm:w-[26rem]">
            <ul id={listboxId} role="listbox" aria-label="Search results" className="max-h-96 overflow-y-auto py-1">
              {query.trim().length < MIN_QUERY_LENGTH ? (
                <li role="presentation" className="px-4 py-3 text-sm text-[var(--color-text-muted)]">
                  Type at least {MIN_QUERY_LENGTH} characters
                </li>
              ) : pending ? (
                <li role="presentation" aria-live="polite" className="space-y-2 px-4 py-3">
                  <span className="sr-only">Searching…</span>
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="flex items-center gap-3">
                      <Skeleton className="h-4 flex-1" />
                      <Skeleton className="h-4 w-10" />
                    </div>
                  ))}
                </li>
              ) : status === 'error' ? (
                <li role="presentation" className="flex items-center gap-2 px-4 py-3 text-sm text-[var(--color-losses)]">
                  <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Search is unavailable right now. Please try again.
                </li>
              ) : results.length === 0 ? (
                <li role="presentation" className="px-4 py-3 text-sm text-[var(--color-text-muted)]">
                  No results for “{debouncedQuery}”
                </li>
              ) : (
                results.map((result, index) => (
                  <li
                    key={result.id}
                    id={`${listboxId}-option-${index}`}
                    role="option"
                    aria-selected={index === activeIndex}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => select(result)}
                    className={cn(
                      'flex cursor-pointer items-center gap-3 px-4 py-2.5',
                      index === activeIndex && 'bg-[var(--color-background-tertiary)]',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-[var(--color-text-primary)]">{result.name}</div>
                      {result.subtitle && (
                        <div className="truncate text-xs text-[var(--color-text-muted)]">{result.subtitle}</div>
                      )}
                    </div>
                    <TypeTag type={result.type} />
                  </li>
                ))
              )}
            </ul>
            {status === 'success' && partial && !pending && (
              <p className="border-t border-[var(--color-border-subtle)] px-4 py-2 text-xs text-[var(--color-text-muted)]">
                Fund results are temporarily unavailable; showing stocks only.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
