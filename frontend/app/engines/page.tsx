"use client";

import { Activity, Server, Globe, Database, Loader2, AlertCircle, PlayCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useTaskStatus } from "@/hooks/useTaskStatus";
import { Button } from "@/components/ui/button";

type EngineMetricsResponse = {
  metrics: {
    total_jobs: number;
    total_sources: number;
    active_sources: number;
    inactive_sources: number;
    total_tasks: number;
    running_discovery_tasks: number;
    queued_discovery_tasks: number;
  };
  discovery: {
    state: "running" | "idle";
    last_task_status: string | null;
    last_task_error: string | null;
  };
  engines: {
    id: string;
    domain: string;
    start_url: string | null;
    ats_type: string | null;
    is_active: boolean;
    last_run_at: string | null;
    runtime: {
      status: string;
      error: string | null;
      updated_at: string | null;
      task_id: string | null;
    };
  }[];
};

type RunDiscoveryResponse = {
  queued: number;
  skipped: number;
  task_ids: string[];
  message: string;
};

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

function runtimeLabel(status: string) {
  const s = (status || "unknown").toUpperCase();
  if (["RUNNING", "QUEUED", "WAITING", "RETRYING"].includes(s)) return "running";
  if (["SUCCEEDED", "COMPLETED"].includes(s)) return "completed";
  if (["FAILED", "ERROR", "CANCELLED"].includes(s)) return "error";
  return "unknown";
}

function runtimePillClass(status: string) {
  const label = runtimeLabel(status);
  if (label === "running") return "text-amber-300 bg-amber-500/10 border-amber-500/30";
  if (label === "completed") return "text-primary bg-primary/10 border-primary/30";
  if (label === "error") return "text-destructive bg-destructive/10 border-destructive/30";
  return "text-muted-foreground bg-zinc-800/70 border-zinc-700";
}

export default function EnginesPage() {
  const systemStatus = useTaskStatus();
  const [data, setData] = useState<EngineMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runLoading, setRunLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get<EngineMetricsResponse>("/engines/metrics");
      setData(res);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initial = setTimeout(() => {
      void fetchData();
    }, 0);
    const interval = setInterval(() => {
      void fetchData();
    }, 5000);
    return () => {
      clearTimeout(initial);
      clearInterval(interval);
    };
  }, [fetchData]);

  const handleRunDiscovery = async () => {
    setRunLoading(true);
    setRunMessage(null);
    try {
      const res = await api.post<RunDiscoveryResponse>("/engines/discovery/run");
      setRunMessage(`Queued ${res.queued} source(s), skipped ${res.skipped}.`);
      await fetchData();
    } catch (err: unknown) {
      setRunMessage(errorMessage(err));
    } finally {
      setRunLoading(false);
    }
  };

  const discoveryStateText = useMemo(() => {
    if (!data) return "loading";
    if (data.discovery.state === "running") return "running";
    if (!data.discovery.last_task_status) return "idle";
    const s = data.discovery.last_task_status.toUpperCase();
    if (["SUCCEEDED", "COMPLETED"].includes(s)) return "completed";
    if (["FAILED", "ERROR", "CANCELLED"].includes(s)) return "error";
    return "idle";
  }, [data]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-10">
        <div className="bg-destructive/10 border border-destructive/30 rounded-[24px] p-5 text-destructive flex items-start gap-3">
          <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Failed to load discovery engines</div>
            <div className="text-sm text-destructive/90 mt-1">{error || "Unknown error"}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto w-full px-6 py-8 overflow-y-auto">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3 mb-2">
            <div className="p-2 bg-primary/10 rounded-full">
              <Activity className="w-7 h-7 text-primary" />
            </div>
            Pipeline & Engines
          </h1>
          <p className="text-muted-foreground">Real registry and discovery execution state.</p>
        </div>

        <div className="flex flex-col items-start lg:items-end gap-2 max-w-full">
          <div className="text-sm text-muted-foreground">
            Discovery: <span className="font-semibold capitalize">{discoveryStateText}</span>
          </div>
          <Button
            onClick={handleRunDiscovery}
            disabled={runLoading || data.metrics.active_sources === 0}
            className="gap-2"
          >
            {runLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
            {runLoading ? "Queuing..." : "Run Registry Discovery"}
          </Button>
          {runMessage ? <div className="text-xs text-muted-foreground break-words">{runMessage}</div> : null}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        <MetricCard icon={<Globe className="w-5 h-5 text-blue-400" />} label="Sources" value={data.metrics.total_sources.toLocaleString()} sub={`${data.metrics.active_sources} active / ${data.metrics.inactive_sources} inactive`} />
        <MetricCard icon={<Database className="w-5 h-5 text-primary" />} label="Jobs" value={data.metrics.total_jobs.toLocaleString()} sub="Persisted canonical jobs" />
        <MetricCard icon={<Activity className="w-5 h-5 text-amber-400" />} label="Discovery Tasks" value={`${data.metrics.running_discovery_tasks}`} sub={`Running · ${data.metrics.queued_discovery_tasks} queued`} />
        <MetricCard icon={<Server className="w-5 h-5 text-purple-400" />} label="Workers" value={`${systemStatus.workers_online ?? 0}`} sub={`${systemStatus.worker_status} · ${systemStatus.active_tasks} active task(s)`} />
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Registry Engines</h2>

      {data.engines.length === 0 ? (
        <div className="bg-card/30 border border-border rounded-[24px] p-8 flex flex-col items-center justify-center text-center">
          <Server className="w-10 h-10 text-zinc-600 mb-3" />
          <h3 className="text-lg font-medium text-muted-foreground">No Engines Registered</h3>
          <p className="text-muted-foreground mt-1 max-w-md">
            No sources exist in the registry. Discovery cannot run until sources are configured.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-6">
          {data.engines.map((engine) => {
            const statusClass = runtimePillClass(engine.runtime.status);
            return (
              <div key={engine.id} className="bg-card/50 border border-border rounded-[24px] p-4 min-w-0">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-zinc-100 break-all">{engine.domain}</h3>
                    <div className="text-xs text-muted-foreground mt-1 break-all">
                      {engine.start_url || "No start URL configured"}
                    </div>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded border whitespace-nowrap ${
                      engine.is_active
                        ? "text-primary bg-primary/10 border-primary/30"
                        : "text-muted-foreground bg-zinc-800/70 border-zinc-700"
                    }`}
                  >
                    {engine.is_active ? "Active" : "Inactive"}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                  <div className="text-muted-foreground">ATS Type</div>
                  <div className="text-foreground break-words">{engine.ats_type || "Unknown"}</div>

                  <div className="text-muted-foreground">Runtime</div>
                  <div>
                    <span className={`inline-flex text-xs px-2 py-1 rounded border ${statusClass}`}>
                      {engine.runtime.status || "unknown"}
                    </span>
                  </div>

                  <div className="text-muted-foreground">Last Update</div>
                  <div className="text-foreground break-words">{engine.runtime.updated_at || "N/A"}</div>

                  <div className="text-muted-foreground">Last Error</div>
                  <div className="text-foreground break-words">{engine.runtime.error || "None"}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MetricCard({ icon, label, value, sub }: { icon: ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="bg-card/60 border border-white/10 rounded-[24px] p-4 min-w-0">
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 bg-zinc-800 rounded-[24px] shrink-0">{icon}</div>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="text-xl font-bold text-white truncate">{value}</div>
        </div>
      </div>
      <div className="text-xs text-muted-foreground break-words">{sub}</div>
    </div>
  );
}
