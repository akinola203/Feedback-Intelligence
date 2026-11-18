"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import axios from "axios";
import {
  AlertCircle,
  ArrowUpRight,
  Download,
  RefreshCw,
  Star,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

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

interface TaskDelegatedAlert {
  id: string;
  complaint_id: string;
  branch_name: string;
  sector_label: string;
  priority: string;
  assigned_to_name: string;
  delegated_by_name: string;
  note: string;
  created_at: string;
}

export default function ManagerAnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<string>("ALL");
  const [datePreset, setDatePreset] = useState<string>("30");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Real-time alert states
  const [liveAlerts, setLiveAlerts] = useState<NegativeFeedbackAlert[]>([]);
  const [delegationAlerts, setDelegationAlerts] = useState<TaskDelegatedAlert[]>([]);
  const [isExportingPDF, setIsExportingPDF] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

  const fetchAnalytics = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const params: Record<string, string> = {};
      if (selectedBranch && selectedBranch !== "ALL") params.branch_id = selectedBranch;

      const now = new Date();
      if (datePreset !== "all") {
        const days = parseInt(datePreset, 10);
        const startDate = new Date();
        startDate.setDate(now.getDate() - days);
        params.start_date = startDate.toISOString().split("T")[0];
        params.end_date = now.toISOString().split("T")[0];
      }

      const res = await axios.get<AnalyticsPayload>(`${apiBase}/api/analytics/overview/`, {
        params,
        withCredentials: true,
      });
      setData(res.data);
    } catch {
      setError("Failed to load analytics metrics. Please ensure you are logged in.");
    } finally {
      setIsLoading(false);
    }
  }, [selectedBranch, datePreset, apiBase]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  // Real-Time WebSocket Alerts Setup (30s heartbeat + 4001/4003 zombie close handling)
  useEffect(() => {
    const wsProtocol = apiBase.startsWith("https:") ? "wss:" : "ws:";
    let wsHost = "localhost:8000";

    try {
      const url = new URL(apiBase);
      wsHost = url.host;
    } catch {
      wsHost = window.location.host;
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
            if (payload.event_type === "TASK_DELEGATED") {
              setDelegationAlerts((prev) => [
                {
                  id: `${payload.complaint_id}-${Date.now()}`,
                  complaint_id: payload.complaint_id || "",
                  branch_name: payload.branch_name || "Store Branch",
                  sector_label: payload.sector_label || payload.sector || "Operations",
                  priority: payload.priority || "high",
                  assigned_to_name: payload.assigned_to_name || "Sector Manager",
                  delegated_by_name: payload.delegated_by_name || "Supervisor",
                  note: payload.note || "Please review and action this escalation.",
                  created_at: payload.created_at || new Date().toISOString(),
                },
                ...prev.slice(0, 3),
              ]);
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
  }, [fetchAnalytics, apiBase]);

  const dismissAlert = (id: string) => {
    setLiveAlerts((prev) => prev.filter((alert) => alert.id !== id));
  };

  const dismissDelegationAlert = (id: string) => {
    setDelegationAlerts((prev) => prev.filter((alert) => alert.id !== id));
  };

  const handleExportPDF = async () => {
    setIsExportingPDF(true);
    try {
      const params: Record<string, string> = {};
      if (selectedBranch && selectedBranch !== "ALL") params.branch_id = selectedBranch;
      if (datePreset !== "all") params.days = datePreset;

      const response = await axios.get(`${apiBase}/api/reports/executive-pdf/`, {
        params,
        responseType: "blob",
        withCredentials: true,
      });

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
      <div className="space-y-6">
        <div className="h-9 w-64 bg-black/[0.04] rounded-2xl animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="h-36 animate-pulse" />
          <Card className="h-36 animate-pulse" />
          <Card className="h-36 animate-pulse" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card className="p-8 max-w-md mx-auto text-center space-y-4">
        <div className="w-10 h-10 bg-black text-white rounded-2xl flex items-center justify-center mx-auto">
          <AlertCircle className="h-5 w-5" />
        </div>
        <p className="text-xs text-neutral-600 font-medium">{error}</p>
        <Button onClick={fetchAnalytics} size="sm">
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Retry Connection</span>
        </Button>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      {/* Real-time WebSocket Task Delegation Alert (Smoked Black Glass) */}
      {delegationAlerts.length > 0 && (
        <div className="space-y-3">
          {delegationAlerts.map((alert) => (
            <div
              key={alert.id}
              className="glass-smoked p-5 rounded-3xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-white shadow-2xl transition-all"
            >
              <div className="flex items-start space-x-3.5">
                <div className="relative mt-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-white block animate-ping absolute inset-0 opacity-75" />
                  <span className="w-2.5 h-2.5 rounded-full bg-white block relative" />
                </div>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="inverted">Task Delegated • {alert.priority}</Badge>
                    <span className="text-xs font-bold text-white">{alert.branch_name}</span>
                    <span className="text-xs text-neutral-400">• {alert.sector_label}</span>
                  </div>
                  <p className="text-xs font-medium text-neutral-200">
                    Assigned to <strong className="text-white">{alert.assigned_to_name}</strong> by{" "}
                    {alert.delegated_by_name}
                  </p>
                  {alert.note && (
                    <p className="text-[11px] text-neutral-300 italic">&ldquo;{alert.note}&rdquo;</p>
                  )}
                </div>
              </div>

              <div className="self-end sm:self-center flex items-center gap-2">
                <Button asChild variant="inverted" size="sm">
                  <Link href="/dashboard/complaints">
                    <span>Open Queue</span>
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => dismissDelegationAlert(alert.id)}
                  className="text-neutral-400 hover:text-white hover:bg-white/10"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Real-time WebSocket Critical Review Alert (Smoked Black Glass) */}
      {liveAlerts.length > 0 && (
        <div className="space-y-3">
          {liveAlerts.map((alert) => (
            <div
              key={alert.id}
              className="glass-smoked p-5 rounded-3xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-white shadow-2xl transition-all"
            >
              <div className="flex items-start space-x-3.5">
                <div className="relative mt-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-white block animate-ping absolute inset-0 opacity-75" />
                  <span className="w-2.5 h-2.5 rounded-full bg-white block relative" />
                </div>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="inverted">Critical Alert ({alert.rating}★)</Badge>
                    <span className="text-xs font-bold text-white">{alert.branch_name}</span>
                    <span className="text-xs text-neutral-400">• {alert.category}</span>
                  </div>
                  <p className="text-xs font-medium text-neutral-200 italic">
                    &ldquo;{alert.message}&rdquo;
                  </p>
                  <p className="text-[10px] text-neutral-400">
                    Customer: {alert.customer_name} • Received via Live Stand QR
                  </p>
                </div>
              </div>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => dismissAlert(alert.id)}
                className="self-end sm:self-center text-neutral-400 hover:text-white hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Header and shadcn Controls */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Store Intelligence
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Real-time customer feedback metrics &amp; sentiment aggregation
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
          <div className="w-48">
            <Select value={selectedBranch} onValueChange={setSelectedBranch}>
              <SelectTrigger>
                <SelectValue placeholder="All Store Locations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All Store Locations</SelectItem>
                {data.branches.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="w-40">
            <Select value={datePreset} onValueChange={setDatePreset}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 Days</SelectItem>
                <SelectItem value="30">Last 30 Days</SelectItem>
                <SelectItem value="90">Last 90 Days</SelectItem>
                <SelectItem value="all">All Time History</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Button onClick={handleExportPDF} disabled={isExportingPDF}>
            <Download className="h-3.5 w-3.5" />
            <span>{isExportingPDF ? "Generating PDF..." : "Export Executive PDF"}</span>
          </Button>
        </div>
      </div>

      {/* Bento Grid Tier 1: Hero KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="hover:shadow-lg transition">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center text-neutral-400 text-[10px] font-bold uppercase tracking-wider">
              <span>Feedback Volume</span>
              <span className="text-black font-mono">01</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-4xl font-extrabold tracking-tight text-black">
                {data.summary.total_feedback.toLocaleString()}
              </div>
              <p className="text-xs text-neutral-500 font-medium mt-1">
                Verified customer submissions
              </p>
            </div>
            <Separator />
            <div className="flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-black" />
              <span>Aggregated across active branch QR stands</span>
            </div>
          </CardContent>
        </Card>

        <Card className="hover:shadow-lg transition">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center text-neutral-400 text-[10px] font-bold uppercase tracking-wider">
              <span>Average Rating</span>
              <span className="text-black font-mono">02</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex items-baseline space-x-2">
                <span className="text-4xl font-extrabold tracking-tight text-black">
                  {data.summary.average_rating.toFixed(2)}
                </span>
                <Star className="h-5 w-5 fill-black text-black self-center" />
                <span className="text-xs text-neutral-400 font-mono">/ 5.0</span>
              </div>
              <p className="text-xs text-neutral-500 font-medium mt-1">
                Overall customer satisfaction index
              </p>
            </div>
            <Separator />
            <div className="flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-black" />
              <span>Reflects service, pricing, and product freshness</span>
            </div>
          </CardContent>
        </Card>

        <Card className="hover:shadow-lg transition">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center text-neutral-400 text-[10px] font-bold uppercase tracking-wider">
              <span>Satisfaction Rate</span>
              <span className="text-black font-mono">03</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-4xl font-extrabold tracking-tight text-black">
                {data.sentiment.positive.percentage}%
              </div>
              <p className="text-xs text-neutral-500 font-medium mt-1">
                Share of positive reviews (4–5★)
              </p>
            </div>
            <Separator />
            <div className="flex items-center space-x-2 text-[11px] text-neutral-600 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-black" />
              <span>Target benchmark: 85.0% or above</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bento Grid Tier 2: Sentiment Breakdown & Rating Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Sentiment Distribution</CardTitle>
                <CardDescription className="mt-1">
                  Categorized by customer star rating thresholds
                </CardDescription>
              </div>
              <span className="text-xs font-mono font-bold text-neutral-400">04</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
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
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Rating Spread</CardTitle>
                <CardDescription className="mt-1">
                  Granular 1 to 5 star frequency breakdown
                </CardDescription>
              </div>
              <span className="text-xs font-mono font-bold text-neutral-400">05</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3.5">
            {[
              { key: "5_star", stars: 5, color: "bg-black" },
              { key: "4_star", stars: 4, color: "bg-neutral-800" },
              { key: "3_star", stars: 3, color: "bg-neutral-500" },
              { key: "2_star", stars: 2, color: "bg-neutral-700" },
              { key: "1_star", stars: 1, color: "bg-neutral-900 striped-bar-negative" },
            ].map(({ key, stars, color }) => {
              const dist = data.rating_distribution[key] || { count: 0, percentage: 0 };
              return (
                <div key={key} className="flex items-center space-x-3 text-xs">
                  <div className="w-12 font-bold text-black flex items-center gap-1">
                    <span>{stars}</span>
                    <Star className="h-3 w-3 fill-neutral-400 text-neutral-400" />
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
