"use client";

import { useEffect, useState } from "react";
import { contactsApi, Contact, api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { Search, UserPlus, Users, Sparkles, RefreshCw, MessageSquare, Trash2, CheckCircle2, XCircle, Clock } from "lucide-react";

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [suggestions, setSuggestions] = useState<Contact[]>([]);
  const [pending, setPending] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"all" | "suggestions" | "pending">("all");
  const [search, setSearch] = useState("");
  const [processing, setProcessing] = useState<string | null>(null);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [contactsData, suggestionsData, pendingData] = await Promise.all([
        contactsApi.list(),
        contactsApi.suggestions(),
        api.get<Contact[]>("/contacts/pending").catch(() => []),
      ]);
      setContacts(contactsData);
      setSuggestions(suggestionsData);
      setPending(pendingData);
    } catch (e) {
      console.error("Failed to load contacts:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleAddAsCustomer(contact: Contact) {
    setProcessing(contact.id);
    try {
      await contactsApi.addAsCustomer(contact.id);
      await loadData();
    } catch { alert("Failed to add as customer"); }
    finally { setProcessing(null); }
  }

  async function handleConfirm(id: string) {
    setProcessing(id);
    try {
      await api.post(`/contacts/${id}/confirm`, {});
      await loadData();
    } catch { alert("Failed to confirm contact"); }
    finally { setProcessing(null); }
  }

  async function handleDismiss(id: string) {
    setProcessing(id);
    try {
      await api.post(`/contacts/${id}/dismiss`, {});
      await loadData();
    } catch { alert("Failed to dismiss contact"); }
    finally { setProcessing(null); }
  }

  async function handleDelete(contact: Contact) {
    if (!confirm(`Delete contact ${contact.name}?`)) return;
    setProcessing(contact.id);
    try {
      await contactsApi.delete(contact.id);
      await loadData();
    } catch { alert("Failed to delete contact"); }
    finally { setProcessing(null); }
  }

  async function handleScanSuggestions() {
    setLoading(true);
    try {
      await contactsApi.scanSuggestions();
      await loadData();
    } catch { alert("Failed to scan for suggestions"); }
    finally { setLoading(false); }
  }

  const tabData = activeTab === "all" ? contacts : activeTab === "suggestions" ? suggestions : pending;
  const filtered = tabData.filter(c => {
    const q = search.toLowerCase();
    return !q || c.name.toLowerCase().includes(q) || c.phone_number.includes(q);
  });

  const TABS = [
    { id: "all" as const, label: "All Contacts", count: contacts.length, icon: Users },
    { id: "pending" as const, label: "Pending", count: pending.length, icon: Clock },
    { id: "suggestions" as const, label: "AI Suggestions", count: suggestions.length, icon: Sparkles },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Contacts</h1>
          <p className="text-slate-500 text-sm mt-1">WhatsApp contacts and classification</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleScanSuggestions} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white text-sm font-semibold rounded-lg hover:bg-purple-700 disabled:opacity-50">
            <Sparkles size={15} /> AI Scan
          </button>
          <button onClick={loadData} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-slate-600 text-white text-sm font-semibold rounded-lg hover:bg-slate-700 disabled:opacity-50">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 flex-wrap">
        {TABS.map(({ id, label, count, icon: Icon }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === id ? "bg-indigo-600 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            <Icon size={14} /> {label}
            {count > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${
                activeTab === id ? "bg-white/20 text-white" : id === "pending" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"
              }`}>{count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search contacts..."
          className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500" />
      </div>

      {/* Pending banner */}
      {pending.length > 0 && activeTab !== "pending" && (
        <div className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-xl text-sm">
          <Clock size={16} className="text-amber-600 shrink-0" />
          <p className="text-amber-800"><strong>{pending.length}</strong> contacts waiting for classification.</p>
          <button onClick={() => setActiveTab("pending")} className="ml-auto text-xs font-semibold text-amber-700 hover:underline shrink-0">
            Review →
          </button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-slate-200 rounded-full" />
                <div className="flex-1">
                  <div className="h-4 bg-slate-200 rounded w-3/4 mb-1" />
                  <div className="h-3 bg-slate-200 rounded w-1/2" />
                </div>
              </div>
              <div className="h-8 bg-slate-200 rounded" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <Users size={48} className="mx-auto text-slate-300 mb-4" />
          <p className="text-slate-500 text-lg font-medium">No contacts found</p>
          <p className="text-slate-400 text-sm mt-1">
            {activeTab === "suggestions" ? "Run AI Scan to find potential customers"
              : activeTab === "pending" ? "No contacts awaiting classification"
              : "Contacts appear here after WhatsApp sync"}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((contact) => (
            <div key={contact.id} className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
                  {contact.profile_picture ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={contact.profile_picture} alt={contact.name} className="w-10 h-10 rounded-full object-cover" />
                  ) : (
                    <span className="text-indigo-600 font-semibold text-sm">{contact.name.charAt(0).toUpperCase()}</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-slate-800 truncate">{contact.name}</p>
                    {activeTab === "suggestions" && (
                      <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium shrink-0">AI Pick</span>
                    )}
                    {activeTab === "pending" && (
                      <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium shrink-0">Pending</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 font-mono">{contact.phone_number}</p>
                </div>
              </div>

              {contact.last_message && (
                <div className="mb-3 p-2 bg-slate-50 rounded-lg">
                  <p className="text-xs text-slate-600 line-clamp-2">{contact.last_message}</p>
                  {contact.last_contacted && (
                    <p className="text-xs text-slate-400 mt-1">{timeAgo(contact.last_contacted)}</p>
                  )}
                </div>
              )}

              {activeTab === "pending" ? (
                <div className="flex gap-2">
                  <button onClick={() => handleConfirm(contact.id)} disabled={processing === contact.id}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50">
                    <CheckCircle2 size={14} /> Confirm
                  </button>
                  <button onClick={() => handleDismiss(contact.id)} disabled={processing === contact.id}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 text-sm rounded-lg hover:bg-slate-50 disabled:opacity-50">
                    <XCircle size={14} /> Dismiss
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button onClick={() => handleAddAsCustomer(contact)} disabled={processing === contact.id}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                    <UserPlus size={14} /> Add Customer
                  </button>
                  <a href={`https://wa.me/${contact.phone_number.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer"
                    className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors" title="WhatsApp">
                    <MessageSquare size={16} />
                  </a>
                  <button onClick={() => handleDelete(contact)} disabled={processing === contact.id}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50" title="Delete">
                    <Trash2 size={16} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
