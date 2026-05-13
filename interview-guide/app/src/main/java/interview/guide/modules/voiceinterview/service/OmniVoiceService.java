package interview.guide.modules.voiceinterview.service;

import com.alibaba.dashscope.audio.omni.OmniRealtimeCallback;
import com.alibaba.dashscope.audio.omni.OmniRealtimeConfig;
import com.alibaba.dashscope.audio.omni.OmniRealtimeConversation;
import com.alibaba.dashscope.audio.omni.OmniRealtimeModality;
import com.alibaba.dashscope.audio.omni.OmniRealtimeParam;
import com.google.gson.JsonObject;
import interview.guide.modules.voiceinterview.config.VoiceInterviewProperties;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Qwen-Omni-Realtime Voice Service
 *
 * Wraps DashScope's OmniRealtimeConversation API, which unifies ASR + LLM + TTS
 * in a single WebSocket connection. This eliminates the separate ASR→LLM→TTS pipeline.
 *
 * Key features over the existing 3-service pipeline:
 * - Single WebSocket (lower latency, simpler lifecycle)
 * - Native interruption via {@code cancelResponse()}
 * - Server VAD for automatic speech endpoint detection
 * - Real-time bidirectional audio + text streaming
 */
@Slf4j
@Service
public class OmniVoiceService {

  private String apiKey;
  private String model;
  private String voice;
  private int silenceDurationMs;
  private final Map<String, OmniSession> sessions = new ConcurrentHashMap<>();

  public OmniVoiceService(VoiceInterviewProperties props) {
    applyConfig(props.getOmni());
  }

  public void reload(VoiceInterviewProperties props) {
    applyConfig(props.getOmni());
    log.info("OmniVoiceService reloaded: model={}, voice={}", model, voice);
  }

  private void applyConfig(VoiceInterviewProperties.OmniConfig omni) {
    this.apiKey = omni.getApiKey();
    this.model = omni.getModel();
    this.voice = omni.getVoice();
    this.silenceDurationMs = omni.getSilenceDurationMs();
  }

  /**
   * Callbacks for Omni voice session events delivered to the WebSocket handler.
   */
  public interface Callbacks {
    void onUserTranscript(String text, boolean isFinal);
    void onAiTextDelta(String text);
    void onAiAudioDelta(byte[] pcm);
    void onAiResponseDone();
    void onError(String message);
  }

  /**
   * Create and connect a new Omni voice session.
   *
   * @param sessionId   interview session identifier
   * @param instructions system prompt for the AI interviewer
   */
  public void createSession(String sessionId, String instructions, Callbacks callbacks) {
    if (sessions.containsKey(sessionId)) {
      closeSession(sessionId);
    }

    OmniRealtimeParam param = OmniRealtimeParam.builder()
        .model(model)
        .apikey(apiKey)
        .build();

    OmniRealtimeConversation conversation = new OmniRealtimeConversation(param, new OmniRealtimeCallback() {
      @Override
      public void onOpen() {
        log.info("[Omni:{}] WebSocket connected", sessionId);
      }

      @Override
      public void onEvent(JsonObject message) {
        handleEvent(sessionId, message, callbacks);
      }

      @Override
      public void onClose(int code, String reason) {
        log.warn("[Omni:{}] WebSocket closed code={} reason={}", sessionId, code, reason);
        sessions.remove(sessionId);
      }
    });

    OmniSession omniSession = new OmniSession(conversation, callbacks);
    sessions.put(sessionId, omniSession);

    new Thread(() -> {
      try {
        conversation.connect();

        OmniRealtimeConfig config = OmniRealtimeConfig.builder()
            .modalities(Arrays.asList(OmniRealtimeModality.TEXT, OmniRealtimeModality.AUDIO))
            .voice(voice)
            .enableInputAudioTranscription(true)
            .enableTurnDetection(true)
            .turnDetectionType("server_vad")
            .turnDetectionSilenceDurationMs(silenceDurationMs)
            .build();
        conversation.updateSession(config);

        // Send initial instructions as the first response
        conversation.createResponse(instructions, null);

        log.info("[Omni:{}] Session configured, model={} voice={}", sessionId, model, voice);
      } catch (Exception e) {
        log.error("[Omni:{}] Connection failed", sessionId, e);
        sessions.remove(sessionId);
        callbacks.onError("Omni 服务连接失败: " + e.getMessage());
      }
    }, "Omni-Connect-" + sessionId).start();
  }

