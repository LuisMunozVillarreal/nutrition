'use client'

import { signIn } from 'next-auth/react'
import { Suspense, useState, useTransition } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { safeCallbackPath } from '@/lib/routeAccess'

function LoginForm() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [isPending, startTransition] = useTransition()
    const router = useRouter()
    const searchParams = useSearchParams()
    const callbackPath = safeCallbackPath(searchParams.get('callbackUrl'))

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        const result = await signIn('credentials', {
            email,
            password,
            callbackUrl: callbackPath,
            redirect: false
        })

        if (result?.ok) {
            startTransition(() => {
                router.refresh()
                router.push(callbackPath)
            })
        } else {
            alert("Login failed")
        }
    }

    return (
        <div className="flex min-h-screen flex-col items-center justify-center p-24">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4 bg-white p-8 rounded shadow text-black">
                <h1 className="text-2xl font-bold">Login</h1>
                <input
                    type="email"
                    placeholder="Email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="border p-2 rounded"
                />
                <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="border p-2 rounded"
                />
                <button type="submit" disabled={isPending} className="bg-blue-500 text-white p-2 rounded disabled:opacity-50">
                    {isPending ? 'Signing in...' : 'Sign In'}
                </button>
            </form>
        </div>
    )
}

export default function LoginPage() {
    return (
        <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading login...</div>}>
            <LoginForm />
        </Suspense>
    )
}
