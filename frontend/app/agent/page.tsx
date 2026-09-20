"use client";

import { Bot, Play, Pause, Settings, CheckCircle2, AlertCircle, Clock, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export default function AgentPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const applications: any[] = [];

  if (!mounted) return null;

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto w-full px-6 py-8 overflow-y-auto">
      <div className="flex flex-col md:flex-row md:items-end justify-between mb-10 gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-white flex items-center gap-3 mb-2">
            <div className="p-2 bg-orange-500/10 rounded-[24px]">
              <Bot className="w-8 h-8 text-orange-400" />
            </div>
            Auto-Apply Agent
          </h1>
          <p className="text-muted-foreground text-lg">Autonomous Playwright form-filler and application tracking system.</p>
        </div>
        
        <div className="flex items-center gap-3 bg-card/50 p-1.5 rounded-full border border-border opacity-50 cursor-not-allowed">
          <Button disabled className="gap-2 rounded-full">
            <Play className="w-4 h-4 fill-current" />
            Start Agent
          </Button>
          <Button disabled variant="outline" className="gap-2 rounded-full">
            <Pause className="w-4 h-4 fill-current" />
            Pause
          </Button>
          <Button disabled variant="ghost" size="icon" className="rounded-full">
            <Settings className="w-5 h-5" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Kanban Column: Queued */}
        <div className="bg-card/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-muted-foreground flex items-center gap-2">
              <Clock className="w-4 h-4 text-muted-foreground" />
              Queued
            </h3>
            <span className="bg-zinc-800 text-muted-foreground text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
            <p className="text-sm text-zinc-600">Awaiting Phase 10 implementation.</p>
          </div>
        </div>

        {/* Kanban Column: In Progress */}
        <div className="bg-card/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
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
        <div className="bg-card/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-muted-foreground flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-primary/50" />
              Submitted
            </h3>
            <span className="bg-zinc-800 text-muted-foreground text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
             <p className="text-sm text-zinc-600">No applications submitted yet.</p>
          </div>
        </div>

        {/* Kanban Column: Failed / Action Required */}
        <div className="bg-card/30 rounded-2xl p-5 border border-white/[0.05] flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-muted-foreground flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-destructive/50" />
              Action Required
            </h3>
            <span className="bg-destructive/5 border border-destructive/10 text-destructive/50 text-xs px-2 py-0.5 rounded-full">0</span>
          </div>
          
          <div className="space-y-3 flex-1 flex items-center justify-center text-center">
             <p className="text-sm text-zinc-600">No failed tasks.</p>
          </div>
        </div>
      </div>

      <div className="bg-card/40 border border-border rounded-2xl p-6 flex flex-col md:flex-row gap-6 items-center">
        <div className="w-16 h-16 rounded-2xl bg-zinc-800 flex items-center justify-center flex-shrink-0">
          <Bot className="w-8 h-8 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-white mb-2">Agent Status: Paused</h2>
          <p className="text-muted-foreground">
            The Playwright form-filler is currently idle. Configure your Auto-Apply criteria in settings, then start the agent to let Job-Claw automatically navigate ATS portals and submit applications on your behalf using your synced Candidate Profile.
          </p>
        </div>
      </div>
    </div>
  );
}

function AppCard({ app, active = false }: { app: any, active?: boolean }) {
  return (
    <div className={`bg-card border rounded-[24px] p-4 transition-all cursor-pointer group ${active ? 'border-orange-500/50 shadow-[0_0_15px_rgba(249,115,22,0.15)]' : 'border-border hover:border-white/20'}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-[24px] flex items-center justify-center text-lg font-bold flex-shrink-0 ${active ? 'bg-orange-500 text-white' : 'bg-zinc-800 text-muted-foreground'}`}>
          {app.logo}
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="font-medium text-zinc-100 truncate">{app.role}</h4>
          <div className="text-sm text-muted-foreground truncate mb-2">{app.company}</div>
          
          <div className="flex items-center justify-between text-xs">
            <span className={
              app.status === 'in_progress' ? 'text-orange-400 font-medium' :
              app.status === 'submitted' ? 'text-primary' :
              app.status === 'failed' ? 'text-destructive' : 'text-muted-foreground'
            }>
              {app.time}
            </span>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-muted-foreground transition-colors" />
          </div>
        </div>
      </div>
      
      {active && (
        <div className="mt-4 pt-3 border-t border-border">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-muted-foreground">Filling Experience...</span>
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
