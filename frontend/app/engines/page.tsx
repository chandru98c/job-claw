"use client";

import {
  Activity,
  Server,
  Globe,
  Database,
  Loader2,
  AlertCircle,
  PlayCircle,
  Search,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Play,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
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
  ats_counts?: Record<string, number>;
  total?: number;
  page?: number;
  limit?: number;
  pages?: number;
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

const ATS_FILTERS = [
  { id: "all", label: "All Adapters" },
  { id: "greenhouse", label: "Greenhouse" },
  { id: "ashby", label: "Ashby" },
  { id: "workable", label: "Workable" },
  { id: "lever", label: "Lever" },
  { id: "bamboohr", label: "BambooHR" },
  { id: "smartrecruiters", label: "SmartRecruiters" },
  { id: "zohorecruit", label: "Zoho Recruit" },
  { id: "keka", label: "Keka" },
  { id: "recruitee", label: "Recruitee" },
  { id: "teamtailor", label: "Teamtailor" },
  { id: "personio", label: "Personio" },
  { id: "custom", label: "Custom ATS" },
];

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

function runtimeLabel(status: string) {
  const s = (status || "unknown").toUpperCase();
  if (["RUNNING", "QUEUED", "WAITING", "RETRYING"].includes(s)) return "running";
  if (["SUCCEEDED", "COMPLETED"].includes(s)) return "completed";
  if (["FAILED", "ERROR", "CANCELLED"].includes(s)) return "error";
  return "idle";
}

function runtimePillClass(status: string) {
  const label = runtimeLabel(status);
  if (label === "running") return "text-amber-300 bg-amber-500/10 border-amber-500/30";
  if (label === "completed") return "text-[#c8f542] bg-[#c8f542]/10 border-[#c8f542]/30";
  if (label === "error") return "text-rose-400 bg-rose-500/10 border-rose-500/30";
  return "text-zinc-400 bg-zinc-800/70 border-zinc-700";
}

export default function EnginesPage() {
  const systemStatus = useTaskStatus();
  const [data, setData] = useState<EngineMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [scanningId, setScanningId] = useState<string | null>(null);

  // Filters & Pagination
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(24);
  const [limitInput, setLimitInput] = useState<string>("24");
  const [search, setSearch] = useState("");
  const [selectedAts, setSelectedAts] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  useEffect(() => {
    setLimitInput(limit.toString());
  }, [limit]);

  const handleLimitCommit = () => {
    const parsed = parseInt(limitInput.trim(), 10);
    if (!isNaN(parsed) && parsed > 0) {
      const clamped = Math.min(Math.max(1, parsed), 100);
      setLimit(clamped);
      setLimitInput(clamped.toString());
      setPage(1);
    } else {
      setLimitInput(limit.toString());
    }
  };

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      if (search.trim()) params.append("search", search.trim());
      if (selectedAts && selectedAts !== "all") params.append("ats_type", selectedAts);
      if (statusFilter === "active") params.append("is_active", "true");
      if (statusFilter === "inactive") params.append("is_active", "false");

      const res = await api.get<EngineMetricsResponse>(`/engines/metrics?${params.toString()}`);
      setData(res);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, selectedAts, statusFilter]);

  useEffect(() => {
    fetchData();
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

  const handleSingleScan = async (sourceId: string, domain: string) => {
    setScanningId(sourceId);
    try {
      const res: any = await api.post(`/sources/${sourceId}/scan`);
      setRunMessage(`Scan triggered for ${domain}: ${res.status || "Job started"}`);
      setTimeout(() => {
        fetchData();
        setScanningId(null);
      }, 3000);
    } catch (err: any) {
      setRunMessage(`Scan failed: ${err.message || "Unknown error"}`);
      setScanningId(null);
    }
  };

  const discoveryStateText = useMemo(() => {
    if (!data) return "loading";
    if (systemStatus?.workers_online === 0) {
      if ((data.metrics.queued_discovery_tasks ?? 0) > 0 || (data.metrics.running_discovery_tasks ?? 0) > 0) {
        return "worker offline (tasks paused)";
      }
      return "worker offline";
    }
    if (data.discovery.state === "running") return "running";
    if (!data.discovery.last_task_status) return "idle";
    const s = data.discovery.last_task_status.toUpperCase();
    if (["SUCCEEDED", "COMPLETED"].includes(s)) return "completed";
    if (["FAILED", "ERROR", "CANCELLED"].includes(s)) return "error";
    return "idle";
  }, [data, systemStatus]);

  const discoveryStateColor = useMemo(() => {
    if (systemStatus?.workers_online === 0) return "text-amber-400";
    if (discoveryStateText === "running") return "text-[#c8f542]";
    if (discoveryStateText === "error") return "text-rose-400";
    if (discoveryStateText === "completed") return "text-emerald-400";
    return "text-zinc-400";
  }, [discoveryStateText, systemStatus]);

  const totalEngines = data?.total ?? data?.metrics?.total_sources ?? 0;
  const totalPages = data?.pages ?? Math.max(1, Math.ceil(totalEngines / limit));

  if (loading && !data) {
    return (
      <div className="h-full flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-[#c8f542] animate-spin" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-10">
        <div className="bg-destructive/10 border border-destructive/30 rounded-2xl p-5 text-destructive flex items-start gap-3">
          <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Failed to load discovery engines</div>
            <div className="text-sm text-destructive/90 mt-1">{error}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col max-w-6xl mx-auto w-full px-4 sm:px-6 py-8 relative">
      {/* Ambient Top Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[850px] h-[300px] bg-gradient-to-b from-[#c8f542]/[0.07] via-[#c8f542]/[0.02] to-transparent blur-3xl pointer-events-none -z-10" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
            <Activity className="w-7 h-7 text-[#c8f542] shrink-0" />
            Pipeline & Discovery Engines
            <span className="text-xs sm:text-sm font-semibold px-2.5 py-0.5 rounded-full bg-[#c8f542]/10 border border-[#c8f542]/30 text-[#c8f542] font-mono">
              {(data?.metrics.total_sources ?? 0).toLocaleString()} total engines
            </span>
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Live execution status across ATS adapters and discovery tasks.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start sm:self-auto">
          <div className="text-xs text-muted-foreground hidden sm:block">
            Pipeline: <span className={`font-semibold capitalize ${discoveryStateColor}`}>{discoveryStateText}</span>
          </div>
          <Button
            onClick={handleRunDiscovery}
            disabled={runLoading || data?.metrics.active_sources === 0}
            className="h-9 px-4 rounded-xl gap-1.5 bg-[#c8f542] hover:bg-[#d8ff4e] text-black font-semibold text-xs shadow-sm transition-all"
          >
            {runLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlayCircle className="w-3.5 h-3.5" />}
            {runLoading ? "Queuing..." : "Sweep All Active Engines"}
          </Button>
          {runMessage && (
            <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 rounded-lg">
              {runMessage}
            </div>
          )}
        </div>
      </div>

      {/* Worker Offline Alert Banner */}
      {systemStatus && systemStatus.workers_online === 0 && (
        <div className="mb-6 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Background Worker Offline:</strong> No ARQ worker process is currently running. Discovery tasks will remain queued until the worker is started.
            </span>
          </div>
          <span className="font-mono text-[10px] bg-amber-500/20 px-2.5 py-1 rounded-lg text-amber-200 shrink-0">
            arq app.workers.settings.WorkerSettings
          </span>
        </div>
      )}

      {/* Compact High-Density Metrics Cards */}
      {data && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <div className="px-3.5 py-2.5 rounded-xl bg-card/40 border border-white/10 backdrop-blur-md">
            <div className="flex items-center justify-between text-muted-foreground text-[11px] font-medium uppercase tracking-wider mb-1">
              <span>Total Sources</span>
              <Globe className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <div className="text-xl font-bold text-white font-mono">
              {data.metrics.total_sources.toLocaleString()}
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              {data.metrics.active_sources.toLocaleString()} active · {data.metrics.inactive_sources.toLocaleString()} disabled
            </div>
          </div>

          <div className="px-3.5 py-2.5 rounded-xl bg-card/40 border border-white/10 backdrop-blur-md">
            <div className="flex items-center justify-between text-muted-foreground text-[11px] font-medium uppercase tracking-wider mb-1">
              <span>Canonical Jobs</span>
              <Database className="w-3.5 h-3.5 text-[#c8f542]" />
            </div>
            <div className="text-xl font-bold text-[#c8f542] font-mono">
              {data.metrics.total_jobs.toLocaleString()}
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">Persisted and indexed live</div>
          </div>

          <div className="px-3.5 py-2.5 rounded-xl bg-card/40 border border-white/10 backdrop-blur-md">
            <div className="flex items-center justify-between text-muted-foreground text-[11px] font-medium uppercase tracking-wider mb-1">
              <span>Discovery Tasks</span>
              <Activity className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-amber-400 font-mono">
              {data.metrics.running_discovery_tasks} Running
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              {data.metrics.queued_discovery_tasks} in queue · {data.metrics.total_tasks} total
            </div>
          </div>

          <div className="px-3.5 py-2.5 rounded-xl bg-card/40 border border-white/10 backdrop-blur-md">
            <div className="flex items-center justify-between text-muted-foreground text-[11px] font-medium uppercase tracking-wider mb-1">
              <span>Engine Workers</span>
              <Server className="w-3.5 h-3.5 text-purple-400" />
            </div>
            <div className="text-xl font-bold text-purple-400 font-mono">
              {systemStatus.workers_online ?? 1} Online
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              {systemStatus.active_tasks ?? 0} active worker tasks
            </div>
          </div>
        </div>
      )}

      {/* Filter and Search Bar for Engines */}
      <div className="flex flex-col gap-3 p-3.5 rounded-2xl bg-card/40 border border-white/10 backdrop-blur-md mb-6">
        <div className="flex flex-col sm:flex-row items-center gap-3">
          {/* Search Box */}
          <div className="relative flex-1 w-full">
            <Search className="absolute left-3.5 top-3 h-4 w-4 text-muted-foreground" />
            <input
              id="engine-search-input"
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search all 19,154 discovery engines by company domain or URL..."
              className="w-full bg-zinc-950/70 border border-white/10 rounded-xl pl-10 pr-9 py-2 text-xs text-white placeholder:text-muted-foreground focus:outline-none focus:border-[#c8f542]/70 focus:ring-1 focus:ring-[#c8f542]/30 transition-all"
            />
            {search && (
              <button
                onClick={() => {
                  setSearch("");
                  setPage(1);
                }}
                className="absolute right-3 top-2.5 text-zinc-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => { setStatusFilter("all"); setPage(1); }}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                statusFilter === "all"
                  ? "bg-white text-black font-bold border-white"
                  : "bg-white/[0.04] border-white/10 text-zinc-400 hover:text-white"
              }`}
            >
              All
            </button>
            <button
              onClick={() => { setStatusFilter("active"); setPage(1); }}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                statusFilter === "active"
                  ? "bg-emerald-500 text-black font-bold border-emerald-500"
                  : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20"
              }`}
            >
              Active
            </button>
            <button
              onClick={() => { setStatusFilter("inactive"); setPage(1); }}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                statusFilter === "inactive"
                  ? "bg-zinc-700 text-white font-bold border-zinc-500"
                  : "bg-white/[0.04] border-white/10 text-zinc-400 hover:text-white"
              }`}
            >
              Inactive
            </button>
          </div>
        </div>

        {/* ATS Adapter Selector Pills */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-white/[0.04] text-xs">
          <span className="text-muted-foreground text-[11px] font-medium uppercase mr-1">ATS Adapter:</span>
          {ATS_FILTERS.map((f) => {
            const active = selectedAts === f.id;
            const count = data?.ats_counts?.[f.id];
            return (
              <button
                key={f.id}
                onClick={() => {
                  setSelectedAts(f.id);
                  setPage(1);
                }}
                className={`px-2.5 py-0.5 rounded-full border text-[11px] cursor-pointer transition-all flex items-center gap-1 ${
                  active
                    ? "bg-[#c8f542] text-black font-bold border-[#c8f542] shadow-[0_0_8px_rgba(200,245,66,0.2)]"
                    : "bg-white/[0.04] border-white/10 text-zinc-400 hover:text-white hover:bg-white/[0.08]"
                }`}
              >
                <span>{f.label}</span>
                {count !== undefined && (
                  <span
                    className={`font-mono text-[9px] px-1 rounded-full ${
                      active ? "bg-black/20 text-black font-bold" : "bg-white/10 text-zinc-400"
                    }`}
                  >
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Discovery Engines Grid */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Server className="w-4 h-4 text-purple-400" />
          Configured Registry Engines
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-white/10 text-zinc-300 font-mono">
            {totalEngines.toLocaleString()} matching
          </span>
        </h2>
      </div>

      {!data || data.engines.length === 0 ? (
        <div className="bg-card/30 border border-border rounded-2xl p-10 flex flex-col items-center justify-center text-center">
          <Server className="w-10 h-10 text-zinc-600 mb-3" />
          <h3 className="text-base font-medium text-muted-foreground">No Engines Found</h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-md">
            No engines matched your search or adapter filter. Try adjusting your search query.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 pb-6">
          {data.engines.map((engine) => {
            const statusClass = runtimePillClass(engine.runtime.status);
            return (
              <div
                key={engine.id}
                className="bg-card/50 border border-white/10 hover:border-white/20 rounded-2xl p-4 flex flex-col justify-between transition-all backdrop-blur-md group hover:bg-card/70"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <h3 className="font-bold text-zinc-100 text-sm truncate flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
                        {engine.domain}
                      </h3>
                      {engine.start_url && (
                        <a
                          href={engine.start_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-zinc-400 hover:text-[#c8f542] truncate flex items-center gap-1 transition-colors mt-0.5 max-w-xs"
                        >
                          <span className="truncate">{engine.start_url}</span>
                          <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                        </a>
                      )}
                    </div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap font-medium ${
                        engine.is_active
                          ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                          : "text-zinc-400 bg-zinc-800/70 border-zinc-700"
                      }`}
                    >
                      {engine.is_active ? "Active" : "Disabled"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs py-2 border-t border-b border-white/[0.06] my-2.5">
                    <div>
                      <span className="text-[10px] text-muted-foreground uppercase tracking-wider block">Adapter</span>
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 mt-0.5 rounded-md bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[10px] font-mono uppercase font-semibold">
                        {engine.ats_type || "Custom"}
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] text-muted-foreground uppercase tracking-wider block">Runtime</span>
                      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 mt-0.5 rounded-md border font-medium ${statusClass}`}>
                        {engine.runtime.status || "idle"}
                      </span>
                    </div>

                    <div className="col-span-2">
                      <span className="text-[10px] text-muted-foreground uppercase tracking-wider block">Last Swept</span>
                      <span className="text-zinc-300 font-mono text-[11px]">
                        {engine.last_run_at ? new Date(engine.last_run_at).toLocaleString() : "Never swept"}
                      </span>
                    </div>

                    {engine.runtime.error && (
                      <div className="col-span-2">
                        <span className="text-[10px] text-rose-400 uppercase tracking-wider block flex items-center gap-1">
                          <AlertCircle className="w-2.5 h-2.5" /> Discovery Issue
                        </span>
                        <span className="text-rose-300/80 text-[10px] truncate block" title={engine.runtime.error}>
                          {engine.runtime.error}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-end pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSingleScan(engine.id, engine.domain)}
                    disabled={scanningId === engine.id || !engine.is_active}
                    className="h-7 text-xs gap-1.5 border-white/10 hover:border-[#c8f542]/40 hover:text-[#c8f542]"
                  >
                    {scanningId === engine.id ? (
                      <Loader2 className="w-3 h-3 animate-spin text-[#c8f542]" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    Scan Board
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Toolbar */}
      {totalEngines > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 bg-card/40 rounded-2xl border border-white/10 text-xs">
          <div className="flex flex-wrap items-center gap-3 text-zinc-400">
            <div>
              Showing page <span className="font-semibold text-white">{page}</span> of{" "}
              <span className="font-semibold text-white">{totalPages}</span>{" "}
              (<span className="text-[#c8f542] font-semibold">{totalEngines.toLocaleString()}</span> engines)
            </div>

            <div className="flex items-center gap-2 pl-3 border-l border-white/10">
              <label htmlFor="engines-rows-input" className="text-zinc-400 text-xs font-medium cursor-pointer">
                Rows:
              </label>
              <input
                id="engines-rows-input"
                type="number"
                min={1}
                max={100}
                value={limitInput}
                onChange={(e) => setLimitInput(e.target.value)}
                onBlur={handleLimitCommit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handleLimitCommit();
                    (e.target as HTMLInputElement).blur();
                  }
                }}
                className="w-16 h-7 bg-zinc-950/80 border border-white/15 rounded-lg px-2 text-xs text-white text-center font-mono focus:outline-none focus:border-[#c8f542] focus:ring-1 focus:ring-[#c8f542]/40 transition-all"
                title="Enter rows per page and press Enter"
              />
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="h-8 gap-1 text-xs border-white/10 disabled:opacity-40 hover:border-[#c8f542]/40"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </Button>
            <div className="px-3 py-1 font-mono text-zinc-400">
              {page} / {totalPages}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="h-8 gap-1 text-xs border-white/10 disabled:opacity-40 hover:border-[#c8f542]/40"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
