import NextAuth, { NextAuthOptions } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import { GraphQLClient } from 'graphql-request'
import {
    authorizeCredentials,
    fetchCurrentStaffCapability,
    type CredentialRequest,
    type StaffCapabilityRequest,
} from '@/lib/auth'
import {
    applyTokenCapabilitiesToSession,
    createJwtCapabilityCallback,
} from '@/lib/sessionCapabilities'

const endpoint = process.env.GRAPHQL_ENDPOINT || 'http://localhost:8000/graphql/';
const client = new GraphQLClient(endpoint);
const credentialRequest: CredentialRequest = (document, variables) =>
    client.request(document, variables)
const staffCapabilityRequest: StaffCapabilityRequest = (
    document,
    variables,
    requestHeaders,
) => client.request(document, variables, requestHeaders)
const jwtCapabilityCallback = createJwtCapabilityCallback((accessToken) =>
    fetchCurrentStaffCapability(accessToken, staffCapabilityRequest)
)

export const authOptions: NextAuthOptions = {
    session: {
        maxAge: 7 * 24 * 60 * 60,
    },
    jwt: {
        maxAge: 7 * 24 * 60 * 60,
    },
    providers: [
        CredentialsProvider({
            name: 'Credentials',
            credentials: {
                email: { label: "Email", type: "email" },
                password: { label: "Password", type: "password" }
            },
            async authorize(credentials) {
                return authorizeCredentials(credentials, credentialRequest)
            }
        })
    ],
    callbacks: {
        async jwt({ token, user }) {
            return jwtCapabilityCallback({ token, user })
        },
        async session({ session, token }) {
            return applyTokenCapabilitiesToSession(session, token)
        }
    },
    pages: {
        signIn: '/login'
    }
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