  /** Send audio chunk from browser microphone. */
  public void sendAudio(String sessionId, String base64Audio) {
    OmniSession session = sessions.get(sessionId);
    if (session == null) {
      log.warn("[Omni:{}] sendAudio ignored, no active session", sessionId);
      return;
    }
    session.conversation.appendAudio(base64Audio);
  }

  /** Interrupt current AI response (cancel TTS playback + LLM generation). */
  public void interrupt(String sessionId) {
    OmniSession session = sessions.get(sessionId);
    if (session == null) {
      return;
    }
    log.info("[Omni:{}] Interrupting AI response", sessionId);
    session.conversation.cancelResponse();
    session.conversation.clearAppendedAudio();
  }

  /** Close the Omni session (non-blocking). */
  public void closeSession(String sessionId) {
    OmniSession session = sessions.remove(sessionId);
    if (session == null) {
      return;
    }
    session.conversation.endSessionAsync();
    try {
      session.conversation.close();
    } catch (Exception e) {
      log.debug("[Omni:{}] Error closing: {}", sessionId, e.getMessage());
    }
  }

  public boolean hasSession(String sessionId) {
    return sessions.containsKey(sessionId);
  }

  @PreDestroy
  public void destroy() {
    sessions.keySet().forEach(this::closeSession);
    sessions.clear();
  }

  // ---- event routing ----

  private void handleEvent(String sessionId, JsonObject msg, Callbacks cb) {
    if (!msg.has("type")) return;
    String type = msg.get("type").getAsString();

    switch (type) {
      case "conversation.item.input_audio_transcription.completed" -> {
        if (msg.has("transcript")) {
          String text = msg.get("transcript").getAsString();
          cb.onUserTranscript(text, true);
        }
      }
      case "conversation.item.input_audio_transcription.text" -> {
        // Partial transcript for live subtitles
        String text = extractPartialText(msg);
        if (text != null && !text.isBlank()) {
          cb.onUserTranscript(text, false);
        }
      }
      case "response.audio_transcript.delta" -> {
        if (msg.has("delta")) {
          String delta = msg.get("delta").getAsString();
          cb.onAiTextDelta(delta);
        }
      }
      case "response.audio.delta" -> {
        if (msg.has("delta")) {
          byte[] pcm = Base64.getDecoder().decode(msg.get("delta").getAsString());
          cb.onAiAudioDelta(pcm);
        }
      }
      case "response.done" -> cb.onAiResponseDone();
      case "error" -> {
        String errMsg = msg.has("error")
            ? msg.getAsJsonObject("error").toString()
            : "Unknown error";
        log.error("[Omni:{}] Server error: {}", sessionId, errMsg);
        cb.onError("Omni 服务错误: " + errMsg);
      }
      case "session.created", "session.updated", "response.created",
           "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped",
           "session.finished" -> {
        // lifecycle events, no action needed
      }
      default -> log.trace("[Omni:{}] Unhandled event: {}", sessionId, type);
    }
  }

  private static String extractPartialText(JsonObject msg) {
    if (msg.has("text") && !msg.get("text").isJsonNull()) {
      return msg.get("text").getAsString();
    }
    if (msg.has("delta") && !msg.get("delta").isJsonNull()) {
      return msg.get("delta").getAsString();
    }
    return null;
  }

  private record OmniSession(OmniRealtimeConversation conversation, Callbacks callbacks) {}
}
