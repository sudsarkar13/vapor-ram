import * as React from "react"

const MOBILE_BREAKPOINT = 768
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribe(onChange: () => void) {
  const mql = window.matchMedia(QUERY)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

/**
 * Tracks the mobile breakpoint.
 *
 * Uses useSyncExternalStore rather than an effect: matchMedia is an external
 * store, and reading it through this hook avoids the synchronous setState in an
 * effect body that caused a second render on every mount (and a hydration
 * mismatch window between the server snapshot and the first client read).
 */
export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribe,
    () => window.innerWidth < MOBILE_BREAKPOINT,
    // Server has no viewport; assume desktop so SSR markup stays stable.
    () => false,
  )
}
