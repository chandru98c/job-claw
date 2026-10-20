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
    <div className="flex flex-col max-w-6xl mx-auto w-full px-4 sm:px-6 py-8 relative">
      {/* Ambient Top Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[850px] h-[300px] bg-gradient-to-b from-[#c8f542]/[0.07] via-[#c8f542]/[0.02] to-transparent blur-3xl pointer-events-none -z-10" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
            <Bot className="w-7 h-7 text-[#c8f542] shrink-0" />
            Auto-Apply Workflow
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Application preparation, review, and submission pipeline.
          </p>
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
