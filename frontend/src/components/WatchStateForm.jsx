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

const PRESET_PROMPTS = [
  { label: '🧪 Chemistry & RV Cooks', text: 'Focus on Walter and Jesse cooking meth in the RV' },
  { label: "🔍 Hank's Investigation", text: "Focus on Hank Schrader's DEA investigation and clues" },
  { label: '⚡ Walt & Jesse Partnership', text: 'Focus on Walter and Jesse partnership and relationship' },
  { label: '💥 Bathtub & Acid Disaster', text: 'Focus on the body disposal and hydrofluoric acid disaster' },
]

export default function WatchStateForm({ seriesInfo, onGenerate, loading }) {
  const [watched, setWatched]             = useState([])
  const [timeSince, setTimeSince]         = useState('last_week')
  const [focusChars, setFocusChars]       = useState([])  // Array for multi-character selection
  const [customPrompt, setCustomPrompt]   = useState('')
  const [recapLength, setRecapLength]     = useState('medium')
  const [submitting, setSubmitting]       = useState(false)

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

  const toggleCharacter = (char) => {
    setFocusChars(prev =>
      prev.includes(char) ? prev.filter(c => c !== char) : [...prev, char]
    )
  }

  const handleSubmit = async () => {
    if (watched.length === 0 || !nextEpisode) return
    setSubmitting(true)
    await onGenerate({
      watched_episodes: watched,
      next_episode: nextEpisode,
      time_since_last_watch: timeSince,
      focus_character: focusChars.length > 0 ? focusChars.join(', ') : null,
      focus_characters: focusChars.length > 0 ? focusChars : null,
      custom_prompt: customPrompt.trim() || null,
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

      {/* Multi-Character Focus */}
      <div className="netflix-row">
        <div className="netflix-row-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Character Focus (Select 1 or more to merge storylines)</span>
          {focusChars.length > 0 && (
            <span style={{ fontSize: '0.78rem', color: '#E50914', fontWeight: 700 }}>
              {focusChars.length} selected ({focusChars.join(' + ')})
            </span>
          )}
        </div>
        <div className="netflix-slider">
          <button
            className={`char-btn ${focusChars.length === 0 ? 'selected' : ''}`}
            onClick={() => setFocusChars([])}
          >
            All characters
          </button>
          {characters.map(char => (
            <button
              key={char}
              className={`char-btn ${focusChars.includes(char) ? 'selected' : ''}`}
              onClick={() => toggleCharacter(char)}
              style={focusChars.includes(char) ? { background: '#E50914', borderColor: '#E50914', color: '#fff' } : {}}
            >
              {focusChars.includes(char) ? `✓ ${char}` : char}
            </button>
          ))}
        </div>
      </div>

      {/* Custom Recap Prompt / Topic */}
      <div className="netflix-row" style={{ padding: '0 50px', marginBottom: 24 }}>
        <div className="netflix-row-title" style={{ padding: 0, marginBottom: 8 }}>
          ✨ Custom Recap Topic / Directing Prompt (Optional)
        </div>
        <div style={{ position: 'relative', marginBottom: 10 }}>
          <input
            type="text"
            value={customPrompt}
            onChange={e => setCustomPrompt(e.target.value)}
            placeholder="e.g. Focus on the chemistry cooking scenes in the RV..."
            style={{
              width: '100%',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 8,
              padding: '12px 16px',
              color: '#fff',
              fontSize: '0.92rem',
              outline: 'none',
              fontFamily: 'inherit',
              transition: 'border-color 0.2s',
            }}
            onFocus={e => e.target.style.borderColor = 'rgba(229,9,20,0.6)'}
            onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.15)'}
          />
        </div>

        {/* Preset Prompt Pills */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {PRESET_PROMPTS.map((p, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setCustomPrompt(p.text)}
              style={{
                background: customPrompt === p.text ? 'rgba(229,9,20,0.2)' : 'rgba(255,255,255,0.05)',
                border: '1px solid ' + (customPrompt === p.text ? '#E50914' : 'rgba(255,255,255,0.1)'),
                color: customPrompt === p.text ? '#fff' : 'rgba(255,255,255,0.7)',
                padding: '5px 12px',
                borderRadius: 99,
                cursor: 'pointer',
                fontSize: '0.78rem',
                fontWeight: 600,
                transition: '0.2s',
              }}
            >
              {p.label}
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
              className={`time-btn ${recapLength === opt.value ? 'selected' : ''}`}
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
          {submitting ? 'Generating Custom Recap...' : '▶ Play Recap'}
        </button>
      </div>
    </div>
  )
}
