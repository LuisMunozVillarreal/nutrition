export type SessionStatus = 'authenticated' | 'loading' | 'unauthenticated'

export type RouteAccessDecision =
  | { kind: 'allow' }
  | { kind: 'loading' }
  | { kind: 'redirect'; destination: string }

const PUBLIC_PATHS = new Set(['/', '/login'])

function isLoginPath(pathname: string): boolean {
  return pathname === '/login' || pathname === '/login/'
}

export function safeCallbackPath(callbackUrl: string | null): string {
  if (
    !callbackUrl?.startsWith('/') ||
    callbackUrl.startsWith('//') ||
    callbackUrl.includes('\\')
  ) {
    return '/'
  }
  const fragmentIndex = callbackUrl.indexOf('#')
  const localPath =
    fragmentIndex === -1 ? callbackUrl : callbackUrl.slice(0, fragmentIndex)
  if (/^\/login(?:[/?#]|$)/.test(localPath)) return '/'
  return localPath
}

export function buildCallbackPath(pathname: string, encodedQuery: string): string {
  return encodedQuery ? `${pathname}?${encodedQuery}` : pathname
}

function loginDestination(callbackPath: string): string {
  return `/login?callbackUrl=${encodeURIComponent(safeCallbackPath(callbackPath))}`
}

function staffRouteDestination(pathname: string): string | null {
  if (/^\/products\/[^/]+\/?$/.test(pathname)) return '/products'
  if (/^\/recipes\/[^/]+\/?$/.test(pathname)) return '/recipes'
  if (/^\/servings(?:\/|$)/.test(pathname)) return '/products'
  return null
}

export function decideRouteAccess(
  pathname: string,
  status: SessionStatus,
  isStaff: boolean | undefined,
  callbackPath = pathname,
  reauthenticationRequired = false,
): RouteAccessDecision {
  if (status === 'loading') return { kind: 'loading' }

  if (reauthenticationRequired) {
    if (isLoginPath(pathname)) return { kind: 'allow' }
    return { kind: 'redirect', destination: loginDestination(callbackPath) }
  }

  if (status === 'unauthenticated') {
    if (PUBLIC_PATHS.has(pathname) || isLoginPath(pathname)) return { kind: 'allow' }
    return {
      kind: 'redirect',
      destination: loginDestination(callbackPath),
    }
  }

  if (isLoginPath(pathname)) {
    return { kind: 'redirect', destination: safeCallbackPath(callbackPath) }
  }

  const staffFallback = staffRouteDestination(pathname)
  if (staffFallback && isStaff !== true) {
    return { kind: 'redirect', destination: staffFallback }
  }

  return { kind: 'allow' }
}
