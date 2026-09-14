"use client";

import React, { useState } from "react";
import { UserCircle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAppState } from "@/components/providers";

export function ProfileDialog() {
  const { profileName, setProfileName } = useAppState();
  const [tempName, setTempName] = useState(profileName);
  const [keywords, setKeywords] = useState("");
  const [locations, setLocations] = useState("");
  const [open, setOpen] = useState(false);

  // Load from API on open
  React.useEffect(() => {
    if (open) {
      fetch("http://127.0.0.1:8000/system/profile")
        .then(res => res.json())
        .then(data => {
          setTempName(data.name || "");
          setKeywords((data.keywords || []).join(", "));
          setLocations((data.locations || []).join(", "));
        })
        .catch(console.error);
    }
  }, [open]);

  const handleSave = async () => {
    const kwArray = keywords.split(",").map(k => k.trim()).filter(Boolean);
    const locArray = locations.split(",").map(l => l.trim()).filter(Boolean);
    
    try {
      await fetch("http://127.0.0.1:8000/system/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: tempName, keywords: kwArray, locations: locArray })
      });
      setProfileName(tempName);
      setOpen(false);
      // Trigger a reload to fetch sorted jobs
      window.dispatchEvent(new Event('profileUpdated'));
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/5 transition-colors">
        <UserCircle className="w-5 h-5 text-zinc-400" />
        <span className="text-sm font-medium text-zinc-300 hidden sm:block">{profileName || "User"}</span>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md bg-zinc-950 border-zinc-800 text-white">
        <DialogHeader>
          <DialogTitle>Edit Profile & Matching Criteria</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-4">
          <div className="flex flex-col gap-2">
            <label className="text-sm text-zinc-400">Profile Name</label>
            <Input 
              value={tempName}
              onChange={(e) => setTempName(e.target.value)}
              className="bg-zinc-900 border-zinc-800"
              placeholder="e.g. Sannos"
            />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm text-zinc-400">Keywords (comma separated)</label>
            <Input 
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="bg-zinc-900 border-zinc-800"
              placeholder="e.g. React, Next.js, Python"
            />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-sm text-zinc-400">Locations (comma separated)</label>
            <Input 
              value={locations}
              onChange={(e) => setLocations(e.target.value)}
              className="bg-zinc-900 border-zinc-800"
              placeholder="e.g. Remote, San Francisco"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={handleSave}>Save</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
