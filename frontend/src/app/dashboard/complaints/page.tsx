"use client";

import React, { useState, useEffect, useCallback } from "react";
import api, { UserProfile } from "@/lib/api";

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
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high" | "urgent";
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
      setActionSuccess("Complaint status updated successfully.");
    } catch (err) {
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
      setActionSuccess("Internal note added.");
    } catch (err) {
      alert("Failed to add note.");
    } finally {
      setIsAddingNote(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "open":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-100 text-rose-800">Open</span>;
      case "in_progress":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-800">In Progress</span>;
      case "resolved":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800">Resolved</span>;
      case "closed":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-800">Closed</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-600">{status}</span>;
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-rose-600 text-white">Urgent</span>;
      case "high":
        return <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-orange-500 text-white">High</span>;
      case "medium":
        return <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-yellow-500 text-white">Med</span>;
      case "low":
        return <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-slate-300 text-slate-700">Low</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Filter */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Complaints & Escalations</h1>
          <p className="text-slate-500 text-sm">Review, investigate, and resolve escalated customer grievances</p>
        </div>

        <div className="flex items-center space-x-2 bg-white p-1 rounded-xl border border-slate-200 text-xs">
          {[
            { label: "All", value: "" },
            { label: "Open", value: "open" },
            { label: "In Progress", value: "in_progress" },
            { label: "Resolved", value: "resolved" },
            { label: "Closed", value: "closed" },
          ].map((pill) => (
            <button
              key={pill.value}
              onClick={() => setStatusFilter(pill.value)}
              className={`px-3 py-1.5 rounded-lg font-medium transition ${
                statusFilter === pill.value
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>
      </div>

      {/* Complaints List Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400 text-sm animate-pulse">
            Loading complaints data...
          </div>
        ) : complaints.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <span className="text-3xl block">🎉</span>
            <p className="text-slate-700 font-semibold text-sm">No complaints found</p>
            <p className="text-slate-400 text-xs">
              {statusFilter ? `No complaints currently marked as ${statusFilter}.` : "Your supermarket has zero open complaints!"}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold">
                <tr>
                  <th className="px-6 py-3.5">Branch & Category</th>
                  <th className="px-6 py-3.5">Rating & Feedback Snippet</th>
                  <th className="px-6 py-3.5">Priority</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Assigned To</th>
                  <th className="px-6 py-3.5">Date</th>
                  <th className="px-6 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {complaints.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => handleOpenDetail(c)}
                    className="hover:bg-slate-50/80 cursor-pointer transition"
                  >
                    <td className="px-6 py-4 font-medium text-slate-900">
                      <div>{c.branch_name}</div>
                      <div className="text-[11px] text-slate-400 font-normal">{c.feedback_category}</div>
                    </td>
                    <td className="px-6 py-4 max-w-xs">
                      <div className="flex items-center space-x-1.5 font-bold text-amber-500 mb-0.5">
                        <span>{c.feedback_rating}★</span>
                      </div>
                      <p className="text-slate-600 truncate">{c.feedback_message || "No comment provided."}</p>
                    </td>
                    <td className="px-6 py-4">{getPriorityBadge(c.priority)}</td>
                    <td className="px-6 py-4">{getStatusBadge(c.status)}</td>
                    <td className="px-6 py-4 text-slate-600">
                      {c.assigned_to_email || <span className="text-slate-400 italic">Unassigned</span>}
                    </td>
                    <td className="px-6 py-4 text-slate-400">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-indigo-600 hover:text-indigo-800 font-semibold">
                        View & Resolve →
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail & Resolution Drawer/Modal */}
      {selectedComplaint && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-xl bg-white h-full shadow-2xl p-6 sm:p-8 flex flex-col justify-between overflow-y-auto space-y-6">
            <div className="space-y-6">
              <div className="flex justify-between items-start border-b border-slate-100 pb-4">
                <div>
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                      Complaint Details
                    </span>
                    {getPriorityBadge(selectedComplaint.priority)}
                  </div>
                  <h2 className="text-xl font-bold text-slate-900">
                    {selectedComplaint.branch_name}
                  </h2>
                  <p className="text-xs text-slate-500">
                    Category: {selectedComplaint.feedback_category} • Created:{" "}
                    {new Date(selectedComplaint.created_at).toLocaleString()}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedComplaint(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 text-lg"
                >
                  ✕
                </button>
              </div>

              {actionSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 font-medium">
                  {actionSuccess}
                </div>
              )}

              {/* Feedback Quote */}
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700">Customer Review</span>
                  <span className="font-bold text-amber-500 text-sm">
                    {selectedComplaint.feedback_rating}★
                  </span>
                </div>
                <p className="text-sm text-slate-800 italic">
                  "{selectedComplaint.feedback_message || "No text submitted"}"
                </p>
              </div>

              {/* Update Status Form */}
              <form onSubmit={handleUpdateStatus} className="space-y-4 bg-white p-4 rounded-xl border border-slate-200">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Update Resolution Status
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase mb-1">
                      Status
                    </label>
                    <select
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="open">Open</option>
                      <option value="in_progress">In Progress</option>
                      <option value="resolved">Resolved</option>
                      <option value="closed">Closed</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase mb-1">
                    Resolution Summary / Corrective Action
                  </label>
                  <textarea
                    rows={2}
                    value={editSummary}
                    onChange={(e) => setEditSummary(e.target.value)}
                    placeholder="Details on corrective action taken (e.g. refund issued, cashier retrained)..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white rounded-lg text-xs font-medium transition"
                >
                  {isUpdating ? "Saving..." : "Save Resolution Status"}
                </button>
              </form>

              {/* Internal Notes Thread */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Internal Investigation Notes ({selectedComplaint.notes?.length || 0})
                </h3>

                <form onSubmit={handleAddNote} className="space-y-2">
                  <textarea
                    rows={2}
                    value={newNoteBody}
                    onChange={(e) => setNewNoteBody(e.target.value)}
                    placeholder="Add an internal note or supervisor comment..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={isAddingNote || !newNoteBody.trim()}
                    className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-lg text-xs font-medium transition"
                  >
                    {isAddingNote ? "Adding Note..." : "Add Internal Note"}
                  </button>
                </form>

                <div className="space-y-2.5 max-h-56 overflow-y-auto pr-1">
                  {(selectedComplaint.notes || []).map((note) => (
                    <div key={note.id} className="p-3 bg-slate-50 border border-slate-100 rounded-lg space-y-1">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="font-semibold text-slate-700">{note.author_email}</span>
                        <span className="text-slate-400">
                          {new Date(note.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600">{note.body}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setSelectedComplaint(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium"
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
