"use client";

import { useState, useEffect } from "react";
import { JobCard } from "@/components/jobs/job-card";
import { Sparkles, SlidersHorizontal, ArrowDownWideNarrow, Search, MapPin, Loader2, AlertCircle } from "lucide-react";
import { useSearchMode, useAppState } from "@/components/providers";
import { api } from "@/lib/api";

type JobResponse = {
  id: string;
  title: string;
  company_name: string;
  location: string | null;
  job_type: string | null;
  canonical_apply_url: string;
  status: string;
  matchScore: number | null;
  matchReasons: string[] | null;
  timeAgo: string;
};

export default function Home() {
  const { isOpenSearch } = useSearchMode();
  const { apiMode } = useAppState();
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Search states
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [remote, setRemote] = useState(false);

  const fetchJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      let endpoint = "/jobs";
      
      if (isOpenSearch) {
        const params = new URLSearchParams();
        if (q) params.append("q", q);
        if (location) params.append("location", location);
        if (remote) params.append("remote", "true");
        endpoint = `/jobs?${params.toString()}`;
      } else {
        endpoint = `/jobs/match`;
      }
      
      const res = await api.get<{items: JobResponse[]}>(endpoint);
      setJobs(res.items || []);
    } catch (e: any) {
      console.error("Failed to fetch jobs", e);
      setError(e.message || "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    
    // Listen for custom event from ProfileDialog
    const handleProfileUpdate = () => fetchJobs();
    window.addEventListener('profileUpdated', handleProfileUpdate);
    return () => window.removeEventListener('profileUpdated', handleProfileUpdate);
  }, [apiMode, isOpenSearch]);

  // Debounced search trigger (naive for now, or just enter key)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      fetchJobs();
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full flex flex-col">
      {/* Header Area */}
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
        {isOpenSearch ? (
          <div className="w-full">
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-4">
              <Search className="w-6 h-6 text-green-400" />
              Open Search
            </h1>
            <div className="flex flex-col md:flex-row gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
                <input 
                  type="text" 
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Job title, keywords, or company (Press Enter to search)" 
                  className="w-full bg-black/40 border border-white/10 rounded-md pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-green-500/50"
                />
              </div>
              <div className="relative flex-1">
                <MapPin className="absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
                <input 
                  type="text" 
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="City, state, or zip code (Press Enter to search)" 
                  className="w-full bg-black/40 border border-white/10 rounded-md pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-green-500/50"
                />
              </div>
              <div className="flex items-center gap-2 px-3 border border-white/10 rounded-md bg-black/40 h-9">
                <input 
                  type="checkbox" 
                  id="remote" 
                  checked={remote}
                  onChange={(e) => {
                    setRemote(e.target.checked);
                    // Slight hack to fetch immediately on checkbox
                    setTimeout(fetchJobs, 50);
                  }}
                  className="rounded bg-zinc-900 border-white/10 text-green-500 focus:ring-green-500 focus:ring-offset-black" 
                />
                <label htmlFor="remote" className="text-sm text-zinc-300 whitespace-nowrap">Remote Only</label>
              </div>
            </div>
          </div>
        ) : (
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2 mb-2">
              <Sparkles className="w-6 h-6 text-green-400" />
              Discover
            </h1>
            <p className="text-zinc-400">Curated opportunities matching your active profile.</p>
          </div>
        )}
        
        <div className="flex items-center gap-3 shrink-0">
          <button className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-zinc-300 bg-zinc-900 border border-white/10 rounded-md hover:bg-white/5 transition-colors h-9">
            <SlidersHorizontal className="w-4 h-4" />
            Filters
          </button>
          <button className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-zinc-300 bg-zinc-900 border border-white/10 rounded-md hover:bg-white/5 transition-colors h-9">
            <ArrowDownWideNarrow className="w-4 h-4" />
            Sort: {isOpenSearch ? 'Recent' : 'Match Score'}
          </button>
        </div>
      </div>

      {/* Job Feed */}
      <div className="flex-1 overflow-y-auto pr-2 pb-8 space-y-4">
        {loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-20 bg-red-500/10 rounded-xl border border-red-500/20">
            <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-4" />
            <p className="text-red-400 font-medium">{error}</p>
            <button onClick={fetchJobs} className="mt-4 px-4 py-2 bg-red-500/20 text-red-400 rounded-md hover:bg-red-500/30 transition-colors">Try Again</button>
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-20 bg-zinc-900/30 rounded-xl border border-zinc-800/50">
            <p className="text-zinc-400">No matching jobs found. Try adjusting your profile keywords or run the scraper.</p>
          </div>
        ) : (
          jobs.map(job => (
            <JobCard 
              key={job.id}
              title={job.title}
              company={job.company_name}
              location={job.location || "Remote"}
              source={job.status === "ACTIVE" ? "Direct" : job.status}
              matchScore={job.matchScore}
              matchReasons={job.matchReasons}
              timeAgo={job.timeAgo}
              type={job.job_type || "Full-time"}
              hideMatchScore={isOpenSearch}
              onApply={() => console.log(`Applying to ${job.id}`)}
            />
          ))
        )}

        {!loading && jobs.length > 0 && (
          <div className="py-8 text-center">
            <p className="text-sm text-zinc-500">
              {isOpenSearch ? "End of search results." : "You've reached the end of your matched feed."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
