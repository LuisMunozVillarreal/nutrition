'use client'

import { useEffect, useMemo } from 'react'
import { useSession } from 'next-auth/react'
import { usePathname, useRouter } from 'next/navigation'
import { decideRouteAccess } from '@/lib/routeAccess'
import Sidebar from './Sidebar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const pathname = usePathname()
  const router = useRouter()
  const access = useMemo(
    () => decideRouteAccess(pathname, status, session?.user?.isStaff),
    [pathname, status, session?.user?.isStaff],
  )

  useEffect(() => {
    if (access.kind === 'redirect') {
      router.replace(access.destination)
    }
  }, [access, router])

  if (status === 'loading' || access.kind === 'loading') {
    return (
      <div className="p-12 text-center text-slate-500" data-testid="session-loading">
        Loading session...
      </div>
    )
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
      <main className="main-content p-6 md:p-10">
        {children}
      </main>
    </>
  )
}
