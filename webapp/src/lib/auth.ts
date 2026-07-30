export interface LoginCredentials {
  email?: string
  password?: string
}

export interface AuthorizedUser {
  id: string
  email: string
  name: string
  accessToken: string
  isStaff: boolean
}

interface LoginResponse {
  login: {
    token: string
    user: {
      id: string
      email: string
      firstName: string
      lastName: string
      isStaff: boolean
    }
  } | null
}

export type CredentialRequest = (
  document: string,
  variables: { email?: string; password?: string },
) => Promise<LoginResponse>

interface StaffCapabilityResponse {
  me: { isStaff: boolean } | null
}

export type StaffCapabilityResult =
  | { authentication: 'authenticated'; isStaff: boolean }
  | { authentication: 'unauthenticated' }

export type StaffCapabilityRequest = (
  document: string,
  variables: Record<string, never>,
  requestHeaders: { Authorization: string },
) => Promise<StaffCapabilityResponse>

const LOGIN_MUTATION = `
  mutation Login($email: String!, $password: String!) {
    login(email: $email, password: $password) {
      token
      user {
        id
        email
        firstName
        lastName
        isStaff
      }
    }
  }
`

const CURRENT_STAFF_CAPABILITY_QUERY = `
  query CurrentStaffCapability {
    me {
      isStaff
    }
  }
`

export async function fetchCurrentStaffCapability(
  accessToken: string,
  request: StaffCapabilityRequest,
): Promise<StaffCapabilityResult> {
  const data = await request(CURRENT_STAFF_CAPABILITY_QUERY, {}, {
    Authorization: `Bearer ${accessToken}`,
  })
  if (!data.me) return { authentication: 'unauthenticated' }
  return { authentication: 'authenticated', isStaff: data.me.isStaff === true }
}

export async function authorizeCredentials(
  credentials: LoginCredentials | undefined,
  request: CredentialRequest,
): Promise<AuthorizedUser | null> {
  try {
    const data = await request(LOGIN_MUTATION, {
      email: credentials?.email,
      password: credentials?.password,
    })
    if (!data.login) return null

    return {
      id: data.login.user.id,
      email: data.login.user.email,
      name: `${data.login.user.firstName} ${data.login.user.lastName}`,
      accessToken: data.login.token,
      isStaff: data.login.user.isStaff,
    }
  } catch {
    return null
  }
}
