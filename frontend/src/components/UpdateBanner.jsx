import { useState, useEffect, useRef } from 'react'
import { checkForUpdates, triggerUpgrade, getUpgradeStatus } from '../api/client'

const POLL_INTERVAL = 60 * 60 * 1000; // 60 minutes
const UPGRADE_STATUS_POLL_INTERVAL = 5000; // 5 seconds
const DISMISSED_VERSION_KEY = 'update_banner_dismissed_version';

/**
 * Simple markdown to HTML converter for release notes
 * Handles basic markdown: ###, **, -, code blocks
 */
const markdownToHtml = (markdown) => {
  if (!markdown) return '';

  let html = markdown
    // Escape any existing HTML to prevent injection
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Convert headings: ### -> <h4>
    .replace(/^### (.*?)$/gm, '<h4 class="font-bold text-lg mt-3 mb-2">$1</h4>')
    // Convert bold: **text** -> <strong>
    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold">$1</strong>')
    // Convert list items: - text -> <li>
    .replace(/^- (.*?)$/gm, '<li class="ml-4">$1</li>')
    // Wrap consecutive <li> in <ul>
    .replace(/(<li.*?<\/li>)(\n<li|<li)/g, '<ul class="list-disc mb-3">$1</ul>\n<ul class="list-disc">')
    .replace(/(<li.*?<\/li>)(?!\n<li|<li)/g, '$1\n</ul>')
    // Convert code blocks: ```...``` -> <pre>
    .replace(/```(.*?)```/gs, '<pre class="bg-gray-100 dark:bg-gray-900 p-3 rounded text-sm overflow-x-auto mb-3">$1</pre>')
    // Convert inline code: `text` -> <code>
    .replace(/`(.*?)`/g, '<code class="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-sm font-mono">$1</code>')
    // Convert line breaks
    .replace(/\n\n/g, '<br/><br/>');

  return html;
};

/**
 * UpdateBanner Component
 *
 * Displays an update notification banner with:
 * - Polling for available updates (every 60 minutes)
 * - Dismissible banner with release notes expansion
 * - Upgrade confirmation and progress tracking
 * - Error handling and recovery
 */
export default function UpdateBanner() {
  // Update check state
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [latestVersion, setLatestVersion] = useState(null);
  const [releaseNotes, setReleaseNotes] = useState('');
  const [showReleaseNotes, setShowReleaseNotes] = useState(false);

  // Upgrade process state
  const [upgradeStep, setUpgradeStep] = useState(null); // null, 'confirm', 'in_progress', 'completed', 'error'
  const [upgradeError, setUpgradeError] = useState(null);
  const [upgradeProgress, setUpgradeProgress] = useState(null);

  // Loading and error state
  const [isCheckingUpdates, setIsCheckingUpdates] = useState(false);
  const [checkError, setCheckError] = useState(null);

  // Refs for cleanup
  const pollIntervalRef = useRef(null);
  const statusPollIntervalRef = useRef(null);
  const reloadTimeoutRef = useRef(null);

  /**
   * Check for available updates
   */
  const checkForUpdatesHandler = async () => {
    setIsCheckingUpdates(true);
    setCheckError(null);

    try {
      const response = await checkForUpdates();

      if (response.update_available) {
        const dismissedVersion = localStorage.getItem(DISMISSED_VERSION_KEY);

        // Only show banner if this version hasn't been dismissed
        if (dismissedVersion !== response.latest_version) {
          setUpdateAvailable(true);
          setLatestVersion(response.latest_version);
          setReleaseNotes(response.release_notes || '');
          setShowReleaseNotes(false);
        }
      } else {
        setUpdateAvailable(false);
        setLatestVersion(null);
        setReleaseNotes('');
      }
    } catch (error) {
      console.error('Error checking for updates:', error);
      setCheckError(error.message || 'Failed to check for updates');
    } finally {
      setIsCheckingUpdates(false);
    }
  };

  /**
   * Dismiss the update banner for this version
   */
  const handleDismiss = () => {
    if (latestVersion) {
      localStorage.setItem(DISMISSED_VERSION_KEY, latestVersion);
    }
    setUpdateAvailable(false);
    setShowReleaseNotes(false);
    setUpgradeStep(null);
    setUpgradeError(null);
  };

  /**
   * Initiate upgrade - show confirmation step
   */
  const handleUpgradeClick = () => {
    setUpgradeStep('confirm');
  };

  /**
   * Confirm upgrade and start the process
   */
  const handleConfirmUpgrade = async () => {
    setUpgradeStep('in_progress');
    setUpgradeError(null);
    setUpgradeProgress({ message: 'Starting upgrade...', step: 0, total_steps: 5, progress: 0 });

    try {
      await triggerUpgrade();

      // Start polling for upgrade status
      let attempt = 0;
      const maxAttempts = 120; // 10 minutes with 5-second intervals

      statusPollIntervalRef.current = setInterval(async () => {
        attempt++;

        try {
          const statusResponse = await getUpgradeStatus();

          if (statusResponse.status === 'running') {
            setUpgradeProgress({
              message: statusResponse.message || 'Upgrading...',
              step: statusResponse.step || 0,
              total_steps: statusResponse.total_steps || 5,
              progress: statusResponse.progress || 0,
            });
          } else if (statusResponse.status === 'completed') {
            clearInterval(statusPollIntervalRef.current);
            setUpgradeStep('completed');
            setUpgradeProgress({
              message: 'Upgrade complete! Refreshing...',
              step: statusResponse.total_steps || 5,
              total_steps: statusResponse.total_steps || 5,
              progress: 100,
            });

            // Reload page after 3 seconds
            reloadTimeoutRef.current = setTimeout(() => {
              window.location.reload();
            }, 3000);
          } else if (statusResponse.status === 'failed') {
            clearInterval(statusPollIntervalRef.current);
            setUpgradeStep('error');
            setUpgradeError(statusResponse.message || 'Upgrade failed. Please try again.');
          }
        } catch (statusError) {
          // Continue polling even if a single request fails (might be temporary)
          console.error('Error polling upgrade status:', statusError);

          if (attempt >= maxAttempts) {
            clearInterval(statusPollIntervalRef.current);
            setUpgradeStep('error');
            setUpgradeError('Upgrade status check timed out. The upgrade may still be in progress.');
          }
        }
      }, UPGRADE_STATUS_POLL_INTERVAL);
    } catch (error) {
      console.error('Error triggering upgrade:', error);
      setUpgradeStep('error');
      setUpgradeError(error.message || 'Failed to start upgrade. Please try again.');
    }
  };

  /**
   * Cancel upgrade confirmation
   */
  const handleCancelUpgrade = () => {
    setUpgradeStep(null);
    setUpgradeError(null);
  };

  /**
   * Dismiss error state
   */
  const handleDismissError = () => {
    setUpgradeStep(null);
    setUpgradeError(null);
    setUpgradeProgress(null);
  };

  /**
   * Initialize polling on mount
   */
  useEffect(() => {
    // Check immediately on mount
    checkForUpdatesHandler();

    // Set up polling interval
    pollIntervalRef.current = setInterval(() => {
      checkForUpdatesHandler();
    }, POLL_INTERVAL);

    return () => {
      // Cleanup intervals and timeouts
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      if (statusPollIntervalRef.current) {
        clearInterval(statusPollIntervalRef.current);
      }
      if (reloadTimeoutRef.current) {
        clearTimeout(reloadTimeoutRef.current);
      }
    };
  }, []);

  // Don't render anything if no update available and not in progress
  if (!updateAvailable && upgradeStep !== 'in_progress' && upgradeStep !== 'completed' && upgradeStep !== 'error') {
    return null;
  }

  // Render banner with different states
  return (
    <div className="animate-slide-down">
      {/* Normal update available state */}
      {updateAvailable && upgradeStep === null && (
        <div className="bg-gradient-to-r from-indigo-600 to-blue-600 dark:from-indigo-700 dark:to-blue-700 text-white px-4 py-3 shadow-lg">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
              <span className="font-medium text-sm sm:text-base">
                Update available: <span className="font-semibold">v{latestVersion}</span>
              </span>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => setShowReleaseNotes(!showReleaseNotes)}
                className="px-3 py-1 rounded text-sm font-medium bg-white bg-opacity-20 hover:bg-opacity-30 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-indigo-600 dark:focus:ring-offset-indigo-700"
              >
                {showReleaseNotes ? "Hide" : "What's new"}
              </button>
              <button
                onClick={handleUpgradeClick}
                className="px-3 py-1 rounded text-sm font-medium bg-white text-indigo-600 dark:text-indigo-700 hover:bg-opacity-90 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-indigo-600 dark:focus:ring-offset-indigo-700"
              >
                Upgrade now
              </button>
              <button
                onClick={handleDismiss}
                className="p-1 rounded hover:bg-white hover:bg-opacity-20 transition-colors focus:outline-none focus:ring-2 focus:ring-white"
                aria-label="Dismiss update notification"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>

          {/* Release notes expansion */}
          {showReleaseNotes && releaseNotes && (
            <div className="mt-3 pt-3 border-t border-white border-opacity-20 bg-black bg-opacity-10 rounded p-3">
              <h3 className="text-sm font-semibold mb-2">Release Notes:</h3>
              <div
                className="text-sm text-white text-opacity-95 space-y-2"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(releaseNotes) }}
              />
            </div>
          )}
          {showReleaseNotes && !releaseNotes && (
            <div className="mt-3 pt-3 border-t border-white border-opacity-20 bg-black bg-opacity-10 rounded p-3 text-sm text-white text-opacity-90">
              No release notes available.
            </div>
          )}
        </div>
      )}

      {/* Upgrade confirmation state */}
      {upgradeStep === 'confirm' && (
        <div className="bg-gradient-to-r from-indigo-600 to-blue-600 dark:from-indigo-700 dark:to-blue-700 text-white px-4 py-4 shadow-lg">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 5v8a2 2 0 01-2 2h-5l-5 4v-4H4a2 2 0 01-2-2V5a2 2 0 012-2h12a2 2 0 012 2zm-11-1a1 1 0 11-2 0 1 1 0 012 0z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <p className="font-medium">Confirm Upgrade to v{latestVersion}</p>
                <p className="text-sm text-white text-opacity-90 mt-1">
                  This will back up your data, pull updated containers, restart services, and verify health. You may lose connection briefly during the restart.
                </p>
              </div>
            </div>

            <div className="flex gap-3 mt-4 justify-end">
              <button
                onClick={handleCancelUpgrade}
                className="px-4 py-2 rounded text-sm font-medium bg-white bg-opacity-20 hover:bg-opacity-30 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-indigo-600 dark:focus:ring-offset-indigo-700"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmUpgrade}
                className="px-4 py-2 rounded text-sm font-medium bg-white text-indigo-600 dark:text-indigo-700 hover:bg-opacity-90 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-indigo-600 dark:focus:ring-offset-indigo-700"
              >
                Confirm upgrade
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upgrade in progress state */}
      {upgradeStep === 'in_progress' && (
        <div className="bg-gradient-to-r from-amber-500 to-orange-500 dark:from-amber-600 dark:to-orange-600 text-white px-4 py-4 shadow-lg">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center gap-3 mb-3">
              <div className="animate-spin flex-shrink-0">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <div className="flex-1">
                <p className="font-medium text-sm sm:text-base">
                  Upgrading to v{latestVersion}
                </p>
              </div>
              {upgradeProgress?.step > 0 && (
                <span className="text-xs font-mono bg-white bg-opacity-20 px-2 py-1 rounded">
                  Step {upgradeProgress.step}/{upgradeProgress.total_steps}
                </span>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full bg-black bg-opacity-20 rounded-full h-2.5 mb-2">
              <div
                className="bg-white h-2.5 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${upgradeProgress?.progress || 0}%` }}
              />
            </div>

            {/* Step message */}
            <p className="text-sm text-white text-opacity-90">
              {upgradeProgress?.message || 'Starting upgrade...'}
            </p>

            {/* Step timeline */}
            <div className="mt-3 space-y-1">
              {[
                { step: 1, label: 'Backing up data' },
                { step: 2, label: 'Pulling backend container' },
                { step: 3, label: 'Pulling frontend container' },
                { step: 4, label: 'Restarting services' },
                { step: 5, label: 'Running health check' },
              ].map(({ step, label }) => {
                const currentStep = upgradeProgress?.step || 0;
                const isDone = currentStep > step;
                const isActive = currentStep === step;
                return (
                  <div key={step} className="flex items-center gap-2 text-xs">
                    {isDone ? (
                      <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    ) : isActive ? (
                      <div className="w-3.5 h-3.5 flex-shrink-0 flex items-center justify-center">
                        <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                      </div>
                    ) : (
                      <div className="w-3.5 h-3.5 flex-shrink-0 flex items-center justify-center">
                        <div className="w-1.5 h-1.5 bg-white bg-opacity-40 rounded-full" />
                      </div>
                    )}
                    <span className={isDone ? 'text-white text-opacity-60 line-through' : isActive ? 'text-white font-medium' : 'text-white text-opacity-40'}>
                      {label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Upgrade completed state */}
      {upgradeStep === 'completed' && (
        <div className="bg-gradient-to-r from-green-600 to-emerald-600 dark:from-green-700 dark:to-emerald-700 text-white px-4 py-4 shadow-lg">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center gap-3 mb-3">
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <p className="font-medium text-sm sm:text-base">
                {upgradeProgress?.message || 'Upgrade complete! Refreshing...'}
              </p>
            </div>
            {/* Completed progress bar */}
            <div className="w-full bg-black bg-opacity-20 rounded-full h-2.5">
              <div
                className="bg-white h-2.5 rounded-full transition-all duration-500 ease-out"
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Upgrade error state */}
      {upgradeStep === 'error' && (
        <div className="bg-gradient-to-r from-red-600 to-rose-600 dark:from-red-700 dark:to-rose-700 text-white px-4 py-4 shadow-lg">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <p className="font-medium">Upgrade Failed</p>
                <p className="text-sm text-white text-opacity-90 mt-1">
                  {upgradeError || 'An error occurred during the upgrade. Please try again.'}
                </p>
              </div>
              <button
                onClick={handleDismissError}
                className="p-1 rounded hover:bg-white hover:bg-opacity-20 transition-colors flex-shrink-0 focus:outline-none focus:ring-2 focus:ring-white"
                aria-label="Dismiss error"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>

            <div className="flex gap-3 mt-4">
              <button
                onClick={handleDismissError}
                className="px-4 py-2 rounded text-sm font-medium bg-white bg-opacity-20 hover:bg-opacity-30 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-red-600 dark:focus:ring-offset-red-700"
              >
                Dismiss
              </button>
              <button
                onClick={() => {
                  setUpgradeStep(null);
                  setUpgradeError(null);
                  handleUpgradeClick(); // Show confirmation again to retry
                }}
                className="px-4 py-2 rounded text-sm font-medium bg-white text-red-600 dark:text-red-700 hover:bg-opacity-90 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-red-600 dark:focus:ring-offset-red-700"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Animation keyframes in style tag would go here, but we'll define it globally */}
    </div>
  );
}
