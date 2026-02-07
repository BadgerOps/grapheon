import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import frontendChangelog from '../../CHANGELOG.md?raw'
import { version as frontendVersion } from '../../package.json'
import * as api from '../api/client'

// ---------------------------------------------------------------------------
// Markdown changelog parser  — turns Keep-a-Changelog markdown into
// structured data: [ { version, date, categories: { Added: [...], ... } } ]
// ---------------------------------------------------------------------------

function parseChangelog(md) {
  const releases = []
  let current = null
  let currentCategory = null

  for (const raw of md.split('\n')) {
    const line = raw.trimEnd()

    // ## 0.6.0 - 2026-02-06  or  ## [0.6.0] - 2026-02-06
    const versionMatch = line.match(/^##\s+\[?(\d+\.\d+\.\d+)\]?\s*-?\s*(.*)/)
    if (versionMatch) {
      current = {
        version: versionMatch[1],
        date: versionMatch[2].trim() || null,
        categories: {},
      }
      releases.push(current)
      currentCategory = null
      continue
    }

    // ### Added / ### Changed / ### Fixed / ### Removed / etc.
    const catMatch = line.match(/^###\s+(.+)/)
    if (catMatch && current) {
      currentCategory = catMatch[1].trim()
      if (!current.categories[currentCategory]) {
        current.categories[currentCategory] = []
      }
      continue
    }

    // Bullet item (may be multi-line; continuation lines start with spaces)
    if (line.match(/^\s*-\s+/) && current && currentCategory) {
      current.categories[currentCategory].push(line.replace(/^\s*-\s+/, ''))
    } else if (line.match(/^\s{2,}/) && current && currentCategory) {
      // continuation of previous bullet
      const items = current.categories[currentCategory]
      if (items.length > 0) {
        items[items.length - 1] += ' ' + line.trim()
      }
    }
  }

  return releases
}

// ---------------------------------------------------------------------------
// Visual constants per category
// ---------------------------------------------------------------------------

const CATEGORY_META = {
  Added: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
      </svg>
    ),
    color: 'emerald',
    label: 'New',
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    text: 'text-emerald-700 dark:text-emerald-300',
    border: 'border-emerald-200 dark:border-emerald-800',
    dot: 'bg-emerald-500',
    badge: 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300',
  },
  Changed: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
    color: 'amber',
    label: 'Changed',
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
    dot: 'bg-amber-500',
    badge: 'bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300',
  },
  Fixed: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    color: 'blue',
    label: 'Fixed',
    bg: 'bg-blue-100 dark:bg-blue-900/40',
    text: 'text-blue-700 dark:text-blue-300',
    border: 'border-blue-200 dark:border-blue-800',
    dot: 'bg-blue-500',
    badge: 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300',
  },
  Removed: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    ),
    color: 'red',
    label: 'Removed',
    bg: 'bg-red-100 dark:bg-red-900/40',
    text: 'text-red-700 dark:text-red-300',
    border: 'border-red-200 dark:border-red-800',
    dot: 'bg-red-500',
    badge: 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300',
  },
  Security: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
    color: 'purple',
    label: 'Security',
    bg: 'bg-purple-100 dark:bg-purple-900/40',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-200 dark:border-purple-800',
    dot: 'bg-purple-500',
    badge: 'bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300',
  },
}

const DEFAULT_CAT = {
  icon: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  color: 'gray',
  label: 'Other',
  bg: 'bg-gray-100 dark:bg-gray-800',
  text: 'text-gray-700 dark:text-gray-300',
  border: 'border-gray-200 dark:border-gray-700',
  dot: 'bg-gray-400',
  badge: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
}

function getCategoryMeta(name) {
  return CATEGORY_META[name] || DEFAULT_CAT
}

// ---------------------------------------------------------------------------
// Inline markdown-ish renderer for bullet text
// Handles: `code`, **bold**, *italic*, and backtick-quoted identifiers
// ---------------------------------------------------------------------------

