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
      </header>

      <main className="main">
        {screen === 'form' && (
          <>
            <div className="hero">
              <h1>Catch up in seconds.</h1>
              <p>
                Select your place in the series. We generate a seamless, director's cut recap of exactly what you need to remember. No spoilers.
              </p>
            </div>

            {seriesError && (
              <div className="error-box" style={{ marginBottom: 24 }}>
                ⚠️ Can't connect to backend: {seriesError}
                <br /><small>Make sure the FastAPI server is running on port 8000.</small>
              </div>
            )}

            {error && (
              <div className="error-box" style={{ marginBottom: 24 }}>
                ❌ {error}
              </div>
            )}

            <WatchStateForm
              seriesInfo={seriesInfo}
              onGenerate={handleGenerate}
              loading={!seriesInfo && !seriesError}
            />
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
