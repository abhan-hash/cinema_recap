import { useState } from 'react'

const TIME_OPTIONS = [
  { value: 'last_night',  label: 'Last night',  sub: '< 24 hours' },
  { value: 'last_week',   label: 'Last week',   sub: '2-7 days' },
  { value: 'last_month',  label: 'Last month',  sub: '1-4 weeks' },
  { value: '6_months_ago',label: '6+ months',   sub: 'Long time ago' },
]

const LENGTH_OPTIONS = [
  { value: 'short',  label: 'Quick',  sub: '~30 sec' },
  { value: 'medium', label: 'Standard', sub: '~90 sec' },
  { value: 'long',   label: 'Full',   sub: '~3 min' },
]

export default function WatchStateForm({ seriesInfo, onGenerate, loading }) {
  const [watched, setWatched] = useState([])
  const [timeSince, setTimeSince] = useState('last_week')
  const [focusChar, setFocusChar] = useState(null)
  const [recapLength, setRecapLength] = useState('medium')
  const [submitting, setSubmitting] = useState(false)

  const episodes = seriesInfo?.episodes || []
  const characters = seriesInfo?.characters || []

  // Next episode = first unwatched
  const nextEpisode = episodes.find(ep => !watched.includes(ep.number))?.number
    || (episodes.length > 0 ? episodes[episodes.length - 1].number + 1 : null)

  const toggleEpisode = (num) => {
    setWatched(prev =>
      prev.includes(num) ? prev.filter(n => n !== num) : [...prev, num]
    )
  }

  const handleSubmit = async () => {
    if (watched.length === 0 || !nextEpisode) return
    setSubmitting(true)
    await onGenerate({
      watched_episodes: watched,
      next_episode: nextEpisode,
      time_since_last_watch: timeSince,
      focus_character: focusChar,
      recap_length: recapLength,
    })
    setSubmitting(false)
  }

  if (loading) {
    return (
      <div>
        {[1,2,3].map(i => (
          <div key={i} className="card" style={{ marginBottom: 16 }}>
            <div className="skeleton" style={{ height: 16, width: '30%', marginBottom: 16 }} />
            <div className="skeleton" style={{ height: 48, width: '100%' }} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      {/* Series name */}
      {seriesInfo && (
        <div style={{ marginBottom: 24, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Series: <strong style={{ color: 'var(--text)' }}>{seriesInfo.series_name}</strong>
          {nextEpisode && watched.length > 0 && (
            <> — watching next: <strong style={{ color: 'var(--accent)' }}>Episode {nextEpisode}</strong></>
          )}
        </div>
      )}

      {/* Episode selector */}
      <div className="card">
        <div className="card-title">Episodes watched</div>
        {episodes.length > 0 ? (
          <div className="episode-grid">
            {episodes.map(ep => (
              <div
                key={ep.number}
                className={`episode-tile ${watched.includes(ep.number) ? 'selected' : ''}`}
                onClick={() => toggleEpisode(ep.number)}
              >
                <div className="check" />
                <div className="ep-label">
                  <div className="ep-num">Episode {ep.number}</div>
                  <div style={{ color: 'var(--text)', fontSize: '0.8rem', marginTop: 1 }}>
                    {ep.title}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>
            No episodes found. Run <code style={{ background: 'var(--bg-raised)', padding: '2px 6px', borderRadius: 4 }}>ingest.py</code> first.
          </div>
        )}

        {watched.length > 0 && (
          <div style={{ marginTop: 12, fontSize: '0.78rem', color: 'var(--text-dim)' }}>
            {watched.length} episode{watched.length > 1 ? 's' : ''} selected
            {' · '}
            <span
              style={{ color: 'var(--accent)', cursor: 'pointer' }}
              onClick={() => setWatched([])}
            >
              Clear all
            </span>
          </div>
        )}
      </div>

      {/* Time since last watch */}
      <div className="card">
        <div className="card-title">When did you last watch?</div>
        <div className="time-options">
          {TIME_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`time-btn ${timeSince === opt.value ? 'selected' : ''}`}
              onClick={() => setTimeSince(opt.value)}
            >
              {opt.label}
              <div style={{ fontSize: '0.68rem', color: 'inherit', opacity: 0.6, marginTop: 2 }}>
                {opt.sub}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Recap length */}
      <div className="card">
        <div className="card-title">Recap length</div>
        <div className="length-row">
          {LENGTH_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`length-btn ${recapLength === opt.value ? 'selected' : ''}`}
              onClick={() => setRecapLength(opt.value)}
            >
              {opt.label}
              <small>{opt.sub}</small>
            </button>
          ))}
        </div>
      </div>

      {/* Character focus (optional) */}
      {characters.length > 0 && (
        <div className="card">
          <div className="card-title">Focus character <span style={{ color: 'var(--text-dim)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></div>
          <div className="character-row">
            <button
              className={`char-btn ${focusChar === null ? 'selected' : ''}`}
              onClick={() => setFocusChar(null)}
            >
              All characters
            </button>
            {characters.map(char => (
              <button
                key={char}
                className={`char-btn ${focusChar === char ? 'selected' : ''}`}
                onClick={() => setFocusChar(char)}
              >
                {char}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Generate button */}
      <button
        className="generate-btn"
        onClick={handleSubmit}
        disabled={watched.length === 0 || !nextEpisode || submitting || !seriesInfo}
      >
        {submitting
          ? 'Generating...'
          : `Generate My Recap → Episode ${nextEpisode || '?'}`
        }
      </button>
    </div>
  )
}
