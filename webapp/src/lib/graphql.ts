
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
    let session = await getSession();
    
    // Retry once if session is missing, as it might take a moment to initialize after login
    if (!session) {
        await new Promise(resolve => setTimeout(resolve, 500));
        session = await getSession();
    }
    
    const token = session?.accessToken;

    const headers: Record<string, string> = {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    } else {
        console.warn('graphqlRequest: No access token found in session', { hasSession: !!session });
    }

    const extras: Record<string, unknown> = {};
    extras.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
        return fetch(input, { ...init, cache: 'no-store' });
    };

    return request<T>({
        url: endpoint,
        document: query,
        variables,
        requestHeaders: headers,
        ...extras
    });
}

export { gql };
