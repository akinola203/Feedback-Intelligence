"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  QrCode,
  RefreshCw,
} from "lucide-react";

import api from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
  const [confirmRotateBranch, setConfirmRotateBranch] = useState<BranchQRItem | null>(null);
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

  const handleConfirmRotate = async () => {
    if (!confirmRotateBranch) return;
    const branch = confirmRotateBranch;
    setConfirmRotateBranch(null);
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

        <Button variant="outline" size="sm" onClick={fetchBranchQRCodes}>
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Refresh Stands</span>
        </Button>
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

      {/* Bento Grid of shadcn Branch QR Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="h-56 animate-pulse" />
          <Card className="h-56 animate-pulse" />
        </div>
      ) : branches.length === 0 ? (
        <Card className="p-12 text-center text-xs text-neutral-500 font-medium">
          No assigned supermarket branches found for your account.
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {branches.map((branch, index) => (
            <Card
              key={branch.branch_id}
              className="flex flex-col justify-between hover:shadow-lg transition duration-200"
            >
              <CardHeader className="pb-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-3">
                    <span className="w-9 h-9 rounded-2xl bg-black text-white flex items-center justify-center text-xs font-black shadow-sm">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <CardTitle className="text-lg">{branch.branch_name}</CardTitle>
                      <p className="text-[10px] text-neutral-400 font-mono mt-0.5">
                        ID: {branch.branch_id}
                      </p>
                    </div>
                  </div>
                  <Badge variant={branch.token ? "default" : "muted"}>
                    <QrCode className="h-3 w-3" />
                    <span>{branch.token ? "Active QR" : "No Token"}</span>
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="pb-4">
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
                      <div className="pt-1">
                        <a
                          href={`/scan/${branch.token}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 text-xs font-bold text-black underline hover:text-neutral-600 transition"
                        >
                          <span>Preview Customer Scan Portal</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-neutral-500 italic">
                      No active QR token issued yet. Rotate token to generate one.
                    </p>
                  )}
                </div>
              </CardContent>

              <CardFooter className="flex flex-wrap items-center gap-3">
                <Button
                  onClick={() => handleDownloadQR(branch)}
                  disabled={downloadingBranchId === branch.branch_id || !branch.token}
                  className="flex-1 min-w-[160px]"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>
                    {downloadingBranchId === branch.branch_id
                      ? "Generating..."
                      : "Download Printable QR"}
                  </span>
                </Button>

                <Button
                  variant="outline"
                  onClick={() => setConfirmRotateBranch(branch)}
                  disabled={rotatingBranchId === branch.branch_id}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>
                    {rotatingBranchId === branch.branch_id ? "Rotating..." : "Rotate Token"}
                  </span>
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* Radix Confirmation Dialog for Atomic QR Token Rotation */}
      <Dialog
        open={confirmRotateBranch !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmRotateBranch(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <div className="w-10 h-10 rounded-2xl bg-black text-white flex items-center justify-center mb-2">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <DialogTitle>Rotate Branch QR Token?</DialogTitle>
            <DialogDescription>
              You are about to atomically revoke the active QR code for{" "}
              <strong className="text-black">{confirmRotateBranch?.branch_name}</strong> and issue a
              new cryptographic token. Any printed store stands using the old code will immediately
              stop accepting submissions.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setConfirmRotateBranch(null)}>
              Cancel
            </Button>
            <Button onClick={handleConfirmRotate}>
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Revoke & Rotate Token</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
