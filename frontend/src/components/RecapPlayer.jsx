import { useState, useRef, useEffect } from 'react'
import Hls from 'hls.js'
import SceneChatbot from './SceneChatbot'
import EpisodeModal from './EpisodeModal'

// ─────────────────────────────────────────────────────────────
// PreviouslyOnIntro
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
      .catch(() => handleDone())
  }

  const handleDone = () => {
    setDone(true)
    setTimeout(onDone, 400)
  }

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
        <audio ref={audioRef} src={`${apiBase}${audioUrl}`} onEnded={handleDone} style={{ display: 'none' }} />
      )}

      <div style={{ fontSize: '0.75rem', letterSpacing: '0.2em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>
        {playing ? 'Now playing' : 'Preparing recap...'}
      </div>

      <div style={{ fontSize: 'clamp(1.4rem, 4vw, 2.2rem)', fontWeight: 700, color: '#fff', textAlign: 'center', letterSpacing: '-0.02em', animation: 'pulse 2s ease-in-out infinite' }}>
        Previously on<br />{seriesName}…
      </div>

      {playing && (
        <div style={{ display: 'flex', gap: 5, alignItems: 'flex-end', height: 24 }}>
          {[0,1,2,3,4].map(i => (
            <div key={i} style={{ width: 3, background: 'var(--accent, #e05c2a)', borderRadius: 2, animation: `pulse ${0.6 + i * 0.1}s ease-in-out infinite`, height: 8 + i * 3 }} />
          ))}
        </div>
      )}

      <button onClick={handleDone} style={{ marginTop: 8, background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem', padding: '6px 18px', borderRadius: 99, cursor: 'pointer', letterSpacing: '0.05em' }}>
        Skip
      </button>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────
// ClipPlayer — HLS video player with dynamic verbatim dialogue subtitles
// ─────────────────────────────────────────────────────────────
function ClipPlayer({ clip, narrationText, apiBase, isActive, onEnded, streamUrlOverride, onWatchOriginal, segments }) {
  const videoRef = useRef(null)
  const hlsRef   = useRef(null)
  const [streamUrl,    setStreamUrl]    = useState(streamUrlOverride || null)
  const [loading,      setLoading]      = useState(false)
  const [playing,      setPlaying]      = useState(false)
  const [showCaptions, setShowCaptions] = useState(true)
  const [currentTime,  setCurrentTime]  = useState(0)

  // Calculate verbatim dialogue caption
  let caption = narrationText || clip?.moment_description || ""

  // Dynamic live subtitles during Seamless Director's Cut stream playback
  if (streamUrlOverride && segments && segments.length > 0) {
    let accumTime = 0
    for (const seg of segments) {
      const dur = (seg.clip.end - seg.clip.start) || 10
      if (currentTime >= accumTime && currentTime <= accumTime + dur + 0.5) {
        caption = seg.narration_text || seg.clip?.moment_description || ""
        break
      }
      accumTime += dur
    }
  }

  useEffect(() => {
    if (streamUrl || streamUrlOverride || !clip?.video_id) return
    setLoading(true)
    fetch(`${apiBase}/clip-stream?video_id=${clip.video_id}&start=${clip.start}&end=${clip.end}`)
      .then(r => r.json())
      .then(d => { setStreamUrl(d.stream_url); setLoading(false) })
      .catch(() => setLoading(false))
  }, [clip?.video_id, clip?.start, clip?.end, streamUrlOverride])

  useEffect(() => {
    if (!streamUrl || !videoRef.current) return
    const video = videoRef.current
    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null }

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = streamUrl
    } else if (Hls.isSupported()) {
      const hls = new Hls({ autoStartLoad: true })
      hls.loadSource(streamUrl)
      hls.attachMedia(video)
      hlsRef.current = hls
    }

    return () => { hlsRef.current?.destroy(); hlsRef.current = null }
  }, [streamUrl])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !streamUrl) return
    if (isActive) {
      video.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
    } else {
      video.pause()
      setPlaying(false)
    }
  }, [isActive, streamUrl])

  const togglePlay = () => {
    if (!videoRef.current) return
    if (videoRef.current.paused) {
      videoRef.current.play().then(() => setPlaying(true)).catch(() => {})
    } else {
      videoRef.current.pause(); setPlaying(false)
    }
  }

  return (
    <div>
      <div className="video-wrapper">
        {streamUrl ? (
          <video
            ref={videoRef}
            controls
            playsInline
            onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
            onEnded={() => { setPlaying(false); onEnded?.() }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : (
          <div style={{ background: '#000', aspectRatio: '16/9', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
            {loading ? 'Loading clip...' : isActive ? 'Fetching stream...' : 'Ready'}
          </div>
        )}

        {/* Play button overlay */}
        {streamUrl && !playing && (
          <div className="video-overlay" onClick={togglePlay}>
            <div className="play-btn-big">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="white"><path d="M8 5v14l11-7z"/></svg>
            </div>
          </div>
        )}

        {/* Top-left CC Subtitles toggle button */}
        {(caption || (segments && segments.length > 0)) && (
          <div style={{ position: 'absolute', top: 12, left: 12, zIndex: 12 }}>
            <button
              onClick={(e) => { e.stopPropagation(); setShowCaptions(s => !s) }}
              style={{
                background: showCaptions ? 'rgba(229,9,20,0.85)' : 'rgba(0,0,0,0.75)',
                border: '1px solid rgba(255,255,255,0.25)',
                color: '#fff', padding: '5px 12px', borderRadius: 99,
                cursor: 'pointer', fontSize: '0.75rem', fontWeight: 700,
                fontFamily: 'inherit', transition: '0.2s',
                backdropFilter: 'blur(8px)',
              }}
            >
              {showCaptions ? '💬 CC On' : '💬 CC Off'}
            </button>
          </div>
        )}

        {/* Top-right Watch Full Episode button */}
        {clip?.video_id && onWatchOriginal && (
          <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 12 }}>
            <button
              onClick={(e) => { e.stopPropagation(); onWatchOriginal(clip) }}
              style={{
                background: 'rgba(0,0,0,0.85)',
                backdropFilter: 'blur(8px)',
                border: '1px solid rgba(255,255,255,0.25)',
                color: '#fff',
                padding: '7px 14px',
                borderRadius: 99,
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 700,
                display: 'flex', alignItems: 'center', gap: 6,
                boxShadow: '0 4px 14px rgba(0,0,0,0.6)',
                transition: 'all 0.2s ease',
                fontFamily: 'inherit',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = '#E50914'; e.currentTarget.style.borderColor = '#E50914' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.85)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.25)' }}
            >
              📺 Watch Full Episode
            </button>
          </div>
        )}

        {/* Bottom Movie Subtitles Overlay (Live Synced) */}
        {showCaptions && caption && (
          <div style={{
            position: 'absolute', bottom: 48, left: 20, right: 20, zIndex: 11,
            pointerEvents: 'none', display: 'flex', justifyContent: 'center',
          }}>
            <div style={{
              background: 'rgba(0,0,0,0.85)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: 6,
              padding: '8px 18px',
              maxWidth: '90%',
              display: 'flex', alignItems: 'center', gap: 10,
              boxShadow: '0 4px 20px rgba(0,0,0,0.8)',
            }}>
              <span style={{
                background: '#E50914', color: '#fff', fontSize: '0.65rem',
                fontWeight: 900, padding: '2px 6px', borderRadius: 3,
                letterSpacing: '0.08em', textTransform: 'uppercase', flexShrink: 0,
              }}>SUBTITLES</span>
              <span style={{ color: '#fff', fontSize: '0.95rem', fontWeight: 600, lineHeight: 1.45, fontStyle: 'italic' }}>
                "{caption}"
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Metadata & Prominent Watch Button Bar */}
      {clip?.episode_number && (
        <div style={{ marginTop: 16, padding: '0 4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
              {clip.episode_title || `Episode ${clip.episode_number}`}
            </div>
            {clip.moment_description && (
              <div style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.4 }}>
                {clip.moment_description}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {onWatchOriginal && (
              <button
                onClick={() => onWatchOriginal(clip)}
                style={{
                  background: 'linear-gradient(135deg, #E50914, #c4000f)',
                  border: 'none',
                  color: '#fff',
                  padding: '9px 18px',
                  borderRadius: 99,
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  display: 'flex', alignItems: 'center', gap: 6,
                  boxShadow: '0 4px 14px rgba(229,9,20,0.4)',
                  transition: 'all 0.2s ease',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.04)'}
                onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
              >
                📺 Watch in Full Episode
              </button>
            )}
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', background: 'rgba(255,255,255,0.1)', padding: '6px 12px', borderRadius: 6, whiteSpace: 'nowrap' }}>
              Ep {clip.episode_number}
            </div>
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
  const [showIntro,      setShowIntro]      = useState(!!recap.previously_on_audio_url)
  const [activeIndex,    setActiveIndex]    = useState(0)
  const [playMode,       setPlayMode]       = useState('interactive')
  const [chatOpen,       setChatOpen]       = useState(false)
  const [episodeClip,    setEpisodeClip]    = useState(null)   // triggers EpisodeModal

  const segments = recap.segments || []

  const goNext = () => { if (activeIndex < segments.length - 1) setActiveIndex(i => i + 1) }
  const goPrev = () => { if (activeIndex > 0) setActiveIndex(i => i - 1) }

  const activeClip = segments[activeIndex]?.clip || null
  const activeNarration = segments[activeIndex]?.narration_text || ""

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

      {/* Full episode modal */}
      {episodeClip && (
        <EpisodeModal
          apiBase={apiBase}
          clip={episodeClip}
          onClose={() => setEpisodeClip(null)}
        />
      )}

      {/* Scene chatbot panel */}
      <SceneChatbot
        apiBase={apiBase}
        userState={recap.user_state}
        currentClip={activeClip}
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
      />

      {/* Floating Chat Button */}
      {!showIntro && (
        <button
          onClick={() => setChatOpen(o => !o)}
          title="Ask about this scene"
          style={{
            position: 'fixed',
            bottom: 32, right: chatOpen ? 448 : 32,
            zIndex: 1997,
            width: 56, height: 56,
            borderRadius: '50%',
            background: chatOpen
              ? 'rgba(255,255,255,0.15)'
              : 'linear-gradient(135deg, #E50914, #c4000f)',
            border: 'none',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.4rem',
            boxShadow: chatOpen
              ? '0 4px 20px rgba(0,0,0,0.4)'
              : '0 4px 20px rgba(229,9,20,0.5)',
            transition: 'all 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        >
          {chatOpen ? '✕' : '💬'}
        </button>
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
            <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
              <button
                className="ctrl-btn"
                style={{
                  flex: 1,
                  background: playMode === 'interactive' ? 'var(--accent)' : 'rgba(255,255,255,0.1)',
                  color: '#fff',
                  border: 'none',
                  fontWeight: 700,
                }}
                onClick={() => setPlayMode('interactive')}
              >
                📱 Interactive Clip Player
              </button>
              <button
                className="ctrl-btn"
                style={{
                  flex: 1,
                  background: playMode === 'seamless' ? 'var(--accent)' : 'rgba(255,255,255,0.1)',
                  color: '#fff',
                  border: 'none',
                  fontWeight: 700,
                }}
                onClick={() => setPlayMode('seamless')}
              >
                🎬 Seamless Director's Cut
              </button>
            </div>
          )}
        </div>

        {playMode === 'seamless' ? (
          <div style={{ marginTop: 24, padding: 20, background: 'var(--bg-card)', borderRadius: 12 }}>
            <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ fontSize: '1rem', color: 'var(--accent)', fontWeight: 700 }}>
                Seamless Director's Cut
              </div>
              <div style={{
                background: 'rgba(229,9,20,0.15)', border: '1px solid rgba(229,9,20,0.3)',
                padding: '4px 12px', borderRadius: 99, color: '#fca5a5', fontSize: '0.78rem', fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                🎵 Breaking Bad Theme Music (0.15 Vol) Active
              </div>
            </div>
            
            <ClipPlayer
              clip={{}}
              apiBase={apiBase}
              isActive={!showIntro}
              streamUrlOverride={recap.compiled_stream_url}
              segments={segments}
            />

            {/* List of moments in this seamless cut for quick full episode watching */}
            <div style={{ marginTop: 32, borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 20 }}>
              <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#fff', marginBottom: 16 }}>
                Moments in this Recap
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {segments.map((seg, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 16px', background: 'rgba(255,255,255,0.04)',
                      borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)',
                      gap: 16, flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>
                        {i + 1}. {seg.clip.episode_title} (Ep {seg.clip.episode_number})
                      </div>
                      <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: 2 }}>
                        {seg.clip.moment_description}
                      </div>
                    </div>

                    <button
                      onClick={() => setEpisodeClip(seg.clip)}
                      style={{
                        background: 'linear-gradient(135deg, #E50914, #c4000f)',
                        border: 'none', color: '#fff',
                        padding: '7px 14px', borderRadius: 99,
                        cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
                        display: 'flex', alignItems: 'center', gap: 6,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      📺 Watch in Full Episode
                    </button>
                  </div>
                ))}
              </div>
            </div>
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
                    narrationText={seg.narration_text}
                    apiBase={apiBase}
                    isActive={!showIntro && i === activeIndex}
                    onEnded={goNext}
                    onWatchOriginal={(clip) => setEpisodeClip(clip)}
                  />
                </div>
              ))}
            </div>

            {/* Navigation */}
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
                      height: 8, borderRadius: 4,
                      background: i === activeIndex ? 'var(--accent)' : 'rgba(255,255,255,0.2)',
                      transition: '0.3s', cursor: 'pointer',
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
