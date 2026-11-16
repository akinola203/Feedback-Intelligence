"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import axios, { AxiosError } from "axios";

interface Category {
  id: string;
  name: string;
}

interface StoreMetadata {
  organization_name: string;
  organization_slug: string;
  branch_name: string;
  branch_id: string;
  categories: Category[];
}

interface FormState {
  rating: number;
  categoryId: string;
  message: string;
  customerName: string;
  customerEmail: string;
  customerPhone: string;
}

const RATING_DESCRIPTIONS: Record<number, { label: string; tag: string }> = {
  1: { label: "Very Poor Experience", tag: "Critical Issue" },
  2: { label: "Below Expectations", tag: "Needs Attention" },
  3: { label: "Average Experience", tag: "Satisfactory" },
  4: { label: "Good Experience", tag: "Positive" },
  5: { label: "Exceptional Service", tag: "Outstanding" },
};

export default function CustomerScanFeedbackPage() {
  const params = useParams();
  const token = params?.token as string;

  const [metadata, setMetadata] = useState<StoreMetadata | null>(null);
  const [isLoadingMetadata, setIsLoadingMetadata] = useState<boolean>(true);
  const [metadataError, setMetadataError] = useState<string | null>(null);

  const [formData, setFormData] = useState<FormState>({
    rating: 0,
    categoryId: "",
    message: "",
    customerName: "",
    customerEmail: "",
    customerPhone: "",
  });

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isSubmitted, setIsSubmitted] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isRateLimited, setIsRateLimited] = useState<boolean>(false);

  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

  const fetchStoreMetadata = useCallback(async () => {
    if (!token) return;
    setIsLoadingMetadata(true);
    setMetadataError(null);

    try {
      const response = await axios.get<StoreMetadata>(
        `${apiBaseUrl}/api/feedback/submit/${token}/`
      );
      setMetadata(response.data);
    } catch (err) {
      const error = err as AxiosError<{ error?: string; detail?: string }>;
      if (error.response?.status === 404) {
        setMetadataError(
          "This QR code is either expired or invalid. Please check with store customer service."
        );
      } else if (error.response?.status === 429) {
        setIsRateLimited(true);
        setMetadataError(
          "Too many requests. Please wait a few moments before trying again."
        );
      } else {
        setMetadataError(
          "Unable to load store feedback portal. Please check your internet connection."
        );
      }
    } finally {
      setIsLoadingMetadata(false);
    }
  }, [token, apiBaseUrl]);

  useEffect(() => {
    fetchStoreMetadata();
  }, [fetchStoreMetadata]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.rating === 0) {
      setSubmitError("Please select a rating from 1 to 5 stars.");
      return;
    }
    if (!formData.categoryId) {
      setSubmitError("Please select a feedback category.");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await axios.post(`${apiBaseUrl}/api/feedback/submit/${token}/`, {
        rating: formData.rating,
        category: formData.categoryId,
        message: formData.message.trim() || null,
        customer_name: formData.customerName.trim() || null,
        customer_email: formData.customerEmail.trim() || null,
        customer_phone: formData.customerPhone.trim() || null,
      });

      setIsSubmitted(true);
    } catch (err) {
      const error = err as AxiosError<{ error?: string; detail?: string }>;
      if (error.response?.status === 429) {
        setIsRateLimited(true);
        setSubmitError(
          "Submission rate limit exceeded. Please wait a moment before trying again."
        );
      } else if (error.response?.status === 400) {
        setSubmitError(
          error.response.data?.error ||
            "Invalid submission details. Please verify your entries."
        );
      } else {
        setSubmitError(
          "An unexpected server error occurred. Please try again shortly."
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#F3F3F3] text-black relative flex items-center justify-center p-4 sm:p-6 overflow-hidden">
      {/* Ambient Depth Background Blobs (Monochrome) */}
      <div className="absolute top-1/4 -left-32 w-96 h-96 bg-neutral-300/30 rounded-full blur-3xl -z-10 pointer-events-none" />
      <div className="absolute bottom-1/4 -right-32 w-96 h-96 bg-black/[0.04] rounded-full blur-3xl -z-10 pointer-events-none" />
      <div className="absolute -top-20 right-1/3 w-80 h-80 bg-neutral-400/20 rounded-full blur-3xl -z-10 pointer-events-none" />

      {/* Loading State */}
      {isLoadingMetadata && (
        <div className="glass-panel max-w-md w-full p-10 text-center rounded-3xl space-y-4">
          <div className="w-10 h-10 border-2 border-black border-t-transparent rounded-full animate-spin mx-auto" />
          <h2 className="text-base font-bold tracking-tight text-black">Verifying Location</h2>
          <p className="text-xs text-neutral-500">Connecting securely to verified store register...</p>
        </div>
      )}

      {/* Error State */}
      {!isLoadingMetadata && (metadataError || !metadata) && (
        <div className="glass-panel max-w-md w-full p-8 text-center rounded-3xl space-y-4 border border-white/80">
          <div className="w-12 h-12 bg-black text-white rounded-2xl flex items-center justify-center mx-auto text-xl font-bold shadow-md">
            !
          </div>
          <h1 className="text-xl font-extrabold tracking-tight text-black">
            {isRateLimited ? "Rate Limit Exceeded" : "Store Verification Failed"}
          </h1>
          <p className="text-xs text-neutral-600 leading-relaxed max-w-xs mx-auto">
            {metadataError}
          </p>
          <button
            onClick={() => fetchStoreMetadata()}
            className="w-full py-3 bg-black hover:bg-neutral-800 text-white font-semibold rounded-2xl text-xs transition duration-200 active:scale-[0.99] shadow-md"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Thank You State */}
      {!isLoadingMetadata && isSubmitted && metadata && (
        <div className="glass-panel max-w-md w-full p-8 text-center rounded-3xl space-y-5 border border-white/90">
          <div className="w-16 h-16 bg-black text-white rounded-2xl flex items-center justify-center mx-auto text-2xl font-black shadow-lg">
            ✓
          </div>
          <div className="space-y-1">
            <h1 className="text-2xl font-extrabold tracking-tight text-black">Thank You</h1>
            <p className="text-xs text-neutral-500">Your direct voice helps elevate store standards</p>
          </div>
          <div className="glass-well p-4 rounded-2xl space-y-1 text-left">
            <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-400">Recorded For</p>
            <p className="text-sm font-bold text-black">{metadata.organization_name}</p>
            <p className="text-xs text-neutral-600">{metadata.branch_name} Branch</p>
          </div>
          <p className="text-xs text-neutral-500">
            Store leadership and floor supervisors review incoming feedback in real time.
          </p>
        </div>
      )}

      {/* Main Feedback Form */}
      {!isLoadingMetadata && !metadataError && !isSubmitted && metadata && (
        <div className="w-full max-w-lg glass-panel rounded-3xl overflow-hidden shadow-[0_12px_48px_rgba(0,0,0,0.08)] border border-white/90 transition-all">
          {/* Smoked Black Glass Header Banner */}
          <div className="glass-smoked p-6 sm:p-7 border-b border-white/10 text-white space-y-1.5">
            <div className="flex items-center space-x-2 text-[10px] uppercase font-bold tracking-widest text-neutral-300">
              <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
              <span>Verified Store Stand</span>
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-white">
              {metadata.organization_name}
            </h1>
            <p className="text-xs text-neutral-300 font-medium">
              {metadata.branch_name} Branch
            </p>
          </div>

          <form onSubmit={handleSubmit} className="p-6 sm:p-7 space-y-6">
            {submitError && (
              <div className="p-3.5 bg-black/[0.04] border border-black/20 rounded-2xl text-xs font-semibold text-black">
                {submitError}
              </div>
            )}

            {/* Star Rating Bar */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-black">
                Overall Experience <span className="text-neutral-400">*</span>
              </label>

              <div className="glass-well p-3 rounded-2xl flex justify-between items-center px-4">
                {[1, 2, 3, 4, 5].map((star) => {
                  const isSelected = formData.rating >= star;
                  return (
                    <button
                      key={star}
                      type="button"
                      onClick={() => setFormData((prev) => ({ ...prev, rating: star }))}
                      className="group p-2 transition-all duration-150 transform hover:-translate-y-0.5 active:scale-95"
                      aria-label={`${star} Stars`}
                    >
                      <span
                        className={`text-2xl sm:text-3xl transition-all ${
                          isSelected
                            ? "text-black drop-shadow-[0_2px_8px_rgba(0,0,0,0.3)]"
                            : "text-neutral-300 group-hover:text-neutral-400"
                        }`}
                      >
                        ★
                      </span>
                    </button>
                  );
                })}
              </div>

              {formData.rating > 0 && (
                <div className="flex items-center justify-between px-1 text-xs">
                  <span className="font-bold text-black">
                    {RATING_DESCRIPTIONS[formData.rating].label}
                  </span>
                  <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
                    {RATING_DESCRIPTIONS[formData.rating].tag} ({formData.rating}/5)
                  </span>
                </div>
              )}
            </div>

            {/* Category Dropdown */}
            <div className="space-y-1.5">
              <label htmlFor="category" className="block text-xs font-bold uppercase tracking-wider text-black">
                Primary Category <span className="text-neutral-400">*</span>
              </label>
              <select
                id="category"
                value={formData.categoryId}
                onChange={(e) => setFormData((prev) => ({ ...prev, categoryId: e.target.value }))}
                className="w-full glass-input rounded-2xl px-4 py-3 text-xs font-medium focus:ring-1 focus:ring-black"
                required
              >
                <option value="" disabled>Select area of observation...</option>
                {metadata.categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Comments Area */}
            <div className="space-y-1.5">
              <label htmlFor="message" className="block text-xs font-bold uppercase tracking-wider text-black">
                Detailed Feedback
              </label>
              <textarea
                id="message"
                rows={3}
                value={formData.message}
                onChange={(e) => setFormData((prev) => ({ ...prev, message: e.target.value }))}
                placeholder="Share any highlights, product issues, or store observations..."
                className="w-full glass-input rounded-2xl p-4 text-xs font-medium placeholder-neutral-400"
                maxLength={1000}
              />
              <div className="text-right text-[10px] text-neutral-400 font-mono">
                {formData.message.length} / 1000
              </div>
            </div>

            {/* Optional Customer Contact Section */}
            <div className="pt-4 border-t border-black/[0.08] space-y-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-400">
                Optional Follow-Up Details
              </p>
              <input
                type="text"
                placeholder="Your Name (optional)"
                value={formData.customerName}
                onChange={(e) => setFormData((prev) => ({ ...prev, customerName: e.target.value }))}
                className="w-full glass-input rounded-2xl px-4 py-2.5 text-xs placeholder-neutral-400"
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <input
                  type="email"
                  placeholder="Email Address"
                  value={formData.customerEmail}
                  onChange={(e) => setFormData((prev) => ({ ...prev, customerEmail: e.target.value }))}
                  className="w-full glass-input rounded-2xl px-4 py-2.5 text-xs placeholder-neutral-400"
                />
                <input
                  type="tel"
                  placeholder="Phone Number"
                  value={formData.customerPhone}
                  onChange={(e) => setFormData((prev) => ({ ...prev, customerPhone: e.target.value }))}
                  className="w-full glass-input rounded-2xl px-4 py-2.5 text-xs placeholder-neutral-400"
                />
              </div>
              <p className="text-[10px] text-neutral-500 font-medium">
                🔒 Privacy Guarantee: Under NDPR regulations, contact info remains strictly confidential.
              </p>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting || isRateLimited}
              className="w-full py-3.5 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white font-bold rounded-2xl text-xs transition duration-200 shadow-xl hover:-translate-y-0.5 active:scale-[0.99] flex items-center justify-center space-x-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Recording Submission...</span>
                </>
              ) : (
                <span>Submit Feedback</span>
              )}
            </button>
          </form>
        </div>
      )}
    </main>
  );
}
