import { useState } from 'react'

const SOURCE_HINTS = {
  nmap: {
    label: 'Nmap',
    command: 'nmap -O -A -oX scan.xml 10.0.0.0/24',
    note: 'Upload the XML file generated with -oX. Add -O for OS detection, -A for aggressive mode.',
    accept: '.xml',
  },
  netstat: {
    label: 'Netstat',
    command: 'netstat -tulnp > netstat.txt',
    note: 'Redirect terminal output to a file, then upload it here.',
    accept: '.txt,.log',
  },
  arp: {
    label: 'ARP',
    command: 'arp -a > arp.txt',
    note: 'Redirect terminal output to a file. Also supports: ip neigh > arp.txt',
    accept: '.txt,.log',
  },
  traceroute: {
    label: 'Traceroute',
    command: 'traceroute -n 10.0.0.1 > trace.txt',
    note: 'Redirect terminal output to a file. Use -n to skip DNS lookups.',
    accept: '.txt,.log',
  },
  ping: {
    label: 'Ping',
    command: 'ping -c 4 10.0.0.1 > ping.txt',
    note: 'Redirect terminal output to a file.',
    accept: '.txt,.log',
  },
}

export default function FileUpload({ onSubmit, isLoading }) {
  const [sourceType, setSourceType] = useState('nmap')
  const [sourceHost, setSourceHost] = useState('')
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')

  const hint = SOURCE_HINTS[sourceType] || {}

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError('')
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!sourceHost.trim()) {
      setError('Source host is required')
      return
    }

    if (!file) {
      setError('Please select a file')
      return
    }

    try {
      await onSubmit(file, sourceType, sourceHost)
      setSourceHost('')
      setFile(null)
      if (document.querySelector('input[type="file"]')) {
        document.querySelector('input[type="file"]').value = ''
      }
    } catch (err) {
      setError(err.message || 'Failed to upload file')
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
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Select File
        </label>
        <input
          type="file"
          accept={hint.accept || '*'}
          onChange={handleFileChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {file && (
          <p className="mt-2 text-sm text-gray-600">
            Selected: {file.name}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading || !file}
        className="w-full px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-400 transition-colors font-medium"
      >
        {isLoading ? 'Uploading...' : 'Upload and Import'}
      </button>
    </form>
  )
}
