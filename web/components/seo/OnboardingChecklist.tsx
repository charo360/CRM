import React, { useState, useEffect } from "react";
import { seoApi } from "@/lib/api";

interface ChecklistItem {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  action?: () => void;
  actionText?: string;
}

interface SeoProfile {
  business_name?: string;
  business_type?: string;
  location?: string;
  website_url?: string;
}

export default function OnboardingChecklist({ profile }: { profile: SeoProfile | null }) {
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [savedKeywords, setSavedKeywords] = useState(false);
  const [hasCalendar, setHasCalendar] = useState(false);
  const [hasPosts, setHasPosts] = useState(false);
  const [hasAudit, setHasAudit] = useState(false);

  useEffect(() => {
    if (!profile) return;
    
    // Check completion status
    const checkStatus = async () => {
      try {
        // Check if keywords saved
        const saved = await seoApi.listSavedKeywords();
        setSavedKeywords(saved.length > 0);

        // Check if calendar exists (simplified - check for recent calendar generation)
        // For now, we'll assume if there are posts, there was a calendar
        const posts = await seoApi.listPosts();
        setHasPosts(posts.length > 0);
        setHasCalendar(posts.length > 0);

        // Check if audit run
        // This would need a new endpoint to check audit history
        setHasAudit(false); // Placeholder
      } catch (error) {
        console.error("Failed to check onboarding status:", error);
      } finally {
        setLoading(false);
      }
    };

    checkStatus();
  }, [profile]);

  useEffect(() => {
    if (loading) return;

    const items: ChecklistItem[] = [
      {
        id: "profile",
        title: "Complete your business profile",
        description: "Add your business name, type, and location",
        completed: !!(profile?.business_name && profile?.business_type && profile?.location),
        action: () => {
          // Navigate to settings
          window.location.href = "/dashboard/settings";
        },
        actionText: "Complete Profile"
      },
      {
        id: "keywords",
        title: "Generate and save keywords",
        description: "Get AI-powered keyword ideas for your business",
        completed: savedKeywords,
        action: () => {
          // Navigate to keywords tab
          window.location.href = "/dashboard/seo?tab=keywords";
        },
        actionText: "Generate Keywords"
      },
      {
        id: "calendar",
        title: "Create content calendar",
        description: "Plan your monthly blog content strategy",
        completed: hasCalendar,
        action: () => {
          window.location.href = "/dashboard/seo?tab=calendar";
        },
        actionText: "Create Calendar"
      },
      {
        id: "drafts",
        title: "Generate blog drafts",
        description: "Write all your monthly content in one click",
        completed: hasPosts,
        action: () => {
          window.location.href = "/dashboard/seo?tab=calendar";
        },
        actionText: "Generate Drafts"
      },
      {
        id: "audit",
        title: "Run SEO audit",
        description: "Find and fix technical SEO issues",
        completed: hasAudit,
        action: () => {
          window.location.href = "/dashboard/seo?tab=audit";
        },
        actionText: "Run Audit"
      }
    ];

    setChecklist(items);
  }, [profile, loading, savedKeywords, hasCalendar, hasPosts, hasAudit]);

  const completedCount = checklist.filter(item => item.completed).length;
  const totalCount = checklist.length;
  const progressPercentage = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-slate-200 rounded w-1/4 mb-4"></div>
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-5 h-5 bg-slate-200 rounded"></div>
                <div className="flex-1">
                  <div className="h-3 bg-slate-200 rounded w-3/4 mb-1"></div>
                  <div className="h-2 bg-slate-200 rounded w-1/2"></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">SEO Setup Checklist</h3>
          <p className="text-sm text-slate-500 mt-1">Get your SEO workflow running in 5 simple steps</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-emerald-600">{completedCount}/{totalCount}</div>
          <div className="text-xs text-slate-500">Complete</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-xs text-slate-500 mb-2">
          <span>Progress</span>
          <span>{Math.round(progressPercentage)}%</span>
        </div>
        <div className="w-full bg-slate-100 rounded-full h-2">
          <div 
            className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* Checklist items */}
      <div className="space-y-3">
        {checklist.map((item) => (
          <div 
            key={item.id} 
            className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
              item.completed 
                ? "bg-green-50 border-green-100" 
                : "bg-slate-50 border-slate-100"
            }`}
          >
            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center mt-0.5 flex-shrink-0 ${
              item.completed 
                ? "bg-green-500 border-green-500" 
                : "bg-white border-slate-300"
            }`}>
              {item.completed && (
                <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className={`text-sm font-medium ${
                item.completed ? "text-green-800" : "text-slate-700"
              }`}>
                {item.title}
              </h4>
              <p className={`text-xs mt-0.5 ${
                item.completed ? "text-green-600" : "text-slate-500"
              }`}>
                {item.description}
              </p>
            </div>
            {!item.completed && item.action && (
              <button
                onClick={item.action}
                className="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-700 font-medium flex-shrink-0"
              >
                {item.actionText}
              </button>
            )}
          </div>
        ))}
      </div>

      {completedCount === totalCount && (
        <div className="mt-6 p-4 bg-emerald-50 border border-emerald-100 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-emerald-800">All set! 🎉</h4>
              <p className="text-xs text-emerald-600 mt-0.5">
                Your SEO workflow is ready. Start monitoring your performance in the Overview tab.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
