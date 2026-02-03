import changelog from '../../CHANGELOG.md?raw'

export default function Changelog() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Changelog</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Release notes for the Graphēon frontend.
        </p>
      </div>
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 shadow-sm">
        <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200 font-mono">
          {changelog}
        </pre>
      </div>
    </div>
  )
}
