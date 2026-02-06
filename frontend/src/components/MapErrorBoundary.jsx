import { Component } from 'react'

/**
 * Error boundary for the CytoscapeNetworkMap component.
 *
 * Catches Cytoscape initialization and render errors, showing a
 * fallback UI with a retry button instead of crashing the whole page.
 */
export default class MapErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, errorMessage: '' }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, errorMessage: error.message || 'Unknown error' }
  }

  componentDidCatch(error, errorInfo) {
    console.error('CytoscapeNetworkMap crashed:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, errorMessage: '' })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"
          style={{ height: '100%', minHeight: '500px' }}
        >
          <div className="text-center p-8 max-w-md">
            <svg
              className="w-16 h-16 mx-auto mb-4 text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
              />
            </svg>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              Map failed to render
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {this.state.errorMessage}
            </p>
            <button
              onClick={this.handleRetry}
              className="btn btn-primary"
            >
              Retry
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
