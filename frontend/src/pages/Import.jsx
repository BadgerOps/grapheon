import { useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'
import ImportForm from '../components/ImportForm'
import FileUpload from '../components/FileUpload'

export default function Import() {
  const [activeTab, setActiveTab] = useState('paste')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const handlePasteSubmit = async (sourceType, sourceHost, rawData) => {
    try {
      setIsLoading(true)
      setError('')
      await api.importRaw(sourceType, sourceHost, rawData)
      setSuccessMessage('Data imported successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
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
      await api.importFile(file, sourceType, sourceHost)
      setSuccessMessage('File imported successfully')
      setTimeout(() => setSuccessMessage(''), 3000)
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
    </div>
  )
}
