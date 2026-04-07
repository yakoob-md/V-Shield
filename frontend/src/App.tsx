import React, { useState, useRef, useEffect } from "react";
import { 
  MessageCircle, 
  Trash2, 
  History, 
  Menu, 
  LifeBuoy, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  HelpCircle,
  Copy,
  Volume2,
  Plus
} from "lucide-react";
import { PromptInputBox } from "@/components/ui/PromptInputBox";
import { EtheralShadow } from "@/components/ui/etheral-shadow";
import { useChat } from "@/hooks/useChat";
import { useVoice } from "@/hooks/useVoice";
import { cn } from "@/lib/utils";

const App: React.FC = () => {
  const { 
    currentChatId, 
    chatSessions, 
    messages, 
    isLoading, 
    createChat, 
    loadChat, 
    sendMessage, 
    sendVoice, 
    deleteChat 
  } = useChat();
  
  const { isRecording, startRecording, stopRecording } = useVoice();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activePlayingId, setActivePlayingId] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (text: string) => {
    if (text.trim()) {
      await sendMessage(text);
    }
  };

  const handleVoiceSend = async () => {
    const audioBlob = await stopRecording();
    if (audioBlob) {
      await sendVoice(audioBlob);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const handleNarration = async (msgId: number, text: string, lang: string) => {
    if (activePlayingId === msgId) {
      audioRef.current?.pause();
      setActivePlayingId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
    }

    console.log("Narration clicked", text); // For debugging logic as requested
    const url = `http://localhost:8000/api/tts?text=${encodeURIComponent(text)}&lang=${lang}`;
    const audio = new Audio(url);
    audioRef.current = audio;
    setActivePlayingId(msgId);

    audio.onended = () => setActivePlayingId(null);
    audio.play().catch(err => {
      console.error("Audio playback error:", err);
      setActivePlayingId(null);
    });
  };

  const getRiskIcon = (level: string) => {
    switch (level) {
      case "safe": return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case "caution": return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
      case "banned": return <XCircle className="w-4 h-4 text-red-500" />;
      default: return <HelpCircle className="w-4 h-4 text-purple-500" />;
    }
  };



  return (
    <div className="flex h-screen bg-[#020617] text-slate-100 overflow-hidden font-sans relative">
      {/* Background Animation - Vivid & Wow */}
      <div className="fixed inset-0 z-0">
        <EtheralShadow
          color="rgba(79, 70, 229, 0.4)" // Indigo
          animation={{ scale: 80, speed: 40 }}
          noise={{ opacity: 0.2, scale: 1 }}
          sizing="fill"
          className="opacity-40"
        />
        <EtheralShadow
          color="rgba(6, 182, 212, 0.3)" // Cyan
          animation={{ scale: 100, speed: 30 }}
          noise={{ opacity: 0, scale: 1 }}
          sizing="fill"
          className="opacity-30 mix-blend-screen"
          style={{ transform: 'rotate(180deg)' }}
        />
      </div>

      {/* Sidebar - Floating Glass */}
      <aside 
        className={cn(
          "fixed md:relative z-50 flex flex-col m-4 mr-0 glass-panel rounded-3xl transition-all duration-500 ease-in-out",
          sidebarOpen ? "w-[300px]" : "w-0 -ml-10 opacity-0 overflow-hidden"
        )}
      >
        <div className="flex flex-col h-full p-6">
          <div className="flex items-center gap-3 mb-10 px-2">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
              <MessageCircle className="w-6 h-6 text-white" />
            </div>
            <h2 className="text-xl font-black italic tracking-tighter premium-gradient-text uppercase">Shield AI</h2>
          </div>

          <button 
            className="flex items-center gap-3 w-full p-4 mb-8 rounded-2xl bg-white/10 hover:bg-white/15 border border-white/10 transition-all group shadow-xl"
            onClick={() => createChat()}
          >
            <Plus className="w-5 h-5 text-sky-400 group-hover:rotate-90 transition-transform duration-300" />
            <span className="text-sm font-bold text-slate-200">New Conversation</span>
          </button>

          <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
            <div className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em] px-3 mb-4 opacity-50">Journal</div>
            {chatSessions.map((session) => (
              <div 
                key={session.id} 
                className={cn(
                  "group flex items-center justify-between p-4 rounded-2xl cursor-pointer transition-all duration-300 border",
                  currentChatId === session.id 
                    ? "bg-white/15 border-white/20 shadow-lg shadow-black/20" 
                    : "bg-transparent border-transparent hover:bg-white/5"
                )}
                onClick={() => loadChat(session.id)}
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <History className={cn("w-4 h-4 flex-shrink-0", currentChatId === session.id ? "text-sky-400" : "text-slate-500")} />
                  <span className={cn("text-xs truncate font-semibold", currentChatId === session.id ? "text-white" : "text-slate-400 group-hover:text-slate-200")}>
                    {session.title}
                  </span>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); deleteChat(session.id); }}
                  className="opacity-0 group-hover:opacity-100 p-2 hover:bg-red-500/20 rounded-xl text-slate-500 hover:text-red-400 transition-all"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <div className="mt-auto pt-6 border-t border-white/10">
            <div className="flex items-center gap-4 w-full p-5 rounded-2xl bg-white/5 border border-white/5">
               <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center p-[2px]">
                 <div className="w-full h-full rounded-full bg-slate-900 flex items-center justify-center">
                    <LifeBuoy className="w-5 h-5 text-sky-400" />
                 </div>
               </div>
               <div className="flex flex-col">
                 <span className="text-[11px] font-black text-white uppercase tracking-widest">Athlete Shield</span>
                 <span className="text-[10px] text-slate-400 font-medium">NADA Verified v2.1</span>
               </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden h-full z-10 m-4 ml-2 md:ml-4 glass-panel rounded-3xl">
        {/* Header */}
        <header className="flex items-center justify-between p-6 border-b border-white/10 bg-white/5 backdrop-blur-3xl">
          <div className="flex items-center gap-6">
             <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-3 bg-white/5 hover:bg-white/10 rounded-xl text-slate-300 transition-all shadow-inner">
               <Menu className="w-5 h-5" />
             </button>
             <div>
               <h1 className="text-xl font-black tracking-tight premium-gradient-text uppercase">NADA Assistant</h1>
               <div className="flex items-center gap-2 mt-1">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_12px_rgba(34,197,94,0.6)]" />
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Neural Shield Active</span>
               </div>
             </div>
          </div>
          <div className="flex items-center gap-4">
             <div className="hidden lg:flex flex-col items-end mr-4">
                <span className="text-[10px] font-black text-slate-500 uppercase tracking-tighter">Secure Thread</span>
                <span className="text-[12px] text-slate-300 font-bold truncate max-w-[250px]">
                  {chatSessions.find(s => s.id === currentChatId)?.title || "Select or start a chat"}
                </span>
             </div>
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto px-6 py-12 space-y-12 no-scrollbar scroll-smooth">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full animate-in fade-in zoom-in duration-1000">
               <div className="w-32 h-32 glass-card rounded-[2.5rem] flex items-center justify-center mb-8 border border-white/20 shadow-2xl rotate-6 transition-transform hover:rotate-0 duration-500">
                  <MessageCircle className="w-14 h-14 text-sky-400" />
               </div>
               <h2 className="text-4xl font-black text-white mb-4 tracking-tighter uppercase text-center">Guardian of Clean Sport</h2>
               <p className="text-sm text-slate-400 max-w-md text-center leading-relaxed font-bold">
                 Poochiye koi bhi sawaal doping, supplements, ya medications ke baare mein. 
                 <span className="block mt-4 text-[11px] text-sky-400 uppercase font-black tracking-[0.3em]">Built for the modern road athlete.</span>
               </p>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto space-y-10 pb-40">
              {messages.map((msg, idx) => (
                <div key={msg.id || idx} className="animate-in fade-in slide-in-from-bottom-8 duration-700">
                  {msg.role === 'user' ? (
                    /* User Question */
                    <div className="flex flex-col items-end gap-3 pr-4">
                      <div className="bg-sky-500/20 backdrop-blur-xl border border-sky-500/30 px-8 py-5 rounded-3xl rounded-tr-lg max-w-[80%] shadow-2xl shadow-sky-500/10">
                        <p className="text-[15px] text-sky-50 leading-relaxed font-semibold tracking-tight whitespace-pre-wrap">{msg.content}</p>
                      </div>
                      <span className="text-[10px] text-sky-400 font-black uppercase tracking-widest mr-4">Athlete User</span>
                    </div>
                  ) : (
                    /* AI Response */
                    <div className="flex flex-col items-start gap-5 pl-4">
                      <div className="flex items-center gap-4 px-4">
                         <div className={cn("flex items-center gap-2 px-5 py-2 rounded-full border text-[11px] font-black uppercase tracking-widest shadow-xl backdrop-blur-md", 
                           msg.risk_level === 'safe' ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400 shadow-emerald-500/10" :
                           msg.risk_level === 'caution' ? "bg-amber-500/20 border-amber-500/30 text-amber-400 shadow-amber-500/10" :
                           msg.risk_level === 'banned' ? "bg-rose-500/20 border-rose-500/30 text-rose-400 shadow-rose-500/10" :
                           "bg-slate-500/20 border-slate-500/30 text-slate-400 shadow-slate-500/10"
                         )}>
                           {getRiskIcon(msg.risk_level)}
                           {msg.risk_level}
                         </div>
                         <span className="text-[10px] text-slate-500 font-mono font-bold uppercase tracking-tighter">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                      </div>
                      
                      <div className="group relative w-full pr-8">
                         <div className="absolute -inset-2 bg-gradient-to-r from-sky-500/20 via-indigo-500/10 to-purple-500/20 rounded-[2.5rem] opacity-0 group-hover:opacity-100 blur-2xl transition-all duration-700 pointer-events-none" />
                         <div className="relative glass-card px-10 py-8 rounded-[2.5rem] rounded-tl-lg shadow-2xl w-full">
                            <p className="text-[16px] text-slate-100 leading-9 font-medium tracking-wide whitespace-pre-wrap selection:bg-sky-500/30">
                               {msg.content}
                            </p>
                            <div className="flex items-center gap-4 mt-8 opacity-0 group-hover:opacity-100 transition-all duration-500 translate-y-4 group-hover:translate-y-0">
                               <button 
                                 onClick={() => copyToClipboard(msg.content)}
                                 className="glass-button flex items-center gap-2 px-5 py-2.5 rounded-2xl text-slate-300 hover:text-sky-400 font-black uppercase text-[10px] shadow-lg shadow-black/40"
                               >
                                 <Copy className="w-4 h-4" />
                                 <span>Copy</span>
                               </button>
                               <button 
                                 onClick={() => handleNarration(msg.id, msg.content, msg.language)}
                                 className={cn(
                                   "glass-button flex items-center gap-2 px-5 py-2.5 rounded-2xl font-black uppercase text-[10px] shadow-lg shadow-black/40",
                                   activePlayingId === msg.id ? "text-sky-400 bg-white/15" : "text-slate-300"
                                 )}
                               >
                                  <Volume2 className={cn("w-4 h-4", activePlayingId === msg.id && "animate-pulse")} />
                                  <span>{activePlayingId === msg.id ? "Stopping..." : "Narration"}</span>
                               </button>
                            </div>
                         </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="w-full absolute bottom-0 left-0 bg-gradient-to-t from-[#020617] via-[#020617]/90 to-transparent pt-32 pb-8 px-6">
           <div className="max-w-4xl mx-auto relative">
             {isLoading && (
               <div className="absolute -top-16 left-1/2 -translate-x-1/2 flex items-center gap-4 glass-panel border-sky-500/20 shadow-2xl shadow-sky-500/10 px-8 py-3 rounded-full animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-sky-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" />
                  </div>
                  <span className="text-[11px] font-black text-sky-400 uppercase tracking-[0.3em]">Quantum Search Active</span>
               </div>
             )}
             
             <PromptInputBox 
                onSend={handleSend} 
                isLoading={isLoading} 
                isRecording={isRecording}
                onStartRecording={startRecording}
                onStopRecording={handleVoiceSend}
                placeholder="Ask about supplements, banned items, or safety rules..."
              />
             
             <div className="mt-6 flex items-center justify-center gap-10 opacity-30">
               <div className="flex items-center gap-2">
                 <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">WADA 2024</span>
               </div>
               <div className="flex items-center gap-2">
                 <CheckCircle2 className="w-4 h-4 text-sky-400" />
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">CoE-NSTS</span>
               </div>
               <div className="flex items-center gap-2">
                 <XCircle className="w-4 h-4 text-rose-500" />
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Zero Doping Shield</span>
               </div>
             </div>
           </div>
        </div>
      </main>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 5px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
};

export default App;
