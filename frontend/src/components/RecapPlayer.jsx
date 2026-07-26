import { useState, useRef, useEffect } from 'react'
import Hls from 'hls.js'

// ─────────────────────────────────────────────────────────────
// PreviouslyOnIntro
// Full-screen intro card that plays the character-voiced audio,
// then dismisses itself. Handles browser autoplay gracefully.
// ─────────────────────────────────────────────────────────────
function PreviouslyOnIntro({ audioUrl, apiBase, seriesName, onDone }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [done,    setDone]    = useState(false)

  const tryPlay = () => {
    if (!audioRef.current || playing) return
    audioRef.current.volume = 1.0
    audioRef.current.play()
      .then(() => setPlaying(true))
      .catch(() => {
        // Autoplay blocked — skip intro silently
        handleDone()
      })
  }

  const handleDone = () => {
    setDone(true)
    setTimeout(onDone, 400) // short fade before showing recap
  }

  // Try autoplay after a tiny delay (gives browser time after user click)
  useEffect(() => {
    if (!audioUrl) { onDone(); return }
    const t = setTimeout(tryPlay, 300)
    return () => clearTimeout(t)
  }, [])

  if (done) return null

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#000',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: 24,
      animation: done ? 'fadeOut 0.4s ease forwards' : 'fadeIn 0.6s ease',
    }}>
      <style>{`
        @keyframes fadeIn  { from { opacity: 0 } to { opacity: 1 } }
        @keyframes fadeOut { from { opacity: 1 } to { opacity: 0 } }
        @keyframes pulse   { 0%,100% { opacity: 0.6 } 50% { opacity: 1 } }
      `}</style>

      {audioUrl && (
        <audio
          ref={audioRef}
          src={`${apiBase}${audioUrl}`}
          onEnded={handleDone}
          style={{ display: 'none' }}
        />
      )}

      <div style={{
        fontSize: '0.75rem', letterSpacing: '0.2em', textTransform: 'uppercase',
        color: 'rgba(255,255,255,0.4)', fontWeight: 600,
      }}>
        {playing ? 'Now playing' : 'Preparing recap...'}
      </div>

      <div style={{
        fontSize: 'clamp(1.4rem, 4vw, 2.2rem)',
        fontWeight: 700,
        color: '#fff',
        textAlign: 'center',
        letterSpacing: '-0.02em',
        animation: 'pulse 2s ease-in-out infinite',
      }}>
        Previously on<br />{seriesName}…
      </div>

      {playing && (
        <div style={{ display: 'flex', gap: 5, alignItems: 'flex-end', height: 24 }}>
          {[0,1,2,3,4].map(i => (
            <div key={i} style={{
              width: 3, background: 'var(--accent, #e05c2a)', borderRadius: 2,
              animation: `pulse ${0.6 + i * 0.1}s ease-in-out infinite`,
              height: 8 + i * 3,
            }} />
          ))}
        </div>
      )}

      <button
        onClick={handleDone}
        style={{
          marginTop: 8,
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.2)',
          color: 'rgba(255,255,255,0.4)',
          fontSize: '0.75rem',
          padding: '6px 18px',
          borderRadius: 99,
          cursor: 'pointer',
          letterSpacing: '0.05em',
        }}
      >
        Skip
      </button>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// ClipPlayer — HLS video player, no narration overlay
