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
  if (/^\/login(?:[/?#]|$)/.test(callbackUrl)) return '/'
  return callbackUrl
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
): RouteAccessDecision {
  if (status === 'loading') return { kind: 'loading' }

  if (status === 'unauthenticated') {
    if (PUBLIC_PATHS.has(pathname) || isLoginPath(pathname)) return { kind: 'allow' }
    return {
      kind: 'redirect',
      destination: `/login?callbackUrl=${encodeURIComponent(pathname)}`,
    }
  }

  if (isLoginPath(pathname)) {
    return { kind: 'redirect', destination: '/' }
  }

  const staffFallback = staffRouteDestination(pathname)
  if (staffFallback && isStaff !== true) {
    return { kind: 'redirect', destination: staffFallback }
  }

  return { kind: 'allow' }
}
