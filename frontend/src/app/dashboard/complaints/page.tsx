"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Clock,
  Send,
  ShieldAlert,
  Star,
  UserCheck,
  Users,
} from "lucide-react";

import api, { UserProfile } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

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
  const [queueTab, setQueueTab] = useState<"all" | "mine">("all");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [sectorFilter, setSectorFilter] = useState<string>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL");
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
  const [editStatus, setEditStatus] = useState<string>("new");
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
      if (statusFilter !== "ALL") params.status = statusFilter;
      if (sectorFilter !== "ALL") params.sector = sectorFilter;
      if (priorityFilter !== "ALL") params.priority = priorityFilter;
      if (queueTab === "mine") params.assigned_to_me = "true";

      const res = await api.get<{ results: Complaint[] } | Complaint[]>("/api/complaints/", {
        params,
      });
      const data = Array.isArray(res.data) ? res.data : res.data.results || [];
      setComplaints(data);
    } catch (err) {
      console.error("Failed to load complaints:", err);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, sectorFilter, priorityFilter, queueTab]);

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
        `Delegated to ${res.data.assigned_to_name || res.data.assigned_to_email} (${res.data.sector_label}).`
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

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "new":
      case "open":
        return <Badge variant="default">Open</Badge>;
      case "in_progress":
      case "reviewed":
        return <Badge variant="medium">In Progress</Badge>;
      case "resolved":
        return <Badge variant="outline">Resolved</Badge>;
      case "closed":
        return <Badge variant="muted">Closed</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const renderPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return <Badge variant="urgent">Urgent</Badge>;
      case "high":
        return <Badge variant="high">High</Badge>;
      case "medium":
        return <Badge variant="medium">Medium</Badge>;
      case "low":
        return <Badge variant="outline">Low</Badge>;
      default:
        return null;
    }
  };

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
      {/* Header & shadcn Tabs */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-black">
            Complaints & Sector Delegation
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Route department escalations to branch sector leads, track SLAs, and close customer grievances
          </p>
        </div>

        <Tabs
          value={queueTab}
          onValueChange={(v) => setQueueTab(v as "all" | "mine")}
        >
          <TabsList>
            <TabsTrigger value="all" className="gap-1.5">
              <Users className="h-3.5 w-3.5" />
              <span>All Branch Tasks</span>
            </TabsTrigger>
            <TabsTrigger value="mine" className="gap-1.5">
              <UserCheck className="h-3.5 w-3.5" />
              <span>Assigned to Me</span>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Filter Toolbar (shadcn Select dropdowns for Sector, Priority, Status) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Select value={sectorFilter} onValueChange={setSectorFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Filter by sector" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Store Sectors</SelectItem>
            {SECTORS.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={priorityFilter} onValueChange={setPriorityFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Filter by priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Priorities</SelectItem>
            <SelectItem value="urgent">Urgent</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger>
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Statuses</SelectItem>
            <SelectItem value="open">Open / New</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Complaints Table inside Frosted Glass shadcn Card */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-neutral-400 font-semibold animate-pulse">
            Loading department escalations...
          </div>
        ) : complaints.length === 0 ? (
          <div className="p-16 text-center space-y-2">
            <CheckCircle2 className="h-8 w-8 text-black mx-auto" />
            <p className="text-sm font-extrabold text-black">No Matching Escalations</p>
            <p className="text-xs text-neutral-500">
              {queueTab === "mine"
                ? "You have no delegated complaints matching these filters."
                : "All complaints for the selected sector, priority, and status are clear."}
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Branch & Sector</TableHead>
                <TableHead>Customer Review</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Sector Assignee</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {complaints.map((c) => (
                <TableRow
                  key={c.id}
                  onClick={() => handleOpenDetail(c)}
                  className="cursor-pointer group"
                >
                  <TableCell className="space-y-1.5">
                    <div className="font-bold text-black">{c.branch_name}</div>
                    <Badge variant="secondary" className="normal-case font-bold tracking-normal">
                      {c.sector_label || c.sector}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="inline-flex items-center gap-0.5 font-extrabold text-black">
                        {c.feedback_rating}
                        <Star className="h-3 w-3 fill-black text-black" />
                      </span>
                      <span className="text-[11px] text-neutral-400">{c.feedback_category}</span>
                    </div>
                    <p className="text-neutral-600 truncate font-medium">
                      {c.feedback_message || "No comment provided."}
                    </p>
                  </TableCell>
                  <TableCell>{renderPriorityBadge(c.priority)}</TableCell>
                  <TableCell>{renderStatusBadge(c.status)}</TableCell>
                  <TableCell className="space-y-0.5">
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
                  </TableCell>
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-1 text-black font-bold group-hover:underline">
                      <span>Inspect</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Slide-Over Inspection & Delegation Sheet (shadcn/ui Radix Sheet) */}
      <Sheet
        open={selectedComplaint !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedComplaint(null);
        }}
      >
        <SheetContent>
          {selectedComplaint && (
            <div className="space-y-6 pb-8">
              <SheetHeader>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
                    Escalation Ticket
                  </span>
                  {renderPriorityBadge(selectedComplaint.priority)}
                  {renderStatusBadge(selectedComplaint.status)}
                </div>
                <SheetTitle>{selectedComplaint.branch_name}</SheetTitle>
                <SheetDescription>
                  Sector: <strong className="text-black">{selectedComplaint.sector_label}</strong> •{" "}
                  {selectedComplaint.feedback_category}
                </SheetDescription>
              </SheetHeader>

              <Separator />

              {actionSuccess && (
                <div className="p-3.5 bg-black text-white rounded-2xl text-xs font-semibold shadow-md flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  <span>{actionSuccess}</span>
                </div>
              )}

              {actionError && (
                <div className="p-3.5 bg-black/[0.05] border border-black/30 rounded-2xl text-xs font-bold text-black flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span>{actionError}</span>
                </div>
              )}

              {/* Feedback Well */}
              <div className="glass-well p-5 rounded-2xl space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-black uppercase tracking-wider text-[10px]">
                    Customer Submission
                  </span>
                  <span className="inline-flex items-center gap-1 font-black text-black text-sm">
                    {selectedComplaint.feedback_rating}
                    <Star className="h-3.5 w-3.5 fill-black text-black" />
                  </span>
                </div>
                <p className="text-xs text-neutral-700 italic leading-relaxed">
                  &ldquo;{selectedComplaint.feedback_message || "No text submitted"}&rdquo;
                </p>
                <Separator />
                <div className="flex flex-wrap justify-between gap-2 text-[10px] text-neutral-500">
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
                  {selectedComplaint.due_at && (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      SLA: {new Date(selectedComplaint.due_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Delegate to Sector Manager shadcn Card */}
              {canDelegate && (
                <Card className="rounded-2xl shadow-sm">
                  <CardHeader className="p-5 pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xs uppercase tracking-wider flex items-center gap-1.5">
                        <ClipboardList className="h-3.5 w-3.5" />
                        <span>Delegate to Sector Manager</span>
                      </CardTitle>
                      <span className="text-[10px] font-mono text-neutral-400">
                        {branchDelegates.length} personnel
                      </span>
                    </div>
                    <CardDescription>
                      Assign department ownership, priority, and SLA instructions
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="p-5 pt-2">
                    <form onSubmit={handleDelegateTask} className="space-y-4">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label>Target Sector</Label>
                          <Select value={delegateSector} onValueChange={setDelegateSector}>
                            <SelectTrigger>
                              <SelectValue placeholder="Select sector" />
                            </SelectTrigger>
                            <SelectContent>
                              {SECTORS.map((s) => (
                                <SelectItem key={s.value} value={s.value}>
                                  {s.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        <div className="space-y-1.5">
                          <Label>Priority</Label>
                          <Select value={delegatePriority} onValueChange={setDelegatePriority}>
                            <SelectTrigger>
                              <SelectValue placeholder="Select priority" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="low">Low</SelectItem>
                              <SelectItem value="medium">Medium</SelectItem>
                              <SelectItem value="high">High</SelectItem>
                              <SelectItem value="urgent">Urgent</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <Label>Sector Manager / Assignee</Label>
                        <Select
                          value={delegateAssigneeId}
                          onValueChange={setDelegateAssigneeId}
                          disabled={isLoadingDelegates}
                        >
                          <SelectTrigger>
                            <SelectValue
                              placeholder={
                                isLoadingDelegates
                                  ? "Loading branch roster..."
                                  : "Select sector manager or staff..."
                              }
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {sortedDelegates.map((m) => (
                              <SelectItem key={`${m.user_id}-${m.branch_id}`} value={m.user_id}>
                                {m.full_name} — {m.sector_label}
                                {m.is_sector_lead ? " (Lead)" : ""}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-1.5">
                        <Label>
                          SLA Deadline{" "}
                          <span className="font-normal text-neutral-400 normal-case">(optional)</span>
                        </Label>
                        <Input
                          type="datetime-local"
                          value={delegateDueAt}
                          onChange={(e) => setDelegateDueAt(e.target.value)}
                        />
                      </div>

                      <div className="space-y-1.5">
                        <Label>Delegation Directive</Label>
                        <Textarea
                          rows={2}
                          value={delegateDirective}
                          onChange={(e) => setDelegateDirective(e.target.value)}
                          placeholder="e.g. Inspect cold room thermometer on Aisle 4 and follow up with customer..."
                        />
                      </div>

                      <Button
                        type="submit"
                        disabled={isDelegating || !delegateAssigneeId}
                        className="w-full"
                      >
                        <Send className="h-3.5 w-3.5" />
                        <span>{isDelegating ? "Delegating Task..." : "Delegate Task"}</span>
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              )}

              {/* Resolution Workflow Card */}
              <Card className="rounded-2xl shadow-sm">
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-xs uppercase tracking-wider">
                    Update Resolution Status
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5 pt-2">
                  <form onSubmit={handleUpdateStatus} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label>Status</Label>
                      <Select value={editStatus} onValueChange={setEditStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="new">New / Open</SelectItem>
                          <SelectItem value="reviewed">Reviewed</SelectItem>
                          <SelectItem value="in_progress">In Progress</SelectItem>
                          <SelectItem value="resolved">Resolved</SelectItem>
                          <SelectItem value="closed">Closed</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1.5">
                      <Label>Corrective Action Summary</Label>
                      <Textarea
                        rows={2}
                        value={editSummary}
                        onChange={(e) => setEditSummary(e.target.value)}
                        placeholder="Document resolution steps taken (e.g. refund processed, chiller recalibrated)..."
                      />
                    </div>

                    <Button type="submit" disabled={isUpdating} variant="default" size="sm">
                      {isUpdating ? "Saving..." : "Commit Status Change"}
                    </Button>
                  </form>
                </CardContent>
              </Card>

              {/* Delegation & Investigation Timeline */}
              <div className="space-y-3">
                <h3 className="text-xs font-extrabold text-black uppercase tracking-wider">
                  Delegation & Investigation Timeline ({selectedComplaint.notes?.length || 0})
                </h3>

                <form onSubmit={handleAddNote} className="space-y-2">
                  <Textarea
                    rows={2}
                    value={newNoteBody}
                    onChange={(e) => setNewNoteBody(e.target.value)}
                    placeholder="Add an internal update or supervisor comment..."
                  />
                  <Button
                    type="submit"
                    disabled={isAddingNote || !newNoteBody.trim()}
                    variant="outline"
                    size="sm"
                  >
                    {isAddingNote ? "Attaching..." : "Attach Note"}
                  </Button>
                </form>

                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {(selectedComplaint.notes || []).map((note) => (
                    <div key={note.id} className="p-3.5 glass-well rounded-2xl space-y-1">
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
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
