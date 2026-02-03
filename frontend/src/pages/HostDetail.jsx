import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import * as api from '../api/client'

export default function HostDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [host, setHost] = useState(null)
  const [ports, setPorts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchHost()
  }, [id])

  const fetchHost = async () => {
    try {
      setLoading(true)
      setError('')
      const data = await api.getHost(id)
      // API returns {host: {...}, ports: [...]}
      setHost(data.host)
      setPorts(data.ports || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (window.confirm('Are you sure you want to delete this host?')) {
      try {
        await api.deleteHost(id)
        navigate('/hosts')
      } catch (err) {
        setError(err.message)
      }
    }
  }

  if (loading) {
    return (
      <div className="p-8">
        <p className="text-gray-600">Loading host details...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
        <Link to="/hosts" className="text-blue-500 hover:text-blue-700">
          ← Back to Hosts
        </Link>
      </div>
    )
  }

  if (!host) {
    return (
      <div className="p-8">
        <p className="text-gray-600">Host not found</p>
        <Link to="/hosts" className="text-blue-500 hover:text-blue-700">
          ← Back to Hosts
        </Link>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          {host.hostname || host.ip_address}
        </h1>
        <div className="flex gap-4">
          <Link
            to="/hosts"
            className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 transition-colors"
          >
            Back to Hosts
          </Link>
          <button
            onClick={handleDelete}
            className="px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors"
          >
            Delete Host
          </button>
        </div>
      </div>

      {/* Host Information */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Host Information</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <InfoItem label="IP Address" value={host.ip_address} />
          <InfoItem label="GUID" value={host.guid} />
          <InfoItem label="IPv6 Address" value={host.ip_v6_address} />
          <InfoItem label="MAC Address" value={host.mac_address} />
          <InfoItem label="Hostname" value={host.hostname} />
          <InfoItem label="FQDN" value={host.fqdn} />
          <InfoItem label="NetBIOS Name" value={host.netbios_name} />
          <InfoItem label="OS Name" value={host.os_name} />
          <InfoItem label="OS Version" value={host.os_version} />
          <InfoItem label="OS Family" value={host.os_family} />
          <InfoItem label="OS Confidence" value={host.os_confidence ? `${host.os_confidence}%` : null} />
          <InfoItem label="Device Type" value={host.device_type} />
          <InfoItem label="Vendor" value={host.vendor} />
          <InfoItem label="Criticality" value={host.criticality} />
          <InfoItem label="Owner" value={host.owner} />
          <InfoItem label="Location" value={host.location} />
          <InfoItem label="Verified" value={host.is_verified ? 'Yes' : 'No'} />
          <InfoItem label="Active" value={host.is_active ? 'Yes' : 'No'} />
          <InfoItem label="First Seen" value={host.first_seen ? new Date(host.first_seen).toLocaleString() : null} />
          <InfoItem label="Last Seen" value={host.last_seen ? new Date(host.last_seen).toLocaleString() : null} />
        </div>
        {host.tags && host.tags.length > 0 && (
          <div className="mt-4">
            <span className="text-sm font-medium text-gray-500">Tags: </span>
            {host.tags.map((tag, i) => (
              <span key={i} className="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded mr-2">
                {tag}
              </span>
            ))}
          </div>
        )}
        {host.notes && (
          <div className="mt-4">
            <span className="text-sm font-medium text-gray-500">Notes: </span>
            <p className="text-gray-700 mt-1">{host.notes}</p>
          </div>
        )}
        {host.source_types && host.source_types.length > 0 && (
          <div className="mt-4">
            <span className="text-sm font-medium text-gray-500">Data Sources: </span>
            {host.source_types.map((src, i) => (
              <span key={i} className="inline-block bg-green-100 text-green-800 text-xs px-2 py-1 rounded mr-2">
                {src}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Ports */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">
          Open Ports ({ports.length})
        </h2>
        {ports.length === 0 ? (
          <p className="text-gray-500">No ports discovered</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-100 border-b-2 border-gray-300">
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Port</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Protocol</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">State</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Service</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Version</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Product</th>
                </tr>
              </thead>
              <tbody>
                {ports.map((port) => (
                  <tr key={port.id} className="border-b border-gray-200 hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-900 font-mono">{port.port_number}</td>
                    <td className="px-4 py-3 text-gray-900">{port.protocol}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                        port.state === 'open' ? 'bg-green-100 text-green-800' :
                        port.state === 'filtered' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-red-100 text-red-800'
                      }`}>
                        {port.state}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-900">{port.service_name || '-'}</td>
                    <td className="px-4 py-3 text-gray-900">{port.service_version || '-'}</td>
                    <td className="px-4 py-3 text-gray-900">{port.product || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function InfoItem({ label, value }) {
  return (
    <div>
      <dt className="text-sm font-medium text-gray-500">{label}</dt>
      <dd className="mt-1 text-gray-900">{value || '-'}</dd>
    </div>
  )
}
