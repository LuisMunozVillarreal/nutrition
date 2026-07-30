export interface CapabilityUser {
  accessToken?: string
  isStaff?: boolean
}

export interface CapabilityToken {
  accessToken?: string
  isStaff?: boolean
  staffCapabilityRefreshedAt?: number
  [key: string]: unknown
}

export type StaffCapabilityFetcher = (accessToken: string) => Promise<boolean>

export const STAFF_CAPABILITY_REFRESH_INTERVAL_MS = 5 * 60 * 1_000

export interface JwtCapabilityCallbackOptions {
  now?: () => number
}

export interface CapabilitySession {
  accessToken?: string
  user?: Record<string, unknown> | null
  [key: string]: unknown
}

export function applyUserCapabilitiesToToken<Token extends CapabilityToken>(
  token: Token,
  user?: CapabilityUser | null,
): Token {
  if (!user) return token

  token.accessToken = user.accessToken
  token.isStaff = user.isStaff === true
  return token
}

export function applyTokenCapabilitiesToSession<Session extends CapabilitySession>(
  session: Session,
  token: CapabilityToken,
): Session & { user: Record<string, unknown> & { isStaff: boolean } } {
  session.accessToken = token.accessToken
  session.user = {
    ...(session.user ?? {}),
    isStaff: token.isStaff === true,
  }
  return session as Session & {
    user: Record<string, unknown> & { isStaff: boolean }
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
      token.isStaff = (await fetchStaffCapability(token.accessToken)) === true
    } catch {
      token.isStaff = false
    }
    token.staffCapabilityRefreshedAt = refreshedAt
    return token
  }
}
