import { useState } from 'react'

const SOURCE_TYPES = ['nmap', 'netstat', 'arp', 'traceroute', 'ping']

const createSegment = () => ({
  id: typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  sourceType: 'nmap',
  sourceHost: '',
  inputMode: 'file',
  file: null,
  rawData: '',
  tags: [],
  tagInput: '',
})

const parseTagsFromValue = (value) =>
  value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)

export default function ImportSegments({ onSubmit, isLoading }) {
  const [segments, setSegments] = useState([createSegment()])
  const [segmentErrors, setSegmentErrors] = useState({})

  const updateSegment = (id, updates) => {
    setSegments((prev) =>
      prev.map((segment) => (segment.id === id ? { ...segment, ...updates } : segment))
    )
  }

  const addSegment = () => {
    setSegments((prev) => [...prev, createSegment()])
  }

  const removeSegment = (id) => {
    setSegments((prev) => prev.filter((segment) => segment.id !== id))
    setSegmentErrors((prev) => {
      if (!prev[id]) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const addTags = (segmentId, value) => {
    const newTags = parseTagsFromValue(value)
    setSegments((prev) =>
      prev.map((segment) => {
        if (segment.id !== segmentId) return segment
        if (newTags.length === 0) {
          return { ...segment, tagInput: '' }
        }
        const existing = new Set(segment.tags.map((tag) => tag.toLowerCase()))
        const merged = [...segment.tags]
        newTags.forEach((tag) => {
          const normalized = tag.toLowerCase()
          if (!existing.has(normalized)) {
            existing.add(normalized)
            merged.push(tag)
          }
        })
        return { ...segment, tags: merged, tagInput: '' }
      })
    )
  }

  const removeTag = (segmentId, tagToRemove) => {
    setSegments((prev) =>
      prev.map((segment) => {
        if (segment.id !== segmentId) return segment
        return {
          ...segment,
          tags: segment.tags.filter((tag) => tag !== tagToRemove),
        }
      })
    )
  }

  const validateSegment = (segment) => {
    const messages = []
    if (!segment.sourceHost.trim()) {
      messages.push('Source host is required.')
    }
    if (segment.inputMode === 'file' && !segment.file) {
      messages.push('File is required.')
    }
    if (segment.inputMode === 'paste' && !segment.rawData.trim()) {
      messages.push('Raw data is required.')
    }
    return messages.length ? messages.join(' ') : null
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const errors = {}
    segments.forEach((segment) => {
      const message = validateSegment(segment)
      if (message) {
        errors[segment.id] = message
      }
    })
    setSegmentErrors(errors)
    if (Object.keys(errors).length > 0) {
      return
    }

    const result = await onSubmit(segments)
    if (result?.failures?.length) {
      const failures = result.failures.reduce((acc, failure) => {
        acc[failure.id] = failure.message
        return acc
      }, {})
      setSegmentErrors(failures)
      return
    }

    setSegments([createSegment()])
    setSegmentErrors({})
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Import Segments</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Add one segment per data source (netstat, arp, traceroute, etc.).
          </p>
        </div>
        <button
          type="button"
          onClick={addSegment}
          disabled={isLoading}
          className="btn btn-secondary inline-flex items-center gap-2"
        >
          + Add segment
        </button>
      </div>

      <div className="space-y-6">
        {segments.map((segment, index) => (
          <div
            key={segment.id}
            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/60 p-6 shadow-sm space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Segment {index + 1}
              </h3>
              {segments.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeSegment(segment.id)}
                  disabled={isLoading}
                  className="text-sm font-medium text-red-600 dark:text-red-300 hover:text-red-700 dark:hover:text-red-200 disabled:opacity-60"
                >
                  Remove
                </button>
              )}
            </div>

            {segmentErrors[segment.id] && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 rounded-lg">
                {segmentErrors[segment.id]}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Source Type
                </label>
                <select
                  value={segment.sourceType}
                  onChange={(event) => updateSegment(segment.id, { sourceType: event.target.value })}
                  disabled={isLoading}
                  className="select"
                >
                  {SOURCE_TYPES.map((source) => (
                    <option key={source} value={source}>
                      {source}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Source Host
                </label>
                <input
                  type="text"
                  value={segment.sourceHost}
                  onChange={(event) => updateSegment(segment.id, { sourceHost: event.target.value })}
                  placeholder="e.g., 192.168.1.1"
                  disabled={isLoading}
                  className="input"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Input
              </label>
              <div className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 p-1">
                <button
                  type="button"
                  onClick={() => updateSegment(segment.id, { inputMode: 'file' })}
                  disabled={isLoading}
                  className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
                    segment.inputMode === 'file'
                      ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                      : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
                  }`}
                >
                  File
                </button>
                <button
                  type="button"
                  onClick={() => updateSegment(segment.id, { inputMode: 'paste' })}
                  disabled={isLoading}
                  className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
                    segment.inputMode === 'paste'
                      ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                      : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
                  }`}
                >
                  Paste
                </button>
              </div>
            </div>

            {segment.inputMode === 'file' ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Select File
                </label>
                <input
                  type="file"
                  onChange={(event) =>
                    updateSegment(segment.id, { file: event.target.files?.[0] || null })
                  }
                  disabled={isLoading}
                  className="file-input"
                />
                {segment.file && (
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Selected: {segment.file.name}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Raw Data
                </label>
                <textarea
                  value={segment.rawData}
                  onChange={(event) => updateSegment(segment.id, { rawData: event.target.value })}
                  placeholder="Paste your data here..."
                  rows={8}
                  disabled={isLoading}
                  className="input font-mono text-sm min-h-[180px]"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Tags (optional)
              </label>
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
                {segment.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200 px-2.5 py-1 text-xs font-medium"
                  >
                    {tag}
                    <button
                      type="button"
                      onClick={() => removeTag(segment.id, tag)}
                      className="text-blue-500 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-100"
                      aria-label={`Remove ${tag}`}
                      disabled={isLoading}
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  value={segment.tagInput}
                  onChange={(event) =>
                    updateSegment(segment.id, { tagInput: event.target.value })
                  }
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ',') {
                      event.preventDefault()
                      addTags(segment.id, segment.tagInput)
                    }
                    if (event.key === 'Backspace' && !segment.tagInput && segment.tags.length) {
                      event.preventDefault()
                      removeTag(segment.id, segment.tags[segment.tags.length - 1])
                    }
                  }}
                  onBlur={() => addTags(segment.id, segment.tagInput)}
                  placeholder="ip, hostname"
                  disabled={isLoading}
                  className="flex-1 min-w-[160px] border-0 bg-transparent focus:outline-none focus:ring-0 text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
                />
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Press Enter or comma to add tags.
              </p>
            </div>
          </div>
        ))}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="btn btn-primary w-full py-3 text-base"
      >
        {isLoading ? 'Importing...' : 'Import Segments'}
      </button>
    </form>
  )
}
