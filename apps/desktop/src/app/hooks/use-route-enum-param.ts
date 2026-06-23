import { useCallback, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

// Read/write an enum-shaped URL search param (e.g. ?tab=foo). Used to make
// tabbed views survive a refresh. Always navigates with replace so tab clicks
// don't pile up in history.
export function useRouteEnumParam<T extends string>(
  key: string,
  values: readonly T[],
  fallback: T
): [T, (next: T) => void] {
  const { hash, pathname, search } = useLocation()
  const navigate = useNavigate()

  const value = useMemo<T>(() => {
    const raw = new URLSearchParams(search).get(key)

    return raw && values.includes(raw as T) ? (raw as T) : fallback
  }, [fallback, key, search, values])

  const setValue = useCallback(
    (next: T) => {
      // Read the LIVE query string (not the closed-over `search` from this
      // render). navigate({replace}) updates history synchronously, so two
      // setValue calls in the same tick (e.g. setActiveView + setSubView)
      // compose instead of the second clobbering the first — which previously
      // wiped ?tab=providers and left the page stuck on the default tab.
      const liveSearch = typeof window !== 'undefined' ? window.location.search : search
      const params = new URLSearchParams(liveSearch)

      if (next === fallback) {
        params.delete(key)
      } else {
        params.set(key, next)
      }

      const qs = params.toString()
      navigate({ hash, pathname, search: qs ? `?${qs}` : '' }, { replace: true })
    },
    [fallback, hash, key, navigate, pathname, search]
  )

  return [value, setValue]
}
