'use client'

import { useSession } from 'next-auth/react'
import Sidebar from './Sidebar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession()

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
