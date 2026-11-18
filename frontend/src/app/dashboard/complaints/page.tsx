"use client";

import React, { useState, useEffect, useCallback } from "react";
import api, { UserProfile } from "@/lib/api";

interface ComplaintNote {
  id: string;
  author_email: string;
  author_name?: string;
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
  sector: string;
  sector_label: string;
  status: "new" | "reviewed" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high" | "urgent";
  assigned_to?: string | null;
  assigned_to_email?: string | null;
  assigned_to_name?: string | null;
  created_by_email?: string | null;
  delegated_by?: string | null;
  delegated_by_email?: string | null;
  delegated_by_name?: string | null;
  delegated_at?: string | null;
  due_at?: string | null;
  resolved_at?: string | null;
  resolution_summary?: string | null;
  created_at: string;
  notes: ComplaintNote[];
}

interface DelegateMember {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  branch_id: string;
  branch_name: string;
  sector: string;
  sector_label: string;
  is_sector_lead: boolean;
}

const SECTORS = [
  { value: "", label: "All Sectors" },
  { value: "GENERAL", label: "General Store Operations" },
  { value: "POS_CASHIER", label: "Front-End POS & Cashiers" },
  { value: "BAKERY_PRODUCE", label: "Bakery & Fresh Produce" },
  { value: "COLD_CHAIN_MEAT", label: "Cold Chain, Dairy & Butchery" },
  { value: "GROCERY_STOCK", label: "Grocery, Aisles & Shelf Stocking" },
  { value: "CUSTOMER_SERVICE", label: "Customer Service & Returns" },
  { value: "FACILITY_SECURITY", label: "Facility, Hygiene & Security" },
];