function renderInlineMarkdown(text) {
  const parts = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Find the earliest match
    const codeMatch = remaining.match(/`([^`]+)`/)
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/)

    let earliest = null
    let type = null

    if (codeMatch && (!earliest || codeMatch.index < earliest.index)) {
      earliest = codeMatch
      type = 'code'
    }
    if (boldMatch && (!earliest || boldMatch.index < earliest.index)) {
      earliest = boldMatch
      type = 'bold'
    }

    if (!earliest) {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }

    // Text before match
    if (earliest.index > 0) {
      parts.push(<span key={key++}>{remaining.slice(0, earliest.index)}</span>)
    }

    // The match itself
    if (type === 'code') {
      parts.push(
        <code key={key++} className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-sm font-mono text-pink-600 dark:text-pink-400">
          {earliest[1]}
        </code>
      )
    } else if (type === 'bold') {
      parts.push(
        <strong key={key++} className="font-semibold text-gray-900 dark:text-gray-100">
          {earliest[1]}
        </strong>
      )
    }

    remaining = remaining.slice(earliest.index + earliest[0].length)
  }

  return parts
}

// ---------------------------------------------------------------------------
// Format a date string nicely
// ---------------------------------------------------------------------------

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

// ---------------------------------------------------------------------------
// Compute a version type label (major, minor, patch)
// ---------------------------------------------------------------------------

function versionType(version) {
  const parts = version.split('.').map(Number)
  if (parts[0] > 0 && parts[1] === 0 && parts[2] === 0) return 'major'
  if (parts[2] === 0) return 'minor'
  return 'patch'
}

const VERSION_TYPE_STYLES = {
  major: 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 ring-1 ring-red-200 dark:ring-red-800',
  minor: 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-800',
  patch: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 ring-1 ring-gray-200 dark:ring-gray-700',
}

// ---------------------------------------------------------------------------
// Single release card component
// ---------------------------------------------------------------------------

function ReleaseCard({ release, isLatest, defaultExpanded }) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const totalChanges = Object.values(release.categories).reduce((sum, items) => sum + items.length, 0)
  const vType = versionType(release.version)

  return (
    <div className="relative pl-8 pb-8 last:pb-0">
      {/* Timeline connector line */}
      <div className="absolute left-[11px] top-6 bottom-0 w-px bg-gradient-to-b from-blue-300 dark:from-blue-700 to-gray-200 dark:to-gray-800 last:hidden" />

      {/* Timeline dot */}
      <div className={`absolute left-0 top-1.5 w-6 h-6 rounded-full border-2 flex items-center justify-center ${
        isLatest
          ? 'bg-blue-500 border-blue-300 dark:border-blue-700 shadow-lg shadow-blue-500/30'
          : 'bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-600'
      }`}>
        {isLatest && (
          <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
        )}
      </div>

      {/* Card */}
      <div
        className={`group rounded-xl border transition-all duration-200 cursor-pointer ${
          expanded
            ? 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 shadow-md'
            : 'bg-gray-50 dark:bg-gray-900/50 border-gray-200 dark:border-gray-800 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-sm'
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3 min-w-0">
            {/* Version badge */}
            <span className={`inline-flex items-center px-3 py-1 rounded-lg text-sm font-bold font-mono ${VERSION_TYPE_STYLES[vType]}`}>
              v{release.version}
            </span>

            {isLatest && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500 text-white shadow-sm">
                Latest
              </span>
            )}

            {/* Category summary pills */}
            <div className="hidden sm:flex items-center gap-1.5 ml-1">
              {Object.entries(release.categories).map(([cat, items]) => {
                const meta = getCategoryMeta(cat)
                return (
                  <span key={cat} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.badge}`}>
                    {meta.icon}
                    <span>{items.length}</span>
                  </span>
                )
              })}
            </div>
          </div>

          <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400 shrink-0">
            {release.date && (
              <span className="hidden md:inline">{formatDate(release.date)}</span>
            )}
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {totalChanges} change{totalChanges !== 1 ? 's' : ''}
            </span>
            <svg
              className={`w-4 h-4 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Expanded content */}
        {expanded && (
          <div className="px-5 pb-5 space-y-4 border-t border-gray-100 dark:border-gray-800 pt-4" onClick={(e) => e.stopPropagation()}>
            {Object.entries(release.categories).map(([category, items]) => {
              const meta = getCategoryMeta(category)
              return (
                <div key={category}>
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md ${meta.bg} ${meta.text}`}>
                      {meta.icon}
                    </span>
                    <h4 className={`text-sm font-semibold ${meta.text}`}>
                      {category}
                    </h4>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${meta.badge}`}>
                      {items.length}
                    </span>
                  </div>
                  <ul className="space-y-2 ml-8">
                    {items.map((item, i) => (
                      <li key={i} className="relative text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                        <span className={`absolute -left-4 top-2 w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        {renderInlineMarkdown(item)}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Combined view — interleaves both changelogs by date
// ---------------------------------------------------------------------------

function CombinedTimeline({ frontendReleases, backendReleases }) {
  const combined = useMemo(() => {
    const all = [
      ...frontendReleases.map(r => ({ ...r, source: 'frontend' })),
      ...backendReleases.map(r => ({ ...r, source: 'backend' })),
    ]
    // Sort by version descending (semver), then by source
    all.sort((a, b) => {
      const [aMaj, aMin, aPat] = a.version.split('.').map(Number)
      const [bMaj, bMin, bPat] = b.version.split('.').map(Number)
      if (bMaj !== aMaj) return bMaj - aMaj
      if (bMin !== aMin) return bMin - aMin
      if (bPat !== aPat) return bPat - aPat
      // Same version: backend first
      return a.source === 'backend' ? -1 : 1
    })
    return all
  }, [frontendReleases, backendReleases])

  return (
    <div className="relative">
      {combined.map((release, idx) => (
        <div key={`${release.source}-${release.version}`} className="relative pl-8 pb-8 last:pb-0">
          {/* Timeline line */}
          {idx < combined.length - 1 && (
            <div className="absolute left-[11px] top-6 bottom-0 w-px bg-gradient-to-b from-blue-300 dark:from-blue-700 to-gray-200 dark:to-gray-800" />
          )}

          {/* Timeline dot with source indicator */}
          <div className={`absolute left-0 top-1.5 w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-bold ${
            release.source === 'backend'
              ? 'bg-green-500 border-green-300 dark:border-green-700 text-white'
              : 'bg-blue-500 border-blue-300 dark:border-blue-700 text-white'
          } ${idx === 0 ? 'shadow-lg' : ''}`}>
            {release.source === 'backend' ? 'B' : 'F'}
          </div>

          {/* Card */}
          <CombinedReleaseCard release={release} isLatest={idx === 0} />
        </div>
      ))}
    </div>
  )
}

function CombinedReleaseCard({ release, isLatest }) {
  const [expanded, setExpanded] = useState(isLatest)
  const totalChanges = Object.values(release.categories).reduce((sum, items) => sum + items.length, 0)
  const vType = versionType(release.version)

  return (
    <div
      className={`group rounded-xl border transition-all duration-200 cursor-pointer ${
        expanded
          ? 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 shadow-md'
          : 'bg-gray-50 dark:bg-gray-900/50 border-gray-200 dark:border-gray-800 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-sm'
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3 min-w-0 flex-wrap">
          <span className={`inline-flex items-center px-3 py-1 rounded-lg text-sm font-bold font-mono ${VERSION_TYPE_STYLES[vType]}`}>
            v{release.version}
          </span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            release.source === 'backend'
              ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300'
              : 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300'
          }`}>
            {release.source === 'backend' ? 'Backend' : 'Frontend'}
          </span>
          {isLatest && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500 text-white shadow-sm">
              Latest
            </span>
          )}
          <div className="hidden sm:flex items-center gap-1.5">
            {Object.entries(release.categories).map(([cat, items]) => {
              const meta = getCategoryMeta(cat)
              return (
                <span key={cat} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.badge}`}>
                  {meta.icon}
                  <span>{items.length}</span>
                </span>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400 shrink-0">
          {release.date && <span className="hidden md:inline">{formatDate(release.date)}</span>}
          <span className="text-xs text-gray-400 dark:text-gray-500">{totalChanges}</span>
          <svg className={`w-4 h-4 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-gray-100 dark:border-gray-800 pt-4" onClick={(e) => e.stopPropagation()}>
          {Object.entries(release.categories).map(([category, items]) => {
            const meta = getCategoryMeta(category)
            return (
              <div key={category}>
                <div className="flex items-center gap-2 mb-2.5">
                  <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md ${meta.bg} ${meta.text}`}>
                    {meta.icon}
                  </span>
                  <h4 className={`text-sm font-semibold ${meta.text}`}>{category}</h4>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${meta.badge}`}>{items.length}</span>
                </div>
                <ul className="space-y-2 ml-8">
                  {items.map((item, i) => (
                    <li key={i} className="relative text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                      <span className={`absolute -left-4 top-2 w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                      {renderInlineMarkdown(item)}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stats bar — quick summary of total changes
// ---------------------------------------------------------------------------

function StatsBar({ releases }) {
  const stats = useMemo(() => {
    let added = 0, changed = 0, fixed = 0
    for (const r of releases) {
      added += (r.categories.Added || []).length
      changed += (r.categories.Changed || []).length
      fixed += (r.categories.Fixed || []).length
    }
    return { added, changed, fixed, versions: releases.length }
  }, [releases])

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      {[
        { label: 'Releases', value: stats.versions, icon: '🏷️' },
        { label: 'Features', value: stats.added, icon: '✨' },
        { label: 'Improvements', value: stats.changed, icon: '🔄' },
        { label: 'Bug Fixes', value: stats.fixed, icon: '🛡️' },
      ].map(({ label, value, icon }) => (
        <div key={label} className="flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-800">
          <span className="text-lg">{icon}</span>
          <div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{value}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Changelog component
// ---------------------------------------------------------------------------

export default function Changelog() {
  const [activeTab, setActiveTab] = useState('combined')
  const [backendInfo, setBackendInfo] = useState({ version: 'loading...', changelog: 'Loading...' })
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    const fetchBackendInfo = async () => {
      try {
        const info = await api.getBackendInfo()
        setBackendInfo({ version: info.version, changelog: info.changelog })
      } catch {
        setBackendInfo({ version: 'unavailable', changelog: '' })
      } finally {
        setLoading(false)
      }
    }
    fetchBackendInfo()
  }, [])

  const frontendReleases = useMemo(() => parseChangelog(frontendChangelog), [])
  const backendReleases = useMemo(
    () => (backendInfo.changelog ? parseChangelog(backendInfo.changelog) : []),
    [backendInfo.changelog]
  )

  // Filter releases by search term
  const filterReleases = (releases) => {
    if (!searchTerm.trim()) return releases
    const term = searchTerm.toLowerCase()
    return releases
      .map(r => {
        const filteredCats = {}
        for (const [cat, items] of Object.entries(r.categories)) {
          const filtered = items.filter(item => item.toLowerCase().includes(term))
          if (filtered.length > 0) filteredCats[cat] = filtered
        }
        if (Object.keys(filteredCats).length === 0 && !r.version.includes(term)) return null
        return { ...r, categories: Object.keys(filteredCats).length > 0 ? filteredCats : r.categories }
      })
      .filter(Boolean)
  }

  const tabs = [
    { id: 'combined', label: 'All Changes', icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    )},
    { id: 'frontend', label: 'Frontend', version: frontendVersion, icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    )},
    { id: 'backend', label: 'Backend', version: backendInfo.version, icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    )},
  ]

  const displayReleases = activeTab === 'frontend' ? filterReleases(frontendReleases) : filterReleases(backendReleases)
  const allReleasesForStats = [...frontendReleases, ...backendReleases]

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Changelog</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">What's new in Grapheon</p>
            </div>
          </div>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Dashboard
          </Link>
        </div>
      </div>

      {/* Stats */}
      <StatsBar releases={allReleasesForStats} />

      {/* Search + Tabs */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        {/* Tab navigation */}
        <div className="flex items-center gap-1 p-1 rounded-lg bg-gray-100 dark:bg-gray-800/50">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {tab.version && (
                <span className="text-xs opacity-60 font-mono">v{tab.version}</span>
              )}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-64">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search changes..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {loading && activeTab === 'backend' ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-gray-300 dark:border-gray-600 border-t-blue-500 mb-4"></div>
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading backend changelog...</p>
        </div>
      ) : activeTab === 'combined' ? (
        <CombinedTimeline
          frontendReleases={filterReleases(frontendReleases)}
          backendReleases={filterReleases(backendReleases)}
        />
      ) : (
        <div className="relative">
          {displayReleases.map((release, idx) => (
            <ReleaseCard
              key={release.version}
              release={release}
              isLatest={idx === 0}
              defaultExpanded={idx === 0}
            />
          ))}
          {displayReleases.length === 0 && (
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <p className="text-gray-500 dark:text-gray-400">No changes matching "{searchTerm}"</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
