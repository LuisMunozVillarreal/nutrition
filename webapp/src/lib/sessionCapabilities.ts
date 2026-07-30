export interface CapabilityUser {
  accessToken?: string
  isStaff?: boolean
}

export interface CapabilityToken {
  accessToken?: string
  isStaff?: boolean
  [key: string]: unknown
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
