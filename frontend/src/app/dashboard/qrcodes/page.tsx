"use client";

import React, { useState, useEffect } from "react";
import api, { Branch, UserProfile } from "@/lib/api";

interface RotatedTokenInfo {
  branchId: string;
  token: string;
  scanUrl: string;
}

export default function QRCodesPage() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [downloadingBranchId, setDownloadingBranchId] = useState<string | null>(null);
  const [rotatingBranchId, setRotatingBranchId] = useState<string | null>(null);
  const [lastRotated, setLastRotated] = useState<RotatedTokenInfo | null>(null);
  const [notification, setNotification] = useState<{ type: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    api
      .get<UserProfile>("/api/auth/me/")
      .then((res) => {
        setBranches(res.data.branches || []);
      })
      .catch((err) => {
        console.error("Failed to load branches:", err);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const handleDownloadQR = async (branch: Branch) => {
    setDownloadingBranchId(branch.id);
    setNotification(null);

    try {
      const response = await api.get(`/api/feedback/qr/download/${branch.id}/`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "image/png" });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.setAttribute("download", `QR_${branch.name.replace(/\s+/g, "_")}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setNotification({
        type: "success",
        message: `Printable PNG QR code for "${branch.name}" downloaded successfully.`,
      });
    } catch (err: any) {
      setNotification({
        type: "error",
        message: "Failed to download QR code image. Please check your branch permissions.",
      });
    } finally {
      setDownloadingBranchId(null);
    }
  };

  const handleRotateQR = async (branch: Branch) => {
    const confirmed = window.confirm(
      `⚠️ Warning: Are you sure you want to rotate the QR code for "${branch.name}"?\n\nThe existing printed QR code in the store will immediately become invalid and stop accepting feedback.`
    );
    if (!confirmed) return;

    setRotatingBranchId(branch.id);
    setNotification(null);

    try {
      const res = await api.post<{ token: string; scan_url: string; message: string }>(
        `/api/feedback/qr/rotate/${branch.id}/`
      );

      setLastRotated({
        branchId: branch.id,
        token: res.data.token,
        scanUrl: res.data.scan_url,
      });

      setNotification({
        type: "success",
        message: `QR code token rotated successfully for "${branch.name}". Download and print the new QR code below.`,
      });
    } catch (err: any) {
      setNotification({
        type: "error",
        message: "Failed to rotate QR code. Please verify your permissions.",
      });
    } finally {
      setRotatingBranchId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Branch QR Code Management</h1>
        <p className="text-slate-500 text-sm">
          Download high-resolution printable QR codes for customer scan stands and rotate tokens securely
        </p>
      </div>

      {notification && (
        <div
          className={`p-4 rounded-xl text-xs font-medium border ${
            notification.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"
          }`}
        >
          {notification.message}
        </div>
      )}

      {lastRotated && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-5 space-y-2">
          <div className="flex items-center space-x-2 text-indigo-900 font-bold text-sm">
            <span>✨</span>
            <span>New Active QR Token Generated</span>
          </div>
          <p className="text-xs text-indigo-700">
            Active Token: <code className="bg-white px-2 py-0.5 rounded font-mono font-bold">{lastRotated.token}</code>
          </p>
          <p className="text-xs text-indigo-700">
            Direct Scan URL:{" "}
            <a
              href={lastRotated.scanUrl}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 underline font-medium hover:text-indigo-800"
            >
              {lastRotated.scanUrl} ↗
            </a>
          </p>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400 text-sm animate-pulse">
            Loading assigned branches...
          </div>
        ) : branches.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No assigned supermarket branches found for your account.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {branches.map((b) => (
              <div
                key={b.id}
                className="p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 hover:bg-slate-50/60 transition"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-lg">🏪</span>
                    <h3 className="text-base font-bold text-slate-900">{b.name}</h3>
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                        b.is_active
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {b.is_active ? "Active Branch" : "Inactive"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 font-mono">Branch ID: {b.id}</p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => handleDownloadQR(b)}
                    disabled={downloadingBranchId === b.id}
                    className="flex items-center space-x-1.5 px-4 py-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white rounded-xl text-xs font-semibold shadow-sm transition"
                  >
                    <span>📥</span>
                    <span>
                      {downloadingBranchId === b.id ? "Downloading..." : "Download Printable QR"}
                    </span>
                  </button>

                  <button
                    onClick={() => handleRotateQR(b)}
                    disabled={rotatingBranchId === b.id}
                    className="flex items-center space-x-1.5 px-3.5 py-2 bg-white hover:bg-rose-50 text-rose-700 hover:text-rose-800 border border-rose-200 rounded-xl text-xs font-semibold transition"
                  >
                    <span>🔄</span>
                    <span>
                      {rotatingBranchId === b.id ? "Rotating..." : "Rotate QR Token"}
                    </span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
