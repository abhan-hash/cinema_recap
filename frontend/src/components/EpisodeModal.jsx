import { useState, useRef, useEffect } from 'react'
import Hls from 'hls.js'

/**
 * EpisodeModal — full-screen overlay to watch the original episode
 * Auto-seeks to the exact timestamp of the recap clip.
 *
 * Props:
 *   apiBase    — backend URL
 *   clip       — RetrievedClip with video_id, start, episode_title, etc.
 *   onClose    — callback to close the modal
 */
export default function EpisodeModal({ apiBase, clip, onClose }) {
  const videoRef  = useRef(null)
  const hlsRef    = useRef(null)
  const [streamUrl, setStreamUrl] = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [seeked,    setSeeked]    = useState(false)

  // Close on Escape key
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Fetch full-episode stream URL
  useEffect(() => {
    if (!clip?.video_id) return
    setLoading(true)
    setError(null)
    const seekSec = clip.start ?? 0
    fetch(`${apiBase}/episode-stream?video_id=${clip.video_id}&seek=${seekSec}`)
      .then(r => r.json())
      .then(data => {
        if (data.stream_url) setStreamUrl(data.stream_url)
        else setError('Could not get episode stream URL')
        setLoading(false)
      })
      .catch(() => { setError('Failed to connect to backend'); setLoading(false) })
  }, [clip?.video_id, clip?.start, apiBase])

  const hasSeekedRef = useRef(false)

  // Attach HLS player once stream URL is ready
  useEffect(() => {
    if (!streamUrl || !videoRef.current) return
    const video = videoRef.current
    hasSeekedRef.current = false

    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null }

    const seekTo = clip?.start ?? 0

    const executeSeek = () => {
      if (!hasSeekedRef.current && video) {
        hasSeekedRef.current = true
        try {
          video.currentTime = seekTo
          video.play().catch(() => {})
        } catch (e) {
          console.warn('Seek error:', e)
        }
      }
    }

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = streamUrl
      video.addEventListener('loadedmetadata', executeSeek, { once: true })
      video.addEventListener('canplay', executeSeek, { once: true })
    } else if (Hls.isSupported()) {
      // HLS.js native startPosition instructs HLS to fetch segment at seekTo immediately
      const hls = new Hls({
        autoStartLoad: true,
        startPosition: seekTo > 0 ? seekTo : -1,
      })
      hls.loadSource(streamUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MEDIA_ATTACHED, () => {
        video.addEventListener('canplay', executeSeek, { once: true })
      })
      hls.on(Hls.Events.MANIFEST_PARSED, executeSeek)
      hlsRef.current = hls
    }

    return () => { hlsRef.current?.destroy(); hlsRef.current = null }
  }, [streamUrl, clip?.start])

  const formatTime = (secs) => {
    if (!secs) return '0:00'
    const m = Math.floor(secs / 60)
    const s = Math.floor(secs % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 3000,
      background: 'rgba(0,0,0,0.95)',
      display: 'flex', flexDirection: 'column',
      animation: 'modalFadeIn 0.25s ease',
    }}>
      <style>{`
        @keyframes modalFadeIn { from { opacity: 0 } to { opacity: 1 } }
      `}</style>

      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 24px',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.9), transparent)',
        position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.1)', border: 'none',
              color: '#fff', padding: '8px 16px', borderRadius: 99,
              cursor: 'pointer', fontWeight: 700, fontSize: '0.85rem',
              display: 'flex', alignItems: 'center', gap: 6,
              transition: '0.2s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.18)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
          >
            ← Back to Recap
          </button>
          <div style={{
            width: 1, height: 20,
            background: 'rgba(255,255,255,0.2)',
          }} />
          <div>
            <div style={{ fontWeight: 800, fontSize: '1rem', color: '#fff' }}>
              {clip?.episode_title || 'Original Episode'}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>
              Episode {clip?.episode_number} · Jumped to {formatTime(clip?.start)}
            </div>
          </div>
        </div>

        <div style={{
          background: 'rgba(229,9,20,0.15)',
          border: '1px solid rgba(229,9,20,0.3)',
          borderRadius: 99,
          padding: '4px 12px',
          fontSize: '0.75rem',
          color: '#fca5a5',
          fontWeight: 600,
        }}>
          📍 Jumped to {formatTime(clip?.start)}
        </div>
      </div>

      {/* Video area */}
      <div style={{
        flex: 1,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '80px 0 60px',
      }}>
        {loading && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20,
          }}>
            <div style={{
              width: 48, height: 48,
              border: '3px solid rgba(229,9,20,0.2)',
              borderTop: '3px solid #E50914',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem' }}>
              Loading episode stream…
            </div>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        )}

        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 12, padding: '24px 32px',
            color: '#fca5a5', textAlign: 'center', maxWidth: 400,
          }}>
            <div style={{ fontSize: '2rem', marginBottom: 12 }}>⚠️</div>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Couldn't load episode</div>
            <div style={{ fontSize: '0.85rem', opacity: 0.8 }}>{error}</div>
          </div>
        )}

        {!loading && !error && (
          <video
            ref={videoRef}
            controls
            playsInline
            onPlay={(e) => {
              const seekTo = clip?.start ?? 0
              if (seekTo > 0 && !hasSeekedRef.current && Math.abs(e.target.currentTime - seekTo) > 3) {
                hasSeekedRef.current = true
                e.target.currentTime = seekTo
              }
            }}
            style={{
              width: '100%',
              maxWidth: '90vw',
              maxHeight: '80vh',
              borderRadius: 8,
              background: '#000',
              boxShadow: '0 20px 80px rgba(0,0,0,0.8)',
            }}
          />
        )}
      </div>

      {/* Bottom hint */}
      <div style={{
        position: 'absolute', bottom: 24, left: 0, right: 0,
        textAlign: 'center',
        fontSize: '0.78rem',
        color: 'rgba(255,255,255,0.25)',
      }}>
        Press <kbd style={{ background: 'rgba(255,255,255,0.1)', padding: '1px 6px', borderRadius: 4 }}>Esc</kbd> to return to recap
      </div>
    </div>
  )
}
