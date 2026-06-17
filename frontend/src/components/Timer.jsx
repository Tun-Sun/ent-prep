import { useState, useEffect } from 'react'

export default function Timer({ seconds, onTimeout, isActive }) {
  const [timeLeft, setTimeLeft] = useState(seconds)

  useEffect(() => {
    setTimeLeft(seconds)
  }, [seconds])

  useEffect(() => {
    if (!isActive || timeLeft <= 0) return
    const interval = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(interval)
          onTimeout?.()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [isActive, timeLeft])

  const minutes = Math.floor(timeLeft / 60)
  const secs = timeLeft % 60
  const isDanger = timeLeft < 60

  return (
    <div className={`timer ${isDanger ? 'danger' : ''}`}>
      {String(minutes).padStart(2, '0')}:{String(secs).padStart(2, '0')}
    </div>
  )
}
