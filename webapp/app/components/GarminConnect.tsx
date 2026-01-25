"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { gql, GraphQLClient } from "graphql-request"

const CONNECT_MUTATION = gql`
  mutation ConnectGarmin($redirectUri: String!) {
    connectGarminUrl(redirectUri: $redirectUri)
  }
`

const DISCONNECT_MUTATION = gql`
  mutation DisconnectGarmin {
    disconnectGarmin
  }
`

interface Props {
    isConnected: boolean
    accessToken: string
}

export default function GarminConnect({ isConnected: initialConnected, accessToken }: Props) {
    const router = useRouter()
    const [isConnected, setIsConnected] = useState(initialConnected)
    const [loading, setLoading] = useState(false)
    const [mounted, setMounted] = useState(false)

    // Ensure component is mounted to avoid hydration mismatch
    useEffect(() => {
        setMounted(true)
        console.log("GarminConnect mounted. AccessToken present:", !!accessToken)
    }, [accessToken])

    const getClient = () => {
        const endpoint = process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT || "/graphql/"
        const client = new GraphQLClient(endpoint)
        if (accessToken) {
            client.setHeader("Authorization", `Bearer ${accessToken}`)
        }
        return client
    }

    const handleConnect = async () => {
        setLoading(true)
        try {
            const client = getClient()
            const redirectUri = `${window.location.origin}/settings/garmin-callback`
            const data: any = await client.request(CONNECT_MUTATION, { redirectUri })
            const url = data.connectGarminUrl
            window.location.href = url
        } catch (error) {
            console.error("Failed to get connect URL", error)
            setLoading(false)
        }
    }

    const handleDisconnect = async () => {
        if (!confirm("Are you sure you want to disconnect Garmin?")) return
        setLoading(true)
        try {
            const client = getClient()
            await client.request(DISCONNECT_MUTATION)
            setIsConnected(false)
            router.refresh()
        } catch (error) {
            console.error("Failed to disconnect", error)
        } finally {
            setLoading(false)
        }
    }

    if (!mounted) {
        return null; // or a skeleton loader
    }

    return (
        <div className="p-4 border rounded shadow-sm bg-white dark:bg-zinc-800">
            <h3 className="text-lg font-bold mb-4">Garmin Integration</h3>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <span className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500" : "bg-gray-300"}`} />
                    <span>{isConnected ? "Connected to Garmin" : "Not connected"}</span>
                </div>

                {isConnected ? (
                    <button
                        onClick={handleDisconnect}
                        disabled={loading}
                        className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50"
                    >
                        {loading ? "Processing..." : "Disconnect"}
                    </button>
                ) : (
                    <button
                        onClick={handleConnect}
                        disabled={loading}
                        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                    >
                        {loading ? "Redirecting..." : "Connect with Garmin"}
                    </button>
                )}
            </div>
        </div>
    )
}
