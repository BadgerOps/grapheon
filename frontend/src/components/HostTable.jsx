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
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No hosts found
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-100 dark:bg-gray-700 border-b-2 border-gray-300 dark:border-gray-600">
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">IP Address</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">Hostname</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">OS Family</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">Device Type</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">Vendor</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">Last Seen</th>
            <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-200">Actions</th>
          </tr>
        </thead>
        <tbody>
          {hosts.map((host) => (
            <tr
              key={host.id}
              onClick={() => handleRowClick(host.id)}
              className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
            >
              <td className="px-6 py-4 text-gray-900 dark:text-gray-100 font-mono text-sm">{host.ip_address}</td>
              <td className="px-6 py-4 text-gray-900 dark:text-gray-100">{host.hostname || '-'}</td>
              <td className="px-6 py-4 text-gray-900 dark:text-gray-100">
                {host.os_family ? (
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    host.os_family === 'linux' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300' :
                    host.os_family === 'windows' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300' :
                    host.os_family === 'macos' ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300' :
                    host.os_family === 'network' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300' :
                    'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
                  }`}>
                    {host.os_family}
                  </span>
                ) : '-'}
              </td>
              <td className="px-6 py-4 text-gray-900 dark:text-gray-100">
                {host.device_type ? (
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    host.device_type === 'router' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300' :
                    host.device_type === 'switch' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300' :
                    host.device_type === 'firewall' ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300' :
                    host.device_type === 'server' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300' :
                    host.device_type === 'workstation' ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' :
                    host.device_type === 'printer' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300' :
                    'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
                  }`}>
                    {host.device_type}
                  </span>
                ) : '-'}
              </td>
              <td className="px-6 py-4 text-gray-700 dark:text-gray-300 text-sm">{host.vendor || '-'}</td>
              <td className="px-6 py-4 text-gray-700 dark:text-gray-300 text-sm">
                {host.last_seen ? new Date(host.last_seen).toLocaleString() : '-'}
              </td>
              <td className="px-6 py-4">
                <button
                  onClick={(e) => handleDelete(e, host.id)}
                  className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded text-sm transition-colors"
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
