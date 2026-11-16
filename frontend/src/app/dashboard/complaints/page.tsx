"use client";

import React, { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

interface ComplaintNote {
  id: string;
  author_email: string;
  body: string;
  created_at: string;
}

interface Complaint {
  id: string;
  feedback: string;
  feedback_rating: number;
  feedback_message: string;
  feedback_category: string;
  branch: string;
  branch_name: string;
  status: "new" | "reviewed" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high";
  assigned_to?: string | null;
  assigned_to_email?: string | null;
  created_by_email: string;
  resolved_at?: string | null;
  resolution_summary?: string | null;
  created_at: string;
  notes: ComplaintNote[];
}

export default function ComplaintsPage() {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedComplaint, setSelectedComplaint] = useState<Complaint | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [newNoteBody, setNewNoteBody] = useState<string>("");
  const [isAddingNote, setIsAddingNote] = useState<boolean>(false);
  const [editStatus, setEditStatus] = useState<string>("");
  const [editSummary, setEditSummary] = useState<string>("");
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const fetchComplaints = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;

      const res = await api.get<{ results: Complaint[] } | Complaint[]>("/api/complaints/", { params });
      const data = Array.isArray(res.data) ? res.data : res.data.results || [];
      setComplaints(data);
    } catch (err) {
      console.error("Failed to load complaints:", err);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchComplaints();
  }, [fetchComplaints]);

  const handleOpenDetail = (complaint: Complaint) => {
    setSelectedComplaint(complaint);
    setEditStatus(complaint.status);
    setEditSummary(complaint.resolution_summary || "");
    setActionSuccess(null);
  };

  const handleUpdateStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedComplaint) return;
    setIsUpdating(true);
    setActionSuccess(null);

    try {
      const res = await api.patch<Complaint>(`/api/complaints/${selectedComplaint.id}/`, {
        status: editStatus,
        resolution_summary: editSummary.trim() || null,
      });

      setSelectedComplaint(res.data);
      setComplaints((prev) => prev.map((c) => (c.id === res.data.id ? res.data : c)));
      setActionSuccess("Status updated successfully.");
    } catch {
      alert("Failed to update complaint status. Please try again.");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedComplaint || !newNoteBody.trim()) return;
    setIsAddingNote(true);

    try {
      const res = await api.post<ComplaintNote>(`/api/complaints/${selectedComplaint.id}/notes/`, {
        body: newNoteBody.trim(),
      });

      const updatedComplaint = {
        ...selectedComplaint,
        notes: [res.data, ...(selectedComplaint.notes || [])],
      };
      setSelectedComplaint(updatedComplaint);
      setComplaints((prev) => prev.map((c) => (c.id === updatedComplaint.id ? updatedComplaint : c)));
      setNewNoteBody("");
      setActionSuccess("Internal investigation note attached.");
    } catch {
      alert("Failed to append note.");
    } finally {
      setIsAddingNote(false);
    }
  };

  // Strict Monochrome Status Badges
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "new":
      case "open":
        return (
          <span className="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider rounded-md bg-black text-white shadow-sm">
            Open / New
          </span>
        );
      case "in_progress":
      case "reviewed":
        return (
          <span className="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider rounded-md bg-neutral-200 text-neutral-800 border border-neutral-300">
            In Progress
          </span>
        );
      case "resolved":
        return (
          <span className="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider rounded-md bg-white border border-black text-black">
            Resolved
          </span>
        );
      case "closed":
        return (
          <span className="px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider rounded-md bg-neutral-100 text-neutral-400 border border-neutral-200">
            Closed
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 text-[10px] font-bold rounded-md bg-neutral-100 text-neutral-600">
            {status}
          </span>
        );
    }
  };

  const renderPriorityBadge = (priority: string) => {
    switch (priority) {
      case "high":
        return <span className="px-2 py-0.5 text-[9px] font-black rounded uppercase bg-black text-white">High</span>;
      case "medium":
        return <span className="px-2 py-0.5 text-[9px] font-bold rounded uppercase bg-neutral-200 text-neutral-700">Med</span>;
      case "low":
        return <span className="px-2 py-0.5 text-[9px] font-bold rounded uppercase border border-neutral-300 text-neutral-500">Low</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Editorial Header & Filter Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Complaints Resolution
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Triage, investigate, and close customer dissatisfaction tickets
          </p>
        </div>

        {/* Status Filter Glass Well */}
        <div className="glass-well p-1 rounded-2xl flex items-center space-x-1">
          {[
            { label: "All", value: "" },
            { label: "New", value: "new" },
            { label: "In Progress", value: "in_progress" },
            { label: "Resolved", value: "resolved" },
            { label: "Closed", value: "closed" },
          ].map((pill) => (
            <button
              key={pill.value}
              onClick={() => setStatusFilter(pill.value)}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all duration-150 ${
                statusFilter === pill.value
                  ? "bg-black text-white shadow-sm"
                  : "text-neutral-600 hover:text-black hover:bg-white/60"
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>
      </div>

      {/* Complaints List Panel */}
      <div className="glass-panel rounded-3xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.04)] border border-white/80">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-neutral-400 font-semibold animate-pulse">
            Loading active complaints registry...
          </div>
        ) : complaints.length === 0 ? (
          <div className="p-16 text-center space-y-2">
            <span className="text-3xl block">✓</span>
            <p className="text-sm font-extrabold text-black">No Active Escalations</p>
            <p className="text-xs text-neutral-400">
              {statusFilter ? `No complaints match the filter '${statusFilter}'.` : "All customer complaints are currently resolved."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-black/[0.02] border-b border-black/[0.06] text-neutral-400 uppercase tracking-wider font-bold text-[10px]">
                <tr>
                  <th className="px-6 py-4">Branch & Category</th>
                  <th className="px-6 py-4">Customer Review</th>
                  <th className="px-6 py-4">Priority</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Assigned Staff</th>
                  <th className="px-6 py-4">Date</th>
                  <th className="px-6 py-4 text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04]">
                {complaints.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => handleOpenDetail(c)}
                    className="hover:bg-white/80 cursor-pointer transition duration-150 group"
                  >
                    <td className="px-6 py-4 font-bold text-black">
                      <div>{c.branch_name}</div>
                      <div className="text-[11px] text-neutral-400 font-normal">{c.feedback_category}</div>
                    </td>
                    <td className="px-6 py-4 max-w-xs">
                      <div className="flex items-center space-x-1 font-extrabold text-black mb-0.5">
                        <span>{c.feedback_rating}★</span>
                      </div>
                      <p className="text-neutral-600 truncate font-medium">
                        {c.feedback_message || "No comment provided."}
                      </p>
                    </td>
                    <td className="px-6 py-4">{renderPriorityBadge(c.priority)}</td>
                    <td className="px-6 py-4">{renderStatusBadge(c.status)}</td>
                    <td className="px-6 py-4 font-mono text-[11px] text-neutral-600">
                      {c.assigned_to_email || <span className="text-neutral-300 italic">Unassigned</span>}
                    </td>
                    <td className="px-6 py-4 text-neutral-400 font-mono text-[11px]">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-black font-bold group-hover:underline">
                        Details →
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Slide-Over Drawer: Frosted White Glass Panel Deep */}
      {selectedComplaint && (
        <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm flex justify-end transition-all">
          <div className="w-full max-w-xl glass-panel-deep h-full p-6 sm:p-8 flex flex-col justify-between overflow-y-auto space-y-6 shadow-2xl border-l border-white">
            <div className="space-y-6">
              <div className="flex justify-between items-start border-b border-black/[0.06] pb-4">
                <div>
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
                      Resolution Ticket
                    </span>
                    {renderPriorityBadge(selectedComplaint.priority)}
                  </div>
                  <h2 className="text-2xl font-extrabold tracking-tight text-black">
                    {selectedComplaint.branch_name}
                  </h2>
                  <p className="text-xs text-neutral-500 font-medium">
                    Category: {selectedComplaint.feedback_category} • Created:{" "}
                    {new Date(selectedComplaint.created_at).toLocaleString()}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedComplaint(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-xl bg-black/[0.04] hover:bg-black/10 text-black text-sm font-bold transition"
                >
                  ✕
                </button>
              </div>

              {actionSuccess && (
                <div className="p-3.5 bg-black text-white rounded-2xl text-xs font-semibold shadow-md">
                  ✓ {actionSuccess}
                </div>
              )}

              {/* Feedback Well */}
              <div className="glass-well p-5 rounded-2xl space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-black uppercase tracking-wider text-[11px]">
                    Customer Submission
                  </span>
                  <span className="font-black text-black text-sm">
                    {selectedComplaint.feedback_rating}★
                  </span>
                </div>
                <p className="text-xs text-neutral-700 italic leading-relaxed">
                  "{selectedComplaint.feedback_message || "No text submitted"}"
                </p>
              </div>

              {/* Status Update Form */}
              <form onSubmit={handleUpdateStatus} className="glass-panel p-5 rounded-2xl space-y-4 border border-white/80">
                <h3 className="text-xs font-bold text-black uppercase tracking-wider">
                  Update Resolution Workflow
                </h3>
                <div>
                  <label className="block text-[11px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                    Status
                  </label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full glass-input rounded-xl px-3.5 py-2.5 text-xs font-semibold"
                  >
                    <option value="new">New / Open</option>
                    <option value="in_progress">In Progress</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                    Corrective Action Summary
                  </label>
                  <textarea
                    rows={2}
                    value={editSummary}
                    onChange={(e) => setEditSummary(e.target.value)}
                    placeholder="Document resolution steps taken (e.g. refund processed, staff retrained)..."
                    className="w-full glass-input rounded-xl p-3 text-xs placeholder-neutral-400"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-5 py-2.5 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white rounded-xl text-xs font-bold transition shadow-md active:scale-95"
                >
                  {isUpdating ? "Saving..." : "Commit Status Change"}
                </button>
              </form>

              {/* Internal Notes Thread */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-black uppercase tracking-wider">
                  Internal Investigation Log ({selectedComplaint.notes?.length || 0})
                </h3>

                <form onSubmit={handleAddNote} className="space-y-2">
                  <textarea
                    rows={2}
                    value={newNoteBody}
                    onChange={(e) => setNewNoteBody(e.target.value)}
                    placeholder="Add an internal investigation note or supervisor feedback..."
                    className="w-full glass-input rounded-xl p-3 text-xs placeholder-neutral-400"
                  />
                  <button
                    type="submit"
                    disabled={isAddingNote || !newNoteBody.trim()}
                    className="px-4 py-2 bg-neutral-900 hover:bg-black disabled:bg-neutral-200 disabled:text-neutral-400 text-white rounded-xl text-xs font-bold transition shadow"
                  >
                    {isAddingNote ? "Attaching..." : "Attach Internal Note"}
                  </button>
                </form>

                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {(selectedComplaint.notes || []).map((note) => (
                    <div key={note.id} className="p-3.5 glass-well rounded-xl space-y-1">
                      <div className="flex justify-between items-center text-[10px]">
                        <span className="font-bold text-black font-mono">{note.author_email}</span>
                        <span className="text-neutral-400">
                          {new Date(note.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-700">{note.body}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-black/[0.06] flex justify-end">
              <button
                onClick={() => setSelectedComplaint(null)}
                className="px-5 py-2.5 bg-black/[0.05] hover:bg-black/10 text-black rounded-xl text-xs font-bold transition"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
