import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { PhoneOff, Bot, Mic, ArrowLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import AudioRecorder from '../components/AudioRecorder';
import InterviewPageHeader from '../components/InterviewPageHeader';
import { voiceInterviewApi } from '../api/voiceInterview';

interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
  id: string;
}

export default function OmniVoiceChatPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const queryParams = new URLSearchParams(location.search);
  const skillId = queryParams.get('skillId') || 'java-backend';
  const difficulty = queryParams.get('difficulty') || 'mid';
  const resumeId = queryParams.get('resumeId') || undefined;

  const [isRecording, setIsRecording] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [userText, setUserText] = useState('');
  const [aiText, setAiText] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const sessionIdRef = useRef<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const aiTextRef = useRef('');
  const isAiSpeakingRef = useRef(false);
  const queueRef = useRef<AudioBuffer[]>([]);
  const playingRef = useRef(false);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const lastCommittedRef = useRef('');

  useEffect(() => { aiTextRef.current = aiText; }, [aiText]);
  useEffect(() => { isAiSpeakingRef.current = isAiSpeaking; }, [isAiSpeaking]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'User left');
      }
      sourceRef.current?.stop();
      audioContextRef.current?.close();
    };
  }, []);

  // ---- Audio playback for Omni PCM chunks (24kHz, 16-bit, mono) ----
  const getAudioCtx = useCallback(() => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new AudioContext({ sampleRate: 24000 });
    }
    return audioContextRef.current;
  }, []);

  const playNext = useCallback(() => {
    if (queueRef.current.length === 0) {
      playingRef.current = false;
      return;
    }
    playingRef.current = true;
    const ctx = getAudioCtx();
    if (ctx.state === 'suspended') ctx.resume();
    const buffer = queueRef.current.shift()!;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    sourceRef.current = source;
    source.onended = () => {
      sourceRef.current = null;
      playNext();
    };
    source.start(0);
  }, [getAudioCtx]);

  const handlePcmChunk = useCallback((base64Pcm: string) => {
    try {
      const binary = atob(base64Pcm);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const sampleCount = bytes.length / 2;
      const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, sampleCount);
      const float32 = new Float32Array(sampleCount);
      for (let i = 0; i < sampleCount; i++) float32[i] = pcm[i] / 32768.0;

      const ctx = getAudioCtx();
      const audioBuffer = ctx.createBuffer(1, float32.length, 24000);
      audioBuffer.getChannelData(0).set(float32);

      queueRef.current.push(audioBuffer);
      setIsAiSpeaking(true);
      if (!playingRef.current) playNext();
    } catch (e) {
      console.error('[Omni] Audio decode error:', e);
    }
  }, [getAudioCtx, playNext]);

  // ---- WebSocket connection ----
  const connect = useCallback(async () => {
    setError(null);
    setConnectionStatus('connecting');
    try {
      const session = await voiceInterviewApi.createSession({
        skillId,
        difficulty,
        resumeId: resumeId ? Number(resumeId) : undefined,
        introEnabled: true,
        techEnabled: true,
        projectEnabled: true,
        hrEnabled: false,
        plannedDuration: 15,
      });

      sessionIdRef.current = session.sessionId;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/omni-voice/${session.sessionId}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => setConnectionStatus('connected');
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          switch (msg.type) {
            case 'subtitle':
              if (msg.isFinal) {
                const text = (msg.text || '').trim();
                if (text) {
                  setMessages(prev => [...prev, { role: 'user', text, id: `u-${Date.now()}` }]);
                }
                setUserText('');
              } else {
                setUserText(msg.text || '');
              }
              break;
            case 'text':
              setAiText(prev => prev + (msg.content || ''));
              break;
            case 'audio':
              handlePcmChunk(msg.data);
              break;
            case 'response_done':
              setIsAiSpeaking(false);
              sourceRef.current?.stop();
              queueRef.current.length = 0;
              playingRef.current = false;
              const finalText = aiTextRef.current.trim();
              if (finalText && finalText !== lastCommittedRef.current) {
                lastCommittedRef.current = finalText;
                setMessages(prev => [...prev, { role: 'ai', text: finalText, id: `ai-${Date.now()}` }]);
              }
              setAiText('');
              break;
            case 'error':
              setError(msg.message || '服务错误');
              break;
          }
        } catch {
          // ignore parse errors
        }
      };
      ws.onclose = (e) => {
        setConnectionStatus('disconnected');
        if (e.code !== 1000) setError('连接已断开');
      };
      ws.onerror = () => {
        setConnectionStatus('disconnected');
        setError('WebSocket 连接错误');
      };
    } catch (e) {
      setConnectionStatus('disconnected');
      setError('创建会话失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
  }, [skillId, difficulty, resumeId, handlePcmChunk]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- User actions ----
  const sendAudio = useCallback((audioData: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const msg = JSON.stringify({ type: 'audio', data: audioData, timestamp: Date.now() });
      wsRef.current.send(msg);

      if (isAiSpeakingRef.current) {
        // Interrupt: user speaks while AI is talking
        wsRef.current.send(JSON.stringify({ type: 'control', action: 'interrupt' }));
        sourceRef.current?.stop();
        queueRef.current.length = 0;
        playingRef.current = false;
        setIsAiSpeaking(false);
      }
    }
  }, []);

  const endInterview = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'control', action: 'end_interview' }));
    }
    wsRef.current?.close(1000, 'User ended');
    setConnectionStatus('disconnected');
  }, []);

  const handleMicToggle = useCallback(() => {
    setIsRecording(prev => !prev);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button
          onClick={() => { endInterview(); navigate(-1); }}
          className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <InterviewPageHeader
          title="语音对话 (Omni)"
          subtitle="AI 面试官 - 可打断实时对话"
          icon={<Bot className="w-6 h-6 text-white" />}
        />
      </div>

      {/* Error banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="mx-4 mt-4 p-3 bg-red-900/60 border border-red-700/50 rounded-xl text-red-200 text-sm flex items-center gap-2"
          >
            <span className="shrink-0">!</span>
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-red-300 hover:text-red-100">x</button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status bar */}
      <div className="flex items-center gap-2 px-4 py-2 text-xs text-slate-400">
        <div className={`w-2 h-2 rounded-full ${
          connectionStatus === 'connected' ? 'bg-emerald-400' :
          connectionStatus === 'connecting' ? 'bg-amber-400 animate-pulse' :
          'bg-red-400'
        }`} />
        <span>
          {connectionStatus === 'connected' ? '已连接 - 开始对话' :
           connectionStatus === 'connecting' ? '连接中...' : '未连接'}
        </span>
        {isAiSpeaking && <span className="text-indigo-400 ml-2">AI 正在说话...</span>}
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && connectionStatus === 'connected' && (
          <div className="text-center text-slate-500 mt-8">
            <Bot className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>点击麦克风开始对话</p>
            <p className="text-xs mt-2 text-slate-600">说话后 AI 会自动回复，你可以随时打断</p>
          </div>
        )}
        <AnimatePresence>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-indigo-600/50 border border-indigo-500/30 text-white'
                  : 'bg-slate-800 border border-slate-700/50 text-slate-200'
              }`}>
                {msg.role === 'ai' && <Bot className="w-4 h-4 inline mr-1.5 mb-0.5 text-indigo-400" />}
                {msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Live subtitles (not yet committed to messages) */}
        {userText && (
          <div className="flex justify-end">
            <div className="max-w-[80%] px-4 py-2 rounded-2xl bg-indigo-600/20 border border-indigo-500/20 text-slate-300 text-sm italic">
              {userText}
            </div>
          </div>
        )}
        {aiText && (
          <div className="flex justify-start">
            <div className="max-w-[80%] px-4 py-2 rounded-2xl bg-slate-800/50 border border-slate-700/30 text-slate-300 text-sm italic">
              <Bot className="w-4 h-4 inline mr-1 mb-0.5 text-indigo-400" />
              {aiText}
            </div>
          </div>
        )}
      </div>

      {/* Bottom controls */}
      <div className="p-4 border-t border-slate-800 flex items-center justify-center gap-4">
        {/* End interview */}
        <button
          onClick={endInterview}
          className="p-3 rounded-full bg-red-900/50 border border-red-700/40 text-red-300 hover:bg-red-800/50 transition-colors"
          title="结束对话"
        >
          <PhoneOff className="w-5 h-5" />
        </button>

        {/* Mic button */}
        <button
          onClick={handleMicToggle}
          disabled={connectionStatus !== 'connected'}
          className={`p-5 rounded-full transition-all ${
            isRecording
              ? 'bg-indigo-600 shadow-lg shadow-indigo-500/40 text-white scale-110'
              : 'bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
          title={isAiSpeaking ? '点击打断 AI 回复' : '点击开始/停止录音'}
        >
          <Mic className={`w-6 h-6 ${isRecording ? 'animate-pulse' : ''}`} />
        </button>

        {/* Interrupt hint */}
        {isAiSpeaking && (
          <span className="text-xs text-amber-400 animate-pulse">点击麦克风打断</span>
        )}
      </div>

      {/* Hidden AudioRecorder for VAD-based audio capture */}
      <AudioRecorder
        isRecording={isRecording}
        onRecordingChange={setIsRecording}
        onAudioData={sendAudio}
        onSpeechStart={() => {}}
        onSpeechEnd={() => {}}
      />
    </div>
  );
}
