"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
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

interface NegativeFeedbackAlert {
  id: string;
  branch_name: string;
  category: string;
  rating: number;
  message: string;
  customer_name: string;
  created_at: string;
}

export default function ManagerAnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<string>("");
  const [datePreset, setDatePreset] = useState<string>("30");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Real-time alert states
  const [liveAlerts, setLiveAlerts] = useState<NegativeFeedbackAlert[]>([]);
  const [isExportingPDF, setIsExportingPDF] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);

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

  // Real-Time WebSocket Alerts Setup
  useEffect(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    let wsHost = window.location.host;

    try {
      if (process.env.NEXT_PUBLIC_API_BASE_URL) {
        const url = new URL(process.env.NEXT_PUBLIC_API_BASE_URL);
        wsHost = url.host;
      }
    } catch {
      // fallback
    }

    const wsUrl = `${wsProtocol}//${wsHost}/ws/alerts/manager/`;
    let socket: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;
    let heartbeatInterval: ReturnType<typeof setInterval>;

    const connectWebSocket = () => {
      try {
        socket = new WebSocket(wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          clearInterval(heartbeatInterval);
          heartbeatInterval = setInterval(() => {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "ping" }));
            }
          }, 30000);
        };

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === "pong") {
              return;
            }
            if (payload.rating && payload.rating <= 2) {
              setLiveAlerts((prev) => [
                {
                  id: payload.id || String(Date.now()),
                  branch_name: payload.branch_name || "Unknown Branch",
                  category: payload.category || "General",
                  rating: payload.rating,
                  message: payload.message || "No comment provided",
                  customer_name: payload.customer_name || "Anonymous",
                  created_at: payload.created_at || new Date().toISOString(),
                },
                ...prev.slice(0, 4),
              ]);
              fetchAnalytics();
            }
          } catch (e) {
            console.error("Failed to parse WebSocket alert message:", e);
          }
        };

        socket.onclose = (event) => {
          clearInterval(heartbeatInterval);
          // Do not reconnect if server closed due to unauthenticated (4001) or revoked session (4003)
          if (event.code !== 4001 && event.code !== 4003) {
            reconnectTimeout = setTimeout(connectWebSocket, 5000);
          }
        };

        socket.onerror = (err) => {
          console.warn("WebSocket connection error:", err);
          socket?.close();
        };
      } catch (e) {
        console.warn("Could not initiate WebSocket:", e);
      }
    };

    connectWebSocket();

    return () => {
      clearTimeout(reconnectTimeout);
      clearInterval(heartbeatInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [fetchAnalytics]);

  const dismissAlert = (id: string) => {
    setLiveAlerts((prev) => prev.filter((alert) => alert.id !== id));
  };

  const handleExportPDF = async () => {
    setIsExportingPDF(true);
    try {
      const params: Record<string, string> = {};
      if (selectedBranch) params.branch_id = selectedBranch;
      if (datePreset !== "all") params.days = datePreset;

      const response = await axios.get(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || ""}/api/reports/executive-pdf/`,
        {
          params,
          responseType: "blob",
          withCredentials: true,
        }
      );

      const blob = new Blob([response.data], { type: "application/pdf" });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      const todayStr = new Date().toISOString().split("T")[0];
      link.setAttribute("download", `Executive_Feedback_Report_${todayStr}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch {
      alert("Failed to generate executive PDF report. Please verify your permissions and try again.");
    } finally {
      setIsExportingPDF(false);
    }
  };

  if (isLoading && !data) {
    return (
      <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
        <div className="h-9 w-64 bg-black/[0.04] rounded-2xl animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-36 glass-panel rounded-3xl animate-pulse" />
          <div className="h-36 glass-panel rounded-3xl animate-pulse" />
          <div className="h-36 glass-panel rounded-3xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 max-w-md mx-auto text-center glass-panel rounded-3xl space-y-4">
        <div className="w-10 h-10 bg-black text-white rounded-xl flex items-center justify-center mx-auto text-base font-bold">
          !
        </div>
        <p className="text-xs text-neutral-600 font-medium">{error}</p>
        <button
          onClick={fetchAnalytics}
          className="px-5 py-2.5 bg-black hover:bg-neutral-800 text-white rounded-2xl text-xs font-semibold shadow transition"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Real-time WebSocket Critical Review Alert (Smoked Black Glass) */}
      {liveAlerts.length > 0 && (
        <div className="space-y-3">
          {liveAlerts.map((alert) => (
            <div
              key={alert.id}
              className="glass-smoked p-5 rounded-3xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-white/20 text-white shadow-2xl transition-all"
            >
              <div className="flex items-start space-x-3.5">
                <div className="relative mt-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-white block animate-ping absolute inset-0 opacity-75" />
                  <span className="w-2.5 h-2.5 rounded-full bg-white block relative" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="bg-white text-black font-extrabold text-[10px] uppercase tracking-wider px-2 py-0.5 rounded">
                      Critical Alert ({alert.rating}★)
                    </span>
                    <span className="text-xs font-bold text-white">{alert.branch_name}</span>
                    <span className="text-xs text-neutral-400">• {alert.category}</span>
                  </div>
                  <p className="text-xs font-medium text-neutral-200 italic">
                    "{alert.message}"
                  </p>
                  <p className="text-[10px] text-neutral-400">
                    Customer: {alert.customer_name} • Received via Live Stand QR
                  </p>
                </div>
              </div>

              <button
                onClick={() => dismissAlert(alert.id)}
                className="self-end sm:self-center text-xs font-semibold text-neutral-400 hover:text-white px-3 py-1.5 rounded-xl border border-white/10 hover:border-white/30 transition"
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Header and Filter Controls */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Store Intelligence
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Real-time customer feedback metrics & sentiment aggregation
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Branch Filter Glass Well */}
          <div className="glass-well p-1 rounded-2xl flex items-center">
            <select
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              className="bg-transparent border-none text-xs font-semibold text-black px-3 py-1.5 focus:outline-none cursor-pointer"
            >
              <option value="">All Store Locations</option>
              {data.branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>

          {/* Date Filter Glass Well */}
          <div className="glass-well p-1 rounded-2xl flex items-center">
            <select
              value={datePreset}
              onChange={(e) => setDatePreset(e.target.value)}
              className="bg-transparent border-none text-xs font-semibold text-black px-3 py-1.5 focus:outline-none cursor-pointer"
            >
              <option value="7">Last 7 Days</option>
              <option value="30">Last 30 Days</option>
              <option value="90">Last 90 Days</option>
              <option value="all">All Time History</option>
            </select>
          </div>

          {/* Smoked Black Glass PDF Export Button */}
          <button
            onClick={handleExportPDF}
            disabled={isExportingPDF}
            className="flex items-center space-x-2 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white px-4 py-2.5 rounded-2xl text-xs font-bold shadow-xl hover:-translate-y-0.5 active:scale-[0.99] transition duration-200"
          >
            <span>↓</span>
            <span>{isExportingPDF ? "Generating PDF..." : "Export Executive PDF"}</span>
          </button>
        </div>
      </div>

      {/* Bento Grid Analytics Showcase */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Bento Card 1: Volume */}
        <div className="glass-panel p-7 rounded-3xl space-y-4 hover:shadow-lg transition">
          <div className="flex justify-between items-center text-neutral-400 text-xs font-bold uppercase tracking-wider">
            <span>Feedback Volume</span>
            <span className="text-black font-mono">01</span>
          </div>
          <div>
            <div className="text-4xl font-extrabold tracking-tight text-black">
              {data.summary.total_feedback.toLocaleString()}
            </div>
            <p className="text-xs text-neutral-500 font-medium mt-1">Verified customer submissions</p>
          </div>
          <div className="pt-2 border-t border-black/[0.06] flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-black" />
            <span>Aggregated across active branch QR stands</span>
          </div>
        </div>

        {/* Bento Card 2: Rating */}
        <div className="glass-panel p-7 rounded-3xl space-y-4 hover:shadow-lg transition">
          <div className="flex justify-between items-center text-neutral-400 text-xs font-bold uppercase tracking-wider">
            <span>Average Rating</span>
            <span className="text-black font-mono">02</span>
          </div>
          <div>
            <div className="flex items-baseline space-x-2">
              <span className="text-4xl font-extrabold tracking-tight text-black">
                {data.summary.average_rating.toFixed(2)}
              </span>
              <span className="text-lg text-black font-bold">★</span>
              <span className="text-xs text-neutral-400 font-mono">/ 5.0</span>
            </div>
            <p className="text-xs text-neutral-500 font-medium mt-1">Overall customer satisfaction index</p>
          </div>
          <div className="pt-2 border-t border-black/[0.06] flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-black" />
            <span>Reflects service, pricing, and product freshness</span>
          </div>
        </div>

        {/* Bento Card 3: Satisfaction */}
        <div className="glass-panel p-7 rounded-3xl space-y-4 hover:shadow-lg transition">
          <div className="flex justify-between items-center text-neutral-400 text-xs font-bold uppercase tracking-wider">
            <span>Satisfaction Rate</span>
            <span className="text-black font-mono">03</span>
          </div>
          <div>
            <div className="text-4xl font-extrabold tracking-tight text-black">
              {data.sentiment.positive.percentage}%
            </div>
            <p className="text-xs text-neutral-500 font-medium mt-1">Share of positive reviews (4–5★)</p>
          </div>
          <div className="pt-2 border-t border-black/[0.06] flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-black" />
            <span>Target benchmark: 85.0% or above</span>
          </div>
        </div>
      </div>

      {/* Bento Grid Tier 2: Sentiment Breakdown & Rating Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Sentiment Breakdown Card */}
        <div className="glass-panel p-7 sm:p-8 rounded-3xl space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-extrabold tracking-tight text-black">
                Sentiment Distribution
              </h2>
              <p className="text-xs text-neutral-500">Categorized by customer star rating thresholds</p>
            </div>
            <span className="text-xs font-mono font-bold text-neutral-400">04</span>
          </div>

          <div className="space-y-4">
            {/* Positive */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold">
                <span className="text-black">Positive Experience (4–5★)</span>
                <span className="text-black font-mono">
                  {data.sentiment.positive.count} ({data.sentiment.positive.percentage}%)
                </span>
              </div>
              <div className="w-full bg-black/[0.05] rounded-full h-2.5 overflow-hidden p-0.5">
                <div
                  className="bg-black h-full rounded-full transition-all duration-700"
                  style={{ width: `${data.sentiment.positive.percentage}%` }}
                />
              </div>
            </div>

            {/* Neutral */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold">
                <span className="text-neutral-700">Neutral Experience (3★)</span>
                <span className="text-neutral-700 font-mono">
                  {data.sentiment.neutral.count} ({data.sentiment.neutral.percentage}%)
                </span>
              </div>
              <div className="w-full bg-black/[0.05] rounded-full h-2.5 overflow-hidden p-0.5">
                <div
                  className="bg-neutral-500 h-full rounded-full transition-all duration-700"
                  style={{ width: `${data.sentiment.neutral.percentage}%` }}
                />
              </div>
            </div>

            {/* Negative (High contrast striped dark charcoal) */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold">
                <span className="text-neutral-900">Negative Grievances (1–2★)</span>
                <span className="text-neutral-900 font-mono">
                  {data.sentiment.negative.count} ({data.sentiment.negative.percentage}%)
                </span>
              </div>
              <div className="w-full bg-black/[0.05] rounded-full h-2.5 overflow-hidden p-0.5">
                <div
                  className="striped-bar-negative h-full rounded-full transition-all duration-700"
                  style={{ width: `${data.sentiment.negative.percentage}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Rating Distribution Card */}
        <div className="glass-panel p-7 sm:p-8 rounded-3xl space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-extrabold tracking-tight text-black">
                Rating Spread
              </h2>
              <p className="text-xs text-neutral-500">Granular 1 to 5 star frequency breakdown</p>
            </div>
            <span className="text-xs font-mono font-bold text-neutral-400">05</span>
          </div>

          <div className="space-y-3.5">
            {[
              { key: "5_star", stars: 5, color: "bg-black" },
              { key: "4_star", stars: 4, color: "bg-neutral-800" },
              { key: "3_star", stars: 3, color: "bg-neutral-600" },
              { key: "2_star", stars: 2, color: "bg-neutral-400" },
              { key: "1_star", stars: 1, color: "bg-neutral-900 striped-bar-negative" },
            ].map(({ key, stars, color }) => {
              const dist = data.rating_distribution[key] || { count: 0, percentage: 0 };
              return (
                <div key={key} className="flex items-center space-x-3 text-xs">
                  <div className="w-14 font-bold text-black flex items-center space-x-1">
                    <span>{stars}</span>
                    <span className="text-neutral-400">★</span>
                  </div>
                  <div className="flex-1 bg-black/[0.05] rounded-full h-2 overflow-hidden">
                    <div
                      className={`${color} h-2 rounded-full transition-all duration-700`}
                      style={{ width: `${dist.percentage}%` }}
                    />
                  </div>
                  <div className="w-20 text-right font-mono text-[11px] text-neutral-600">
                    <span className="font-bold text-black">{dist.count}</span>{" "}
                    <span className="text-neutral-400">({dist.percentage}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
