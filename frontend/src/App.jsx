import { useState, useEffect } from 'react'
import WatchStateForm from './components/WatchStateForm'
import GeneratingScreen from './components/GeneratingScreen'
import RecapPlayer from './components/RecapPlayer'

const API_BASE = 'http://localhost:8000'

export default function App() {
  const [screen, setScreen] = useState('form')          // 'form' | 'generating' | 'player'
  const [seriesInfo, setSeriesInfo] = useState(null)
  const [seriesError, setSeriesError] = useState(null)
  const [recapData, setRecapData] = useState(null)
  const [generatingStep, setGeneratingStep] = useState(0)
  const [error, setError] = useState(null)

  // Load series info on mount
  useEffect(() => {
    fetch(`${API_BASE}/series`)
      .then(r => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`)
        return r.json()
      })
      .then(setSeriesInfo)
      .catch(e => setSeriesError(e.message))
  }, [])

  const handleGenerate = async (userState) => {
    setError(null)
    setScreen('generating')
    setGeneratingStep(0)

    try {
      // Step indicators fire on a rough timeline
      setGeneratingStep(1)  // Planning agent
      await new Promise(r => setTimeout(r, 1200))
      setGeneratingStep(2)  // Retrieving clips

      const res = await fetch(`${API_BASE}/generate-recap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(userState),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail || `Server error ${res.status}`)
      }

      setGeneratingStep(3)  // Writing narration
      const data = await res.json()
      await new Promise(r => setTimeout(r, 800))

      setGeneratingStep(4)  // Done
      await new Promise(r => setTimeout(r, 600))

      setRecapData(data)
      setScreen('player')
    } catch (e) {
      setError(e.message)
      setScreen('form')
    }
  }

  const handleReset = () => {
    setScreen('form')
    setRecapData(null)
    setError(null)
    setGeneratingStep(0)
  }

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          CINEMA RECAP
        </div>
        <div style={{ display: 'flex', gap: 20, fontWeight: 500, fontSize: '0.9rem', color: '#e5e5e5' }}>
          <span style={{ color: '#fff', fontWeight: 700 }}>Home</span>
          <span>TV Shows</span>
          <span>Movies</span>
          <span>My List</span>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ width: 32, height: 32, background: 'var(--accent)', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
          U
        </div>
      </header>

      <main className="main">
        {screen === 'form' && (
          <>
            <div className="netflix-hero">
              <div className="netflix-hero-vignette" />
              <div className="netflix-hero-content">
                <div style={{ fontSize: '3rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.02em', marginBottom: 8, textShadow: '0 2px 20px rgba(0,0,0,0.8)' }}>
                  Breaking Bad
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, fontSize: '0.9rem', fontWeight: 600, color: '#a3a3a3' }}>
                  <span style={{ color: '#46d369' }}>98% Match</span>
                  <span>2008</span>
                  <span style={{ border: '1px solid rgba(255,255,255,0.4)', padding: '1px 4px', borderRadius: 2 }}>TV-MA</span>
                  <span>5 Seasons</span>
                  <span style={{ border: '1px solid rgba(255,255,255,0.4)', padding: '1px 4px', borderRadius: 2, fontSize: '0.7rem' }}>HD</span>
                </div>
                <p style={{ maxWidth: 500, fontSize: '1.2rem', lineHeight: 1.5, textShadow: '0 2px 4px rgba(0,0,0,0.8)', marginBottom: 24, fontWeight: 500 }}>
                  A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing and selling methamphetamine in order to secure his family's future.
                </p>
                {/* Form will inject the play button here */}
              </div>
            </div>

            <div className="netflix-rows-container">
              {seriesError && (
                <div className="error-box" style={{ marginBottom: 24, margin: '0 50px' }}>
                  ⚠️ Can't connect to backend: {seriesError}
                  <br /><small>Make sure the FastAPI server is running on port 8000.</small>
                </div>
              )}

              {error && (
                <div className="error-box" style={{ marginBottom: 24, margin: '0 50px' }}>
                  ❌ {error}
                </div>
              )}

              <WatchStateForm
                seriesInfo={seriesInfo}
                onGenerate={handleGenerate}
                loading={!seriesInfo && !seriesError}
              />
            </div>
          </>
        )}

        {screen === 'generating' && (
          <GeneratingScreen step={generatingStep} />
        )}

        {screen === 'player' && recapData && (
          <RecapPlayer
            recap={recapData}
            apiBase={API_BASE}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  )
}
