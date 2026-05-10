export function getScoreColor(score: number): string {
  if (score >= 90) return "bg-green-100 text-green-700 border-green-200";
  if (score >= 75) return "bg-blue-100 text-blue-700 border-blue-200";
  if (score >= 60) return "bg-yellow-100 text-yellow-700 border-yellow-200";
  if (score >= 40) return "bg-orange-100 text-orange-700 border-orange-200";
  return "bg-red-100 text-red-700 border-red-200";
}

export function getScoreLabel(score: number): string {
  if (score >= 90) return "Excellent";
  if (score >= 75) return "Good";
  if (score >= 60) return "Fair";
  if (score >= 40) return "Needs work";
  return "Poor";
}

export function getDifficultyColor(difficulty: string): string {
  if (difficulty === "low") return "text-green-600";
  if (difficulty === "medium") return "text-yellow-600";
  return "text-red-500";
}

export function getDifficultyLabel(difficulty: string): string {
  if (difficulty === "low") return "Easy";
  if (difficulty === "medium") return "Medium";
  return "Hard";
}

export function getIntentColor(intent: string): string {
  if (intent === "transactional") return "bg-green-100 text-green-700";
  if (intent === "local") return "bg-blue-100 text-blue-700";
  if (intent === "informational") return "bg-purple-100 text-purple-700";
  return "bg-slate-100 text-slate-600";
}

export function getTrafficColor(traffic: string): string {
  if (traffic === "high") return "text-green-600";
  if (traffic === "medium") return "text-yellow-600";
  return "text-slate-400";
}

export function getStatusColor(status: string): string {
  if (status === "published") return "bg-green-100 text-green-700";
  if (status === "scheduled") return "bg-blue-100 text-blue-700";
  return "bg-slate-100 text-slate-600";
}

export function getPriorityStyle(priority: string): string {
  if (priority === "high") return "bg-red-50 border-red-100 text-red-700";
  if (priority === "medium") return "bg-yellow-50 border-yellow-100 text-yellow-700";
  return "bg-slate-50 border-slate-100 text-slate-500";
}

export function getIssueTypeStyle(type: "critical" | "warning" | "info"): string {
  const styles = {
    critical: "bg-red-100 text-red-700",
    warning: "bg-yellow-100 text-yellow-700",
    info: "bg-blue-100 text-blue-700",
  };
  return styles[type];
}

export function formatDate(dateString: string | undefined): string {
  if (!dateString) return "";
  return new Date(dateString).toLocaleDateString();
}

export function formatDateTime(dateString: string | undefined): string {
  if (!dateString) return "";
  return new Date(dateString).toLocaleString();
}

export function splitCommaSeparated(value: string): string[] {
  return value.split(",").map(v => v.trim()).filter(Boolean);
}

export function joinWithCommas(values: string[]): string {
  return values.join(", ");
}
