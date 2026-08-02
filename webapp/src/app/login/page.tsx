'use client'

import { LoaderCircle } from 'lucide-react'
import { signIn } from 'next-auth/react'
import { Suspense, useRef, useState, useTransition } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { safeCallbackPath } from '@/lib/routeAccess'

const LOGIN_ERROR_MESSAGE =
    'Unable to sign in. Please check your connection or credentials and try again.'

function LoginForm() {
    const submissionInFlight = useRef(false)
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isPending, startTransition] = useTransition()
    const router = useRouter()
    const searchParams = useSearchParams()
    const callbackPath = safeCallbackPath(searchParams.get('callbackUrl'))
    const isBusy = isSubmitting || isPending

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (submissionInFlight.current) return

        submissionInFlight.current = true
        setError(null)
        setIsSubmitting(true)

        try {
            const result = await signIn('credentials', {
                email,
                password,
                callbackUrl: callbackPath,
                redirect: false
            })

            if (!result?.ok) {
                submissionInFlight.current = false
                setError(LOGIN_ERROR_MESSAGE)
                setIsSubmitting(false)
                return
            }

            startTransition(() => {
                router.refresh()
                router.push(callbackPath)
            })
        } catch {
            submissionInFlight.current = false
            setError(LOGIN_ERROR_MESSAGE)
            setIsSubmitting(false)
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
                    disabled={isBusy}
                />
                <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="border p-2 rounded"
                    disabled={isBusy}
                />
                {error && (
                    <p role="alert" className="text-sm text-red-600">
                        {error}
                    </p>
                )}
                <p role="status" aria-live="polite" className="sr-only">
                    {isBusy ? 'Signing in...' : ''}
                </p>
                <button
                    type="submit"
                    disabled={isBusy}
                    aria-busy={isBusy}
                    className="flex items-center justify-center gap-2 rounded bg-blue-500 p-2 text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {isBusy ? (
                        <>
                            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                            Signing in...
                        </>
                    ) : (
                        'Sign In'
                    )}
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
