import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'
import ImportForm from '../components/ImportForm'
import FileUpload from '../components/FileUpload'

export default function Import() {
  const [activeTab, setActiveTab] = useState('paste')
  const [isLoading, setIsLoading] = useState(false)
  const [taskStatus, setTaskStatus] = useState(null) // tracks background task progress
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [sourceOrigin, setSourceOrigin] = useState('')
  const [imports, setImports] = useState([])
  const [loadingImports, setLoadingImports] = useState(true)

  const fetchImports = async () => {
    try {
      setLoadingImports(true)
      const response = await api.getImports({ limit: 25, source_origin: sourceOrigin || null })
      setImports(response.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingImports(false)
    }
  }

  useEffect(() => {
    fetchImports()
  }, [sourceOrigin])

  /**
   * Handle an import API response. If it contains a task_id, poll for completion.
   * Otherwise treat as a synchronous success.
   */
  const handleImportResponse = async (result, successMsg) => {
    if (result.task_id) {
      // Async mode — poll for task completion
      setTaskStatus({ status: 'pending', message: 'Processing import...' })
      try {
        const finalStatus = await api.pollTask(result.task_id, (s) => {
          setTaskStatus({ status: s.status, message: s.progress || `Status: ${s.status}` })
        })
        if (finalStatus.status === 'success') {
          setSuccessMessage(successMsg)
          setTimeout(() => setSuccessMessage(''), 5000)
          await fetchImports()
        } else {
          setError(finalStatus.error || 'Import failed')
        }
      } finally {
        setTaskStatus(null)
      }
    } else {
      // Synchronous mode — already complete
      setSuccessMessage(successMsg)
      setTimeout(() => setSuccessMessage(''), 3000)
      await fetchImports()
    }
  }

  const handlePasteSubmit = async (sourceType, sourceHost, rawData) => {
    try {
      setIsLoading(true)
      setError('')
      const result = await api.importRaw(sourceType, sourceHost, rawData)
      await handleImportResponse(result, 'Data imported successfully')
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileSubmit = async (file, sourceType, sourceHost) => {
    try {
      setIsLoading(true)
      setError('')
      const result = await api.importFile(file, sourceType, sourceHost)
      await handleImportResponse(result, 'File imported successfully')
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Import Data</h1>
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

      {successMessage && (
        <div className="mb-6 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
          {successMessage}
        </div>
      )}

      {taskStatus && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-300 text-blue-800 rounded flex items-center gap-3">
          <svg className="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>{taskStatus.message}</span>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-md">
        {/* Tab Navigation */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab('paste')}
            className={`flex-1 px-6 py-4 font-medium text-center transition-colors ${
              activeTab === 'paste'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Paste Data
          </button>
          <button
            onClick={() => setActiveTab('file')}
            className={`flex-1 px-6 py-4 font-medium text-center transition-colors ${
              activeTab === 'file'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Upload File
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-8">
          {activeTab === 'paste' && (
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-6">Paste Raw Data</h2>
              <ImportForm onSubmit={handlePasteSubmit} isLoading={isLoading} />
            </div>
          )}

          {activeTab === 'file' && (
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-6">Upload File</h2>
              <FileUpload onSubmit={handleFileSubmit} isLoading={isLoading} />
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 bg-white rounded-lg shadow-md overflow-hidden">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Import History</h2>
          <select
            value={sourceOrigin}
            onChange={(event) => setSourceOrigin(event.target.value)}
            className="select"
          >
            <option value="">All origins</option>
            <option value="manual">Manual imports</option>
            <option value="agent">Agent imports</option>
          </select>
        </div>
        {loadingImports ? (
          <div className="px-6 py-8 text-center text-gray-500">Loading imports...</div>
        ) : imports.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">No imports found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-100 border-b-2 border-gray-300">
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Origin</th>
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Source</th>
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Input</th>
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Status</th>
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Records</th>
                  <th className="px-6 py-3 text-left font-semibold text-gray-700">Created</th>
                </tr>
              </thead>
              <tbody>
                {imports.map((imp) => (
                  <tr key={imp.id} className="border-b border-gray-200 hover:bg-gray-50">
                    <td className="px-6 py-4 text-gray-900">{imp.source_origin || '-'}</td>
                    <td className="px-6 py-4 text-gray-900">{imp.source_type}</td>
                    <td className="px-6 py-4 text-gray-900">{imp.filename || imp.import_type}</td>
                    <td className="px-6 py-4 text-gray-900">{imp.parse_status}</td>
                    <td className="px-6 py-4 text-gray-900">{imp.parsed_count}</td>
                    <td className="px-6 py-4 text-gray-900">
                      {imp.created_at ? new Date(imp.created_at).toLocaleString() : '-'}
                    </td>
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
