"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import axios, { AxiosError } from "axios";
import { AlertCircle, Check, Lock, Send, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";

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
        <Card className="max-w-md w-full p-10 text-center space-y-4">
          <div className="w-10 h-10 border-2 border-black border-t-transparent rounded-full animate-spin mx-auto" />
          <h2 className="text-base font-bold tracking-tight text-black">Verifying Location</h2>
          <p className="text-xs text-neutral-500">Connecting securely to verified store register...</p>
        </Card>
      )}

      {/* Error State */}
      {!isLoadingMetadata && (metadataError || !metadata) && (
        <Card className="max-w-md w-full p-8 text-center space-y-4">
          <div className="w-12 h-12 bg-black text-white rounded-2xl flex items-center justify-center mx-auto shadow-md">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-extrabold tracking-tight text-black">
            {isRateLimited ? "Rate Limit Exceeded" : "Store Verification Failed"}
          </h1>
          <p className="text-xs text-neutral-600 leading-relaxed max-w-xs mx-auto">
            {metadataError}
          </p>
          <Button onClick={() => fetchStoreMetadata()} className="w-full">
            Retry Connection
          </Button>
        </Card>
      )}

      {/* Thank You State */}
      {!isLoadingMetadata && isSubmitted && metadata && (
        <Card className="max-w-md w-full p-8 text-center space-y-5">
          <div className="w-16 h-16 bg-black text-white rounded-2xl flex items-center justify-center mx-auto shadow-lg">
            <Check className="h-8 w-8" />
          </div>
          <div className="space-y-1">
            <h1 className="text-2xl font-extrabold tracking-tight text-black">Thank You</h1>
            <p className="text-xs text-neutral-500">Your direct voice helps elevate store standards</p>
          </div>
          <div className="glass-well p-4 rounded-2xl space-y-1 text-left">
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
              Recorded For
            </p>
            <p className="text-sm font-bold text-black">{metadata.organization_name}</p>
            <p className="text-xs text-neutral-600">{metadata.branch_name} Branch</p>
          </div>
          <p className="text-xs text-neutral-500">
            Store leadership and department sector leads review incoming feedback in real time.
          </p>
        </Card>
      )}

      {/* Main Feedback Form */}
      {!isLoadingMetadata && !metadataError && !isSubmitted && metadata && (
        <Card className="w-full max-w-lg overflow-hidden shadow-[0_12px_48px_rgba(0,0,0,0.08)]">
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

          <CardContent className="p-6 sm:p-7">
            <form onSubmit={handleSubmit} className="space-y-6">
              {submitError && (
                <div className="p-3.5 bg-black/[0.04] border border-black/20 rounded-2xl text-xs font-semibold text-black">
                  {submitError}
                </div>
              )}

              {/* Star Rating Bar */}
              <div className="space-y-2">
                <Label>
                  Overall Experience <span className="text-neutral-400">*</span>
                </Label>

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
                        <Star
                          className={`h-7 w-7 sm:h-8 sm:w-8 transition-all ${
                            isSelected
                              ? "fill-black text-black drop-shadow-[0_2px_8px_rgba(0,0,0,0.25)]"
                              : "text-neutral-300 group-hover:text-neutral-500"
                          }`}
                        />
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

              {/* Category Select (shadcn Radix Select) */}
              <div className="space-y-1.5">
                <Label>
                  Primary Category <span className="text-neutral-400">*</span>
                </Label>
                <Select
                  value={formData.categoryId}
                  onValueChange={(val) =>
                    setFormData((prev) => ({ ...prev, categoryId: val }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select area of observation..." />
                  </SelectTrigger>
                  <SelectContent>
                    {metadata.categories.map((cat) => (
                      <SelectItem key={cat.id} value={cat.id}>
                        {cat.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Comments Area */}
              <div className="space-y-1.5">
                <Label htmlFor="message">Detailed Feedback</Label>
                <Textarea
                  id="message"
                  rows={3}
                  value={formData.message}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, message: e.target.value }))
                  }
                  placeholder="Share any highlights, product issues, or store observations..."
                  maxLength={1000}
                />
                <div className="text-right text-[10px] text-neutral-400 font-mono">
                  {formData.message.length} / 1000
                </div>
              </div>

              <Separator />

              {/* Optional Customer Contact Section */}
              <div className="space-y-3">
                <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
                  Optional Follow-Up Details
                </p>
                <Input
                  type="text"
                  placeholder="Your Name (optional)"
                  value={formData.customerName}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, customerName: e.target.value }))
                  }
                />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Input
                    type="email"
                    placeholder="Email Address"
                    value={formData.customerEmail}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, customerEmail: e.target.value }))
                    }
                  />
                  <Input
                    type="tel"
                    placeholder="Phone Number"
                    value={formData.customerPhone}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, customerPhone: e.target.value }))
                    }
                  />
                </div>
                <p className="flex items-center gap-1.5 text-[10px] text-neutral-500 font-medium">
                  <Lock className="h-3 w-3 shrink-0" />
                  <span>Privacy Guarantee: Under NDPR, contact info remains strictly confidential.</span>
                </p>
              </div>

              <Button
                type="submit"
                disabled={isSubmitting || isRateLimited}
                size="lg"
                className="w-full"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Recording Submission...</span>
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5" />
                    <span>Submit Feedback</span>
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
