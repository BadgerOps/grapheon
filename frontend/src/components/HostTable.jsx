import { useNavigate } from 'react-router-dom'

export default function HostTable({ hosts = [], onDelete }) {
  const navigate = useNavigate()

  const handleRowClick = (hostId) => {
    navigate(`/hosts/${hostId}`)
  }

  const handleDelete = (e, hostId) => {
    e.stopPropagation()
    if (window.confirm('Are you sure you want to delete this host?')) {
      onDelete(hostId)
    }
  }

  if (!hosts || hosts.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No hosts found
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-100 border-b-2 border-gray-300">
            <th className="px-6 py-3 text-left font-semibold text-gray-700">IP Address</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700">Hostname</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700">OS Family</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700">Device Type</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700">Last Seen</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700">Actions</th>
          </tr>
        </thead>
        <tbody>
          {hosts.map((host) => (
            <tr
              key={host.id}
              onClick={() => handleRowClick(host.id)}
              className="border-b border-gray-200 hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <td className="px-6 py-4 text-gray-900">{host.ip_address}</td>
              <td className="px-6 py-4 text-gray-900">{host.hostname || '-'}</td>
              <td className="px-6 py-4 text-gray-900">{host.os_family || '-'}</td>
              <td className="px-6 py-4 text-gray-900">{host.device_type || '-'}</td>
              <td className="px-6 py-4 text-gray-900">
                {host.last_seen ? new Date(host.last_seen).toLocaleString() : '-'}
              </td>
              <td className="px-6 py-4">
                <button
                  onClick={(e) => handleDelete(e, host.id)}
                  className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 transition-colors text-sm"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
