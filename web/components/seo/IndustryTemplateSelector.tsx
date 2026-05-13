import React, { useState } from "react";

interface IndustryTemplate {
  name: string;
  business_type: string;
  sample_keywords: string[];
  content_pillars: string[];
  local_keywords: string[];
  sample_posts: string[];
}

interface IndustryTemplateSelectorProps {
  onSelect: (template: IndustryTemplate) => void;
  selectedType?: string;
}

const industryTemplates: Record<string, IndustryTemplate> = {
  plumbing: {
    name: "Plumbing Services",
    business_type: "plumbing",
    sample_keywords: [
      "emergency plumber near me",
      "water heater repair",
      "pipe leak detection",
      "drain cleaning services",
      "bathroom plumbing installation"
    ],
    content_pillars: [
      "Emergency services availability",
      "Preventive maintenance tips",
      "Cost guides for common repairs",
      "DIY vs professional advice"
    ],
    local_keywords: ["plumber [city]", "emergency plumber [city]", "24 hour plumber [city]"],
    sample_posts: [
      "5 Signs You Need Emergency Plumbing Services",
      "Water Heater Maintenance Guide: Extend Your Unit's Life",
      "How Much Do Common Plumbing Repairs Cost in [City]?",
      "DIY Plumbing: When to Call a Professional"
    ]
  },
  dental: {
    name: "Dental Practice",
    business_type: "dental-services",
    sample_keywords: [
      "dentist near me",
      "teeth cleaning cost",
      "emergency dental care",
      "cosmetic dentistry options",
      "family dental services"
    ],
    content_pillars: [
      "Preventive care education",
      "Treatment cost transparency",
      "Technology and comfort",
      "Patient testimonials"
    ],
    local_keywords: ["dentist [city]", "emergency dentist [city]", "family dentist [city]"],
    sample_posts: [
      "Complete Guide to Dental Cleaning: What to Expect",
      "Are Dental Implants Worth the Cost? A 2024 Analysis",
      "5 Ways to Reduce Dental Anxiety for Your Next Visit",
      "Choosing the Right Family Dentist in [City]"
    ]
  },
  consulting: {
    name: "Business Consulting",
    business_type: "business-consulting",
    sample_keywords: [
      "business strategy consultant",
      "small business growth",
      "operational efficiency",
      "digital transformation",
      "management consulting services"
    ],
    content_pillars: [
      "Industry insights",
      "Case studies and results",
      "Strategic frameworks",
      "Technology trends"
    ],
    local_keywords: ["business consultant [city]", "small business advisor [city]"],
    sample_posts: [
      "7 Strategies Small Businesses Need in 2024",
      "Case Study: How We Increased Client Revenue by 40%",
      "Digital Transformation ROI: A Complete Analysis",
      "Choosing the Right Business Consultant for Your Company"
    ]
  },
  restaurant: {
    name: "Restaurant",
    business_type: "restaurant",
    sample_keywords: [
      "best restaurant [city]",
      "fine dining near me",
      "local cuisine [city]",
      "restaurant reservations",
      "private dining events"
    ],
    content_pillars: [
      "Menu highlights",
      "Chef and kitchen stories",
      "Events and private dining",
      "Local sourcing and sustainability"
    ],
    local_keywords: ["restaurant [city]", "fine dining [city]", "best food [city]"],
    sample_posts: [
      "Behind the Scenes: Our Chef's Philosophy on Local Ingredients",
      "Complete Guide to Planning Your Private Dining Event",
      "Why [Restaurant Name] is the Best Restaurant in [City]",
      "Seasonal Menu: What's Fresh This Spring"
    ]
  },
  fitness: {
    name: "Fitness/Gym",
    business_type: "fitness",
    sample_keywords: [
      "gym near me",
      "personal trainer [city]",
      "fitness classes",
      "weight loss programs",
      "strength training"
    ],
    content_pillars: [
      "Workout guides",
      "Nutrition advice",
      "Success stories",
      "Class schedules and benefits"
    ],
    local_keywords: ["gym [city]", "fitness center [city]", "personal trainer [city]"],
    sample_posts: [
      "Complete Beginner's Guide to Starting a Fitness Routine",
      "5 Myths About Weight Loss Busted by Our Trainers",
      "How Our Members Achieved Their Fitness Goals",
      "Choosing the Right Personal Trainer for Your Goals"
    ]
  },
  legal: {
    name: "Law Firm",
    business_type: "legal-services",
    sample_keywords: [
      "lawyer near me",
      "family law attorney",
      "business lawyer",
      "estate planning services",
      "legal consultation"
    ],
    content_pillars: [
      "Legal education",
      "Case studies",
      "Process explanations",
      "Client rights"
    ],
    local_keywords: ["lawyer [city]", "attorney [city]", "legal services [city]"],
    sample_posts: [
      "Complete Guide to Estate Planning: What You Need to Know",
      "5 Questions to Ask Before Hiring a Family Law Attorney",
      "Business Legal Checklist: Are You Compliant?",
      "How to Choose the Right Lawyer for Your Case"
    ]
  }
};

