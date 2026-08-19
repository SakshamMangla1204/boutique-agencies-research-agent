import { useCallback, useEffect, useRef, useState } from 'react'

const DEFAULT_FIELDS = ['company_name', 'website', 'linkedin', 'description']
const ENTITY_TYPES = ['company', 'college', 'vc_firm', 'startup', 'job', 'custom']
const STAGES = ['discovery', 'research', 'extraction', 'sheets']

const FIELD_LABELS = {
  company_name: 'Company Name',
  website: 'Website',
  linkedin: 'LinkedIn',
  description: 'Description',
}

function stageStatus(job, stage) {
  if (job.status === 'failed') return 'failed'
  if (job.status === 'complete') return 'complete'

  const order = { discovery: 0, research: 1, extraction: 2, sheets: 3 }
  const current = job.stage || 'startup'
  const currentIdx = order[current] ?? -1
  const stageIdx = order[stage]

  if (stageIdx < currentIdx) return 'complete'
  if (stageIdx === currentIdx && current !== 'startup') return 'running'
  return 'pending'
}

function formatError(err) {
  if (!err) return ''
  if (typeof err === 'string') return err
  if (err.detail) return err.detail
  return 'Request failed'
}

export default function App() {
  const [backendOnline, setBackendOnline] = useState(false)
  const [query, setQuery] = useState('')
  const [entityType, setEntityType] = useState('company')
  const [fields, setFields] = useState([...DEFAULT_FIELDS])
  const [customField, setCustomField] = useState('')
  const [maxResults, setMaxResults] = useState(10)

  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)

  const jobIdRef = useRef(null)
  const timerRef = useRef(null)

  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch('/api/health')
      setBackendOnline(res.ok)
    } catch {
      setBackendOnline(false)
    }
  }, [])

  useEffect(() => {
    checkBackend()
    const id = setInterval(checkBackend, 15000)
    return () => clearInterval(id)
  }, [checkBackend])

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startPolling = useCallback(async (jobId) => {
    stopPolling()

    const poll = async () => {
      try {
        const res = await fetch(`/api/research/${jobId}`)
        if (!res.ok) return
        const data = await res.json()
        setJob(data)

        if (data.status === 'complete' || data.status === 'failed') {
          stopPolling()
        }
      } catch {
        // keep polling; transient network errors are fine
      }
    }

    await poll()
    timerRef.current = setInterval(poll, 2000)
  }, [stopPolling])

  const handleStart = async (e) => {
    e.preventDefault()
    setError(null)
    setStarting(true)

    const trimmedQuery = query.trim()
    if (!trimmedQuery) {
      setError('Query is required.')
      setStarting(false)
      return
    }

    if (fields.length === 0) {
      setError('Select at least one field.')
      setStarting(false)
      return
    }

    const payload = {
      query: trimmedQuery,
      entity_type: entityType,
      fields,
      max_results: Math.min(Math.max(1, Number(maxResults) || 10), 50),
    }

    try {
      const res = await fetch('/api/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(formatError(data))
        setStarting(false)
        return
      }

      const data = await res.json()
      jobIdRef.current = data.job_id
      setJob({
        status: 'running',
        stage: 'startup',
        discovered: 0,
        processed: 0,
        written: 0,
        duplicates: 0,
        failed: 0,
      })
      startPolling(data.job_id)
    } catch {
      setError('Backend unavailable. Make sure the API server is running.')
    } finally {
      setStarting(false)
    }
  }

  const handleReset = () => {
    stopPolling()
    jobIdRef.current = null
    setJob(null)
    setError(null)
  }

  const toggleField = (field) => {
    setFields((prev) =>
      prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field],
    )
  }

  const addCustomField = () => {
    const value = customField.trim().toLowerCase().replace(/\s+/g, '_')
    if (!value) return
    setFields((prev) => (prev.includes(value) ? prev : [...prev, value]))
    setCustomField('')
  }

  const isRunning = job && (job.status === 'running' || job.status === 'queued')

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">R</div>
          <div>
            <div className="brand-name">
              ResearchOS <span>—</span>
            </div>
            <div className="brand-subtitle">AI-powered structured research</div>
          </div>
        </div>
        <div className="status-pill">
          <span
            className={`status-dot ${backendOnline ? 'online' : 'offline'}`}
          />
          {backendOnline ? 'Backend Connected' : 'Backend Offline'}
        </div>
      </header>

      <main className="main">
        <div className="hero">
          <h1>Research workspace</h1>
          <p>
            Configure a research job and execute the structured discovery
            pipeline against real web data.
          </p>
        </div>

        {!job || job.status === 'complete' || job.status === 'failed' ? (
          <section className="panel">
            <div className="panel-title">Research Configuration</div>
            <form onSubmit={handleStart}>
              <div className="field">
                <label htmlFor="query">What do you want to research?</label>
                <input
                  id="query"
                  type="text"
                  placeholder="AI startups in India"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={isRunning}
                />
              </div>

              <div className="row">
                <div className="field">
                  <label htmlFor="entity">Entity Type</label>
                  <select
                    id="entity"
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                    disabled={isRunning}
                  >
                    {ENTITY_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type
                          .split('_')
                          .map((w) => w[0].toUpperCase() + w.slice(1))
                          .join(' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="results">Results</label>
                  <input
                    id="results"
                    type="number"
                    min="1"
                    max="50"
                    value={maxResults}
                    onChange={(e) => setMaxResults(e.target.value)}
                    disabled={isRunning}
                  />
                </div>
              </div>

              <div className="field">
                <label>Fields</label>
                <div className="checks">
                  {DEFAULT_FIELDS.map((field) => (
                    <label
                      key={field}
                      className={`check ${fields.includes(field) ? 'active' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={fields.includes(field)}
                        onChange={() => toggleField(field)}
                        disabled={isRunning}
                      />
                      {FIELD_LABELS[field] || field}
                    </label>
                  ))}
                  {fields
                    .filter((f) => !DEFAULT_FIELDS.includes(f))
                    .map((field) => (
                      <label key={field} className="check active">
                        <input
                          type="checkbox"
                          checked
                          onChange={() => toggleField(field)}
                          disabled={isRunning}
                        />
                        {field}
                      </label>
                    ))}
                </div>

                <div className="custom-field-row">
                  <input
                    type="text"
                    placeholder="Add custom field…"
                    value={customField}
                    onChange={(e) => setCustomField(e.target.value)}
                    disabled={isRunning}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addCustomField()
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={addCustomField}
                    disabled={isRunning}
                  >
                    Add
                  </button>
                </div>
              </div>

              {error && <div className="error-box">{error}</div>}

              <div className="form-actions">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isRunning || starting}
                >
                  {starting ? 'Starting…' : 'START RESEARCH →'}
                </button>
              </div>
            </form>
          </section>
        ) : null}

        {job && job.status === 'running' ? (
          <section className="panel">
            <div className="panel-title">Research Status</div>

            <div className="stages">
              {STAGES.map((stage) => {
                const status = stageStatus(job, stage)
                return (
                  <div className="stage" key={stage}>
                    <span className={`stage-icon ${status}`} />
                    <span className="stage-label">{stage}</span>
                    <span className="stage-status">{status}</span>
                  </div>
                )
              })}
            </div>

            <div className="stats">
              <div className="stat">
                <div className="stat-value">{job.discovered ?? 0}</div>
                <div className="stat-label">Discovered</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.processed ?? 0}</div>
                <div className="stat-label">Processed</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.written ?? 0}</div>
                <div className="stat-label">Written</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.duplicates ?? 0}</div>
                <div className="stat-label">Duplicates</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.failed ?? 0}</div>
                <div className="stat-label">Failed</div>
              </div>
            </div>
          </section>
        ) : null}

        {job && job.status === 'complete' ? (
          <section className="panel">
            <div className="result-header">
              <div className="result-check">✓</div>
              <div>
                <div className="result-title">Research Complete</div>
                <div className="result-subtitle">
                  Stop reason: {job.stop_reason || 'TARGET_REACHED'}
                </div>
              </div>
            </div>

            <div className="stats">
              <div className="stat">
                <div className="stat-value">{job.discovered ?? 0}</div>
                <div className="stat-label">Discovered</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.processed ?? 0}</div>
                <div className="stat-label">Processed</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.written ?? 0}</div>
                <div className="stat-label">Written</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.duplicates ?? 0}</div>
                <div className="stat-label">Duplicates</div>
              </div>
              <div className="stat">
                <div className="stat-value">{job.failed ?? 0}</div>
                <div className="stat-label">Failed</div>
              </div>
            </div>

            {job.entities && job.entities.length > 0 ? (
              <div className="entity-list">
                <div className="entity-list-title">Discovered Entities</div>
                <div className="entity-chips">
                  {job.entities.map((entity, i) => (
                    <span className="entity-chip" key={`${entity}-${i}`}>
                      {entity}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {job.failed_entities && job.failed_entities.length > 0 ? (
              <div className="entity-list">
                <div className="entity-list-title">Failed Entities</div>
                <div className="entity-chips">
                  {job.failed_entities.map((f, i) => (
                    <span className="entity-chip" key={i} style={{ color: 'var(--red)' }}>
                      {f.entity} — {f.reason}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="result-actions">
              {job.sheet_url ? (
                <a
                  className="btn btn-primary"
                  href={job.sheet_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  OPEN GOOGLE SHEET
                </a>
              ) : null}
              <button className="btn btn-secondary" onClick={handleReset}>
                NEW RESEARCH
              </button>
            </div>
          </section>
        ) : null}

        {job && job.status === 'failed' ? (
          <section className="panel">
            <div className="result-header">
              <div className="result-check" style={{ borderColor: 'var(--red)', color: 'var(--red)' }}>
                ✕
              </div>
              <div>
                <div className="result-title">Research Failed</div>
                <div className="result-subtitle">
                  {job.stop_reason || 'Pipeline stopped unexpectedly'}
                </div>
              </div>
            </div>

            {job.error ? <div className="error-box">{job.error}</div> : null}

            <div className="result-actions">
              <button className="btn btn-secondary" onClick={handleReset}>
                NEW RESEARCH
              </button>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}