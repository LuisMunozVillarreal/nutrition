'use client'

import { useSession } from 'next-auth/react'
import Sidebar from './Sidebar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()

  if (status === 'loading') {
    return (
      <div className="p-12 text-center text-slate-500" data-testid="session-loading">
        Loading session...
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
