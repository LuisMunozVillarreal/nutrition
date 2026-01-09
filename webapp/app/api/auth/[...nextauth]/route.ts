import NextAuth, { NextAuthOptions } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import { gql, GraphQLClient } from 'graphql-request'

const endpoint = process.env.GRAPHQL_ENDPOINT || 'http://nutrition-backend/graphql/';
const client = new GraphQLClient(endpoint);

export const authOptions: NextAuthOptions = {
    providers: [
        CredentialsProvider({
            name: 'Credentials',
            credentials: {
                email: { label: "Email", type: "email" },
                password: { label: "Password", type: "password" }
            },
            async authorize(credentials) {
                const mutation = gql`
          mutation Login($email: String!, $password: String!) {
            login(email: $email, password: $password) {
              token
              user {
                id
                email
                firstName
                lastName
              }
            }
          }
        `
                try {
                    const data: any = await client.request(mutation, {
                        email: credentials?.email,
                        password: credentials?.password
                    })

                    if (data.login) {
                        return {
                            id: data.login.user.id,
                            email: data.login.user.email,
                            name: `${data.login.user.firstName} ${data.login.user.lastName}`,
                            accessToken: data.login.token
                        }
                    }
                    return null
                } catch (e) {
                    console.error("Login failed", e)
                    return null
                }
            }
        })
    ],
    callbacks: {
        async jwt({ token, user }: any) {
            if (user) {
                token.accessToken = user.accessToken
            }
            return token
        },
        async session({ session, token }: any) {
            session.accessToken = token.accessToken
            return session
        }
    },
    pages: {
        signIn: '/login'
    }
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
