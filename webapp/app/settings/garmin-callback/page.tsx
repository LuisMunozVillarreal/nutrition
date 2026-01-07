import { getServerSession } from "next-auth"
import { redirect } from "next/navigation"
import { authOptions } from "../../api/auth/[...nextauth]/route"
import { gql, GraphQLClient } from "graphql-request"

const CALLBACK_MUTATION = gql`
  mutation GarminCallback($code: String!) {
    garminAuthCallback(code: $code)
  }
`

export default async function GarminCallbackPage(props: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
    const searchParams = await props.searchParams
    const code = searchParams.code

    if (!code || Array.isArray(code)) {
        return (
            <div className="p-8 text-red-500">
                Invalid callback: Missing code. <a href="/settings" className="underline">Go back</a>
            </div>
        )
    }

    const session = await getServerSession(authOptions)
    if (!session) {
        redirect("/login")
    }

    const endpoint = process.env.GRAPHQL_ENDPOINT || "http://localhost:8000/graphql/"
    const client = new GraphQLClient(endpoint, {
        headers: {
            Authorization: `Bearer ${session.accessToken}`,
        },
    })

    try {
        await client.request(CALLBACK_MUTATION, { code })
    } catch (error) {
        console.error("Garmin callback failed", error)
        return (
            <div className="p-8 text-red-500">
                Failed to connect Garmin account. Please try again.
                <br />
                <a href="/settings" className="underline">Back to Settings</a>
            </div>
        )
    }

    redirect("/settings")
}
