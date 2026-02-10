import { useState, useEffect, useRef, useCallback } from 'react'
import { healthCheck } from '../api/client'

const POLL_INTERVAL_MS = 30_000 // 30 seconds

/**
 * Hook that polls the backend health endpoint and returns current status.
 *
 * @returns {{ status: string, health: object|null, lastChecked: Date|null }}
 *   status: "healthy" | "degraded" | "unhealthy" | "unreachable"
 *   health: full health response object (or null if unreachable)
 *   lastChecked: Date of last successful check (or null)
 */
export function useHealthStatus() {
  const [status, setStatus] = useState('healthy') // optimistic default
  const [health, setHealth] = useState(null)
  const [lastChecked, setLastChecked] = useState(null)
  const intervalRef = useRef(null)

  const doCheck = useCallback(async () => {
    try {
      const data = await healthCheck()
      setStatus(data.status)
      setHealth(data)
      setLastChecked(new Date())
    } catch {
      setStatus('unreachable')
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    // Initial check
    doCheck()

    // Set up polling
    intervalRef.current = setInterval(doCheck, POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [doCheck])

  return { status, health, lastChecked }
}