// ─────────────────────────────────────────────────────────────
function ClipPlayer({ clip, apiBase, isActive, onEnded, streamUrlOverride }) {
  const videoRef = useRef(null)
  const hlsRef   = useRef(null)
  const [streamUrl, setStreamUrl] = useState(streamUrlOverride || null)
  const [loading,   setLoading]   = useState(false)
  const [playing,   setPlaying]   = useState(false)

  // Fetch stream URL when active
  useEffect(() => {
    if (!isActive || streamUrl || streamUrlOverride || !clip?.video_id) return
    setLoading(true)
    fetch(`${apiBase}/clip-stream?video_id=${clip.video_id}&start=${clip.start}&end=${clip.end}`)
      .then(r => r.json())
      .then(d => { setStreamUrl(d.stream_url); setLoading(false) })
      .catch(() => setLoading(false))
  }, [isActive])

  // HLS attach + autoplay
  useEffect(() => {
    if (!streamUrl || !videoRef.current) return
    const video = videoRef.current
    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null }

    const playVideo = () => {
      if (isActive) video.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
    }

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = streamUrl
      video.addEventListener('loadedmetadata', playVideo)
    } else if (Hls.isSupported()) {
      const hls = new Hls({ autoStartLoad: true })
      hls.loadSource(streamUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, playVideo)
      hlsRef.current = hls
    }

    return () => {
      hlsRef.current?.destroy(); hlsRef.current = null
      video.removeEventListener('loadedmetadata', playVideo)
    }
  }, [streamUrl, isActive])

  const togglePlay = () => {
    if (!videoRef.current) return
    if (videoRef.current.paused) {
      videoRef.current.play().then(() => setPlaying(true)).catch(() => {})
    } else {
      videoRef.current.pause(); setPlaying(false)
    }
  }

  const scorePercent = Math.round((clip?.search_score || 0.5) * 100)

  return (
    <div>
      <div className="video-wrapper">
        {streamUrl ? (
          <video
            ref={videoRef}
            controls
            playsInline
            onEnded={() => { setPlaying(false); onEnded?.() }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : (
          <div style={{
            background: '#000', aspectRatio: '16/9',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-dim)', fontSize: '0.85rem',
          }}>
            {loading ? 'Loading clip...' : isActive ? 'Fetching stream...' : 'Ready'}
          </div>
        )}
        {streamUrl && !playing && (
          <div className="video-overlay" onClick={togglePlay}>
            <div className="play-btn-big">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
        )}
      </div>

      {clip?.episode_number && (
        <div style={{ marginTop: 16, padding: '0 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            {clip.episode_title}
          </div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', background: 'rgba(255,255,255,0.1)', padding: '4px 10px', borderRadius: 4 }}>
            Episode {clip.episode_number}
          </div>
        </div>
      )}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// RecapPlayer — main component
// ─────────────────────────────────────────────────────────────
export default function RecapPlayer({ recap, apiBase, onReset }) {
  const [showIntro,   setShowIntro]   = useState(!!recap.previously_on_audio_url)
  const [activeIndex, setActiveIndex] = useState(0)
  const [playMode,    setPlayMode]    = useState('interactive')

  const segments = recap.segments || []

  const goNext = () => { if (activeIndex < segments.length - 1) setActiveIndex(i => i + 1) }
  const goPrev = () => { if (activeIndex > 0) setActiveIndex(i => i - 1) }

  const seriesName = recap.user_state
    ? `Episode ${recap.user_state.watched_episodes.slice(-1)[0]}`
    : 'the show'

  return (
    <>
      {/* Previously on... intro */}
      {showIntro && (
        <PreviouslyOnIntro
          audioUrl={recap.previously_on_audio_url}
          apiBase={apiBase}
          seriesName="Breaking Bad"
          onDone={() => setShowIntro(false)}
        />
      )}

      {/* Main recap UI */}
      <div style={{ opacity: showIntro ? 0 : 1, transition: 'opacity 0.4s ease' }}>
        {/* Header */}
        <div className="recap-header">
          <div className="recap-badge">Recap Ready</div>
          <div className="recap-title">Previously on {seriesName}…</div>
          <div className="recap-meta">
            {segments.length} moments · {Math.round(recap.total_duration_seconds)}s total
            {recap.user_state?.focus_character && ` · Focused on ${recap.user_state.focus_character}`}
          </div>

          {recap.compiled_stream_url && (
            <button
              className="ctrl-btn primary"
              style={{
                marginTop: 16, width: '100%',
                background: playMode === 'seamless' ? 'var(--bg-raised)' : 'var(--accent)',
                color: 'white',
              }}
              onClick={() => setPlayMode(playMode === 'interactive' ? 'seamless' : 'interactive')}
            >
              {playMode === 'interactive' ? '🎬 Watch as Seamless Cut' : '⬅ Back to Interactive Mode'}
            </button>
          )}
        </div>

        {playMode === 'seamless' ? (
          <div style={{ marginTop: 24, padding: 16, background: 'var(--bg-card)', borderRadius: 12 }}>
            <div style={{ marginBottom: 12, fontSize: '0.9rem', color: 'var(--accent)', fontWeight: 600 }}>
              Seamless Director's Cut
            </div>
            <ClipPlayer
              clip={{}} apiBase={apiBase} isActive={true}
              streamUrlOverride={recap.compiled_stream_url}
            />
          </div>
        ) : (
          <>
            {recap.status === 'partial' && (
              <div className="error-box" style={{ marginBottom: 16, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.3)', color: '#fde68a' }}>
                ⚠️ {recap.message}
              </div>
            )}

            <div>
              {segments.map((seg, i) => (
                <div
                  key={i}
                  className={`segment ${i === activeIndex ? 'active-segment' : ''}`}
                  style={{ display: i === activeIndex ? 'block' : 'none', border: 'none', background: 'transparent' }}
                  onClick={() => setActiveIndex(i)}
                >
                  <ClipPlayer
                    clip={seg.clip}
                    apiBase={apiBase}
                    isActive={i === activeIndex}
                    onEnded={goNext}
                  />
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 12, marginTop: 24, justifyContent: 'center' }}>
              <button 
                className="ctrl-btn" 
                onClick={goPrev} 
                disabled={activeIndex === 0}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', padding: '12px 24px', borderRadius: 4, fontWeight: 700 }}
              >
                ← Previous
              </button>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 16px' }}>
                {segments.map((_, i) => (
                  <div 
                    key={i} 
                    onClick={() => setActiveIndex(i)}
                    style={{
                      width: i === activeIndex ? 24 : 8,
                      height: 8,
                      borderRadius: 4,
                      background: i === activeIndex ? 'var(--accent)' : 'rgba(255,255,255,0.2)',
                      transition: '0.3s',
                      cursor: 'pointer'
                    }}
                  />
                ))}
              </div>

              <button 
                className="ctrl-btn" 
                onClick={goNext} 
                disabled={activeIndex === segments.length - 1}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', padding: '12px 24px', borderRadius: 4, fontWeight: 700 }}
              >
                Next →
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 32 }}>
              <button 
                onClick={onReset}
                style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: 'rgba(255,255,255,0.6)', padding: '10px 24px', borderRadius: 4, cursor: 'pointer', transition: '0.2s' }}
                onMouseEnter={e => { e.target.style.color = '#fff'; e.target.style.borderColor = '#fff' }}
                onMouseLeave={e => { e.target.style.color = 'rgba(255,255,255,0.6)'; e.target.style.borderColor = 'rgba(255,255,255,0.2)' }}
              >
                Start New Recap
              </button>
            </div>
          </>
        )}
      </div>
    </>
  )
}
