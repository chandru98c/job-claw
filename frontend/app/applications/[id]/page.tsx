"use client";

import React, { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useTaskStream } from "@/hooks/useTaskStream";
import { Loader2, AlertCircle, CheckCircle, Save, Send, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

interface AppField {
  field_id: string;
  label: string;
  type: string;
  required: boolean;
  options?: string[];
  placeholder?: string;
  value?: any;
  source: string;
}

interface Application {
  id: string;
  job_id: string;
  status: string;
  application_url?: string;
  fields?: AppField[];
  unanswered_required_fields?: string[];
  submission_evidence?: any;
}

export default function ApplicationReviewPage() {
  const { id } = useParams() as { id: string };
  const searchParams = useSearchParams();
  const router = useRouter();

  const [app, setApp] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editable fields state
  const [fieldValues, setFieldValues] = useState<Record<string, any>>({});
  const [savingFields, setSavingFields] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isSubmittingRequest, setIsSubmittingRequest] = useState(false);

  // We track the active task ID for SSE. Initially from URL if preparing,
  // but we can also set it dynamically when submitting.
  const initialTaskId = searchParams.get("taskId");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(initialTaskId);

  const taskStream = useTaskStream(activeTaskId);

  const fetchApplication = async () => {
    try {
      const data = await api.get<Application>(`/applications/${id}`);
      setApp(data);
      // Initialize field values
      if (data.fields) {
        const vals: Record<string, any> = {};
        data.fields.forEach(f => {
          vals[f.field_id] = f.value || "";
        });
        setFieldValues(vals);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load application");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApplication();
  }, [id]);

  // When task stream finishes or changes state significantly, refresh application
  useEffect(() => {
    if (taskStream.status === 'SUCCEEDED' || taskStream.status === 'FAILED' || taskStream.status === 'ERROR' || taskStream.status === 'COMPLETED') {
      fetchApplication();
    }
  }, [taskStream.status]);

  const handleFieldChange = (fieldId: string, value: any) => {
    setFieldValues(prev => ({ ...prev, [fieldId]: value }));
  };

  const handleSaveFields = async () => {
    setSavingFields(true);
    try {
      // Find what actually changed
      const updates = app?.fields
        ?.filter(f => fieldValues[f.field_id] !== f.value)
        .map(f => ({ field_id: f.field_id, value: fieldValues[f.field_id] })) || [];
        
      if (updates.length > 0) {
        await api.put(`/applications/${id}/fields`, updates);
        await fetchApplication();
      }
    } catch (err: any) {
      alert(err.message || "Failed to update fields");
    } finally {
      setSavingFields(false);
    }
  };

  const handleApprove = async () => {
    if (isApproving) return;
    setIsApproving(true);
    try {
      await api.post(`/applications/${id}/approve`, {});
      await fetchApplication();
    } catch (err: any) {
      alert(err.message || "Failed to approve application");
    } finally {
      setIsApproving(false);
    }
  };

  const handleSubmit = async () => {
    if (isSubmittingRequest) return;
    setIsSubmittingRequest(true);
    try {
      const res = await api.post<{status: string, task_id: string}>(`/applications/${id}/submit`, {});
      if (res.task_id) {
        setActiveTaskId(res.task_id);
      }
      await fetchApplication();
    } catch (err: any) {
      alert(err.message || "Failed to submit application");
    } finally {
      setIsSubmittingRequest(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  if (error || !app) {
    return (
      <div className="flex flex-col h-full max-w-4xl mx-auto w-full px-6 py-8 overflow-y-auto">
        <div className="text-center py-12 bg-destructive/10 border border-destructive/20 rounded-[24px]">
          <AlertCircle className="w-8 h-8 text-destructive mx-auto mb-4" />
          <p className="text-destructive">{error || "Application not found"}</p>
          <Link href="/recommendations" className="text-primary hover:underline mt-4 inline-block">
            Back to Recommendations
          </Link>
        </div>
      </div>
    );
  }

  const isPreparing = app.status === "PREPARING";
  const isSubmitting = app.status === "SUBMITTING";
  const isReviewable = app.status === "READY_FOR_REVIEW" || app.status === "APPROVED";
  const hasUnanswered = (app.unanswered_required_fields?.length || 0) > 0;

  // Final States
  const isFinalState = ["SUBMITTED", "FAILED", "SUBMISSION_STATUS_UNKNOWN", "CANCELLED", "UNSUPPORTED"].includes(app.status);

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto w-full px-6 py-8 overflow-y-auto">
      <Link href="/recommendations" className="text-muted-foreground hover:text-white flex items-center gap-2 mb-6 w-fit">
        <ArrowLeft className="w-4 h-4" /> Back
      </Link>
      
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/10">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Application Review</h1>
          <div className="text-sm text-muted-foreground">Application ID: {app.id}</div>
        </div>
        <div className="px-4 py-2 bg-zinc-800 rounded-[24px] text-sm font-medium border border-border">
          Status: <span className="text-primary">{app.status}</span>
        </div>
      </div>

      {/* Progress / SSE Block */}
      {(isPreparing || isSubmitting) && (
        <div className="bg-card border border-white/10 rounded-[24px] p-6 mb-8 flex flex-col items-center justify-center text-center">
          <Loader2 className="w-10 h-10 text-primary animate-spin mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">
            {isPreparing ? "Preparing Application..." : "Submitting Application..."}
          </h3>
          <p className="text-muted-foreground mb-4">
            This may take a few moments as we interact with the external ATS.
          </p>
          
          {taskStream.isActive ? (
            <div className="bg-black/50 px-4 py-2 rounded-[24px] text-sm text-muted-foreground font-mono">
              Task Status: {taskStream.status}
              {taskStream.payload?.msg && (
                <span className="block mt-1 text-muted-foreground">"{taskStream.payload.msg}"</span>
              )}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              No live progress available. <button onClick={fetchApplication} className="text-primary hover:underline">Refresh</button>
            </div>
          )}
        </div>
      )}

      {/* Fields Review Block */}
      {isReviewable && app.fields && (
        <div className="bg-card border border-white/10 rounded-[24px] p-6 mb-8">
          <h2 className="text-xl font-semibold text-white mb-6">Review Application Data</h2>
          
          {hasUnanswered && (
            <div className="bg-amber-500/10 border border-amber-500/20 text-amber-400 p-4 rounded-[24px] mb-6 flex gap-3">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Missing Required Fields</p>
                <p className="text-sm opacity-80 mt-1">
                  Please provide values for the required fields before approving.
                </p>
              </div>
            </div>
          )}

          <div className="space-y-6">
            {app.fields.map(f => (
              <div key={f.field_id} className="border-b border-border pb-4 last:border-0 last:pb-0">
                <label className="block text-sm font-medium text-muted-foreground mb-2">
                  {f.label} {f.required && <span className="text-destructive">*</span>}
                </label>
                
                {f.type === "select" ? (
                  <select 
                    className="w-full bg-background border border-white/10 rounded-[24px] px-4 py-2.5 text-white focus:outline-none focus:border-primary disabled:opacity-50"
                    value={fieldValues[f.field_id] || ""}
                    onChange={e => handleFieldChange(f.field_id, e.target.value)}
                    disabled={app.status === "APPROVED"}
                  >
                    <option value="">Select an option...</option>
                    {f.options?.map(o => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                ) : f.type === "file" ? (
                  <input 
                    type="text" 
                    className="w-full bg-background border border-white/10 rounded-[24px] px-4 py-2.5 text-white focus:outline-none focus:border-primary disabled:opacity-50"
                    placeholder={f.placeholder || "Filename or URL"}
                    value={fieldValues[f.field_id] || ""}
                    onChange={e => handleFieldChange(f.field_id, e.target.value)}
                    disabled={app.status === "APPROVED"}
                  />
                ) : (
                  <input 
                    type={f.type === "boolean" ? "checkbox" : "text"}
                    className={f.type === "boolean" ? "w-5 h-5 accent-primary" : "w-full bg-background border border-white/10 rounded-[24px] px-4 py-2.5 text-white focus:outline-none focus:border-primary disabled:opacity-50"}
                    placeholder={f.placeholder}
                    checked={f.type === "boolean" ? fieldValues[f.field_id] === "true" || fieldValues[f.field_id] === true : undefined}
                    value={f.type === "boolean" ? undefined : fieldValues[f.field_id] || ""}
                    onChange={e => {
                      const val = f.type === "boolean" ? e.target.checked : e.target.value;
                      handleFieldChange(f.field_id, val);
                    }}
                    disabled={app.status === "APPROVED"}
                  />
                )}
                <div className="text-xs text-muted-foreground mt-1">Source: {f.source}</div>
              </div>
            ))}
          </div>

          <div className="mt-8 flex gap-3">
            <Button 
              onClick={handleSaveFields}
              disabled={savingFields || app.status === "APPROVED"}
              variant="outline"
              className="flex-1"
            >
              {savingFields ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Changes
            </Button>
            
            {app.status === "READY_FOR_REVIEW" && (
              <Button
                onClick={handleApprove}
                disabled={isApproving || hasUnanswered}
                className="flex-1"
              >
                {isApproving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                {isApproving ? "Approving..." : "Approve Application"}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Submission Block */}
      {app.status === "APPROVED" && (
        <div className="bg-card border border-primary/20 rounded-[24px] p-6 mb-8 text-center">
          <CheckCircle className="w-12 h-12 text-primary mx-auto mb-4" />
          <h3 className="text-xl font-bold text-white mb-2">Application Approved</h3>
          <p className="text-muted-foreground mb-6 max-w-md mx-auto">
            You have reviewed and approved all the required data. The application is now ready to be securely submitted to the employer.
          </p>
          <Button 
            onClick={handleSubmit}
            disabled={isSubmittingRequest}
            size="lg"
            className="mx-auto"
          >
            {isSubmittingRequest ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            {isSubmittingRequest ? "Submitting..." : "Submit Application Now"}
          </Button>
        </div>
      )}

      {/* Final States */}
      {isFinalState && (
        <div className={`bg-card border rounded-[24px] p-8 text-center ${app.status === 'SUBMITTED' ? 'border-primary/20' : app.status === 'SUBMISSION_STATUS_UNKNOWN' ? 'border-amber-500/20' : 'border-destructive/20'}`}>
          {app.status === "SUBMITTED" ? (
            <>
              <CheckCircle className="w-16 h-16 text-primary mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Application Submitted!</h2>
              <p className="text-primary">Your application was successfully sent to the ATS.</p>
            </>
          ) : app.status === "SUBMISSION_STATUS_UNKNOWN" ? (
            <>
              <AlertCircle className="w-16 h-16 text-amber-500 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Submission Outcome Uncertain</h2>
              <p className="text-amber-400 mb-4">The submission completed, but we could not confirm success with the external system.</p>
              <p className="text-muted-foreground text-sm">Please check your email for a confirmation from the employer.</p>
            </>
          ) : app.status === "CANCELLED" ? (
            <>
              <AlertCircle className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Application Cancelled</h2>
              <p className="text-muted-foreground">The application was cancelled before completion.</p>
            </>
          ) : app.status === "UNSUPPORTED" ? (
            <>
              <AlertCircle className="w-16 h-16 text-destructive mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Application Unsupported</h2>
              <p className="text-destructive">The ATS application format for this job is not currently supported.</p>
            </>
          ) : (
            <>
              <AlertCircle className="w-16 h-16 text-destructive mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Submission Failed</h2>
              <p className="text-destructive">There was a problem submitting your application. Please check back later or try again.</p>
            </>
          )}
        </div>
      )}

    </div>
  );
}
