import { useState } from 'react'

const SOURCE_HINTS = {
  nmap: {
    label: 'Nmap',
    command: 'nmap -O -A -oX scan.xml 10.0.0.0/24',
    note: 'Use -oX for XML output. Add -O for OS detection, -A for aggressive (services + scripts).',
    paste: 'Paste the XML output, or use the File tab to upload the .xml file directly.',
  },
  netstat: {
    label: 'Netstat',
    command: 'netstat -tulnp',
    note: 'Shows TCP/UDP listeners with PIDs. Use -a for all connections including ESTABLISHED.',
    paste: 'Paste the full terminal output.',
  },
  arp: {
    label: 'ARP',
    command: 'arp -a',
    note: 'Shows MAC-to-IP mappings on local segments. Also supports: ip neigh',
    paste: 'Paste the full terminal output.',
  },
  traceroute: {
    label: 'Traceroute',
    command: 'traceroute -n 10.0.0.1',
    note: 'Use -n to skip DNS lookups for faster results.',
    paste: 'Paste the full terminal output.',
  },
  ping: {
    label: 'Ping',
    command: 'ping -c 4 10.0.0.1',
    note: 'Use -c to set the number of pings.',
    paste: 'Paste the full terminal output.',
  },
}

export default function ImportForm({ onSubmit, isLoading }) {
  const [sourceType, setSourceType] = useState('nmap')
  const [sourceHost, setSourceHost] = useState('')
  const [rawData, setRawData] = useState('')
  const [error, setError] = useState('')

  const hint = SOURCE_HINTS[sourceType] || {}

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
            placeholder="IP of the machine that ran the scan"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Command hint */}
      <div className="p-3 bg-gray-50 border border-gray-200 rounded-md">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Example command</p>
        <code className="block text-sm font-mono text-blue-700 bg-white px-2 py-1 rounded border border-gray-200 select-all">
          {hint.command}
        </code>
        <p className="text-xs text-gray-500 mt-1.5">{hint.note}</p>
        <p className="text-xs text-gray-400 mt-0.5">{hint.paste}</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Raw Data
        </label>
        <textarea
          value={rawData}
          onChange={(e) => setRawData(e.target.value)}
          placeholder={`Paste ${hint.label || sourceType} output here...`}
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
