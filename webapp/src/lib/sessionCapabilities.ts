import type { StaffCapabilityResult } from './auth'

export const BACKEND_REAUTHENTICATION_REQUIRED =
  'BackendReauthenticationRequired' as const

export interface CapabilityUser {
  accessToken?: string
  isStaff?: boolean
}

export interface CapabilityToken {
  accessToken?: string
  isStaff?: boolean
  staffCapabilityRefreshedAt?: number
  error?: typeof BACKEND_REAUTHENTICATION_REQUIRED
  [key: string]: unknown
}

export type StaffCapabilityFetcher = (
  accessToken: string,
) => Promise<StaffCapabilityResult>

export const STAFF_CAPABILITY_REFRESH_INTERVAL_MS = 5 * 60 * 1_000

export interface JwtCapabilityCallbackOptions {
  now?: () => number
}

export interface CapabilitySession {
  accessToken?: string
  error?: typeof BACKEND_REAUTHENTICATION_REQUIRED
  user?: object | null
}

export function applyUserCapabilitiesToToken<Token extends CapabilityToken>(
  token: Token,
  user?: CapabilityUser | null,
): Token {
  if (!user) return token

  token.accessToken = user.accessToken
  token.isStaff = user.isStaff === true
  delete token.error
  return token
}

export function applyTokenCapabilitiesToSession<Session extends CapabilitySession>(
  session: Session,
  token: CapabilityToken,
): Session & { user: NonNullable<Session['user']> & { isStaff: boolean } } {
  if (token.accessToken) session.accessToken = token.accessToken
  else delete session.accessToken
  if (token.error) session.error = token.error
  else delete session.error
  session.user = {
    ...(session.user ?? {}),
    isStaff: token.isStaff === true,
  }
  return session as Session & {
    user: NonNullable<Session['user']> & { isStaff: boolean }
  }
}

export function createJwtCapabilityCallback(
  fetchStaffCapability: StaffCapabilityFetcher,
  options: JwtCapabilityCallbackOptions = {},
) {
  const now = options.now ?? Date.now

  return async <Token extends CapabilityToken>({
    token,
    user,
  }: {
    token: Token
    user?: CapabilityUser | null
  }): Promise<Token> => {
    const refreshedAt = now()
    if (user) {
      applyUserCapabilitiesToToken(token, user)
      token.staffCapabilityRefreshedAt = refreshedAt
      return token
    }

    if (!token.accessToken) {
      token.isStaff = false
      return token
    }

    const previousRefresh = token.staffCapabilityRefreshedAt
    const refreshIsDue =
      typeof previousRefresh !== 'number' ||
      previousRefresh > refreshedAt ||
      refreshedAt - previousRefresh >= STAFF_CAPABILITY_REFRESH_INTERVAL_MS
    if (!refreshIsDue) return token

    try {
      const capability = await fetchStaffCapability(token.accessToken)
      if (capability.authentication === 'unauthenticated') {
        delete token.accessToken
        token.isStaff = false
        token.error = BACKEND_REAUTHENTICATION_REQUIRED
      } else {
        token.isStaff = capability.isStaff
        delete token.error
      }
    } catch {
      token.isStaff = false
    }
    token.staffCapabilityRefreshedAt = refreshedAt
    return token
  }
}
