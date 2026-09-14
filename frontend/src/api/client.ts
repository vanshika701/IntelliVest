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

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: getDefaultHeaders(),
  })

  if (!response.ok) {
    throw new ApiError(`GET ${path} failed with status ${response.status}`, response.status)
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
      const errData = await response.json()
      message = errData.detail || message
    } catch (e) {}
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
    throw new ApiError(`PATCH ${path} failed with status ${response.status}`, response.status)
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
