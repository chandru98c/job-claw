"use client";

import React, { useEffect, useState } from "react";
import { UserCircle, Settings, Plus, Check } from "lucide-react";
import { 
  DropdownMenu, 
  DropdownMenuTrigger, 
  DropdownMenuContent, 
  DropdownMenuLabel, 
  DropdownMenuItem, 
  DropdownMenuSeparator,
  DropdownMenuGroup
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useAppState } from "@/components/providers";

type ProfileInfo = {
  id: string;
  name: string;
};

export function ProfileSwitcher({ onEditActiveProfile }: { onEditActiveProfile: () => void }) {
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const { profileName, setProfileName } = useAppState();
  const [activeId, setActiveId] = useState<string | null>(null);
  
  useEffect(() => {
    const currentId = localStorage.getItem("active_profile_id");
    setActiveId(currentId);
    fetchProfiles();
  }, []);
  
  const fetchProfiles = async () => {
    try {
      const data = await api.get<ProfileInfo[]>("/profiles");
      setProfiles(data);
      
      const currentId = localStorage.getItem("active_profile_id");
      if (currentId) {
        const active = data.find(p => p.id === currentId);
        if (active) setProfileName(active.name);
      } else if (data.length > 0) {
        // Auto-select first if none selected
        handleSwitch(data[0].id, data[0].name);
      }
    } catch (e) {
      console.error("Failed to load profiles", e);
    }
  };

  const handleSwitch = (id: string, name: string) => {
    localStorage.setItem("active_profile_id", id);
    setActiveId(id);
    setProfileName(name);
    window.dispatchEvent(new Event('profileUpdated'));
  };

  const handleCreate = async () => {
    const name = prompt("Enter a name for the new profile (e.g. Frontend Dev):");
    if (!name) return;
    
    try {
      const newProfile = await api.post<ProfileInfo>("/profiles", { name });
      setProfiles([...profiles, newProfile]);
      handleSwitch(newProfile.id, newProfile.name);
      // Let them edit it right away
      setTimeout(() => onEditActiveProfile(), 100);
    } catch (e) {
      alert("Failed to create profile");
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/5 transition-colors focus:outline-none focus:ring-1 focus:ring-green-500/50">
        <UserCircle className="w-5 h-5 text-zinc-400" />
        <span className="text-sm font-medium text-zinc-300 hidden sm:block max-w-[120px] truncate">
          {profileName || "Select Profile"}
        </span>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent align="end" className="w-56 bg-zinc-950 border-zinc-800 text-white">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-zinc-400">Switch Profile</DropdownMenuLabel>
          
          {profiles.map(p => (
            <DropdownMenuItem 
              key={p.id} 
              onClick={() => handleSwitch(p.id, p.name)}
              className="flex items-center justify-between cursor-pointer hover:bg-zinc-800"
            >
              <span className="truncate">{p.name}</span>
              {activeId === p.id && <Check className="w-4 h-4 text-green-500 shrink-0" />}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        
        <DropdownMenuSeparator className="bg-zinc-800" />
        
        <DropdownMenuGroup>
          <DropdownMenuItem onClick={handleCreate} className="cursor-pointer text-green-400 focus:text-green-300 hover:bg-zinc-800">
            <Plus className="w-4 h-4 mr-2" />
            Create Profile
          </DropdownMenuItem>
          
          <DropdownMenuItem onClick={onEditActiveProfile} className="cursor-pointer hover:bg-zinc-800" disabled={!activeId}>
            <Settings className="w-4 h-4 mr-2" />
            Edit Current Profile
          </DropdownMenuItem>
        </DropdownMenuGroup>
        
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
