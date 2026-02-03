import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'

export default function Arp() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchEntries()
  }, [])

  const fetchEntries = async () => {
    try {
      setLoading(true)
      setError('')
      const data = await api.getArpEntries()
      setEntries(data.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900">ARP Entries</h1>
        <Link
          to="/"
          className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8">
          <p className="text-gray-600">Loading ARP entries...</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-md overflow-hidden">
          {entries.length === 0 ? (
            <div className="text-center py-8 text-gray-500">No ARP entries found</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-100 border-b-2 border-gray-300">
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">IP Address</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">MAC Address</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">Interface</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">Type</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">Vendor</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">Source</th>
                    <th className="px-6 py-3 text-left font-semibold text-gray-700">Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b border-gray-200 hover:bg-gray-50">
                      <td className="px-6 py-4 text-gray-900 font-mono">{entry.ip_address}</td>
                      <td className="px-6 py-4 text-gray-900 font-mono">{entry.mac_address}</td>
                      <td className="px-6 py-4 text-gray-900">{entry.interface || '-'}</td>
                      <td className="px-6 py-4 text-gray-900">{entry.entry_type || entry.is_resolved || '-'}</td>
                      <td className="px-6 py-4 text-gray-900">{entry.vendor || '-'}</td>
                      <td className="px-6 py-4 text-gray-900">{entry.source_type || '-'}</td>
                      <td className="px-6 py-4 text-gray-900">
                        {entry.last_seen ? new Date(entry.last_seen).toLocaleString() : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
