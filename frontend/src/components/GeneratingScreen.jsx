import { useEffect, useState } from 'react'

const STEPS = [
  { id: 1, label: 'Analysing your watch history',    icon: '🧠' },
  { id: 2, label: 'Planning key moments with AI',    icon: '🤖' },
  { id: 3, label: 'Searching video archive',         icon: '🔍' },
  { id: 4, label: 'Writing narration scripts',       icon: '✍️'  },
]

export default function GeneratingScreen({ step }) {
  const [dots, setDots] = useState('')

  useEffect(() => {
    const t = setInterval(() => {
      setDots(d => d.length >= 3 ? '' : d + '.')
    }, 400)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="generating-screen">
      <div className="generating-spinner" />
      <div className="generating-title">Building your recap{dots}</div>
      <div className="generating-subtitle">
        Searching the episode archive for the moments that matter to you
      </div>

      <div className="steps-list">
        {STEPS.map(s => {
          const state = s.id < step ? 'done' : s.id === step ? 'active' : 'pending'
          return (
            <div key={s.id} className={`step-item ${state}`}>
              <div className="step-icon">
                {state === 'done' ? '✓' : s.icon}
              </div>
              <span>{s.label}</span>
            </div>
          )
        })}
      </div>

      <div style={{ marginTop: 40, color: 'var(--text-dim)', fontSize: '0.78rem' }}>
        This takes 10–20 seconds · powered by VideoDB + Claude
      </div>
    </div>
  )
}
