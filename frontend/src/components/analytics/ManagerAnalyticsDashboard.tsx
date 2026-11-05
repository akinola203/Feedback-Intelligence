"use client";

import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";

interface BranchOption {
  id: string;
  name: string;
}

interface AnalyticsPayload {
  summary: {
    total_feedback: number;
    average_rating: number;
  };
  sentiment: {
    positive: { count: number; percentage: number };
    neutral: { count: number; percentage: number };
    negative: { count: number; percentage: number };
  };
  rating_distribution: {
    [key: string]: { count: number; percentage: number };
  };
  branches: BranchOption[];
}

export default function ManagerAnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<string>("");
  const [datePreset, setDatePreset] = useState<string>("30");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const params: Record<string, string> = {};
      if (selectedBranch) params.branch_id = selectedBranch;

      const now = new Date();
      if (datePreset !== "all") {
        const days = parseInt(datePreset, 10);
        const startDate = new Date();
        startDate.setDate(now.getDate() - days);
        params.start_date = startDate.toISOString().split("T")[0];
        params.end_date = now.toISOString().split("T")[0];
      }

      const res = await axios.get<AnalyticsPayload>(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || ""}/api/analytics/overview/`,
        {
          params,
          withCredentials: true,
        }
      );
      setData(res.data);
    } catch {
      setError("Failed to load analytics metrics. Please ensure you are logged in.");
    } finally {
      setIsLoading(false);
    }
  }, [selectedBranch, datePreset]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  if (isLoading && !data) {
    return (
      <div className="p-8 max-w-7xl mx-auto animate-pulse space-y-6">
        <div className="h-8 bg-slate-200 rounded w-1/4 mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-28 bg-slate-200 rounded-2xl" />
          <div className="h-28 bg-slate-200 rounded-2xl" />
          <div className="h-28 bg-slate-200 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 max-w-md mx-auto text-center">
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-sm mb-4">
          {error}
        </div>
        <button
          onClick={fetchAnalytics}
          className="px-4 py-2 bg-slate-900 text-white rounded-xl text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Store Analytics</h1>
          <p className="text-slate-500 text-sm">Live customer feedback & sentiment performance</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedBranch}
            onChange={(e) => setSelectedBranch(e.target.value)}
            className="bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Assigned Branches</option>
            {data.branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>

          <select
            value={datePreset}
            onChange={(e) => setDatePreset(e.target.value)}
            className="bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
            <option value="90">Last 90 Days</option>
            <option value="all">All Time</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Total Feedback Volume</p>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {data.summary.total_feedback.toLocaleString()}
            </span>
            <span className="text-xs text-slate-500">submissions</span>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Average Customer Rating</p>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {data.summary.average_rating.toFixed(2)}
            </span>
            <span className="text-amber-500 text-lg">★</span>
            <span className="text-xs text-slate-400">/ 5.0</span>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Customer Satisfaction Rate</p>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl font-extrabold text-emerald-600">
              {data.sentiment.positive.percentage}%
            </span>
            <span className="text-xs text-slate-500">positive sentiment</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900">Sentiment Breakdown</h2>
          <div className="space-y-3">
            {[
              { label: "Positive (4–5★)", data: data.sentiment.positive, color: "bg-emerald-500", textColor: "text-emerald-700" },
              { label: "Neutral (3★)", data: data.sentiment.neutral, color: "bg-amber-400", textColor: "text-amber-700" },
              { label: "Negative (1–2★)", data: data.sentiment.negative, color: "bg-rose-500", textColor: "text-rose-700" },
            ].map((item, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs font-medium">
                  <span className="text-slate-700">{item.label}</span>
                  <span className={item.textColor}>
                    {item.data.count} ({item.data.percentage}%)
                  </span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                  <div
                    className={`${item.color} h-2.5 rounded-full transition-all duration-500`}
                    style={{ width: `${item.data.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900">Rating Distribution</h2>
          <div className="space-y-2.5">
            {["5_star", "4_star", "3_star", "2_star", "1_star"].map((key, i) => {
              const stars = 5 - i;
              const dist = data.rating_distribution[key] || { count: 0, percentage: 0 };
              return (
                <div key={key} className="flex items-center space-x-3 text-xs">
                  <span className="w-12 font-medium text-slate-600">{stars} Star</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${dist.percentage}%` }}
                    />
                  </div>
                  <span className="w-16 text-right text-slate-400">
                    {dist.count} ({dist.percentage}%)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

