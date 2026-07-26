import { useState } from 'react'

const TIME_OPTIONS = [
  { value: 'last_night',  label: 'Last night',  sub: '< 24 hours' },
  { value: 'last_week',   label: 'Last week',   sub: '2-7 days' },
  { value: 'last_month',  label: 'Last month',  sub: '1-4 weeks' },
  { value: '6_months_ago',label: '6+ months',   sub: 'Long time ago' },
]

const LENGTH_OPTIONS = [
  { value: 'short',  label: '⚡ Quick Flash',  sub: 'Key beats only' },
  { value: 'medium', label: '🎬 Full Recap',   sub: 'Main story threads' },
  { value: 'long',   label: '📺 Deep Dive',    sub: 'Every plot thread' },
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
          <div key={i} className="netflix-row" style={{ marginBottom: 16 }}>
            <div className="skeleton" style={{ height: 16, width: '30%', marginBottom: 16 }} />
            <div className="skeleton" style={{ height: 157, width: '100%' }} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      {/* Episode selector */}
      <div className="netflix-row">
        <div className="netflix-row-title">Episodes Watched</div>
        {episodes.length > 0 ? (
          <div className="netflix-slider">
            {episodes.map(ep => (
              <div
                key={ep.number}
                className={`episode-tile ${watched.includes(ep.number) ? 'selected' : ''}`}
                onClick={() => toggleEpisode(ep.number)}
              >
                <div className="ep-label">
                  <div className="ep-num">Episode {ep.number}</div>
                  <div style={{ color: 'var(--text)', fontSize: '0.9rem', marginTop: 1 }}>
                    {ep.title}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>
            No episodes found.
          </div>
        )}
      </div>

      {/* Time since last watch */}
      <div className="netflix-row">
        <div className="netflix-row-title">Time Since Last Watch</div>
        <div className="netflix-slider">
          {TIME_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`time-btn ${timeSince === opt.value ? 'selected' : ''}`}
              onClick={() => setTimeSince(opt.value)}
            >
              {opt.label}
              <small>{opt.sub}</small>
            </button>
          ))}
        </div>
      </div>

      {/* Character focus */}
      <div className="netflix-row">
        <div className="netflix-row-title">Character Focus (Optional)</div>
        <div className="netflix-slider">
          <button
            className={`char-btn ${!focusChar ? 'selected' : ''}`}
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

      {/* Recap length */}
      <div className="netflix-row">
        <div className="netflix-row-title">Recap Length</div>
        <div className="netflix-slider">
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

      <div style={{ padding: '0 50px', marginTop: 24, paddingBottom: 64 }}>
        <button
          className="generate-btn"
          disabled={watched.length === 0 || submitting}
          onClick={handleSubmit}
        >
          {submitting ? 'Generating...' : '▶ Play Recap'}
        </button>
      </div>
    </div>
  )
}
