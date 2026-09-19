"use client";

import React, { useState, useRef } from "react";
import { UserCircle, Upload, X, Plus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAppState } from "@/components/providers";
import { api } from "@/lib/api";

// Array input component
function ArrayInput({ label, value, onChange, placeholder }: { label: string, value: string[], onChange: (v: string[]) => void, placeholder: string }) {
  const [inputValue, setInputValue] = useState("");

  const handleAdd = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed]);
      setInputValue("");
    }
  };

  const handleRemove = (item: string) => {
    onChange(value.filter(v => v !== item));
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm text-zinc-400">{label}</label>
      <div className="flex gap-2">
        <Input 
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          className="bg-zinc-900 border-zinc-800"
          placeholder={placeholder}
        />
        <Button type="button" onClick={handleAdd} variant="secondary" size="icon" className="shrink-0"><Plus className="w-4 h-4" /></Button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {value.map(item => (
            <div key={item} className="flex items-center gap-1 bg-zinc-800 px-2 py-1 rounded-md text-sm">
              <span>{item}</span>
              <button type="button" onClick={() => handleRemove(item)} className="text-zinc-400 hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProfileDialog({ open, onOpenChange }: { open: boolean, onOpenChange: (open: boolean) => void }) {
  const { profileName, setProfileName } = useAppState();
  
  const [formData, setFormData] = useState({
    name: "", email: "", phone: "", location: "", tagline: "", about: "",
    skills: [] as string[], interested_fields: [] as string[],
    preferred_locations: [] as string[], preferred_job_types: [] as string[],
    resume_path: ""
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load from API on open
  React.useEffect(() => {
    if (open) {
      setError("");
      setSuccess(false);
      api.get("/profiles/me")
        .then((data: any) => {
          setFormData({
            name: data.name || "",
            email: data.email || "",
            phone: data.phone || "",
            location: data.location || "",
            tagline: data.tagline || "",
            about: data.about || "",
            skills: data.skills || [],
            interested_fields: data.interested_fields || [],
            preferred_locations: data.preferred_locations || [],
            preferred_job_types: data.preferred_job_types || [],
            resume_path: data.resume_path || ""
          });
        })
        .catch(err => setError("Failed to load profile: " + err.message));
    }
  }, [open]);

  const handleChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setSuccess(false);
  };

  const handleSave = async () => {
    if (!formData.name) {
      setError("Name is required");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess(false);
    
    try {
      const updated: any = await api.put("/profiles/me", formData);
      setProfileName(updated.name);
      setSuccess(true);
      window.dispatchEvent(new Event('profileUpdated'));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setLoading(true);
    setError("");
    
    const formDataObj = new FormData();
    formDataObj.append("file", file);
    
    const activeProfileId = typeof window !== 'undefined' ? localStorage.getItem('active_profile_id') : null;
    
    try {
      const res = await fetch(`${api.baseUrl}/profiles/me/resume`, {
        method: "POST",
        headers: {
          ...(activeProfileId ? { "X-Profile-ID": activeProfileId } : {})
        },
        body: formDataObj
      });
      if (!res.ok) throw new Error("Failed to upload resume");
      
      const data = await res.json();
      handleChange("resume_path", data.resume_path);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-zinc-950 border-zinc-800 text-white max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Profile & Settings</DialogTitle>
        </DialogHeader>
        
        {error && <div className="p-3 bg-red-900/50 border border-red-500/50 text-red-200 rounded-md text-sm">{error}</div>}
        {success && <div className="p-3 bg-emerald-900/50 border border-emerald-500/50 text-emerald-200 rounded-md text-sm">Profile saved successfully!</div>}
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 py-4">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Basic Info</h3>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">Full Name *</label>
              <Input value={formData.name} onChange={(e) => handleChange("name", e.target.value)} className="bg-zinc-900 border-zinc-800" />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">Email</label>
              <Input value={formData.email} onChange={(e) => handleChange("email", e.target.value)} className="bg-zinc-900 border-zinc-800" type="email" />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">Phone</label>
              <Input value={formData.phone} onChange={(e) => handleChange("phone", e.target.value)} className="bg-zinc-900 border-zinc-800" type="tel" />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">Location</label>
              <Input value={formData.location} onChange={(e) => handleChange("location", e.target.value)} className="bg-zinc-900 border-zinc-800" />
            </div>
          </div>
          
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Professional</h3>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">Tagline / Title</label>
              <Input value={formData.tagline} onChange={(e) => handleChange("tagline", e.target.value)} className="bg-zinc-900 border-zinc-800" placeholder="e.g. Senior Software Engineer" />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-sm text-zinc-400">About (Bio)</label>
              <Textarea value={formData.about} onChange={(e) => handleChange("about", e.target.value)} className="bg-zinc-900 border-zinc-800 min-h-[120px]" />
            </div>
            
            <div className="flex flex-col gap-2 pt-2">
              <label className="text-sm text-zinc-400 flex items-center justify-between">
                Resume (PDF)
                {formData.resume_path && <span className="text-xs text-emerald-400">Uploaded</span>}
              </label>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" className="w-full bg-zinc-900 border-zinc-800 hover:bg-zinc-800" onClick={() => fileInputRef.current?.click()} disabled={loading}>
                  <Upload className="w-4 h-4 mr-2" />
                  {formData.resume_path ? "Replace Resume" : "Upload Resume"}
                </Button>
                <input type="file" ref={fileInputRef} className="hidden" accept=".pdf,.doc,.docx" onChange={handleFileUpload} />
              </div>
            </div>
          </div>
          
          <div className="col-span-1 md:col-span-2 space-y-4 pt-4 border-t border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Matching Preferences</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <ArrayInput 
                label="Skills" 
                value={formData.skills} 
                onChange={(v) => handleChange("skills", v)} 
                placeholder="e.g. Python" 
              />
              <ArrayInput 
                label="Interested Fields" 
                value={formData.interested_fields} 
                onChange={(v) => handleChange("interested_fields", v)} 
                placeholder="e.g. Backend, AI" 
              />
              <ArrayInput 
                label="Preferred Locations" 
                value={formData.preferred_locations} 
                onChange={(v) => handleChange("preferred_locations", v)} 
                placeholder="e.g. Remote, NYC" 
              />
              <ArrayInput 
                label="Preferred Job Types" 
                value={formData.preferred_job_types} 
                onChange={(v) => handleChange("preferred_job_types", v)} 
                placeholder="e.g. Full-time, Contract" 
              />
            </div>
          </div>
        </div>
        
        <div className="flex justify-end gap-2 pt-4 border-t border-zinc-800 mt-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={loading}>Close</Button>
          <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={handleSave} disabled={loading}>
            {loading ? "Saving..." : "Save Profile"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
