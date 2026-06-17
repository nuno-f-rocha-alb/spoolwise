export interface User {
  id: number
  username: string
  display_name: string | null
  email: string | null
  is_admin: boolean
  initials: string
}

export interface AuthMe {
  authenticated: boolean
  user: User
  currency: string
  retail_mode_enabled: boolean
  trust_proxy_auth: boolean
  disable_local_login: boolean
  sso_session: boolean
}

export interface LoginResponse {
  user: User
  currency: string
  retail_mode_enabled: boolean
  trust_proxy_auth: boolean
  disable_local_login: boolean
  sso_session: boolean
}
