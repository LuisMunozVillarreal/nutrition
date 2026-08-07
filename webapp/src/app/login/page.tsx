'use client'

import { LoaderCircle } from 'lucide-react'
import { signIn } from 'next-auth/react'
import { Suspense, useEffect, useRef, useState, useTransition } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { safeCallbackPath } from '@/lib/routeAccess'

const LOGIN_ERROR_MESSAGE =
    'Unable to sign in. Please check your connection or credentials and try again.'
const LOGIN_RECOVERY_DELAY_MS = 10_000

function LoginForm() {
    const submissionInFlight = useRef(false)
    const submitButtonRef = useRef<HTMLButtonElement>(null)
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isRequestPending, setIsRequestPending] = useState(false)
    const [showRecovery, setShowRecovery] = useState(false)
    const [isNavigating, setIsNavigating] = useState(false)
    const [isNavigationPending, startNavigation] = useTransition()
    const router = useRouter()
    const searchParams = useSearchParams()
    const callbackPath = safeCallbackPath(searchParams.get('callbackUrl'))
    const loginRecoveryHref = callbackPath === '/'
        ? '/login'
        : `/login?callbackUrl=${encodeURIComponent(callbackPath)}`
    const isBusy = isRequestPending || isNavigating
    const recoveryHref = isNavigating ? callbackPath : loginRecoveryHref

    useEffect(() => {
        if (!isNavigating || isNavigationPending) return

        submissionInFlight.current = false
        // Intentional reset: the latch and navigation flag must release once the
        // transition settles; this is a response to external navigation state,
        // not a cascading render, so the effect is the correct sync point.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setIsNavigating(false)
    }, [isNavigating, isNavigationPending])

    useEffect(() => {
        if (!isBusy) {
            // Intentional reset: recovery visibility tracks the external busy
            // state; clearing it here mirrors that external change rather than
            // deriving from props, so the effect is the correct sync point.
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setShowRecovery(false)
            return
        }

        const recoveryTimer = window.setTimeout(
            () => setShowRecovery(true),
            LOGIN_RECOVERY_DELAY_MS
        )
        return () => window.clearTimeout(recoveryTimer)
    }, [isBusy])

    useEffect(() => {
        if (!error || isBusy) return
        submitButtonRef.current?.focus()
    }, [error, isBusy])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (submissionInFlight.current) return

        submissionInFlight.current = true
        setError(null)
        setIsRequestPending(true)

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
                setIsRequestPending(false)
                return
            }

            setIsRequestPending(false)
            setIsNavigating(true)
            startNavigation(() => {
                router.refresh()
                router.push(callbackPath)
            })
        } catch {
            submissionInFlight.current = false
            setError(LOGIN_ERROR_MESSAGE)
            setIsRequestPending(false)
        }
    }

    return (
        <div className="flex min-h-screen flex-col items-center justify-center p-24">
            <form
                onSubmit={handleSubmit}
                className="flex flex-col gap-4 bg-white p-8 rounded shadow text-black"
            >
                <h1 className="text-2xl font-bold">Login</h1>
                <input
                    type="email"
                    aria-label="Email"
                    placeholder="Email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="border p-2 rounded"
                    readOnly={isBusy}
                />
                <input
                    type="password"
                    aria-label="Password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="border p-2 rounded"
                    readOnly={isBusy}
                />
                {error && (
                    <p role="alert" className="text-sm text-red-600">
                        {error}
                    </p>
                )}
                <p role="status" aria-live="polite" className="sr-only">
                    {showRecovery
                        ? 'Sign-in is taking longer than expected. Reload the login page to try again.'
                        : isBusy ? 'Signing in...' : ''}
                </p>
                {showRecovery && (
                    <p className="text-sm text-slate-600">
                        Taking longer than expected?{' '}
                        <a href={recoveryHref} className="font-medium text-blue-700 underline">
                            Reload login page
                        </a>
                    </p>
                )}
                <button
                    ref={submitButtonRef}
                    type="submit"
                    disabled={isBusy}
                    aria-busy={isBusy}
                    className="flex items-center justify-center gap-2 rounded bg-blue-500 p-2 text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {isBusy ? (
                        <>
                            <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
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
