import axios from "axios";

const baseURL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL,
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  headers: {
    "Content-Type": "application/json",
  },
});

// Helper to extract CSRF token from document.cookie for POST/PUT/PATCH/DELETE
function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)(" + name + ")=([^;]*)"));
  return match ? decodeURIComponent(match[3]) : null;
}

api.interceptors.request.use((config) => {
  const csrfToken = getCookie("csrftoken");
  if (csrfToken && config.headers) {
    config.headers["X-CSRFToken"] = csrfToken;
  }
  return config;
});

export interface Branch {
  id: string;
  name: string;
  is_active: boolean;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "manager" | "staff";
  is_staff: boolean;
  is_superuser: boolean;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  branches: Branch[];
}

export interface ComplaintNote {
  id: string;
  author_email: string;
  note: string;
  created_at: string;
}

export interface Complaint {
  id: string;
  feedback_id: string;
  branch_id: string;
  branch_name: string;
  category_name: string;
  customer_name?: string;
  customer_email?: string;
  customer_phone?: string;
  rating: number;
  message?: string;
  status: "open" | "in_progress" | "resolved" | "dismissed";
  assigned_to_email?: string;
  created_at: string;
  updated_at: string;
  notes?: ComplaintNote[];
}

export default api;
