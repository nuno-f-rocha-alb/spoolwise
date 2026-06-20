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

export interface OrderListItem {
  id: number
  name: string
  customer: string | null
  created_at: string | null
  is_internal: boolean
  skip_stock_deduction: boolean
  has_vat: boolean
  vat_rate_pct: number | null
  quantity: number
  status: string
  plate_count: number
  total_print_time_hours: number
  total_cost: number
  sell_price: number
  sell_price_with_vat: number
  profit_value: number
}

export interface OrdersResponse {
  currency: string
  retail_mode_enabled: boolean
  orders: OrderListItem[]
}

export interface PlateItem {
  id: number
  filament_id: number
  weight_g: number
  price_per_kg_snapshot: number
  cost: number
  filament: {
    id: number
    name: string
    material: string
    color: string
    color_hex: string | null
  } | null
}

export interface Plate {
  id: number
  position: number
  name: string | null
  print_time_hours: number
  printed_at: string | null
  is_skipped: boolean
  filament_cost: number
  electricity_cost: number
  total_cost: number
  items: PlateItem[]
}

export interface OrderLinkItem {
  id: number
  url: string
  title: string | null
  image: string | null
}

export interface OrderFileItem {
  id: number
  filename: string
  original_name: string
  file_type: string
  is_plate_thumb: boolean
  plate_index: number | null
  is_viewable_3d: boolean
  is_image: boolean
}

export interface OrderDetail {
  id: number
  name: string
  customer: string | null
  notes: string | null
  created_at: string | null
  printed_at: string | null
  delivered_at: string | null
  status: string
  is_internal: boolean
  skip_stock_deduction: boolean
  has_vat: boolean
  vat_rate_pct: number | null
  quantity: number
  profit_pct: number
  printer_power_watts: number
  electricity_price_per_kwh: number
  total_print_time_hours: number
  unit_print_time_hours: number
  filament_cost: number
  electricity_cost: number
  total_cost: number
  unit_cost: number
  sell_price: number
  unit_sell_price: number
  vat_amount: number
  sell_price_with_vat: number
  profit_value: number
  plates: Plate[]
  links: OrderLinkItem[]
  files: OrderFileItem[]
}

export interface OrderDetailResponse {
  currency: string
  retail_mode_enabled: boolean
  order: OrderDetail
}

export interface QuoteItem {
  id: number
  name: string
  customer: string | null
  created_at: string | null
  is_internal: boolean
  has_vat: boolean
  vat_rate_pct: number | null
  quantity: number
  unit_sell_price: number
  sell_price: number
  vat_amount: number
  sell_price_with_vat: number
}

export interface CombinedQuoteResponse {
  currency: string
  orders: QuoteItem[]
  subtotal: number
  vat_total: number
  total: number
  has_any_vat: boolean
  vat_rates: number[]
}

export interface AppSettings {
  electricity_price_per_kwh: number
  printer_power_watts: number
  default_profit_pct: number
  currency_symbol: string
  retail_mode_enabled: boolean
  default_vat_rate_pct: number
}

export interface OrderFormPayload {
  name: string
  customer?: string | null
  notes?: string | null
  model_urls: string[]
  is_internal: boolean
  skip_stock_check: boolean
  profit_pct: number
  quantity: number
  has_vat: boolean
  vat_rate_pct?: number | null
  plates: {
    name: string | null
    print_time_hours: number
    filaments: { filament_id: number; weight_g: number }[]
  }[]
}

export interface OrderMutationResult {
  order: OrderDetail
  stock_warnings: string[]
}

export interface Parse3mfMatched {
  id: number
  brand: string
  material: string
  color: string
  color_hex: string
}

export interface Parse3mfPlate {
  index: number
  name: string
  print_time_hours: number
  filaments: {
    type: string
    color: string
    used_g: number
    matched: Parse3mfMatched | null
  }[]
  thumb_b64: string | null
}

export interface Parse3mfResponse {
  plates: Parse3mfPlate[]
  thumb_b64: string | null
  warning: string | null
}