export default function ComplaintsPage() {
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sectorFilter, setSectorFilter] = useState<string>("");
  const [assignedToMe, setAssignedToMe] = useState<boolean>(false);
  const [selectedComplaint, setSelectedComplaint] = useState<Complaint | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  // Delegation state
  const [branchDelegates, setBranchDelegates] = useState<DelegateMember[]>([]);
  const [isLoadingDelegates, setIsLoadingDelegates] = useState<boolean>(false);
  const [delegateSector, setDelegateSector] = useState<string>("GENERAL");
  const [delegateAssigneeId, setDelegateAssigneeId] = useState<string>("");
  const [delegatePriority, setDelegatePriority] = useState<string>("high");
  const [delegateDueAt, setDelegateDueAt] = useState<string>("");
  const [delegateDirective, setDelegateDirective] = useState<string>("");
  const [isDelegating, setIsDelegating] = useState<boolean>(false);

  // Notes & status edit state
  const [newNoteBody, setNewNoteBody] = useState<string>("");
  const [isAddingNote, setIsAddingNote] = useState<boolean>(false);
  const [editStatus, setEditStatus] = useState<string>("");
  const [editSummary, setEditSummary] = useState<string>("");
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<UserProfile>("/api/auth/me/")
      .then((res) => setCurrentUser(res.data))
      .catch(() => {});
  }, []);

  const fetchComplaints = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      if (sectorFilter) params.sector = sectorFilter;
      if (assignedToMe) params.assigned_to_me = "true";

      const res = await api.get<{ results: Complaint[] } | Complaint[]>("/api/complaints/", { params });
      const data = Array.isArray(res.data) ? res.data : res.data.results || [];
      setComplaints(data);
    } catch (err) {
      console.error("Failed to load complaints:", err);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, sectorFilter, assignedToMe]);

  useEffect(() => {
    fetchComplaints();
  }, [fetchComplaints]);

  const fetchBranchDelegates = async (branchId: string) => {
    setIsLoadingDelegates(true);
    try {
      const res = await api.get<{ delegates: DelegateMember[] }>("/api/complaints/delegates/", {
        params: { branch_id: branchId },
      });
      setBranchDelegates(res.data.delegates || []);
    } catch (err) {
      console.error("Failed to load branch delegates:", err);
      setBranchDelegates([]);
    } finally {
      setIsLoadingDelegates(false);
    }
  };

  const handleOpenDetail = (complaint: Complaint) => {
    setSelectedComplaint(complaint);
    setEditStatus(complaint.status);
    setEditSummary(complaint.resolution_summary || "");
    setDelegateSector(complaint.sector || "GENERAL");
    setDelegateAssigneeId(complaint.assigned_to || "");
    setDelegatePriority(complaint.priority || "high");
    setDelegateDueAt(
      complaint.due_at ? new Date(complaint.due_at).toISOString().slice(0, 16) : ""
    );
    setDelegateDirective("");
    setActionSuccess(null);
    setActionError(null);
    fetchBranchDelegates(complaint.branch);
  };

  const handleDelegateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedComplaint || !delegateAssigneeId) return;
    setIsDelegating(true);
    setActionSuccess(null);
    setActionError(null);

    try {
      const payload: Record<string, unknown> = {
        assigned_to_id: delegateAssigneeId,
        sector: delegateSector,
        priority: delegatePriority,
        note: delegateDirective.trim(),
      };
      if (delegateDueAt) {
        payload.due_at = new Date(delegateDueAt).toISOString();
      }

      const res = await api.post<Complaint>(
        `/api/complaints/${selectedComplaint.id}/delegate/`,
        payload
      );

      setSelectedComplaint(res.data);
      setEditStatus(res.data.status);
      setComplaints((prev) => prev.map((c) => (c.id === res.data.id ? res.data : c)));
      setDelegateDirective("");
      setActionSuccess(
        `Task delegated to ${res.data.assigned_to_name || res.data.assigned_to_email} (${res.data.sector_label}).`
      );
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.assigned_to_id?.[0] ||
        err.response?.data?.error ||
        "Failed to delegate complaint. Verify branch permissions.";
      setActionError(String(detail));
    } finally {
      setIsDelegating(false);
    }
  };

  const handleUpdateStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedComplaint) return;
    setIsUpdating(true);
    setActionSuccess(null);
    setActionError(null);

    try {
      const res = await api.patch<Complaint>(`/api/complaints/${selectedComplaint.id}/`, {
        status: editStatus,
        resolution_summary: editSummary.trim() || null,
      });

      setSelectedComplaint(res.data);
      setComplaints((prev) => prev.map((c) => (c.id === res.data.id ? res.data : c)));
      setActionSuccess("Resolution status updated.");
    } catch {
      setActionError("Failed to update complaint status. Please try again.");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedComplaint || !newNoteBody.trim()) return;
    setIsAddingNote(true);
    setActionError(null);

    try {
      const res = await api.post<ComplaintNote>(`/api/complaints/${selectedComplaint.id}/notes/`, {
        body: newNoteBody.trim(),
      });

      const updatedComplaint = {
        ...selectedComplaint,
        notes: [...(selectedComplaint.notes || []), res.data],
      };
      setSelectedComplaint(updatedComplaint);
      setComplaints((prev) => prev.map((c) => (c.id === updatedComplaint.id ? updatedComplaint : c)));
      setNewNoteBody("");
      setActionSuccess("Internal investigation note attached.");
    } catch {
      setActionError("Failed to append note.");
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
            Open
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

  // Strict Monochrome Priority Badges
  const renderPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 text-[9px] font-black rounded-md uppercase tracking-wider bg-black text-white shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            <span>Urgent</span>
          </span>
        );
      case "high":
        return (
          <span className="px-2 py-0.5 text-[9px] font-extrabold rounded-md uppercase tracking-wider bg-neutral-800 text-white">
            High
          </span>
        );
      case "medium":
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded-md uppercase tracking-wider bg-neutral-200 text-neutral-800 border border-neutral-300">
            Medium
          </span>
        );
      case "low":
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded-md uppercase tracking-wider bg-white/80 border border-black/25 text-neutral-600">
            Low
          </span>
        );
      default:
        return null;
    }
  };

  // Sort delegates so matching sector leads appear first
  const sortedDelegates = [...branchDelegates].sort((a, b) => {
    const aMatches = a.sector === delegateSector ? 1 : 0;
    const bMatches = b.sector === delegateSector ? 1 : 0;
    if (aMatches !== bMatches) return bMatches - aMatches;
    if (a.is_sector_lead !== b.is_sector_lead) return a.is_sector_lead ? -1 : 1;
    return a.full_name.localeCompare(b.full_name);
  });

  const canDelegate = currentUser && currentUser.role !== "staff";

  return (
    <div className="space-y-6">
      {/* Editorial Header */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Complaints & Sector Delegation
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Route department escalations to branch sector leads, track SLAs, and close customer grievances
          </p>
        </div>

        {/* Queue Toggle: All Branch Tasks vs Assigned to Me */}
        <div className="glass-well p-1 rounded-2xl flex items-center space-x-1">
          <button
            onClick={() => setAssignedToMe(false)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all duration-150 ${
              !assignedToMe
                ? "bg-black text-white shadow-sm"
                : "text-neutral-600 hover:text-black hover:bg-white/60"
            }`}
          >
            All Branch Tasks
          </button>
          <button
            onClick={() => setAssignedToMe(true)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all duration-150 ${
              assignedToMe
                ? "bg-black text-white shadow-sm"
                : "text-neutral-600 hover:text-black hover:bg-white/60"
            }`}
          >
            Assigned to Me
          </button>
        </div>
      </div>

      {/* Filter Toolbar (Sector Dropdown + Status Pills) */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div className="glass-well p-1 rounded-2xl flex items-center">
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="bg-transparent border-none text-xs font-bold text-black px-3 py-1.5 focus:outline-none cursor-pointer"
          >
            {SECTORS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <div className="glass-well p-1 rounded-2xl flex flex-wrap items-center gap-1">
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
            Loading department escalations...
          </div>
        ) : complaints.length === 0 ? (
          <div className="p-16 text-center space-y-2">
            <span className="text-3xl block">✓</span>
            <p className="text-sm font-extrabold text-black">No Matching Escalations</p>
            <p className="text-xs text-neutral-400">
              {assignedToMe
                ? "You have no delegated complaints matching these filters."
                : "All complaints for the selected sector and status are clear."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-black/[0.02] border-b border-black/[0.06] text-neutral-400 uppercase tracking-wider font-bold text-[10px]">
                <tr>
                  <th className="px-6 py-4">Branch & Sector</th>
                  <th className="px-6 py-4">Customer Review</th>
                  <th className="px-6 py-4">Priority</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Sector Assignee</th>
                  <th className="px-6 py-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04]">
                {complaints.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => handleOpenDetail(c)}
                    className="hover:bg-white/80 cursor-pointer transition duration-150 group"
                  >
                    <td className="px-6 py-4 space-y-1">
                      <div className="font-bold text-black">{c.branch_name}</div>
                      <span className="inline-block px-2 py-0.5 text-[10px] font-bold rounded-md bg-black/[0.04] border border-black/10 text-neutral-800">
                        {c.sector_label || c.sector}
                      </span>
                    </td>
                    <td className="px-6 py-4 max-w-xs">
                      <div className="flex items-center space-x-2 mb-0.5">
                        <span className="font-extrabold text-black">{c.feedback_rating}★</span>
                        <span className="text-[11px] text-neutral-400">{c.feedback_category}</span>
                      </div>
                      <p className="text-neutral-600 truncate font-medium">
                        {c.feedback_message || "No comment provided."}
                      </p>
                    </td>
                    <td className="px-6 py-4">{renderPriorityBadge(c.priority)}</td>
                    <td className="px-6 py-4">{renderStatusBadge(c.status)}</td>
                    <td className="px-6 py-4 space-y-0.5">
                      <div className="font-bold text-black text-xs">
                        {c.assigned_to_name || c.assigned_to_email || (
                          <span className="text-neutral-400 font-normal italic">Unassigned</span>
                        )}
                      </div>
                      {c.delegated_by_name && (
                        <div className="text-[10px] text-neutral-400">
                          Delegated by {c.delegated_by_name}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-black font-bold group-hover:underline">
                        Delegate / Resolve →
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
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
                      Escalation Ticket
                    </span>
                    {renderPriorityBadge(selectedComplaint.priority)}
                    {renderStatusBadge(selectedComplaint.status)}
                  </div>
                  <h2 className="text-2xl font-extrabold tracking-tight text-black">
                    {selectedComplaint.branch_name}
                  </h2>
                  <p className="text-xs text-neutral-500 font-medium">
                    Sector: <span className="font-bold text-black">{selectedComplaint.sector_label}</span> •{" "}
                    {selectedComplaint.feedback_category}
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

              {actionError && (
                <div className="p-3.5 bg-black/[0.05] border border-black/30 rounded-2xl text-xs font-bold text-black">
                  ! {actionError}
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
                <div className="pt-2 border-t border-black/[0.06] flex flex-wrap justify-between gap-2 text-[10px] text-neutral-500">
                  <span>
                    Owner:{" "}
                    <strong className="text-black">
                      {selectedComplaint.assigned_to_name || "Unassigned"}
                    </strong>
                  </span>
                  {selectedComplaint.delegated_by_name && (
                    <span>
                      Delegated by <strong className="text-black">{selectedComplaint.delegated_by_name}</strong>
                    </span>
                  )}
                </div>
              </div>

              {/* Delegate to Sector Manager Panel */}
              {canDelegate && (
                <form
                  onSubmit={handleDelegateTask}
                  className="glass-panel p-5 rounded-2xl space-y-4 border border-white/90 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-extrabold text-black uppercase tracking-wider">
                      Delegate to Sector Manager
                    </h3>
                    <span className="text-[10px] font-mono text-neutral-400">
                      {branchDelegates.length} branch personnel
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                        Target Sector
                      </label>
                      <select
                        value={delegateSector}
                        onChange={(e) => setDelegateSector(e.target.value)}
                        className="w-full glass-input rounded-xl px-3 py-2.5 text-xs font-semibold"
                      >
                        {SECTORS.filter((s) => s.value !== "").map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                        Priority
                      </label>
                      <select
                        value={delegatePriority}
                        onChange={(e) => setDelegatePriority(e.target.value)}
                        className="w-full glass-input rounded-xl px-3 py-2.5 text-xs font-semibold"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="urgent">Urgent</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                      Sector Manager / Assignee
                    </label>
                    <select
                      required
                      value={delegateAssigneeId}
                      onChange={(e) => setDelegateAssigneeId(e.target.value)}
                      disabled={isLoadingDelegates}
                      className="w-full glass-input rounded-xl px-3 py-2.5 text-xs font-semibold"
                    >
                      <option value="" disabled>
                        {isLoadingDelegates
                          ? "Loading branch sector roster..."
                          : "Select sector manager or staff..."}
                      </option>
                      {sortedDelegates.map((m) => (
                        <option key={`${m.user_id}-${m.branch_id}`} value={m.user_id}>
                          {m.full_name} — {m.sector_label}
                          {m.is_sector_lead ? " (Lead)" : ""}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                      Target SLA Deadline <span className="font-normal text-neutral-400">(optional)</span>
                    </label>
                    <input
                      type="datetime-local"
                      value={delegateDueAt}
                      onChange={(e) => setDelegateDueAt(e.target.value)}
                      className="w-full glass-input rounded-xl px-3 py-2 text-xs font-medium"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-neutral-600 uppercase tracking-wider mb-1">
                      Delegation Directive
                    </label>
                    <textarea
                      rows={2}
                      value={delegateDirective}
                      onChange={(e) => setDelegateDirective(e.target.value)}
                      placeholder="e.g. Inspect cold room thermometer on Aisle 4 and follow up with customer..."
                      className="w-full glass-input rounded-xl p-3 text-xs placeholder-neutral-400"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isDelegating || !delegateAssigneeId}
                    className="w-full py-3 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white rounded-2xl text-xs font-bold shadow-lg hover:-translate-y-0.5 active:scale-[0.99] transition duration-200"
                  >
                    {isDelegating ? "Delegating Task..." : "Delegate Task"}
                  </button>
                </form>
              )}

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
                    <option value="reviewed">Reviewed</option>
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
                    placeholder="Document resolution steps taken (e.g. refund processed, chiller recalibrated)..."
                    className="w-full glass-input rounded-xl p-3 text-xs placeholder-neutral-400"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-5 py-2.5 bg-neutral-900 hover:bg-black disabled:bg-neutral-300 text-white rounded-xl text-xs font-bold transition shadow-md active:scale-95"
                >
                  {isUpdating ? "Saving..." : "Commit Status Change"}
                </button>
              </form>

              {/* Internal Notes Timeline */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-black uppercase tracking-wider">
                  Delegation & Investigation Timeline ({selectedComplaint.notes?.length || 0})
                </h3>

                <form onSubmit={handleAddNote} className="space-y-2">
                  <textarea
                    rows={2}
                    value={newNoteBody}
                    onChange={(e) => setNewNoteBody(e.target.value)}
                    placeholder="Add an internal update or supervisor comment..."
                    className="w-full glass-input rounded-xl p-3 text-xs placeholder-neutral-400"
                  />
                  <button
                    type="submit"
                    disabled={isAddingNote || !newNoteBody.trim()}
                    className="px-4 py-2 bg-white hover:bg-neutral-100 disabled:bg-neutral-100 disabled:text-neutral-400 text-black border border-black/25 rounded-xl text-xs font-bold transition"
                  >
                    {isAddingNote ? "Attaching..." : "Attach Note"}
                  </button>
                </form>

                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {(selectedComplaint.notes || []).map((note) => (
                    <div key={note.id} className="p-3.5 glass-well rounded-xl space-y-1">
                      <div className="flex justify-between items-center text-[10px]">
                        <span className="font-bold text-black">
                          {note.author_name || note.author_email}
                        </span>
                        <span className="text-neutral-400 font-mono">
                          {new Date(note.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-700 leading-relaxed">{note.body}</p>
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
