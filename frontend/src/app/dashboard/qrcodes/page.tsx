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
        message: `High-resolution PNG QR stand for "${branch.name}" downloaded successfully.`,
      });
    } catch {
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
      `⚠️ Revocation Warning: Are you sure you want to rotate the QR code for "${branch.name}"?\n\nThe existing printed QR stand in the supermarket will immediately become invalid and stop accepting feedback.`
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
        message: `Active QR token rotated successfully for "${branch.name}". Download and print the new stand below.`,
      });
    } catch {
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
        <h1 className="text-3xl font-extrabold tracking-tight text-black">
          Branch QR Code Stands
        </h1>
        <p className="text-xs text-neutral-500 font-medium mt-0.5">
          Generate high-resolution printable QR codes for store customer scan stands and rotate tokens securely
        </p>
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

      {lastRotated && (
        <div className="glass-panel p-6 rounded-3xl space-y-2 border border-white/90 shadow-md">
          <div className="flex items-center space-x-2 text-black font-extrabold text-sm">
            <span>✨</span>
            <span>New Active QR Token Generated</span>
          </div>
          <p className="text-xs text-neutral-700">
            Active Token:{" "}
            <code className="bg-black text-white px-2.5 py-0.5 rounded-lg font-mono font-bold text-[11px]">
              {lastRotated.token}
            </code>
          </p>
          <p className="text-xs text-neutral-600">
            Direct Customer Scan URL:{" "}
            <a
              href={lastRotated.scanUrl}
              target="_blank"
              rel="noreferrer"
              className="text-black underline font-bold hover:text-neutral-600"
            >
              {lastRotated.scanUrl} ↗
            </a>
          </p>
        </div>
      )}

      <div className="glass-panel rounded-3xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.04)] border border-white/80">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-neutral-400 font-semibold animate-pulse">
            Loading assigned branches...
          </div>
        ) : branches.length === 0 ? (
          <div className="p-12 text-center text-xs text-neutral-400">
            No assigned supermarket branches found for your account.
          </div>
        ) : (
          <div className="divide-y divide-black/[0.04]">
            {branches.map((b) => (
              <div
                key={b.id}
                className="p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 hover:bg-white/80 transition duration-150"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2.5">
                    <span className="w-8 h-8 rounded-xl bg-black text-white flex items-center justify-center text-xs font-bold shadow-sm">
                      QR
                    </span>
                    <h3 className="text-base font-extrabold tracking-tight text-black">{b.name}</h3>
                    <span
                      className={`text-[9px] uppercase font-black px-2.5 py-0.5 rounded-full border ${
                        b.is_active
                          ? "bg-black text-white border-black"
                          : "bg-neutral-100 text-neutral-400 border-neutral-200"
                      }`}
                    >
                      {b.is_active ? "Active Stand" : "Inactive"}
                    </span>
                  </div>
                  <p className="text-[11px] text-neutral-400 font-mono">Branch ID: {b.id}</p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => handleDownloadQR(b)}
                    disabled={downloadingBranchId === b.id}
                    className="flex items-center space-x-2 px-4 py-2.5 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white rounded-2xl text-xs font-bold shadow-lg hover:-translate-y-0.5 active:scale-95 transition"
                  >
                    <span>📥</span>
                    <span>
                      {downloadingBranchId === b.id ? "Generating..." : "Download Printable PNG"}
                    </span>
                  </button>

                  <button
                    onClick={() => handleRotateQR(b)}
                    disabled={rotatingBranchId === b.id}
                    className="flex items-center space-x-1.5 px-3.5 py-2.5 bg-white/70 hover:bg-white text-black border border-black/20 hover:border-black rounded-2xl text-xs font-bold transition active:scale-95 shadow-sm"
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
