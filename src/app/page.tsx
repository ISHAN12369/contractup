'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  FileText, Upload, Send, Trash2, AlertCircle, CheckCircle,
  Loader2, Key, X, Zap, Shield, Users, AlertTriangle,
  HelpCircle, BookOpen, Home, Clock, ChevronRight, BarChart3,
  Building2, FileSearch, History, ArrowRight, Star, TrendingUp,
  Scale, Eye, Menu, Sparkles
} from 'lucide-react';

/* ─── Types ─── */
interface Message {
  role: 'user' | 'assistant';
  content: string;
  ts: number;
}

interface StoredDoc {
  id: string;
  name: string;
  date: string;
  chars: number;
  preview: string;
  fullText: string;
}

interface BenefitItem {
  party: string;
  benefit: string;
  clause: string;
  score: number;
}

/* ─── Constants ─── */
const QUICK_QUESTIONS = [
  { icon: Users,          label: 'Who benefits most?',    q: 'Which party benefits most from this agreement and why?' },
  { icon: AlertTriangle,  label: 'Breach consequences',   q: 'What happens if either party breaches this agreement?' },
  { icon: Shield,         label: 'Liability & risks',     q: 'What are the liability clauses and who bears the most risk?' },
  { icon: Zap,            label: 'Termination',           q: 'Under what conditions can this agreement be terminated, and by whom?' },
  { icon: AlertCircle,    label: 'Unfair clauses',        q: 'Are there any one-sided, unfair, or risky clauses I should know about?' },
  { icon: BookOpen,       label: 'Plain summary',         q: 'Summarize this entire document in simple, plain English in 5-6 bullet points.' },
  { icon: HelpCircle,     label: 'Key obligations',       q: 'What are the key obligations for each party in this agreement?' },
  { icon: Users,          label: 'Dispute resolution',    q: 'How are disputes handled between the parties?' },
];

const BENEFITS_PROMPT = `Analyze this document and identify the top benefits for each party. Return your response as a JSON array with the following format (and nothing else before or after the JSON):
[
  {"party": "Party A (e.g. Landlord/Seller)", "benefit": "Brief benefit description", "clause": "The exact clause text or section reference", "score": 8},
  {"party": "Party B (e.g. Tenant/Buyer)", "benefit": "Brief benefit description", "clause": "The exact clause text or section reference", "score": 7}
]
Include 3-5 benefits per party. The score should be 1-10 indicating how significant the benefit is. Use the actual party names from the document.`;

const MAX_HISTORY = 10;
const STORAGE_KEY = 'contractiq_history';

// Python/FastAPI + LangChain RAG backend (see /contractiq-backend).
// Handles real embedding + vector-store-backed chat. Falls back to localhost for local dev.
const RAG_API_URL = process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000';

/* ─── Helpers ─── */
function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

function loadHistory(): StoredDoc[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch { return []; }
}

function saveHistory(docs: StoredDoc[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(docs.slice(0, MAX_HISTORY)));
}