export default function IndustryTemplateSelector({ onSelect, selectedType }: IndustryTemplateSelectorProps) {
  const [selected, setSelected] = useState(selectedType || "");
  const [showPreview, setShowPreview] = useState<string | null>(null);

  const handleSelect = (key: string, template: IndustryTemplate) => {
    setSelected(key);
    onSelect(template);
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-2">Choose Your Industry</h3>
        <p className="text-sm text-slate-500">
          Select an industry to get pre-configured keywords, content ideas, and SEO strategies
        </p>
      </div>

      {/* Industry grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(industryTemplates).map(([key, template]) => (
          <div
            key={key}
            className={`relative bg-white rounded-xl border-2 p-5 cursor-pointer transition-all hover:shadow-lg ${
              selected === key 
                ? "border-emerald-500 bg-emerald-50" 
                : "border-slate-200 hover:border-slate-300"
            }`}
            onClick={() => handleSelect(key, template)}
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h4 className="font-semibold text-slate-800">{template.name}</h4>
                <p className="text-xs text-slate-500 mt-1">{template.business_type}</p>
              </div>
              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                selected === key 
                  ? "border-emerald-500 bg-emerald-500" 
                  : "border-slate-300"
              }`}>
                {selected === key && (
                  <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
            </div>

            {/* Quick preview */}
            <div className="space-y-2">
              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Sample keywords:</p>
                <div className="flex flex-wrap gap-1">
                  {template.sample_keywords.slice(0, 3).map((kw, i) => (
                    <span key={i} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                      {kw}
                    </span>
                  ))}
                  {template.sample_keywords.length > 3 && (
                    <span className="text-[10px] text-slate-400">+{template.sample_keywords.length - 3} more</span>
                  )}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Content pillars:</p>
                <ul className="text-xs text-slate-500 space-y-0.5">
                  {template.content_pillars.slice(0, 2).map((pillar, i) => (
                    <li key={i} className="flex items-start gap-1">
                      <span className="text-emerald-500 mt-0.5">•</span>
                      <span>{pillar}</span>
                    </li>
                  ))}
                  {template.content_pillars.length > 2 && (
                    <li className="text-slate-400">+{template.content_pillars.length - 2} more</li>
                  )}
                </ul>
              </div>
            </div>

            {/* Preview button */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowPreview(showPreview === key ? null : key);
              }}
              className="mt-3 text-xs text-emerald-600 hover:text-emerald-700 font-medium"
            >
              {showPreview === key ? "Hide details" : "Preview template →"}
            </button>
          </div>
        ))}
      </div>

      {/* Expanded preview */}
      {showPreview && industryTemplates[showPreview] && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-lg font-semibold text-slate-800">
              {industryTemplates[showPreview].name} Template
            </h4>
            <button
              onClick={() => setShowPreview(null)}
              className="text-slate-400 hover:text-slate-600"
            >
              ×
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Keywords */}
            <div>
              <h5 className="text-sm font-semibold text-slate-700 mb-3">Target Keywords</h5>
              <div className="space-y-2">
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-1">Primary keywords:</p>
                  <div className="flex flex-wrap gap-1">
                    {industryTemplates[showPreview].sample_keywords.map((kw, i) => (
                      <span key={i} className="text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-100">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-1">Local variations:</p>
                  <div className="flex flex-wrap gap-1">
                    {industryTemplates[showPreview].local_keywords.map((kw, i) => (
                      <span key={i} className="text-[10px] bg-green-50 text-green-700 px-2 py-0.5 rounded border border-green-100">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Content strategy */}
            <div>
              <h5 className="text-sm font-semibold text-slate-700 mb-3">Content Strategy</h5>
              <div className="space-y-2">
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-1">Content pillars:</p>
                  <ul className="text-xs text-slate-500 space-y-1">
                    {industryTemplates[showPreview].content_pillars.map((pillar, i) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-emerald-500 mt-0.5">•</span>
                        <span>{pillar}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-1">Sample blog topics:</p>
                  <ul className="text-xs text-slate-500 space-y-1">
                    {industryTemplates[showPreview].sample_posts.map((post, i) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-blue-500 mt-0.5">•</span>
                        <span>{post}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 p-4 bg-emerald-50 border border-emerald-100 rounded-lg">
            <p className="text-sm text-emerald-800">
              <strong>Pro tip:</strong> This template will automatically configure your keyword generation, content calendar, and SEO strategy for maximum results in the {industryTemplates[showPreview].name.toLowerCase()} industry.
            </p>
          </div>
        </div>
      )}

      {/* Custom option */}
      <div className="bg-slate-50 rounded-xl border border-slate-200 p-6">
        <h4 className="font-semibold text-slate-800 mb-2">Don't see your industry?</h4>
        <p className="text-sm text-slate-600 mb-4">
          Choose "Custom" to create a tailored SEO strategy for your specific business type.
        </p>
        <button
          onClick={() => handleSelect("custom", {
            name: "Custom",
            business_type: "custom",
            sample_keywords: [],
            content_pillars: [],
            local_keywords: [],
            sample_posts: []
          })}
          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
            selected === "custom"
              ? "bg-slate-800 text-white"
              : "bg-white border border-slate-300 text-slate-700 hover:bg-slate-50"
          }`}
        >
          Use Custom Configuration
        </button>
      </div>
    </div>
  );
}
