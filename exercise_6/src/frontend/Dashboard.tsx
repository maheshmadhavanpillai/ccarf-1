/**
 * Dashboard component — follows .claude/rules/frontend.md:
 * - Functional component with hooks
 * - TanStack Query for server state
 * - Zustand for client state
 * - Tailwind CSS for styling
 * - Accessibility: keyboard nav, ARIA labels
 */

import React, { useState } from 'react';

// Types (would normally be generated from OpenAPI)
interface MetricPoint {
  timestamp: string;
  value: number;
  dimension: string | null;
}

interface DashboardData {
  workspace_id: string;
  metrics: MetricPoint[];
  cursor: string | null;
  has_more: boolean;
}

interface DashboardProps {
  workspaceId: string;
  defaultMetric?: string;
}

// Component
export function Dashboard({ workspaceId, defaultMetric = 'page_views' }: DashboardProps) {
  const [selectedMetric, setSelectedMetric] = useState(defaultMetric);
  const [period, setPeriod] = useState<7 | 30 | 90>(7);

  // In real code: const { data, isLoading, isError } = useQuery(...)
  const isLoading = false;
  const isError = false;
  const data: DashboardData = {
    workspace_id: workspaceId,
    metrics: [
      { timestamp: '2024-01-15T10:00:00Z', value: 42.5, dimension: selectedMetric },
      { timestamp: '2024-01-15T11:00:00Z', value: 55.2, dimension: selectedMetric },
    ],
    cursor: null,
    has_more: false,
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64" role="status">
        <span className="sr-only">Loading dashboard data...</span>
        <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4" role="alert">
        <p className="text-red-800 dark:text-red-200">Failed to load dashboard data. Please try again.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Metric selector */}
      <div className="flex gap-2" role="tablist" aria-label="Metric selection">
        {['page_views', 'clicks', 'sessions'].map((metric) => (
          <button
            key={metric}
            role="tab"
            aria-selected={selectedMetric === metric}
            onClick={() => setSelectedMetric(metric)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${selectedMetric === metric
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
          >
            {metric.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Period selector */}
      <div className="flex gap-2" role="group" aria-label="Time period">
        {([7, 30, 90] as const).map((days) => (
          <button
            key={days}
            onClick={() => setPeriod(days)}
            aria-pressed={period === days}
            className={`px-3 py-1 rounded text-xs ${
              period === days ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900' : 'bg-gray-200 dark:bg-gray-700'
            }`}
          >
            {days}d
          </button>
        ))}
      </div>

      {/* Metrics display */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.metrics.map((point, idx) => (
          <div key={idx} className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">{point.dimension}</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{point.value}</p>
            <p className="text-xs text-gray-400">{new Date(point.timestamp).toLocaleString()}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
