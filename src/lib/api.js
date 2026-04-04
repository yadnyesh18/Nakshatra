const API_BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Generic fetch wrapper that prepends VITE_API_URL.
 * @param {string} path - e.g. '/exercises'
 * @param {RequestInit} options - standard fetch options
 * @returns {Promise<any>} - parsed JSON response
 */
export async function apiFetch(path, options = {}) {
  const url = `${API_BASE_URL}${path}`

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`[API] ${response.status} ${response.statusText}: ${errorText}`)
  }

  return response.json()
}

// Module-level cache so we only fetch exercises once per session
let _exercisesCache = null

/**
 * Fetches the exercises dictionary from GET /exercises.
 * Caches the result in memory — subsequent calls return the same object.
 * @returns {Promise<Record<string, any>>}
 */
export async function getExercises() {
  if (_exercisesCache !== null) {
    return _exercisesCache
  }
  const data = await apiFetch('/exercises')
  _exercisesCache = data
  return _exercisesCache
}

/**
 * Clears the exercises cache (useful for testing or forced refresh).
 */
export function clearExercisesCache() {
  _exercisesCache = null
}
