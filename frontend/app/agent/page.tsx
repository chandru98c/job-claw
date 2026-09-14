"use client";

import { Bot, Play, Pause, Settings, CheckCircle2, AlertCircle, Clock, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

export default function AgentPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const applications: any[] = [];

  if (!mounted) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full flex flex-col overflow-y-auto">
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-white flex items-center gap-3 mb-2">
            <div className="p-2 bg-orange-500/10 rounded-lg">
              <Bot className="w-8 h-8 text-orange-400" />
            </div>
            Auto-Apply Agent
          </h1>
          <p className="text-zinc-400 text-lg">Autonomous Playwright form-filler and application tracking system.</p>
        </div>
        
        <div className="flex items-center gap-3 bg-zinc-900/50 p-1.5 rounded-xl border border-white/5 opacity-50 cursor-not-allowed">
          <button disabled className="flex items-center gap-2 px-4 py-2 bg-orange-500/50 text-white font-medium rounded-lg transition-colors shadow-[0_0_15px_rgba(249,115,22,0.1)]">
            <Play className="w-4 h-4 fill-current" />
            Start Agent
          </button>
          <button disabled className="flex items-center gap-2 px-4 py-2 bg-zinc-800 text-zinc-500 font-medium rounded-lg transition-colors">
            <Pause className="w-4 h-4 fill-current" />
            Pause
          </button>
          <button disabled className="p-2 text-zinc-600">
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Kanban Column: Queued */}
        <div className="bg-zinc-900/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-zinc-300 flex items-center gap-2">
              <Clock className="w-4 h-4 text-zinc-500" />
              Queued
            </h3>
            <span className="bg-zinc-800 text-zinc-400 text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
            <p className="text-sm text-zinc-600">Awaiting Phase 10 implementation.</p>
          </div>
        </div>

        {/* Kanban Column: In Progress */}
        <div className="bg-zinc-900/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-white flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-orange-500/30" />
              In Progress
            </h3>
            <span className="bg-orange-500/5 border border-orange-500/10 text-orange-400/50 text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
            <p className="text-sm text-zinc-600">No active playwright tasks.</p>
          </div>
        </div>

        {/* Kanban Column: Submitted */}
        <div className="bg-zinc-900/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-zinc-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500/50" />
              Submitted
            </h3>
            <span className="bg-zinc-800 text-zinc-400 text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
             <p className="text-sm text-zinc-600">No applications submitted yet.</p>
          </div>
        </div>

        {/* Kanban Column: Failed / Action Required */}
        <div className="bg-zinc-900/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-zinc-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-500/50" />
              Action Required
            </h3>
            <span className="bg-red-500/5 border border-red-500/10 text-red-400/50 text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
             <p className="text-sm text-zinc-600">No failed tasks.</p>
          </div>
        </div>
      </div>

      <div className="bg-zinc-900/40 border border-white/5 rounded-2xl p-6 flex flex-col md:flex-row gap-6 items-center">
        <div className="w-16 h-16 rounded-2xl bg-zinc-800 flex items-center justify-center flex-shrink-0">
          <Bot className="w-8 h-8 text-zinc-400" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-white mb-2">Agent Status: Paused</h2>
          <p className="text-zinc-400">
            The Playwright form-filler is currently idle. Configure your Auto-Apply criteria in settings, then start the agent to let Job-Claw automatically navigate ATS portals and submit applications on your behalf using your synced Candidate Profile.
          </p>
        </div>
      </div>
    </div>
  );
}

function AppCard({ app, active = false }: { app: any, active?: boolean }) {
  return (
    <div className={`bg-zinc-900 border rounded-xl p-4 transition-all cursor-pointer group ${active ? 'border-orange-500/50 shadow-[0_0_15px_rgba(249,115,22,0.15)]' : 'border-white/5 hover:border-white/20'}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg font-bold flex-shrink-0 ${active ? 'bg-orange-500 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
          {app.logo}
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="font-medium text-zinc-100 truncate">{app.role}</h4>
          <div className="text-sm text-zinc-500 truncate mb-2">{app.company}</div>
          
          <div className="flex items-center justify-between text-xs">
            <span className={
              app.status === 'in_progress' ? 'text-orange-400 font-medium' :
              app.status === 'submitted' ? 'text-green-400' :
              app.status === 'failed' ? 'text-red-400' : 'text-zinc-500'
            }>
              {app.time}
            </span>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </div>
        </div>
      </div>
      
      {active && (
        <div className="mt-4 pt-3 border-t border-white/5">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-zinc-400">Filling Experience...</span>
            <span className="text-orange-400">65%</span>
          </div>
          <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div className="h-full bg-orange-500 w-[65%] rounded-full relative">
              <div className="absolute inset-0 bg-white/20 animate-pulse" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
