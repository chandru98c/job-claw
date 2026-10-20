"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { 
  Activity, 
  Server, 
  Database, 
  Cpu, 
  Globe, 
  Play, 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Zap, 
  ExternalLink,
  Layers,
  ShieldCheck,
  ChevronRight,
  Radio
} from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SystemStatus } from "@/hooks/useTaskStatus";
import { api } from "@/lib/api";

export interface RunningTaskItem {
  task_id: string;
  target_id: string | null;
  domain: string | null;
  start_url: string | null;
  ats_type: string | null;
  worker_type: string;
  status: string;
  started_at: string | null;
  duration_seconds: number;
  retry_count: number;
}

interface RunningTasksResponse {
  running_count: number;
  tasks: RunningTaskItem[];
}

interface SystemStatusModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: SystemStatus;
  onRefreshStatus?: () => void;
}

export function SystemStatusModal({
  open,
  onOpenChange,
  status,
  onRefreshStatus,
}: SystemStatusModalProps) {
  const [runningTasks, setRunningTasks] = useState<RunningTaskItem[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [modeLoading, setModeLoading] = useState(false);
  const [scanWorkingLoading, setScanWorkingLoading] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);

  const fetchRunningTasks = useCallback(async () => {
    try {
      setLoadingTasks(true);
      const res = await api.get<RunningTasksResponse>("/system/running-tasks");
      setRunningTasks(res?.tasks || []);
    } catch {
      setRunningTasks([]);
    } finally {
      setLoadingTasks(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchRunningTasks();
      const interval = setInterval(fetchRunningTasks, 3000);
      return () => clearInterval(interval);
    }
  }, [open, fetchRunningTasks]);

  const handleToggleMode = async () => {
    try {
      setModeLoading(true);
      const targetMode = status.worker_mode === "server" ? "local" : "server";
      await api.post("/system/worker-mode", { mode: targetMode });
      if (onRefreshStatus) onRefreshStatus();
    } catch (err: unknown) {
      console.error("Failed to update worker mode", err);
    } finally {
      setModeLoading(false);
    }
  };

  const handleScanWorking = async () => {
    try {
      setScanWorkingLoading(true);
      setScanMessage("Queuing verified working sites for discovery...");
      const res = await api.post<{ message: string; queued: number }>("/system/scan-working");
      setScanMessage(res?.message || "Verified working sites enqueued successfully!");
      if (onRefreshStatus) onRefreshStatus();
      fetchRunningTasks();
    } catch {
      setScanMessage("Failed to queue working sites scan.");
    } finally {
      setScanWorkingLoading(false);
      setTimeout(() => setScanMessage(null), 5000);
    }
  };

  const isServerMode = status.worker_mode === "server";
  const isWorkerBusy = status.worker_status === "busy";
  const isWorkerOnline = (status.workers_online ?? 0) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto bg-zinc-950/95 border border-white/10 text-white backdrop-blur-2xl p-6 rounded-3xl shadow-2xl">
        <DialogHeader className="border-b border-white/[0.08] pb-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <DialogTitle className="text-xl sm:text-2xl font-extrabold tracking-tight text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-[#c8f542]" />
                System Status & Running Tasks
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                Execution status of crawler pipeline, worker queues, and active scans.
              </DialogDescription>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-auto">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (onRefreshStatus) onRefreshStatus();
                  fetchRunningTasks();
                }}
                className="h-8 text-xs border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-zinc-300 gap-1.5 rounded-xl"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingTasks ? "animate-spin text-[#c8f542]" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Server / Local Mode Configuration */}
        <div className={`mt-4 p-4 rounded-2xl border transition-all ${
          isServerMode 
            ? "bg-gradient-to-r from-emerald-500/10 via-[#c8f542]/5 to-transparent border-emerald-500/30" 
            : "bg-zinc-900/60 border-white/10"
        }`}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Radio className={`w-4 h-4 ${isServerMode ? "text-emerald-400" : "text-zinc-400"}`} />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Crawler Mode: {isServerMode ? "Server Mode" : "Local Mode"}
                </span>
                <Badge variant="outline" className={isServerMode ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10" : "border-zinc-700 text-zinc-400"}>
                  {isServerMode ? "15m Interval" : "Manual"}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {isServerMode 
                  ? "Background scheduler sweeps verified active career boards every 15 minutes."
                  : "Automated background cron discovery is paused. Discovery tasks run only when manually triggered."
                }
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                onClick={handleToggleMode}
                disabled={modeLoading}
                className="h-8 text-xs border-white/15 bg-white/[0.05] hover:bg-white/[0.1] text-white rounded-xl"
              >
                Switch to {isServerMode ? "Local Mode" : "Server Mode"}
              </Button>
              <Button
                size="sm"
                onClick={handleScanWorking}
                disabled={scanWorkingLoading}
                className="h-8 text-xs bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-semibold rounded-xl gap-1.5 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                Scan Active Boards
              </Button>
            </div>
          </div>

          {scanMessage && (
            <div className="mt-3 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1.5 rounded-lg flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              <span>{scanMessage}</span>
            </div>
          )}
        </div>

        {/* Diagnostic High-Density Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-4">
          {/* Card 1: Core API & DB */}
          <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span>Core Plane</span>
              <Server className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <div className="mt-2">
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${status.core_online ? "bg-emerald-400" : "bg-rose-500"}`} />
                <span className="text-sm font-bold text-white">
                  {status.core_online ? "Online" : "Offline"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-400 mt-0.5 space-y-0.5">
                <div>PostgreSQL: <span className={status.db_connected ? "text-emerald-400 font-medium" : "text-rose-400"}>{status.db_connected ? "Connected" : "Disconnected"}</span></div>
                <div>Redis: <span className={status.redis_connected ? "text-emerald-400 font-medium" : "text-rose-400"}>{status.redis_connected ? "Connected" : "Disconnected"}</span></div>
              </div>
            </div>
          </div>

          {/* Card 2: ARQ Background Worker */}
          <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span>Worker Daemon</span>
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
            </div>
            <div className="mt-2">
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${isWorkerOnline ? (isWorkerBusy ? "bg-amber-400 animate-pulse" : "bg-emerald-400") : "bg-rose-500"}`} />
                <span className="text-sm font-bold text-white capitalize">
                  {isWorkerOnline ? (status.worker_status || "Online") : "Offline"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-400 mt-0.5 space-y-0.5">
                <div>Online: <span className="text-white font-mono font-medium">{status.workers_online ?? 0} worker</span></div>
                <div>Queue Depth: <span className="text-white font-mono font-medium">{status.worker_queue_depth ?? status.discovery_queued_tasks ?? 0}</span></div>
              </div>
            </div>
          </div>

          {/* Card 3: Discovery Registry */}
          <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span>Registry Engines</span>
              <Globe className="w-3.5 h-3.5 text-[#c8f542]" />
            </div>
            <div className="mt-2">
              <div className="text-sm font-bold text-white font-mono">
                {(status.total_engines ?? 0).toLocaleString()} Total
              </div>
              <div className="text-[10px] text-zinc-400 mt-0.5 space-y-0.5">
                <div>Active: <span className="text-emerald-400 font-medium font-mono">{(status.active_engines ?? 0).toLocaleString()}</span></div>
                <div>Working: <span className="text-[#c8f542] font-semibold font-mono">{(status.working_engines ?? 0).toLocaleString()} boards</span></div>
              </div>
            </div>
          </div>

          {/* Card 4: Task Execution Pipeline */}
          <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span>Active Tasks</span>
              <Layers className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <div className="mt-2">
              <div className="text-sm font-bold text-amber-400 font-mono">
                {status.active_tasks ?? 0} Total Active
              </div>
              <div className="text-[10px] text-zinc-400 mt-0.5 space-y-0.5">
                <div>Running: <span className="text-[#c8f542] font-bold font-mono">{status.discovery_running_tasks ?? 0}</span></div>
                <div>Queued: <span className="text-zinc-300 font-mono">{status.discovery_queued_tasks ?? 0}</span></div>
              </div>
            </div>
          </div>
        </div>

        {/* Live Running Tasks Section */}
        <div className="mt-6 border border-white/[0.08] rounded-2xl overflow-hidden bg-black/30">
          <div className="px-4 py-3 bg-white/[0.03] border-b border-white/[0.08] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Play className="w-4 h-4 text-[#c8f542]" />
              <span className="text-xs font-bold uppercase tracking-wider text-white">
                Live Running Scans & Crawler Tasks ({runningTasks.length})
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground">
              Updated every 3 seconds
            </span>
          </div>

          <div className="p-2 divide-y divide-white/[0.05] max-h-60 overflow-y-auto">
            {runningTasks.length > 0 ? (
              runningTasks.map((t) => (
                <div key={t.task_id} className="p-2.5 flex items-center justify-between gap-3 hover:bg-white/[0.02] rounded-xl transition-colors">
                  <div className="min-w-0 flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-[#c8f542] animate-ping shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white truncate">
                          {t.domain || t.target_id || "Discovery Scan"}
                        </span>
                        {t.ats_type && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] font-mono uppercase bg-purple-500/20 text-purple-300 border border-purple-500/30">
                            {t.ats_type}
                          </span>
                        )}
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-mono uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          {t.status}
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                        {t.start_url || t.target_id || "Crawling endpoints..."}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                      <div className="text-[11px] font-mono text-zinc-300 flex items-center gap-1 justify-end">
                        <Clock className="w-3 h-3 text-zinc-400" />
                        {t.duration_seconds}s elapsed
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono">
                        {t.worker_type}
                      </div>
                    </div>

                    {t.domain && (
                      <Link 
                        href={`/engines?search=${encodeURIComponent(t.domain)}`}
                        onClick={() => onOpenChange(false)}
                        className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-zinc-300 hover:text-white transition-colors"
                        title="View in Engines page"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="py-8 text-center text-zinc-500 text-xs flex flex-col items-center justify-center gap-2">
                <CheckCircle2 className="w-6 h-6 text-emerald-500/60" />
                <span>No tasks are actively executing right now.</span>
                <span className="text-[11px] text-zinc-600">
                  Workers are standing by for scheduled sweeps or manual triggers.
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer Navigation Link */}
        <div className="mt-4 pt-3 border-t border-white/[0.08] flex items-center justify-between text-xs">
          <span className="text-zinc-500">
            Engine Queue Depth: <strong className="text-white font-mono">{status.worker_queue_depth ?? status.discovery_queued_tasks ?? 0} tasks</strong>
          </span>
          <Link
            href="/engines"
            onClick={() => onOpenChange(false)}
            className="inline-flex items-center gap-1.5 text-[#c8f542] hover:text-[#d8ff4e] font-semibold transition-colors"
          >
            Open Full Pipeline & Discovery Engines <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  );
}
