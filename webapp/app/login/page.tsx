'use client'

import { signIn } from 'next-auth/react'
import { useState } from 'react'

const LoginPage = () => {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [isSubmitting, setIsSubmitting] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsSubmitting(true)
        const result = await signIn('credentials', {
            email,
            password,
            redirect: false
        })

        if (result?.ok) {
            // Use hard navigation to avoid RSC streaming issues through reverse proxies
            window.location.href = '/'
        } else {
            setIsSubmitting(false)
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
                <button type="submit" disabled={isSubmitting} className="bg-blue-500 text-white p-2 rounded disabled:opacity-50">
                    {isSubmitting ? 'Signing in...' : 'Sign In'}
                </button>
            </form>
        </div>
    )
}

export default LoginPage;
