// Thin fetch wrapper — every backend call goes through here so the base
// URL, error handling, and JSON parsing live in one place instead of being
// copy-pasted into every component that needs data.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI errors: `detail` is a string, or a list of {msg} for 422s. */
function errorDetail(errData: any, fallback: string): string {
  if (Array.isArray(errData?.detail)) return errData.detail.map((d: { msg: string }) => d.msg).join('; ')
  return errData?.detail || fallback
}

function getDefaultHeaders() {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const token = localStorage.getItem('intellivest_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export async function apiGet<T>(path: string, init?: { signal?: AbortSignal }): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: getDefaultHeaders(),
    signal: init?.signal,
  })

  if (!response.ok) {
    let message = `GET ${path} failed with status ${response.status}`
    try {
      message = errorDetail(await response.json(), message)
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: any): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: getDefaultHeaders(),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    let message = `POST ${path} failed`
    try {
      message = errorDetail(await response.json(), message)
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export async function apiPut<T>(path: string, body: any): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    headers: getDefaultHeaders(),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    let message = `PUT ${path} failed`
    try {
      message = errorDetail(await response.json(), message)
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export async function apiPatch<T>(path: string, body: any): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: getDefaultHeaders(),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    let message = `PATCH ${path} failed with status ${response.status}`
    try {
      message = errorDetail(await response.json(), message)
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: getDefaultHeaders(),
  })

  if (!response.ok) {
    throw new ApiError(`DELETE ${path} failed with status ${response.status}`, response.status)
  }
}
