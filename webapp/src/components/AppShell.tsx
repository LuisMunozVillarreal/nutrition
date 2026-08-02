'use client'

import { Suspense, useEffect, useMemo } from 'react'
import { useSession } from 'next-auth/react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { BACKEND_REAUTHENTICATION_REQUIRED } from '@/lib/sessionCapabilities'
import { buildCallbackPath, decideRouteAccess } from '@/lib/routeAccess'
import Sidebar from './Sidebar'

function SessionLoading() {
  return (
    <div className="p-12 text-center text-slate-500" data-testid="session-loading">
      Loading session...
    </div>
  )
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const router = useRouter()
  const callbackPath = useMemo(
    () => buildCallbackPath(pathname, searchParams.toString()),
    [pathname, searchParams],
  )
  const reauthenticationRequired =
    session?.error === BACKEND_REAUTHENTICATION_REQUIRED
  const access = useMemo(
    () =>
      decideRouteAccess(
        pathname,
        status,
        session?.user?.isStaff,
        callbackPath,
        reauthenticationRequired,
      ),
    [
      callbackPath,
      pathname,
      reauthenticationRequired,
      session?.user?.isStaff,
      status,
    ],
  )

  useEffect(() => {
    if (access.kind === 'redirect') {
      router.replace(access.destination)
    }
  }, [access, router])

  if (status === 'loading' || access.kind === 'loading') {
    return <SessionLoading />
  }

  if (access.kind === 'redirect') {
    return (
      <div className="p-12 text-center text-slate-500" data-testid="auth-redirecting">
        Redirecting...
      </div>
    )
  }

  if (!session) {
    return <>{children}</>
  }

  return (
    <>
      <Sidebar />
      <main className="main-content p-6 md:p-10" tabIndex={-1}>
        {children}
      </main>
    </>
  )
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<SessionLoading />}>
      <AppShellInner>{children}</AppShellInner>
    </Suspense>
  )
}
