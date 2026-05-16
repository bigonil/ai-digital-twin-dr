import { useState, useEffect } from 'react'

export function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    const stored = localStorage.getItem('athena-theme')
    // Default: dark (the app was dark-first)
    return stored ? stored === 'dark' : true
  })

  useEffect(() => {
    const html = document.documentElement
    if (isDark) {
      html.classList.remove('light')
    } else {
      html.classList.add('light')
    }
    localStorage.setItem('athena-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return { isDark, toggleTheme: () => setIsDark(d => !d) }
}
