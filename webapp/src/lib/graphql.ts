
import { request, gql } from 'graphql-request';
import { getSession } from 'next-auth/react';

let endpoint = process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT || '/graphql/';
if (endpoint.startsWith('/') && typeof window !== 'undefined') {
  endpoint = `${window.location.origin}${endpoint}`;
}

export async function graphqlRequest<T>(
    query: string,
    variables?: Record<string, unknown>,
): Promise<T> {
    const session = await getSession();
    const token = session?.accessToken;

    const headers: Record<string, string> = {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    return request<T>(endpoint, query, variables, headers);
}

export { gql };
