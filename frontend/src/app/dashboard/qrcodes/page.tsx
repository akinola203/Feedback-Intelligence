"use client";

import React, { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

interface BranchQRItem {
  branch_id: string;
  branch_name: string;
  is_active: boolean;
  qr_id: string | null;
  token: string | null;
  scan_url: string | null;
  created_at: string | null;
}

export default function QRCodesPage() {
  const [branches, setBranches] = useState<BranchQRItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [downloadingBranchId, setDownloadingBranchId] = useState<string | null>(null);
  const [rotatingBranchId, setRotatingBranchId] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchBranchQRCodes = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.get<{ branches: BranchQRItem[] }>("/api/feedback/qr/branches/");
      setBranches(res.data.branches || []);
    } catch (err) {
      console.error("Failed to load branch QR codes:", err);
      setNotification({
        type: "error",
        message: "Unable to load branch QR codes. Please verify your session.",
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBranchQRCodes();
  }, [fetchBranchQRCodes]);

  const handleDownloadQR = async (branch: BranchQRItem) => {
    setDownloadingBranchId(branch.branch_id);
    setNotification(null);

    try {
      const response = await api.get(`/api/feedback/qr/download/${branch.branch_id}/`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "image/png" });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.setAttribute("download", `QR_${branch.branch_name.replace(/\s+/g, "_")}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setNotification({
        type: "success",
        message: `High-resolution PNG QR stand for "${branch.branch_name}" downloaded.`,
      });
    } catch {
      setNotification({
        type: "error",
        message: "Failed to download QR code image. Please ensure an active token exists.",
      });
    } finally {
      setDownloadingBranchId(null);
    }
  };

  const handleRotateQR = async (branch: BranchQRItem) => {
    const confirmed = window.confirm(
      `Revocation Warning: Rotate the QR code for "${branch.branch_name}"?\n\nThe currently printed QR stand will immediately stop accepting customer feedback.`
    );
    if (!confirmed) return;

    setRotatingBranchId(branch.branch_id);
    setNotification(null);

    try {
      const res = await api.post<{
        id: string;
        token: string;
        scan_url: string;
        created_at: string;
        message: string;
      }>(`/api/feedback/qr/rotate/${branch.branch_id}/`);

      // Atomically update this branch card's active token and timestamp in place
      setBranches((prev) =>
        prev.map((item) =>
          item.branch_id === branch.branch_id
            ? {
                ...item,
                qr_id: res.data.id,
                token: res.data.token,
                scan_url: res.data.scan_url,
                created_at: res.data.created_at,
              }
            : item
        )
      );

      setNotification({
        type: "success",
        message: `Active QR token rotated atomically for "${branch.branch_name}".`,
      });
    } catch {
      setNotification({
        type: "error",
        message: "Failed to rotate QR code. Please verify your branch permissions.",
      });
    } finally {
      setRotatingBranchId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Branch QR Code Stands
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Inspect active store tokens, preview customer scan portals, download printable PNGs, and rotate tokens atomically
          </p>
        </div>

        <button
          onClick={fetchBranchQRCodes}
          className="px-4 py-2 bg-white/70 hover:bg-white text-black border border-black/15 hover:border-black rounded-2xl text-xs font-bold transition shadow-sm"
        >
          Refresh Stands
        </button>
      </div>

      {notification && (
        <div
          className={`p-4 rounded-2xl text-xs font-bold border transition ${
            notification.type === "success"
              ? "bg-black text-white border-black shadow-md"
              : "bg-white text-black border-black/30"
          }`}
        >
          {notification.message}
        </div>
      )}

      {/* Bento Grid of Branch QR Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="h-56 glass-panel rounded-3xl animate-pulse" />
          <div className="h-56 glass-panel rounded-3xl animate-pulse" />
        </div>
      ) : branches.length === 0 ? (
        <div className="glass-panel rounded-3xl p-12 text-center text-xs text-neutral-500 font-medium">
          No assigned supermarket branches found for your account.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {branches.map((branch, index) => (
            <div
              key={branch.branch_id}
              className="glass-panel p-6 sm:p-7 rounded-3xl flex flex-col justify-between space-y-5 hover:shadow-lg transition duration-200 border border-white/85"
            >
              {/* Card Header */}
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-3">
                    <span className="w-9 h-9 rounded-2xl bg-black text-white flex items-center justify-center text-xs font-black shadow-sm">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h2 className="text-lg font-extrabold tracking-tight text-black leading-tight">
                        {branch.branch_name}
                      </h2>
                      <p className="text-[10px] text-neutral-400 font-mono">
                        ID: {branch.branch_id}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`text-[9px] uppercase font-black tracking-wider px-2.5 py-1 rounded-full border ${
                      branch.token
                        ? "bg-black text-white border-black"
                        : "bg-neutral-100 text-neutral-500 border-neutral-300"
                    }`}
                  >
                    {branch.token ? "Active QR" : "No Token"}
                  </span>
                </div>
              </div>

              {/* Active Token Well */}
              <div className="glass-well p-4 rounded-2xl space-y-2">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-neutral-500">
                  <span>Active Stand Token</span>
                  {branch.created_at && (
                    <span className="font-mono text-neutral-400">
                      Issued {new Date(branch.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                {branch.token ? (
                  <>
                    <code className="block text-[11px] font-mono font-bold text-black bg-white/80 px-3 py-2 rounded-xl border border-black/10 truncate">
                      {branch.token}
                    </code>
                    <div className="flex items-center justify-between pt-1">
                      <a
                        href={`/scan/${branch.token}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-bold text-black underline hover:text-neutral-600 transition"
                      >
                        Preview Customer Scan Portal ↗
                      </a>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-neutral-500 italic">
                    No active QR token issued yet. Click Rotate QR Token to generate one.
                  </p>
                )}
              </div>

              {/* Action Controls */}
              <div className="flex flex-wrap items-center gap-3 pt-1">
                <button
                  onClick={() => handleDownloadQR(branch)}
                  disabled={downloadingBranchId === branch.branch_id || !branch.token}
                  className="flex-1 min-w-[160px] flex items-center justify-center space-x-2 px-4 py-2.5 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white rounded-2xl text-xs font-bold shadow-lg hover:-translate-y-0.5 active:scale-[0.99] transition duration-200"
                >
                  <span>↓</span>
                  <span>
                    {downloadingBranchId === branch.branch_id
                      ? "Generating..."
                      : "Download Printable QR (PNG)"}
                  </span>
                </button>

                <button
                  onClick={() => handleRotateQR(branch)}
                  disabled={rotatingBranchId === branch.branch_id}
                  className="px-4 py-2.5 bg-white/75 hover:bg-white text-black border border-black/20 hover:border-black rounded-2xl text-xs font-bold transition active:scale-[0.99] shadow-sm"
                >
                  {rotatingBranchId === branch.branch_id ? "Rotating..." : "Rotate QR Token"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
