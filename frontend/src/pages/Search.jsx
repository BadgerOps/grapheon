import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'

/**
 * Search Page - Full-text search across all network data
 */
export default function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [selectedTypes, setSelectedTypes] = useState(['hosts', 'ports', 'connections', 'arp', 'imports'])

  // Debounced search
  const performSearch = useCallback(async (searchQuery) => {
    if (!searchQuery || searchQuery.length < 2) {
      setResults(null)
      return
    }

    try {
      setLoading(true)
      setError('')
      const types = selectedTypes.join(',')
      const data = await api.search(searchQuery, types)
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [selectedTypes])

  // Fetch suggestions for autocomplete
  const fetchSuggestions = useCallback(async (searchQuery) => {
    if (!searchQuery || searchQuery.length < 2) {
      setSuggestions([])
      return
    }

    try {
      const data = await api.getSearchSuggestions(searchQuery)
      setSuggestions(data.suggestions || [])
    } catch (err) {
      // Silently fail for suggestions
      setSuggestions([])
    }
  }, [])

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      performSearch(query)
      fetchSuggestions(query)
    }, 300)

    return () => clearTimeout(timeoutId)
  }, [query, performSearch, fetchSuggestions])

  const handleTypeToggle = (type) => {
    setSelectedTypes(prev => {
      if (prev.includes(type)) {
        return prev.filter(t => t !== type)
      }
      return [...prev, type]
    })
  }

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion.value)
    setSuggestions([])
  }

  const getResultIcon = (type) => {
    switch (type) {
      case 'host':
        return (
          <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
          </svg>
        )
      case 'port':
        return (
          <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        )
      case 'connection':
        return (
          <svg className="w-5 h-5 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        )
      case 'arp':
        return (
          <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        )
      default:
        return (
          <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        )
    }
  }

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Search</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Search across all network data
        </p>
      </div>

      {/* Search Input */}
      <div className="relative mb-6">
        <div className="flex items-center">
          <div className="relative flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by IP, hostname, MAC, service, process..."
              className="input pl-12 text-lg"
              autoFocus
            />
            <svg
              className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {loading && (
              <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              </div>
            )}
          </div>
        </div>

        {/* Suggestions dropdown */}
        {suggestions.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 max-h-60 overflow-auto">
            {suggestions.map((suggestion, index) => (
              <button
                key={index}
                onClick={() => handleSuggestionClick(suggestion)}
                className="w-full px-4 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-3"
              >
                <span className="text-xs text-gray-500 dark:text-gray-400 uppercase w-16">
                  {suggestion.type}
                </span>
                <span className="text-gray-900 dark:text-gray-100">{suggestion.value}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Type filters */}
      <div className="flex flex-wrap gap-2 mb-6">
        {['hosts', 'ports', 'connections', 'arp', 'imports'].map((type) => (
          <button
            key={type}
            onClick={() => handleTypeToggle(type)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              selectedTypes.includes(type)
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
          >
            {type.charAt(0).toUpperCase() + type.slice(1)}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-6">
          {/* Results summary */}
          <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
            <span>
              Found {results.total_results} results in {results.search_time_ms}ms
            </span>
          </div>

          {/* Results by type */}
          {Object.entries(results.results).map(([type, items]) => {
            if (items.length === 0) return null

            return (
              <div key={type} className="card">
                <div className="card-header flex items-center justify-between">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 capitalize">
                    {type} ({items.length})
                  </h3>
                </div>
                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                  {items.map((item, index) => (
                    <div key={index} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                      <div className="flex items-start gap-3">
                        {getResultIcon(item._type)}
                        <div className="flex-1 min-w-0">
                          {item._type === 'host' && (
                            <Link
                              to={`/hosts/${item.id}`}
                              className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                            >
                              {item.ip_address}
                            </Link>
                          )}
                          {item._type === 'port' && (
                            <Link
                              to={`/hosts/${item.host_id}`}
                              className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                            >
                              {item.port_number}/{item.protocol}
                            </Link>
                          )}
                          {item._type === 'connection' && (
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.local_ip}:{item.local_port} → {item.remote_ip}:{item.remote_port}
                            </span>
                          )}
                          {item._type === 'arp' && (
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.ip_address}
                            </span>
                          )}
                          {item._type === 'import' && (
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {item.filename || item.source_type}
                            </span>
                          )}

                          <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            {item._type === 'host' && (
                              <>
                                {item.hostname && <span className="mr-3">{item.hostname}</span>}
                                {item.mac_address && <span className="mr-3">{item.mac_address}</span>}
                                {item.os_name && <span>{item.os_name}</span>}
                              </>
                            )}
                            {item._type === 'port' && (
                              <>
                                {item.service_name && <span className="mr-3">Service: {item.service_name}</span>}
                                {item.product && <span>Product: {item.product}</span>}
                              </>
                            )}
                            {item._type === 'connection' && (
                              <>
                                <span className="mr-3">{item.protocol}</span>
                                <span className="mr-3">{item.state}</span>
                                {item.process_name && <span>Process: {item.process_name}</span>}
                              </>
                            )}
                            {item._type === 'arp' && (
                              <>
                                {item.mac_address && <span className="mr-3">{item.mac_address}</span>}
                                {item.vendor && <span>{item.vendor}</span>}
                              </>
                            )}
                            {item._type === 'import' && (
                              <>
                                <span className="mr-3">{item.source_type}</span>
                                <span className={`badge ${item.parse_status === 'success' ? 'badge-success' : 'badge-warning'}`}>
                                  {item.parse_status}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}

          {results.total_results === 0 && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <svg className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <p className="text-lg font-medium">No results found</p>
              <p className="text-sm mt-1">Try a different search term</p>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!results && !loading && query.length === 0 && (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <svg className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <p className="text-lg font-medium">Search your network data</p>
          <p className="text-sm mt-1">Enter at least 2 characters to search</p>
        </div>
      )}
    </div>
  )
}
