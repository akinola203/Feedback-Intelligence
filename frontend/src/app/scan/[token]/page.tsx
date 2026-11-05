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

const RATING_DESCRIPTIONS: Record<number, { label: string; emoji: string }> = {
  1: { label: "Very Poor", emoji: "😡" },
  2: { label: "Poor", emoji: "🙁" },
  3: { label: "Average", emoji: "😐" },
  4: { label: "Good", emoji: "🙂" },
  5: { label: "Excellent", emoji: "🤩" },
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
      setSubmitError("Please select a star rating from 1 to 5.");
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
          "Submission rate limit exceeded. Please wait a minute before submitting again."
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

  if (isLoadingMetadata) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="flex flex-col items-center space-y-4 max-w-sm text-center">
          <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-600 font-medium">Verifying store location...</p>
        </div>
      </main>
    );
  }

  if (metadataError || !metadata) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 max-w-md w-full text-center">
          <div className="w-12 h-12 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl font-bold">
            !
          </div>
          <h1 className="text-xl font-bold text-slate-900 mb-2">
            {isRateLimited ? "Rate Limit Exceeded" : "Store Verification Failed"}
          </h1>
          <p className="text-slate-600 text-sm mb-6 leading-relaxed">
            {metadataError}
          </p>
          <button
            onClick={() => fetchStoreMetadata()}
            className="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white font-medium rounded-xl transition-colors duration-150 text-sm"
          >
            Retry Connection
          </button>
        </div>
      </main>
    );
  }

  if (isSubmitted) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md w-full text-center">
          <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-5 text-3xl">
            ✓
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Thank You!</h1>
          <p className="text-slate-600 text-sm leading-relaxed mb-6">
            Your feedback for{" "}
            <span className="font-semibold text-slate-900">
              {metadata.organization_name} ({metadata.branch_name})
            </span>{" "}
            has been securely recorded.
          </p>
          <div className="bg-slate-50 rounded-xl p-4 border border-slate-100 text-xs text-slate-500">
            Have a pleasant remainder of your day!
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 py-8 px-4 flex justify-center items-start">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 max-w-lg w-full overflow-hidden">
        <div className="bg-slate-900 text-white p-6">
          <div className="flex items-center space-x-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Verified Store Location</span>
          </div>
          <h1 className="text-xl font-bold">{metadata.organization_name}</h1>
          <p className="text-slate-300 text-sm">{metadata.branch_name} Branch</p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {submitError && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs leading-relaxed">
              {submitError}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-2">
              How was your shopping experience today? <span className="text-rose-500">*</span>
            </label>
            <div className="flex justify-between items-center bg-slate-50 p-3 rounded-xl border border-slate-200">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, rating: star }))}
                  className={`p-2 rounded-lg text-2xl transition-all transform active:scale-95 ${
                    formData.rating >= star ? "opacity-100 scale-110" : "opacity-40 hover:opacity-75"
                  }`}
                  aria-label={`${star} Stars`}
                >
                  ⭐
                </button>
              ))}
            </div>
            {formData.rating > 0 && (
              <p className="text-center text-xs font-medium text-slate-600 mt-2">
                {RATING_DESCRIPTIONS[formData.rating].emoji} {RATING_DESCRIPTIONS[formData.rating].label} ({formData.rating}/5)
              </p>
            )}
          </div>

          <div>
            <label htmlFor="category" className="block text-sm font-semibold text-slate-900 mb-1.5">
              Primary Category <span className="text-rose-500">*</span>
            </label>
            <select
              id="category"
              value={formData.categoryId}
              onChange={(e) => setFormData((prev) => ({ ...prev, categoryId: e.target.value }))}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            >
              <option value="" disabled>Select an area of feedback...</option>
              {metadata.categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="message" className="block text-sm font-semibold text-slate-900 mb-1.5">
              Your Comments
            </label>
            <textarea
              id="message"
              rows={3}
              value={formData.message}
              onChange={(e) => setFormData((prev) => ({ ...prev, message: e.target.value }))}
              placeholder="Tell us what went well or what we can improve..."
              className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={1000}
            />
            <div className="text-right text-[11px] text-slate-400 mt-1">
              {formData.message.length}/1000 characters
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Optional Follow-Up Information
            </h3>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Full Name (optional)"
                value={formData.customerName}
                onChange={(e) => setFormData((prev) => ({ ...prev, customerName: e.target.value }))}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <input
                  type="email"
                  placeholder="Email Address (optional)"
                  value={formData.customerEmail}
                  onChange={(e) => setFormData((prev) => ({ ...prev, customerEmail: e.target.value }))}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <input
                  type="tel"
                  placeholder="Phone Number (optional)"
                  value={formData.customerPhone}
                  onChange={(e) => setFormData((prev) => ({ ...prev, customerPhone: e.target.value }))}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <p className="text-[11px] text-slate-400 leading-tight">
                🔒 Privacy Guarantee: Under the NDPR, contact details are kept strictly confidential.
              </p>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || isRateLimited}
            className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white font-semibold rounded-xl transition-all shadow-sm active:scale-[0.99] text-sm flex items-center justify-center space-x-2"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Submitting Feedback...</span>
              </>
            ) : (
              <span>Submit Feedback</span>
            )}
          </button>
        </form>
      </div>
    </main>
  );
}

