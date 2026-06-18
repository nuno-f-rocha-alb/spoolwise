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

export interface Filament {
  id: number
  name: string
  material: string
  color: string
  color_hex: string | null
  stock_g: number
  stock_kg: number
  avg_price_per_kg: number
  stock_value: number
  is_zero_stock: boolean
  is_low_stock: boolean
}

export interface FilamentPurchase {
  id: number
  quantity_g: number
  price_per_kg: number
  purchased_at: string | null
}

export interface FilamentsResponse {
  currency: string
  filaments: Filament[]
  materials: string[]
  brands: string[]
}

export interface FilamentDetailResponse {
  currency: string
  filament: Filament
  purchases: FilamentPurchase[]
}
