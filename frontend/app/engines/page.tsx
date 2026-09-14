"use client";

import { Activity, Server, Zap, ShieldCheck, Cpu, Globe, Search, ArrowRight, Gauge, Database, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTaskStream } from "@/hooks/useTaskStream";

type EngineData = {
  metrics: {
    total_jobs: number;
    total_sources: number;
    total_tasks: number;
  };
  adapters: {
    name: string;
    status: string;
    type: string;
    latency?: string;
    requests?: string;
  }[];
};

export default function EnginesPage() {
  const [data, setData] = useState<EngineData | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Track discovery task
  const [discoveryTaskId, setDiscoveryTaskId] = useState<string | null>(null);
  const taskStream = useTaskStream(discoveryTaskId);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get<EngineData>("/engines/metrics");
        setData(res);
      } catch (err) {
        console.error("Failed to fetch engine metrics", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleRunDiscovery = async () => {
    if (taskStream.isActive) return;
    try {
      const res = await api.post<{task_id: string}>("/tasks/?target_id=global_discovery_run&worker_type=discovery_task");
      setDiscoveryTaskId(res.task_id);
    } catch (err) {
      console.error(err);
      alert("Failed to start discovery task");
    }
  };

  if (loading || !data) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  const isRunning = taskStream.isActive;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full flex flex-col overflow-y-auto">
      <div className="flex items-end justify-between mb-10">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-white flex items-center gap-3 mb-2">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Activity className="w-8 h-8 text-purple-400" />
            </div>
            Pipeline & Engines
          </h1>
          <p className="text-zinc-400 text-lg">Monitor active discovery strategies, adapter health, and system boundaries.</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {discoveryTaskId && (
            <div className="text-sm font-medium text-purple-400 flex items-center gap-2">
              Status: {taskStream.status}
              {taskStream.status === 'FAILED' && <span className="text-red-400">- Failed</span>}
              {taskStream.status === 'SUCCEEDED' && <span className="text-green-400">- Success</span>}
            </div>
          )}
          <button 
            onClick={handleRunDiscovery}
            disabled={isRunning}
            className="px-5 py-2.5 flex items-center gap-2 text-sm font-semibold text-white bg-purple-600 rounded-lg hover:bg-purple-500 transition-all shadow-[0_0_20px_rgba(168,85,247,0.3)] hover:shadow-[0_0_30px_rgba(168,85,247,0.5)] disabled:opacity-50 disabled:cursor-not-allowed">
            {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {isRunning ? "Running..." : "Run Global Discovery"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <div className="bg-gradient-to-br from-zinc-900 to-zinc-950 border border-white/10 rounded-2xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl -mr-10 -mt-10 transition-all group-hover:bg-blue-500/20" />
          <div className="flex items-center gap-4 mb-4 relative z-10">
            <div className="p-3 bg-blue-500/10 rounded-xl">
              <Globe className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <div className="text-sm font-medium text-zinc-400">Total Scanned Sources</div>
              <div className="text-3xl font-bold text-white">{data.metrics.total_sources.toLocaleString()}</div>
            </div>
          </div>
          <div className="text-sm text-blue-400 flex items-center gap-1">
            <TrendingUpIcon /> Registered in Registry
          </div>
        </div>
        
        <div className="bg-gradient-to-br from-zinc-900 to-zinc-950 border border-white/10 rounded-2xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/10 rounded-full blur-3xl -mr-10 -mt-10 transition-all group-hover:bg-green-500/20" />
          <div className="flex items-center gap-4 mb-4 relative z-10">
            <div className="p-3 bg-green-500/10 rounded-xl">
              <Database className="w-6 h-6 text-green-400" />
            </div>
            <div>
              <div className="text-sm font-medium text-zinc-400">Total Valid Jobs</div>
              <div className="text-3xl font-bold text-white">{data.metrics.total_jobs.toLocaleString()}</div>
            </div>
          </div>
          <div className="text-sm text-green-400 flex items-center gap-1">
            <TrendingUpIcon /> Ready for mapping
          </div>
        </div>

        <div className="bg-gradient-to-br from-zinc-900 to-zinc-950 border border-white/10 rounded-2xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-full blur-3xl -mr-10 -mt-10 transition-all group-hover:bg-amber-500/20" />
          <div className="flex items-center gap-4 mb-4 relative z-10">
            <div className="p-3 bg-amber-500/10 rounded-xl">
              <Activity className="w-6 h-6 text-amber-400" />
            </div>
            <div>
              <div className="text-sm font-medium text-zinc-400">Tasks Executed</div>
              <div className="text-3xl font-bold text-white">{data.metrics.total_tasks.toLocaleString()}</div>
            </div>
          </div>
          <div className="text-sm text-amber-400 flex items-center gap-1">
            All pipelines
          </div>
        </div>
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">ATS Adapter Registry</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
        {data.adapters.map((adapter) => (
          <div key={adapter.name} className="bg-zinc-900/50 border border-white/5 hover:border-white/20 transition-colors rounded-xl p-5 flex flex-col cursor-default">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
                  <Server className="w-5 h-5 text-zinc-300" />
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-100">{adapter.name}</h3>
                  <div className="flex items-center gap-1.5 text-xs text-green-400">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    {adapter.status}
                  </div>
                </div>
              </div>
              <span className="text-xs font-medium px-2 py-1 bg-zinc-800 text-zinc-400 rounded">v1.2</span>
            </div>
            <div className="mt-auto space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-zinc-500">Acquisition Method</span>
                <span className="text-zinc-300 font-medium">{adapter.type}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-zinc-500">Avg Latency</span>
                <span className="text-zinc-300 font-medium">{adapter.latency}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-zinc-500">24h Requests</span>
                <span className="text-zinc-300 font-medium">{adapter.requests}</span>
              </div>
            </div>
          </div>
        ))}
        
        <div className="border border-dashed border-white/10 hover:border-white/30 hover:bg-white/[0.02] transition-colors rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer min-h-[180px]">
          <div className="w-12 h-12 rounded-full bg-zinc-900 flex items-center justify-center mb-3">
            <div className="text-2xl font-light text-zinc-500">+</div>
          </div>
          <div className="font-medium text-zinc-400">Register New Adapter</div>
        </div>
      </div>
      
      <div className="bg-zinc-900/30 border border-white/5 rounded-2xl p-6">
        <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-zinc-400" />
          Pipeline Configuration
        </h2>
        
        <div className="space-y-4">
          {[
            { name: "Browser Fallback Policy", desc: "Allow JS rendering when HTTP acquisition fails", active: true },
            { name: "Strict Domain Boundary", desc: "Prevent navigation outside of origin domain", active: true },
            { name: "Rate Limiting", desc: "Enforce exponential backoff on 429s", active: true },
            { name: "Local SSRF Protection", desc: "Block internal IPs and AWS metadata endpoints", active: true },
          ].map((setting, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b border-white/5 last:border-0">
              <div>
                <div className="font-medium text-zinc-200">{setting.name}</div>
                <div className="text-sm text-zinc-500">{setting.desc}</div>
              </div>
              <div className={`w-12 h-6 rounded-full transition-colors relative ${setting.active ? 'bg-purple-500' : 'bg-zinc-700'}`}>
                <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${setting.active ? 'left-7' : 'left-1'}`} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TrendingUpIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}
