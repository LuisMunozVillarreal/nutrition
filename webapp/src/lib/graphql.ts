import { GraphQLClient, gql } from 'graphql-request'
import { getSession } from 'next-auth/react'

const resolveEndpoint = () => {
  let endpoint = process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT || '/graphql/'
  if (endpoint.startsWith('/') && typeof window !== 'undefined') {
    endpoint = `${window.location.origin}${endpoint}`
  }
  return endpoint
}

export async function graphqlRequest<T>(
  query: string,
  variables?: Record<string, unknown>,
): Promise<T> {
  let session = await getSession()

  // Retry once because the session may still be initializing immediately after login.
  if (!session) {
    await new Promise((resolve) => setTimeout(resolve, 500))
    session = await getSession()
  }

  const token = session?.accessToken
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  } else {
    console.warn('graphqlRequest: No access token found in session', { hasSession: Boolean(session) })
  }

  const client = new GraphQLClient(resolveEndpoint(), {
    headers,
    fetch: (input: RequestInfo | URL, init?: RequestInit) =>
      fetch(input, { ...init, cache: 'no-store' }),
  })

  return client.request(query, variables)
}

export { gql }
