// Thin fetch wrapper for the same-origin JSON API. Always sends the session
// cookie (credentials: "include") so Flask-Login works in dev (Vite proxy) and
// prod (served by Flask) alike.

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(message: string, status: number, data: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

type Body = object | undefined

async function request<T>(
  method: string,
  path: string,
  body?: Body
): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  const isJson = res.headers
    .get("content-type")
    ?.includes("application/json")
  const data = isJson ? await res.json() : await res.text()

  if (!res.ok) {
    const message =
      (isJson && data && typeof data === "object" && "error" in data
        ? (data as { error?: string }).error
        : undefined) || `Request failed (${res.status})`
    throw new ApiError(message, res.status, data)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: Body) => request<T>("POST", path, body),
  put: <T>(path: string, body?: Body) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: Body) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
}
