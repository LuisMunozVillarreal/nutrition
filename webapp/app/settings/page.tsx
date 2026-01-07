import { getServerSession } from "next-auth"
import { redirect } from "next/navigation"
import { authOptions } from "../api/auth/[...nextauth]/route"
import { gql, GraphQLClient } from "graphql-request"
import GarminConnect from "../components/GarminConnect"
import Link from "next/link"

const STATUS_QUERY = gql`
  query GarminStatus {
    garminConnectionStatus
  }
`

async function getGarminStatus(accessToken: string) {
    const endpoint = process.env.GRAPHQL_ENDPOINT || "http://localhost:8000/graphql/"
    const client = new GraphQLClient(endpoint, {
        headers: {
            Authorization: `Bearer ${accessToken}`,
        },
    })

    try {
        const data: any = await client.request(STATUS_QUERY)
        return data.garminConnectionStatus
    } catch (error) {
        console.error("Failed to fetch Garmin status", error)
        return false
    }
}

export default async function SettingsPage() {
    const session = await getServerSession(authOptions)

    if (!session) {
        redirect("/login")
    }

    const isConnected = await getGarminStatus(session.accessToken as string)

    return (
        <div className="min-h-screen p-8">
            <div className="max-w-4xl mx-auto">
                <header className="mb-8 flex justify-between items-center">
                    <h1 className="text-2xl font-bold">Settings</h1>
                    <Link href="/" className="text-blue-500 hover:underline">
                        Back to Dashboard
                    </Link>
                </header>

                <section className="space-y-6">
                    <GarminConnect isConnected={isConnected} />
                </section>
            </div>
        </div>
    )
}