/* ─── Benefits Chart Component ─── */
function BenefitsChart({ benefits, onBenefitClick, isLight, onHover }: { benefits: BenefitItem[]; onBenefitClick: (b: BenefitItem) => void; isLight?: boolean; onHover: (h: boolean) => void }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(t);
  }, []);

  // Find the two primary distinct parties from LLM response
  const uniqueParties = Array.from(new Set(benefits.map(b => b.party?.trim()).filter(Boolean)));
  const partyAName = uniqueParties[0] || 'Party A';
  const partyBName = uniqueParties[1] || 'Party B';

  const groupedA = benefits.filter(b => b.party?.trim() === partyAName).slice(0, 5);
  const groupedB = benefits.filter(b => b.party?.trim() === partyBName).slice(0, 5);

  const sumA = groupedA.reduce((s, b) => s + b.score, 0);
  const sumB = groupedB.reduce((s, b) => s + b.score, 0);
  const fairness = Math.max(sumA, sumB) > 0 ? Math.round((Math.min(sumA, sumB) / Math.max(sumA, sumB)) * 100) : 100;

  const renderBars = (items: BenefitItem[], isPartyB: boolean) => (
    <div className={`chart-bar-container ${isLight ? 'cream-mode' : ''} h-48 gap-3 px-2`}>
      {items.map((b, i) => (
        <div 
          key={i} 
          className="flex flex-col items-center gap-2 flex-1 h-full justify-end group cursor-pointer" 
          onClick={() => onBenefitClick(b)}
          onMouseEnter={() => onHover(true)}
          onMouseLeave={() => onHover(false)}
        >
          <span className={`text-xs font-bold transition-all duration-300 transform group-hover:scale-110 ${isLight ? 'text-dark-text' : 'text-cream-white'}`}>{b.score}</span>
          <div
            className={`studio-bar ${isLight ? 'light-bar' : ''}`}
            style={{
              height: mounted ? `${Math.max(b.score * 10, 8)}%` : '0%',
              backgroundImage: isPartyB 
                ? (isLight ? 'linear-gradient(180deg, #E04832 0%, rgba(224, 72, 50, 0.5) 100%)' : 'linear-gradient(180deg, #FF4E3A 0%, rgba(255, 78, 58, 0.45) 100%)')
                : (isLight ? 'linear-gradient(180deg, #7a7975 0%, rgba(122, 121, 117, 0.4) 100%)' : 'linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.3) 100%)'),
              border: isLight ? '1px solid #1d1c19' : '1px solid rgba(255,255,255,0.2)',
              transitionDelay: `${i * 0.08}s`,
            }}
            title={`${b.benefit} (Score: ${b.score})`}
          />
          <span className={`text-[10px] text-center leading-tight max-w-[80px] truncate font-medium opacity-75 group-hover:opacity-100 ${isLight ? 'text-dark-text' : 'text-cream-white'}`}>{b.benefit}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className={`studio-card ${isLight ? 'light-card' : ''} p-6`}>
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="w-5 h-5 text-coral animate-bounce" />
        <h3 className="heading-display text-lg normal-case tracking-normal">Benefits Analysis</h3>
      </div>
      <p className="text-xs opacity-75 mb-6">Click any bar to jump to the relevant clause in the contract</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: isLight ? '#7a7975' : '#ffffff' }} />
            <span className="text-sm font-semibold">{groupedA[0]?.party || 'Party A'}</span>
          </div>
          {renderBars(groupedA, false)}
          <div className="mt-4 flex flex-col gap-1.5 border-t border-black/10 pt-3">
            <span className="text-[10px] uppercase tracking-wider font-bold opacity-60 block mb-1">Benefit Links</span>
            {groupedA.map((b, i) => (
              <button
                key={i}
                onClick={() => onBenefitClick(b)}
                onMouseEnter={() => onHover(true)}
                onMouseLeave={() => onHover(false)}
                className={`text-left text-xs font-medium cursor-pointer hover:text-coral transition-colors py-1 flex items-start gap-1`}
              >
                <span className="text-coral">🔗</span> <span className="underline decoration-current/25 hover:decoration-current">{b.benefit} (Score: {b.score})</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: isLight ? '#E04832' : '#FF4E3A' }} />
            <span className="text-sm font-semibold">{groupedB[0]?.party || 'Party B'}</span>
          </div>
          {renderBars(groupedB, true)}
          <div className="mt-4 flex flex-col gap-1.5 border-t border-black/10 pt-3">
            <span className="text-[10px] uppercase tracking-wider font-bold opacity-60 block mb-1">Benefit Links</span>
            {groupedB.map((b, i) => (
              <button
                key={i}
                onClick={() => onBenefitClick(b)}
                onMouseEnter={() => onHover(true)}
                onMouseLeave={() => onHover(false)}
                className={`text-left text-xs font-medium cursor-pointer hover:text-coral transition-colors py-1 flex items-start gap-1`}
              >
                <span className="text-coral">🔗</span> <span className="underline decoration-current/25 hover:decoration-current">{b.benefit} (Score: {b.score})</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mt-6">
        <div className="text-center p-3 rounded bg-black/10 border border-current">
          <Scale className="w-4 h-4 mx-auto mb-1" />
          <div className="text-xs font-semibold">Fairness</div>
          <div className="text-lg font-bold">{fairness}%</div>
        </div>
        <div className="text-center p-3 rounded bg-black/10 border border-current">
          <TrendingUp className="w-4 h-4 mx-auto mb-1" />
          <div className="text-xs font-semibold">Benefits</div>
          <div className="text-lg font-bold">{benefits.length}</div>
        </div>
        <div className="text-center p-3 rounded bg-black/10 border border-current">
          <Eye className="w-4 h-4 mx-auto mb-1" />
          <div className="text-xs font-semibold">Clauses</div>
          <div className="text-lg font-bold">{benefits.filter(b => b.clause).length}</div>
        </div>
      </div>
    </div>
  );
}

/* ─── Contract Viewer Component ─── */
function ContractViewer({ benefits, highlightClause, isFrosted }: { benefits: BenefitItem[]; highlightClause: string | null; isFrosted?: boolean }) {
  const viewerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlightClause && viewerRef.current) {
      const el = viewerRef.current.querySelector('.highlighted');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightClause]);

  return (
    <div className={`studio-card ${isFrosted ? 'frosted-glass' : ''} overflow-hidden`}>
      <div className="flex items-center gap-2 px-5 py-3 border-b border-white/10">
        <FileSearch className="w-4 h-4 text-coral animate-pulse" />
        <span className="text-sm font-semibold text-white">Relevant Contract Clauses</span>
      </div>
      <div ref={viewerRef} className="contract-viewer flex flex-col gap-3 p-4" style={{ backgroundColor: 'transparent', color: '#fff', maxHeight: '400px', overflowY: 'auto' }}>
        {benefits.map((b, i) => {
          const isHighlighted = highlightClause === b.clause;
          return (
            <div
              key={i}
              className={`clause p-4 rounded border transition-all ${isHighlighted ? 'highlighted' : ''}`}
              style={{
                borderLeft: isHighlighted ? '4px solid var(--studio-coral)' : '1px solid rgba(255,255,255,0.08)',
                backgroundColor: isHighlighted ? 'rgba(255, 78, 58, 0.15)' : 'rgba(255, 255, 255, 0.02)',
              }}
            >
              <div className="text-xs font-bold text-studio-coral mb-1">{b.party} — {b.benefit} (Score: {b.score})</div>
              <div className="text-xs opacity-90 leading-relaxed italic">&quot;{b.clause}&quot;</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Main Page Component ─── */
export default function HomePage() {
  /* ── Custom Cursor State ── */
  const [cursorPos, setCursorPos] = useState({ x: -100, y: -100 });
  const [cursorHovered, setCursorHovered] = useState(false);

  /* ── API Key State (optional — server-side keys used by default) ── */
  const [apiKey, setApiKey]           = useState('');
  const [groqApiKey, setGroqApiKey]   = useState('');
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [keySaved, setKeySaved]       = useState(false);

  /* ── Document State ── */
  const [docText, setDocText]         = useState('');
  const [docName, setDocName]         = useState('');
  const [docChars, setDocChars]       = useState(0);
  const [pasteText, setPasteText]     = useState('');
  const [isDragging, setIsDragging]   = useState(false);
  const [extracting, setExtracting]   = useState(false);
  const [extractError, setExtractError] = useState('');

  /* ── RAG Backend State (Python/FastAPI + LangChain + Chroma) ── */
  const [docId, setDocId]             = useState('');       // vector-store collection id for this doc
  const [ragIndexing, setRagIndexing] = useState(false);     // true while embedding is in progress
  const [ragError, setRagError]       = useState('');        // non-fatal: chat-only backend issue

  /* ── Chat State ── */
  const [messages, setMessages]       = useState<Message[]>([]);
  const [input, setInput]             = useState('');
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');

  /* ── New Features State ── */
  const [history, setHistoryState]    = useState<StoredDoc[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [benefits, setBenefits]       = useState<BenefitItem[]>([]);
  const [highlightClause, setHighlightClause] = useState<string | null>(null);
  const [showContractViewer, setShowContractViewer] = useState(false);
  const [analyzingBenefits, setAnalyzingBenefits] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [activeSection, setActiveSection] = useState('intro');
  const [isQuickAuditorCollapsed, setIsQuickAuditorCollapsed] = useState(false);

  /* ── Refs ── */
  const fileRef     = useRef<HTMLInputElement>(null);
  const chatEndRef  = useRef<HTMLDivElement>(null);
  const inputRef    = useRef<HTMLInputElement>(null);

  /* ── Sections Refs for Scroll Snap/Nav ── */
  const introRef    = useRef<HTMLDivElement>(null);
  const uploadRef   = useRef<HTMLDivElement>(null);
  const benefitsRef = useRef<HTMLDivElement>(null);
  const chatRef     = useRef<HTMLDivElement>(null);

  /* ── Custom Cursor & Scroll Listeners ── */
  useEffect(() => {
    const updateCursor = (e: MouseEvent) => {
      setCursorPos({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener('mousemove', updateCursor);
    return () => window.removeEventListener('mousemove', updateCursor);
  }, []);

  useEffect(() => {
    const savedHf = localStorage.getItem('hf_api_key');
    const savedGroq = localStorage.getItem('groq_api_key');
    if (savedHf) {
      setApiKey(savedHf);
    } else if (process.env.NEXT_PUBLIC_HF_API_KEY) {
      setApiKey(process.env.NEXT_PUBLIC_HF_API_KEY);
    }
    if (savedGroq) {
      setGroqApiKey(savedGroq);
    }
    // Server-side keys are always available, so mark as saved
    setKeySaved(true);
    setHistoryState(loadHistory());
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    const handleScroll = () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      setScrollProgress(docHeight > 0 ? scrollTop / docHeight : 0);

      // Simple active section check based on scroll offsets
      const offsetIntro = introRef.current?.offsetTop || 0;
      const offsetUpload = uploadRef.current?.offsetTop || 0;
      const offsetBenefits = benefitsRef.current?.offsetTop || 0;
      const offsetChat = chatRef.current?.offsetTop || 0;

      const currentScroll = scrollTop + window.innerHeight / 3;

      if (currentScroll >= offsetChat) {
        setActiveSection('chat');
      } else if (currentScroll >= offsetBenefits) {
        setActiveSection('benefits');
      } else if (currentScroll >= offsetUpload) {
        setActiveSection('upload');
      } else {
        setActiveSection('intro');
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Section scroll-to helper
  const scrollTo = (ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  };

  /* ── API Key Handlers (optional overrides) ── */
  const saveKey = () => {
    if (apiKey) localStorage.setItem('hf_api_key', apiKey);
    if (groqApiKey) localStorage.setItem('groq_api_key', groqApiKey);
    setKeySaved(true);
    setShowKeyInput(false);
  };

  const clearKey = () => {
    localStorage.removeItem('hf_api_key');
    localStorage.removeItem('groq_api_key');
    setApiKey('');
    setGroqApiKey('');
    setKeySaved(true); // Server keys still work
  };

  /* ── File Extraction ── */
  /**
   * Ingest a file into the Python/FastAPI + LangChain RAG backend: parses it,
   * chunks it, embeds it locally (HuggingFace embeddings), and stores it in a
   * persisted Chroma collection. Returns the doc_id used for all later /chat calls.
   *
   * This is separate from /api/extract (Next.js) below — that route still handles
   * getting text on-screen for the contract viewer & benefits chart. This call is
   * only responsible for making the document queryable via real vector search.
   */
  const ingestToRagBackend = useCallback(async (file: File): Promise<string> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${RAG_API_URL}/upload`, { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error || 'RAG backend ingestion failed');
    return data.doc_id as string;
  }, []);

  const handleFile = useCallback(async (file: File) => {
    setExtractError('');
    setExtracting(true);
    setDocText('');
    setDocName('');
    setDocId('');
    setRagError('');
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/extract', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setDocText(data.text);
      setDocName(file.name);
      setDocChars(data.chars);
      setMessages([]);
      setBenefits([]);
      setHighlightClause(null);

      const newDoc: StoredDoc = {
        id: generateId(),
        name: file.name,
        date: new Date().toLocaleDateString(),
        chars: data.chars,
        preview: data.text.slice(0, 150),
        fullText: data.text,
      };
      const updated = [newDoc, ...loadHistory().filter(d => d.name !== file.name)].slice(0, MAX_HISTORY);
      saveHistory(updated);
      setHistoryState(updated);
      
      // Auto-scroll to benefits setup section
      setTimeout(() => scrollTo(benefitsRef), 500);
    } catch (e: unknown) {
      setExtractError(e instanceof Error ? e.message : 'Extraction failed');
      setExtracting(false);
      return;
    }
    setExtracting(false);

    // Ingest into the RAG backend in the background so chat becomes available
    // as soon as embedding finishes, without blocking the text preview above.
    setRagIndexing(true);
    try {
      const id = await ingestToRagBackend(file);
      setDocId(id);
    } catch (e: unknown) {
      setRagError(
        e instanceof Error
          ? `Chat backend unavailable: ${e.message}`
          : 'Chat backend unavailable. Is the FastAPI server running?'
      );
    } finally {
      setRagIndexing(false);
    }
  }, [ingestToRagBackend]);

  const handlePasteLoad = async () => {
    if (!pasteText.trim()) return;
    const text = pasteText.trim();
    setDocText(text);
    setDocName('Pasted document');
    setDocChars(text.length);
    setMessages([]);
    setBenefits([]);
    setExtractError('');
    setDocId('');
    setRagError('');

    const newDoc: StoredDoc = {
      id: generateId(),
      name: 'Pasted document',
      date: new Date().toLocaleDateString(),
      chars: text.length,
      preview: text.slice(0, 150),
      fullText: text,
    };
    const updated = [newDoc, ...loadHistory()].slice(0, MAX_HISTORY);
    saveHistory(updated);
    setHistoryState(updated);

    setTimeout(() => scrollTo(benefitsRef), 500);

    // The RAG backend only accepts files, so wrap the pasted text as a .txt file.
    setRagIndexing(true);
    try {
      const file = new File([text], 'pasted-document.txt', { type: 'text/plain' });
      const id = await ingestToRagBackend(file);
      setDocId(id);
    } catch (e: unknown) {
      setRagError(
        e instanceof Error
          ? `Chat backend unavailable: ${e.message}`
          : 'Chat backend unavailable. Is the FastAPI server running?'
      );
    } finally {
      setRagIndexing(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const loadFromHistory = async (doc: StoredDoc) => {
    setDocText(doc.fullText);
    setDocName(doc.name);
    setDocChars(doc.chars);
    setMessages([]);
    setBenefits([]);
    setHighlightClause(null);
    setShowHistory(false);
    setDocId('');
    setRagError('');
    setTimeout(() => scrollTo(benefitsRef), 300);

    // Documents loaded from local history predate this doc's RAG doc_id, so
    // re-ingest the stored text into the vector store to get a fresh doc_id.
    setRagIndexing(true);
    try {
      const file = new File([doc.fullText], doc.name.endsWith('.txt') ? doc.name : `${doc.name}.txt`, {
        type: 'text/plain',
      });
      const id = await ingestToRagBackend(file);
      setDocId(id);
    } catch (e: unknown) {
      setRagError(
        e instanceof Error
          ? `Chat backend unavailable: ${e.message}`
          : 'Chat backend unavailable. Is the FastAPI server running?'
      );
    } finally {
      setRagIndexing(false);
    }
  };

  const deleteFromHistory = (id: string) => {
    const updated = history.filter(d => d.id !== id);
    saveHistory(updated);
    setHistoryState(updated);
  };

  const clearHistory = () => {
    saveHistory([]);
    setHistoryState([]);
  };

  /* ── Chat Functionality ──
   * Now backed by the Python/FastAPI + LangChain RAG server (see /contractiq-backend):
   * real chunking + local embeddings + Chroma similarity search, instead of resending
   * the full docText and doing keyword-match "RAG" on every message.
   * Benefits analysis (below) is intentionally left on the old Next.js /api/chat route —
   * the Python backend only implements retrieval-QA chat for now, not the
   * chunk-extract-then-synthesize benefits pipeline.
   */
  const sendMessage = async (question?: string) => {
    const q = (question || input).trim();
    if (!q || !docText || loading) return;

    if (!docId) {
      setError(
        ragIndexing
          ? 'Still indexing this document for chat — try again in a few seconds.'
          : ragError || 'Document is not indexed for chat yet. Try re-uploading it.'
      );
      return;
    }

    setInput('');
    setError('');
    const userMsg: Message = { role: 'user', content: q, ts: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch(`${RAG_API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: docId,
          question: q,
          history: messages.slice(-8).map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'RAG backend error');
      setMessages(prev => [...prev, { role: 'assistant', content: data.answer, ts: Date.now() }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  /* ── Benefits AI Hook ── */
  const runBenefitsAnalysis = async () => {
    if (!docId) {
      setError(
        ragIndexing
          ? 'Still indexing this document — try again in a few seconds.'
          : ragError || 'Document is not indexed yet. Try re-uploading it.'
      );
      return;
    }
    if (analyzingBenefits) return;
    
    setAnalyzingBenefits(true);
    setError('');

    try {
      const res = await fetch(`${RAG_API_URL}/benefits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'RAG backend error');

      const jsonMatch = data.answer.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]) as any[];
        const normalized = parsed.map((item: any) => ({
          party: item.party || '',
          benefit: item.benefit || item.obligation || item.description || item.finding || '',
          clause: item.clause || item.clause_reference || item.reference || '',
          score: typeof item.score === 'number' ? item.score : parseInt(String(item.score || 0), 10) || 5
        })) as BenefitItem[];
        setBenefits(normalized);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Benefits analysis failed');
    } finally {
      setAnalyzingBenefits(false);
    }
  };

  const handleBenefitClick = (b: BenefitItem) => {
    setHighlightClause(b.clause);
    setShowContractViewer(true);
    // Smooth scroll to contract viewer after transition
    setTimeout(() => {
      const el = document.getElementById('contract-viewer-wrapper');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 150);
  };

  const resetDoc = () => {
    setDocText('');
    setDocName('');
    setDocChars(0);
    setPasteText('');
    setMessages([]);
    setError('');
    setExtractError('');
    setBenefits([]);
    setHighlightClause(null);
    setShowContractViewer(false);
    scrollTo(introRef);
  };

  const docLoaded = !!docText;
  const isSidebarLight = activeSection === 'upload' || activeSection === 'chat';

  return (
    <div className="studio-container relative">
      {/* Custom Cursor */}
      <div 
        className={`custom-cursor hidden md:block ${cursorHovered ? 'hovered' : ''}`}
        style={{ left: `${cursorPos.x}px`, top: `${cursorPos.y}px` }}
      />

      {/* Progress Bar */}
      <div className="studio-progress-bar" style={{ transform: `scaleX(${scrollProgress})` }} />

      {/* ─── Sidebar Navigation ─── */}
      <aside className={`studio-sidebar ${isSidebarLight ? 'light-mode' : ''}`}>
        <a 
          href="#" 
          className="studio-logo"
          onMouseEnter={() => setCursorHovered(true)} 
          onMouseLeave={() => setCursorHovered(false)}
          onClick={(e) => { e.preventDefault(); resetDoc(); }}
        >
          IQ
        </a>

        <nav className="studio-nav-links">
          <a 
            className={`studio-nav-item ${activeSection === 'intro' ? 'active' : ''}`}
            onClick={() => scrollTo(introRef)}
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            Intro
          </a>
          <a 
            className={`studio-nav-item ${activeSection === 'upload' ? 'active' : ''}`}
            onClick={() => scrollTo(uploadRef)}
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            Upload
          </a>
          <a 
            className={`studio-nav-item ${activeSection === 'benefits' ? 'active' : ''}`}
            onClick={() => scrollTo(benefitsRef)}
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            Benefits
          </a>
          <a 
            className={`studio-nav-item ${activeSection === 'chat' ? 'active' : ''}`}
            onClick={() => scrollTo(chatRef)}
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            Chat
          </a>
        </nav>

        <div 
          className="studio-connect-badge"
          onMouseEnter={() => setCursorHovered(true)} 
          onMouseLeave={() => setCursorHovered(false)}
          onClick={() => setShowKeyInput(v => !v)}
        >
          API Keys (Optional) »
        </div>
      </aside>

      {/* ─── Stored Document Sidebar ─── */}
      <div 
        className={`studio-overlay ${showHistory ? 'open' : ''}`} 
        onClick={() => setShowHistory(false)} 
      />
      <div className={`studio-sidebar-panel ${showHistory ? 'open' : ''} ${isSidebarLight ? 'light-panel' : ''}`}>
        <div className="flex items-center justify-between mb-8 border-b pb-4 border-current">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5" />
            <h3 className="heading-display text-lg tracking-normal uppercase">Documents</h3>
          </div>
          <button 
            onClick={() => setShowHistory(false)} 
            className="p-1 hover:opacity-75 transition-opacity"
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {history.length > 0 && (
          <button 
            onClick={clearHistory} 
            className="text-xs uppercase tracking-wider font-bold text-coral mb-4 block hover:underline"
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            Clear Stored History
          </button>
        )}

        {history.length === 0 ? (
          <div className="text-center py-16 opacity-50">
            <Clock className="w-8 h-8 mx-auto mb-2" />
            <p className="text-sm">History is empty</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {history.map((doc) => (
              <div
                key={doc.id}
                className="p-4 border border-current/20 hover:border-current hover:bg-black/5 cursor-pointer transition-all"
                onClick={() => loadFromHistory(doc)}
                onMouseEnter={() => setCursorHovered(true)} 
                onMouseLeave={() => setCursorHovered(false)}
              >
                <div className="flex justify-between items-start gap-2">
                  <span className="font-semibold text-sm truncate">{doc.name}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteFromHistory(doc.id); }}
                    className="hover:text-coral transition-colors p-1"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <div className="text-[10px] opacity-60 mt-1">{doc.date} · {doc.chars.toLocaleString()} chars</div>
                <p className="text-xs opacity-80 mt-2 line-clamp-2 leading-relaxed">{doc.preview}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ─── Main Content ─── */}
      <main className="studio-main">
        {/* Floating Top Header (Status details / API keys) */}
        <header className="absolute top-6 left-0 right-0 z-30 px-8 flex justify-end gap-3 items-center pointer-events-none">
          <button
            onClick={() => setShowHistory(true)}
            className="studio-btn pointer-events-auto text-xs px-4 py-2 border-white/20 text-white hover:border-white"
            onMouseEnter={() => setCursorHovered(true)} 
            onMouseLeave={() => setCursorHovered(false)}
          >
            <History className="w-3.5 h-3.5 mr-1" /> History
          </button>
          <span className="hidden md:inline-flex items-center gap-1.5 text-xs font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded px-3 py-1.5 pointer-events-auto">
            <CheckCircle className="w-3 h-3" /> AI Ready
          </span>
        </header>

        {/* API Key Modal Window */}
        {showKeyInput && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4">
            <div className="studio-card max-w-lg w-full bg-studio-bg-dark border-studio-coral p-6 text-cream-white relative">
              <button 
                onClick={() => setShowKeyInput(false)} 
                className="absolute top-4 right-4 text-cream-white hover:text-studio-coral"
              >
                <X className="w-5 h-5" />
              </button>
              <h3 className="heading-display text-xl mb-4">API Key Setup (Optional)</h3>
              <p className="text-xs text-studio-gray mb-6">
                Server-side keys are pre-configured. Only use this if you want to override with your own keys.
              </p>

              <div className="mb-4">
                <label className="text-[10px] uppercase tracking-wider font-bold text-studio-gray block mb-1.5">HuggingFace API Key (Mistral Chunking)</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="hf_xxxxxxxxxxxxxxxxxxxx"
                  className="w-full text-sm border border-white/20 bg-black/40 rounded px-3 py-2 text-white focus:outline-none focus:border-studio-coral"
                />
                <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer" className="text-[10px] underline text-studio-coral mt-1 inline-block">Get free HuggingFace key →</a>
              </div>

              <div className="mb-6">
                <label className="text-[10px] uppercase tracking-wider font-bold text-studio-gray block mb-1.5">Groq API Key (LLaMA Generation)</label>
                <input
                  type="password"
                  value={groqApiKey}
                  onChange={e => setGroqApiKey(e.target.value)}
                  placeholder="gsk_xxxxxxxxxxxxxxxxxxxx"
                  className="w-full text-sm border border-white/20 bg-black/40 rounded px-3 py-2 text-white focus:outline-none focus:border-studio-coral"
                />
                <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" className="text-[10px] underline text-studio-coral mt-1 inline-block">Get free Groq key →</a>
              </div>

              <div className="flex gap-2">
                <button 
                  onClick={saveKey} 
                  className="studio-btn text-xs"
                >
                  Save Override Keys
                </button>
                <button 
                  onClick={clearKey} 
                  className="studio-btn text-xs border-red-500 text-red-500 hover:bg-red-500/10"
                >
                  Clear Overrides
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ─── Section I: Intro ─── */}
        <section ref={introRef} className="studio-section dark-theme justify-between">
          <div className="bg-text-grid">
            <div>REAL ESTATE</div>
            <div>PROPERTY AGREEMENTS</div>
            <div>DEED CHECKER</div>
          </div>

          <div className="z-10 mt-12">
            <div className="mask-container">
              <h1 className="kinetic-header mask-text">
                REAL ESTATE
              </h1>
            </div>
            <br />
            <div className="mask-container">
              <h1 className="kinetic-header mask-text" style={{ animationDelay: '0.2s' }}>
                CONTRACTS
              </h1>
            </div>
            <br />
            <div className="mask-container">
              <h1 className="kinetic-header mask-text text-white" style={{ animationDelay: '0.4s' }}>
                DEMYSTIFIED
              </h1>
            </div>
            <br />
            <div className="mask-container">
              <h1 className="kinetic-header mask-text" style={{ animationDelay: '0.6s' }}>
                BY CONTRACTIQ
              </h1>
            </div>

            <p className="max-w-md text-sm leading-relaxed text-studio-gray mt-6">
              A high-precision legal analysis engine tailored for landlords, tenants, buyers, and sellers. Upload lease terms, property deeds, or complex transactions to explore risk indices instantly.
            </p>
          </div>

          <div className="z-10 flex gap-4 mt-8">
            <button 
              className="studio-btn"
              onClick={() => scrollTo(uploadRef)}
              onMouseEnter={() => setCursorHovered(true)} 
              onMouseLeave={() => setCursorHovered(false)}
            >
              Get Started <ArrowRight className="w-4 h-4 ml-1" />
            </button>
          </div>

          {/* Marquee Ticker */}
          <div className="marquee-container w-full mt-12">
            <div className="marquee-content">
              {[...Array(2)].map((_, idx) => (
                <div key={idx} className="flex gap-8">
                  <div className="marquee-item"><Sparkles className="w-5 h-5" /> 100% Client-Side Encryption</div>
                  <div className="marquee-item"><Home className="w-5 h-5" /> Landlord & Tenant Equalizer</div>
                  <div className="marquee-item"><Shield className="w-5 h-5" /> Instant Breach & Risk Scoring</div>
                  <div className="marquee-item"><Zap className="w-5 h-5" /> Free HuggingFace Integration</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Section II: Upload ─── */}
        <section ref={uploadRef} className="studio-section cream-theme">
          <div className="bg-text-grid cream-mode">
            <div>SECURE DEED</div>
            <div>LEASE AGREEMENT</div>
            <div>ACQUISITION</div>
          </div>

          <div className="z-10 max-w-[95%] w-full mx-auto">
            <span className="text-xs font-bold tracking-widest text-studio-coral uppercase block mb-2">Upload Terminal</span>
            <h2 className="heading-display dark-text text-3xl sm:text-5xl mb-8">SUBMIT AGREEMENT</h2>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
              {/* Left Form column */}
              <div className="lg:col-span-7">
                <div 
                  className={`studio-card light-card p-6 flex flex-col gap-4 border-2 border-dashed ${isDragging ? 'border-studio-coral bg-black/5' : ''}`}
                  onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,.txt,.md"
                    className="hidden"
                    onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
                  />

                  {extracting ? (
                    <div className="py-12 text-center flex flex-col items-center justify-center gap-3">
                      <Loader2 className="w-12 h-12 text-studio-coral animate-spin" />
                      <p className="font-bold text-dark-text">Processing documents...</p>
                    </div>
                  ) : (
                    <div 
                      className="py-10 text-center cursor-pointer" 
                      onClick={() => fileRef.current?.click()}
                      onMouseEnter={() => setCursorHovered(true)} 
                      onMouseLeave={() => setCursorHovered(false)}
                    >
                      <Upload className="w-12 h-12 text-studio-coral mx-auto mb-4" />
                      <p className="font-bold text-dark-text text-base">Drop your contract file here or browse</p>
                      <p className="text-xs text-studio-gray mt-2">Supports PDF, DOCX, TXT (Max 10MB)</p>
                    </div>
                  )}

                  {extractError && (
                    <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 p-3 rounded">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      {extractError}
                    </div>
                  )}

                  <div className="border-t border-black/10 pt-4 mt-2">
                    <p className="text-xs font-bold text-studio-gray uppercase mb-2">Or paste contract text directly</p>
                    <textarea
                      value={pasteText}
                      onChange={e => setPasteText(e.target.value)}
                      placeholder="Paste contract sections here..."
                      className="w-full h-24 border border-black/10 rounded p-3 text-xs bg-white text-dark-text focus:outline-none resize-none"
                    />
                    <button
                      disabled={!pasteText.trim()}
                      onClick={handlePasteLoad}
                      className="studio-btn light-btn text-xs w-full justify-center mt-3"
                      onMouseEnter={() => setCursorHovered(true)} 
                      onMouseLeave={() => setCursorHovered(false)}
                    >
                      Process Raw Text <ArrowRight className="w-4 h-4 ml-1" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Right Summary Column */}
              <div className="lg:col-span-5 flex flex-col justify-between">
                <div className="studio-card light-card p-6 h-full flex flex-col justify-between">
                  <div>
                    <h4 className="font-bold text-sm text-dark-text uppercase tracking-wider mb-3">Loaded Document</h4>
                    {docLoaded ? (
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center gap-2 text-dark-text font-bold">
                          <FileText className="w-4 h-4 text-studio-coral shrink-0" />
                          <span className="truncate text-sm">{docName}</span>
                        </div>
                        <p className="text-xs text-studio-gray">Length: {docChars.toLocaleString()} characters</p>
                        <div className="flex gap-2 mt-4">
                          <button
                            onClick={() => setShowContractViewer(v => !v)}
                            className="studio-btn light-btn text-[10px] py-2 px-3 flex-1 justify-center"
                            onMouseEnter={() => setCursorHovered(true)} 
                            onMouseLeave={() => setCursorHovered(false)}
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" /> {showContractViewer ? 'Hide text' : 'Show text'}
                          </button>
                          <button
                            onClick={resetDoc}
                            className="studio-btn text-[10px] py-2 px-3 flex-1 justify-center border-red-600 text-red-600 hover:bg-red-50"
                            onMouseEnter={() => setCursorHovered(true)} 
                            onMouseLeave={() => setCursorHovered(false)}
                          >
                            <Trash2 className="w-3.5 h-3.5 mr-1" /> Clear
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-studio-gray leading-relaxed">
                        No active document loaded. Add your lease or transaction documents, or click &quot;History&quot; at the top-right to pull previous agreements.
                      </p>
                    )}
                  </div>

                  {history.length > 0 && (
                    <div className="border-t border-black/10 pt-4 mt-6">
                      <h4 className="font-bold text-[10px] uppercase tracking-widest text-studio-gray mb-2">Recent uploads</h4>
                      <div className="flex flex-col gap-1.5">
                        {history.slice(0, 3).map(doc => (
                          <div 
                            key={doc.id}
                            className="text-xs font-semibold truncate hover:text-studio-coral cursor-pointer flex items-center gap-1 text-dark-text"
                            onClick={() => loadFromHistory(doc)}
                            onMouseEnter={() => setCursorHovered(true)} 
                            onMouseLeave={() => setCursorHovered(false)}
                          >
                            <ChevronRight className="w-3 h-3 text-studio-coral shrink-0" />
                            <span className="truncate">{doc.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Section III: Benefits Analysis ─── */}
        <section ref={benefitsRef} className="studio-section dark-theme">
          <div className="bg-text-grid">
            <div>ANALYSIS STAGE</div>
            <div>CLAUSE BALANCING</div>
            <div>BENEFIT CHECK</div>
          </div>

          <div className="z-10 max-w-[95%] w-full mx-auto">
            <span className="text-xs font-bold tracking-widest text-studio-coral uppercase block mb-2">Balance index</span>
            <h2 className="heading-display text-3xl sm:text-5xl mb-8">BENEFIT CHARTING</h2>

            {!docLoaded ? (
              <div className="studio-card p-8 text-center opacity-60">
                <BarChart3 className="w-12 h-12 text-studio-coral mx-auto mb-4" />
                <p className="font-bold">No agreement analyzed yet</p>
                <p className="text-xs text-studio-gray mt-1">Please submit a document under section II to activate analysis.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-6">
                {benefits.length === 0 ? (
                  <div className="studio-card p-8 text-center">
                    <Scale className="w-12 h-12 text-studio-coral mx-auto mb-4" />
                    <p className="font-bold mb-2">Check the benefit ratio</p>
                    <p className="text-xs text-studio-gray mb-6">Analyze who benefits most from the contractual terms.</p>
                    <button
                      onClick={runBenefitsAnalysis}
                      disabled={analyzingBenefits}
                      className="studio-btn"
                      onMouseEnter={() => setCursorHovered(true)} 
                      onMouseLeave={() => setCursorHovered(false)}
                    >
                      {analyzingBenefits ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analyzing Clauses (Mistral + Groq)...</>
                      ) : (
                        <><Sparkles className="w-4 h-4 mr-2" /> Launch AI Balance Analysis</>
                      )}
                    </button>
                    {error && (
                      <p className="text-xs text-red-500 mt-4 font-semibold select-all pointer-events-auto bg-red-500/10 border border-red-500/20 rounded px-4 py-2 block max-w-md mx-auto">
                        {error}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col gap-6">
                    {/* BenefitsChart above (full width) */}
                    <div>
                      <BenefitsChart benefits={benefits} onBenefitClick={handleBenefitClick} onHover={setCursorHovered} />
                    </div>

                    {/* Text explanation area (ContractViewer) below in frosted glass with a toggle */}
                    <div className="mt-4" id="contract-viewer-wrapper">
                      {showContractViewer ? (
                        <div className="flex flex-col gap-2">
                          <div className="flex justify-between items-center bg-white/5 border border-white/10 rounded px-4 py-2 select-none">
                            <span className="text-xs font-bold tracking-wider text-white">CONTRACT VIEWER (EXPANDED)</span>
                            <button
                              onClick={() => setShowContractViewer(false)}
                              onMouseEnter={() => setCursorHovered(true)}
                              onMouseLeave={() => setCursorHovered(false)}
                              className="studio-btn text-[9px] py-1 px-3 border-white/20 text-white hover:border-white"
                            >
                              Collapse
                            </button>
                          </div>
                          <ContractViewer benefits={benefits} highlightClause={highlightClause} isFrosted={true} />
                        </div>
                      ) : (
                        <div 
                          onClick={() => setShowContractViewer(true)}
                          onMouseEnter={() => setCursorHovered(true)}
                          onMouseLeave={() => setCursorHovered(false)}
                          className="studio-card frosted-glass p-4 cursor-pointer hover:bg-white/10 transition-all flex items-center justify-between"
                        >
                          <div className="flex items-center gap-2">
                            <FileSearch className="w-4 h-4 text-coral animate-pulse" />
                            <span className="text-xs font-bold tracking-wider text-white">CONTRACT DOCUMENT VIEWER (COLLAPSED)</span>
                          </div>
                          <button className="studio-btn text-[9px] py-1 px-3 border-white/20 text-white hover:border-white">
                            Expand
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* ─── Section IV: Chat ─── */}
        <section ref={chatRef} className="studio-section cream-theme">
          <div className="bg-text-grid cream-mode">
            <div>CHATBOT QUERY</div>
            <div>OBLIGATION DETAILS</div>
            <div>RISK ASSESSMENT</div>
          </div>

          <div className="z-10 max-w-[95%] w-full mx-auto">
            <span className="text-xs font-bold tracking-widest text-studio-coral uppercase block mb-2">Dialogue terminal</span>
            <h2 className="heading-display dark-text text-3xl sm:text-5xl mb-2">RISK CHAT</h2>

            {docLoaded && ragIndexing && (
              <p className="text-xs text-studio-gray mb-6 flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Indexing document for chat (embedding + vector store)...
              </p>
            )}
            {docLoaded && !ragIndexing && ragError && (
              <p className="text-xs text-red-600 mb-6 flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5" /> {ragError}
              </p>
            )}
            {docLoaded && !ragIndexing && !ragError && docId && (
              <p className="text-xs text-green-700 mb-6 flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5" /> Document indexed — chat is backed by real vector search.
              </p>
            )}
            {!docLoaded && <div className="mb-8" />}

            {!docLoaded ? (
              <div className="studio-card light-card p-8 text-center opacity-65">
                <HelpCircle className="w-12 h-12 text-studio-coral mx-auto mb-4" />
                <p className="font-bold text-dark-text">No active contract loaded</p>
                <p className="text-xs text-studio-gray mt-1">Submit text under section II to start conversing with the AI auditor.</p>
              </div>
            ) : (
              <div className="flex flex-col lg:flex-row gap-8 items-stretch w-full transition-all duration-500">
                {/* Chat dialogue flex column */}
                <div className={`transition-all duration-500 ease-in-out ${isQuickAuditorCollapsed ? 'w-full' : 'w-full lg:w-[60%]'}`}>
                  <div className="studio-card light-card p-5 flex flex-col h-[400px] justify-between">
                    <div className="flex items-center justify-between mb-2 pb-2 border-b border-black/5">
                      <span className="text-xs font-bold text-studio-gray uppercase tracking-wider">Chat Console</span>
                      {isQuickAuditorCollapsed && (
                        <button
                          onClick={() => setIsQuickAuditorCollapsed(false)}
                          onMouseEnter={() => setCursorHovered(true)}
                          onMouseLeave={() => setCursorHovered(false)}
                          className="studio-btn light-btn py-1 px-3 text-[9px]"
                        >
                          Show Auditor Options
                        </button>
                      )}
                    </div>
                    <div className="flex-1 overflow-y-auto flex flex-col gap-3 pr-2 mb-4 scrollbar-thin">
                      {messages.length === 0 ? (
                        <div className="h-full flex flex-col justify-center items-center text-center p-6 opacity-60">
                          <Building2 className="w-10 h-10 text-studio-coral mb-3" />
                          <p className="font-bold text-sm text-dark-text">Ask ContractIQ anything</p>
                          <p className="text-xs text-studio-gray mt-1">Type your question below or click a quick prompt on the right.</p>
                        </div>
                      ) : (
                        messages.map((msg, i) => (
                          <div key={i} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={msg.role === 'user' ? 'studio-chat-user' : 'studio-chat-ai light-chat-ai'}>
                              <p className="whitespace-pre-wrap text-xs">{msg.content}</p>
                            </div>
                          </div>
                        ))
                      )}

                      {loading && (
                        <div className="flex justify-start">
                          <div className="studio-chat-ai light-chat-ai py-4 px-6 flex items-center gap-1.5">
                            <div className="typing-dot" style={{ backgroundColor: '#1d1c19' }} />
                            <div className="typing-dot" style={{ backgroundColor: '#1d1c19' }} />
                            <div className="typing-dot" style={{ backgroundColor: '#1d1c19' }} />
                          </div>
                        </div>
                      )}
                      <div ref={chatEndRef} />
                    </div>

                    {/* Chat Form Input */}
                    <div className="border-t border-black/10 pt-3 flex gap-2">
                      <input
                        ref={inputRef}
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                        placeholder="Ask about this contract..."
                        className="flex-1 text-xs px-3 py-2 bg-white border border-black/10 focus:border-studio-coral rounded focus:outline-none text-dark-text"
                        disabled={loading}
                      />
                      <button
                        onClick={() => sendMessage()}
                        disabled={!input.trim() || loading}
                        className="studio-btn light-btn !px-4 !py-2 text-xs"
                        onMouseEnter={() => setCursorHovered(true)} 
                        onMouseLeave={() => setCursorHovered(false)}
                      >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                      </button>
                    </div>

                    {error && (
                      <p className="text-[10px] text-red-600 mt-2">{error}</p>
                    )}
                  </div>
                </div>

                {/* Quick actions flex column */}
                <div className={`transition-all duration-500 ease-in-out overflow-hidden flex ${isQuickAuditorCollapsed ? 'w-0 opacity-0 pointer-events-none' : 'w-full lg:w-[40%] opacity-100'}`}>
                  <div className="studio-card light-card p-6 h-full flex flex-col w-full">
                    <div className="flex justify-between items-center mb-4">
                      <h4 className="font-bold text-xs text-dark-text uppercase tracking-wider">Obligation Quick Auditor</h4>
                      <button
                        onClick={() => setIsQuickAuditorCollapsed(true)}
                        onMouseEnter={() => setCursorHovered(true)}
                        onMouseLeave={() => setCursorHovered(false)}
                        className="text-studio-gray hover:text-studio-coral text-[10px] uppercase font-bold"
                      >
                        Hide ✕
                      </button>
                    </div>
                    <div className="flex flex-col gap-2 overflow-y-auto max-h-[300px] pr-1">
                      {QUICK_QUESTIONS.map(({ icon: Icon, label, q }) => (
                        <button
                          key={label}
                          onClick={() => { sendMessage(q); setIsQuickAuditorCollapsed(true); }}
                          className="studio-btn light-btn text-[10px] py-2 px-3 text-left justify-start"
                          onMouseEnter={() => setCursorHovered(true)} 
                          onMouseLeave={() => setCursorHovered(false)}
                        >
                          <Icon className="w-3.5 h-3.5 mr-2 text-studio-coral shrink-0" />
                          <span className="truncate">{label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
