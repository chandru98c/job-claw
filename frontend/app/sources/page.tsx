"use client";

import { useEffect, useState } from "react";
import { Database, Loader2, Server, ExternalLink, Globe } from "lucide-react";

type SourceResponse = {
  id: string;
  domain: string;
  start_url: string | null;
  is_active: boolean;
  last_run_at: string | null;
  ats_type: string | null;
};

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSources = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/sources");
        if (res.ok) {
          const data = await res.json();
          setSources(data);
        }
      } catch (err) {
        console.error("Failed to fetch sources", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSources();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full flex flex-col">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-2">
            <Database className="w-6 h-6 text-green-400" />
            Source Registry
          </h1>
          <p className="text-zinc-400">Manage companies and trigger on-demand job discovery.</p>
        </div>
        <button className="px-4 py-2 text-sm font-medium text-black bg-green-500 rounded-md hover:bg-green-400 transition-colors">
          + Add Source
        </button>
      </div>

      <div className="flex-1 bg-black/40 border border-white/[0.05] rounded-xl overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex flex-col items-center justify-center flex-1 py-20">
            <Loader2 className="w-8 h-8 text-green-500 animate-spin mb-4" />
            <p className="text-zinc-500">Loading sources registry...</p>
          </div>
        ) : (
          <div className="overflow-y-auto max-h-[70vh]">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-white/[0.02] border-b border-white/[0.05] sticky top-0 backdrop-blur-md">
                <tr>
                  <th className="px-6 py-4 font-medium text-zinc-300">Domain</th>
                  <th className="px-6 py-4 font-medium text-zinc-300">ATS Type</th>
                  <th className="px-6 py-4 font-medium text-zinc-300">Status</th>
                  <th className="px-6 py-4 font-medium text-zinc-300">Last Synced</th>
                  <th className="px-6 py-4 font-medium text-zinc-300 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {sources.map((source) => (
                  <tr key={source.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <Globe className="w-4 h-4 text-zinc-500" />
                        <span className="font-medium text-white">{source.domain}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {source.ats_type ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-purple-500/10 text-purple-400 text-xs font-medium">
                          <Server className="w-3.5 h-3.5" />
                          {source.ats_type.toUpperCase()}
                        </span>
                      ) : (
                        <span className="text-zinc-500">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {source.is_active ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-green-500/10 text-green-400 text-xs font-medium">
                          <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-red-500/10 text-red-400 text-xs font-medium">
                          <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
                          Disabled
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-zinc-400">
                      {source.last_run_at ? new Date(source.last_run_at).toLocaleString() : "Never"}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="text-zinc-400 hover:text-green-400 transition-colors p-1" title="Scan Now">
                        <ExternalLink className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {sources.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-zinc-500">
                      No sources found in the registry.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
