import { useState } from 'react'

export default function ImportForm({ onSubmit, isLoading }) {
  const [sourceType, setSourceType] = useState('nmap')
  const [sourceHost, setSourceHost] = useState('')
  const [rawData, setRawData] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!sourceHost.trim()) {
      setError('Source host is required')
      return
    }

    if (!rawData.trim()) {
      setError('Data is required')
      return
    }

    try {
      await onSubmit(sourceType, sourceHost, rawData)
      setSourceHost('')
      setRawData('')
    } catch (err) {
      setError(err.message || 'Failed to import data')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-2xl">
      {error && (
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Source Type
          </label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="nmap">Nmap</option>
            <option value="netstat">Netstat</option>
            <option value="arp">ARP</option>
            <option value="traceroute">Traceroute</option>
            <option value="ping">Ping</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Source Host
          </label>
          <input
            type="text"
            value={sourceHost}
            onChange={(e) => setSourceHost(e.target.value)}
            placeholder="e.g., 192.168.1.1"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Raw Data
        </label>
        <textarea
          value={rawData}
          onChange={(e) => setRawData(e.target.value)}
          placeholder="Paste your data here..."
          rows={12}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-400 transition-colors font-medium"
      >
        {isLoading ? 'Importing...' : 'Import Data'}
      </button>
    </form>
  )
}
