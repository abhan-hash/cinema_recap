import { useState, useRef, useEffect } from 'react'
import Hls from 'hls.js'

function NarrationAudio({ audioUrl, onEnded }) {
  const ref = useRef(null)

  useEffect(() => {
    if (audioUrl && ref.current) {
      ref.current.play().catch(() => {})
    }
  }, [audioUrl])

  if (!audioUrl) return null

  return (
    <audio ref={ref} src={audioUrl} onEnded={onEnded} style={{ display: 'none' }} />
  )
}

function ClipPlayer({ clip, apiBase, isActive, onEnded }) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  const [streamUrl, setStreamUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [playing, setPlaying] = useState(false)

  // Fetch stream URL when this clip becomes active
  useEffect(() => {
    if (!isActive || streamUrl) return
    setLoading(true)
    fetch(`${apiBase}/clip-stream?video_id=${clip.video_id}&start=${clip.start}&end=${clip.end}`)
      .then(r => r.json())
      .then(d => {
        setStreamUrl(d.stream_url)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [isActive])

  // Attach HLS / play logic
  useEffect(() => {
    if (!streamUrl || !videoRef.current) return;
    const video = videoRef.current;

    // cleanup previous hls
    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }

    const playVideo = () => {
      if (isActive) {
        video.play().then(() => setPlaying(true)).catch((e) => {
          console.error("Autoplay blocked:", e);
          setPlaying(false);
        });
      }
    };

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      video.src = streamUrl;
      video.addEventListener('loadedmetadata', playVideo);
    } else if (Hls.isSupported()) {
      // Hls.js fallback for Chrome/Firefox
      const hls = new Hls({ autoStartLoad: true });
      hls.loadSource(streamUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, playVideo);
      hlsRef.current = hls;
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      video.removeEventListener('loadedmetadata', playVideo);
    }
  }, [streamUrl, isActive]);

  const togglePlay = () => {
    if (!videoRef.current) return
    if (videoRef.current.paused) {
      videoRef.current.play().then(() => setPlaying(true)).catch(() => {})
    } else {
      videoRef.current.pause()
      setPlaying(false)
    }
  }

  const scorePercent = Math.round((clip.search_score || 0.5) * 100)

  return (
    <div>
      <div className="video-wrapper">
        {streamUrl ? (
          <video
            ref={videoRef}
            controls
            playsInline
            onEnded={() => { setPlaying(false); onEnded && onEnded() }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : (
          <div style={{
            background: '#000', aspectRatio: '16/9',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-dim)', fontSize: '0.85rem'
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

      <div className="video-meta">
        <span className="video-ep-tag">
          Ep {clip.episode_number} · {clip.episode_title}
          {' · '}{clip.start.toFixed(0)}s – {clip.end.toFixed(0)}s
        </span>
        <span className="video-score">
          <div className="score-bar">
            <div className="score-fill" style={{ width: `${scorePercent}%` }} />
          </div>
          <span>{scorePercent}% match</span>
        </span>
      </div>
    </div>
  )
}

export default function RecapPlayer({ recap, apiBase, onReset }) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [audioPhase, setAudioPhase] = useState('narration') // 'narration' | 'video'
  const [autoPlay, setAutoPlay] = useState(false)

  const segments = recap.segments || []
  const activeSegment = segments[activeIndex]

  const goNext = () => {
    if (activeIndex < segments.length - 1) {
      setActiveIndex(i => i + 1)
      setAudioPhase('narration')
    }
  }

  const goPrev = () => {
    if (activeIndex > 0) {
      setActiveIndex(i => i - 1)
      setAudioPhase('narration')
    }
  }

  const handleNarrationEnd = () => {
    setAudioPhase('video')
  }

  // Closing narration text (after last clip)
  const closing = segments.length > 0
    ? segments[segments.length - 1].narration_text
    : null

  return (
    <div>
      {/* Header */}
      <div className="recap-header">
        <div className="recap-badge">Recap Ready</div>
        <div className="recap-title">
          Previously on Episode {recap.user_state.watched_episodes.slice(-1)[0]}…
        </div>
        <div className="recap-meta">
          {segments.length} moments · {Math.round(recap.total_duration_seconds)}s total
          {recap.user_state.focus_character && ` · Focused on ${recap.user_state.focus_character}`}
        </div>
      </div>

      {/* Status */}
      {recap.status === 'partial' && (
        <div className="error-box" style={{ marginBottom: 16, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.3)', color: '#fde68a' }}>
          ⚠️ {recap.message}
        </div>
      )}

      {/* Segment list */}
      <div>
        {segments.map((seg, i) => (
          <div
            key={i}
            className={`segment ${i === activeIndex ? 'active-segment' : ''}`}
            onClick={() => { setActiveIndex(i); setAudioPhase('narration') }}
          >
            {/* Narration */}
            <div className="narration-bar">
              <div className="narration-icon">🎙️</div>
              <div className="narration-text">
                "{seg.narration_text}"
              </div>
            </div>

            {/* Narration audio (active segment only) */}
            {i === activeIndex && audioPhase === 'narration' && seg.narration_audio_url && (
              <NarrationAudio
                audioUrl={`${apiBase}${seg.narration_audio_url}`}
                onEnded={handleNarrationEnd}
              />
            )}

            {/* Video clip */}
            <ClipPlayer
              clip={seg.clip}
              apiBase={apiBase}
              isActive={i === activeIndex && (audioPhase === 'video' || !seg.narration_audio_url)}
              onEnded={goNext}
            />
          </div>
        ))}
      </div>

      {/* Navigation */}
      <div className="controls-bar" style={{ marginTop: 24 }}>
        <button className="ctrl-btn" onClick={goPrev} disabled={activeIndex === 0}>
          ← Prev
        </button>
        <button
          className="ctrl-btn"
          style={{ flex: 2, fontSize: '0.8rem', color: 'var(--text-dim)' }}
          disabled
        >
          {activeIndex + 1} / {segments.length}
        </button>
        <button className="ctrl-btn" onClick={goNext} disabled={activeIndex === segments.length - 1}>
          Next →
        </button>
      </div>

      {/* Bottom actions */}
      <div className="controls-bar" style={{ marginTop: 12 }}>
        <button className="ctrl-btn" onClick={onReset}>
          ← Change settings
        </button>
        <button className="ctrl-btn primary" onClick={() => {
          setActiveIndex(0)
          setAudioPhase('narration')
        }}>
          ↺ Replay from start
        </button>
      </div>

      {/* Evidence panel — shows judges that VideoDB is doing real retrieval */}
      <div className="card" style={{ marginTop: 32 }}>
        <div className="card-title">VideoDB retrieval evidence</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {segments.map((seg, i) => (
            <div
              key={i}
              style={{
                display: 'flex', gap: 12, alignItems: 'flex-start',
                padding: '10px 12px',
                background: i === activeIndex ? 'rgba(224,92,42,0.06)' : 'var(--bg-raised)',
                borderRadius: 8,
                border: i === activeIndex ? '1px solid rgba(224,92,42,0.3)' : '1px solid var(--border)',
                cursor: 'pointer',
              }}
              onClick={() => { setActiveIndex(i); setAudioPhase('narration') }}
            >
              <div style={{
                width: 24, height: 24, borderRadius: 6,
                background: 'var(--bg-card)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.72rem', fontWeight: 700,
                color: i === activeIndex ? 'var(--accent)' : 'var(--text-dim)',
                flexShrink: 0,
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text)', marginBottom: 2, fontWeight: 500 }}>
                  Ep {seg.clip.episode_number}: {seg.clip.episode_title}
                  <span style={{ color: 'var(--text-dim)', marginLeft: 8 }}>
                    {seg.clip.start.toFixed(0)}s–{seg.clip.end.toFixed(0)}s
                  </span>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', lineHeight: 1.4, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                  {seg.clip.description || seg.clip.moment_description}
                </div>
              </div>
              <div style={{ fontSize: '0.68rem', color: 'var(--accent)', fontWeight: 600, flexShrink: 0 }}>
                {Math.round((seg.clip.search_score || 0.5) * 100)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
