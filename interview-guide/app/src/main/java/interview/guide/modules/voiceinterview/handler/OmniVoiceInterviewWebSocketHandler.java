package interview.guide.modules.voiceinterview.handler;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import interview.guide.common.exception.BusinessException;
import interview.guide.common.exception.ErrorCode;
import interview.guide.modules.voiceinterview.model.VoiceInterviewSessionEntity;
import interview.guide.modules.voiceinterview.service.OmniVoiceService;
import interview.guide.modules.voiceinterview.service.VoiceInterviewService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.ByteArrayOutputStream;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Omni Voice Interview WebSocket Handler
 *
 * Bridges the browser WebSocket to OmniVoiceService (Qwen-Omni-Realtime).
 * Key differences from the existing ASR→LLM→TTS pipeline:
 * - Single Omni WebSocket handles ASR+LLM+TTS end-to-end
 * - Native interruption: user speaks → cancelResponse
 * - Simpler handler: no separate STT/TTS service orchestration
 *
 * Message protocol (browser ↔ server):
 * <pre>
 * Browser → Server:
 *   {"type":"audio", "data":"base64Pcm16k"}
 *   {"type":"control", "action":"interrupt"}
 *   {"type":"control", "action":"end_interview"}
 *
 * Server → Browser:
 *   {"type":"subtitle", "text":"...", "isFinal":true|false}   // user transcript
 *   {"type":"text", "content":"...", "delta":true}            // AI text streaming
 *   {"type":"audio", "data":"base64Pcm24k"}                   // AI audio chunk
 *   {"type":"response_done"}                                   // AI turn complete
 *   {"type":"error", "message":"..."}
 * </pre>
 */
@Component
@Slf4j
public class OmniVoiceInterviewWebSocketHandler extends TextWebSocketHandler {

  private static final int WS_SEND_TIME_LIMIT_MS = 10_000;
  private static final int WS_SEND_BUFFER_LIMIT_BYTES = 512 * 1024;

  private final ObjectMapper objectMapper;
  private final OmniVoiceService omniVoiceService;
  private final VoiceInterviewService interviewService;
  private final Map<String, WebSocketSession> sessions = new ConcurrentHashMap<>();
  private final Map<String, SessionContext> contexts = new ConcurrentHashMap<>();

  public OmniVoiceInterviewWebSocketHandler(
      ObjectMapper objectMapper,
      OmniVoiceService omniVoiceService,
      VoiceInterviewService interviewService) {
    this.objectMapper = objectMapper;
    this.omniVoiceService = omniVoiceService;
    this.interviewService = interviewService;
  }

  @Override
  public void afterConnectionEstablished(WebSocketSession session) {
    String sessionId = extractSessionId(session);
    session.setTextMessageSizeLimit(256 * 1024);

    WebSocketSession safeSession = new ConcurrentWebSocketSessionDecorator(
        session, WS_SEND_TIME_LIMIT_MS, WS_SEND_BUFFER_LIMIT_BYTES);
    sessions.put(sessionId, safeSession);
    contexts.put(sessionId, new SessionContext());
    log.info("[OmniWS:{}] Connected", sessionId);

    try {
      VoiceInterviewSessionEntity entity = getSessionEntity(sessionId);
      String instructions = buildInstructions(entity);
      omniVoiceService.createSession(sessionId, instructions, new OmniVoiceService.Callbacks() {
        @Override
        public void onUserTranscript(String text, boolean isFinal) {
          sendMessage(safeSession, toJson(Map.of(
              "type", "subtitle",
              "text", text,
              "isFinal", isFinal
          )));
          if (isFinal) {
            var ctx = contexts.get(sessionId);
            if (ctx != null) {
              ctx.userText.set(text);
            }
          }
        }

        @Override
        public void onAiTextDelta(String text) {
          sendMessage(safeSession, toJson(Map.of(
              "type", "text",
              "content", text,
              "delta", true
          )));
          var ctx = contexts.get(sessionId);
          if (ctx != null) {
            ctx.aiTextBuilder.append(text);
          }
        }

        @Override
        public void onAiAudioDelta(byte[] pcm) {
          var ctx = contexts.get(sessionId);
          if (ctx != null) {
            ctx.aiAudioOutput.writeBytes(pcm);
          }
          // Send individual PCM chunk as base64
          String base64Audio = Base64.getEncoder().encodeToString(pcm);
          sendMessage(safeSession, toJson(Map.of(
              "type", "audio",
              "data", base64Audio
          )));
        }

        @Override
        public void onAiResponseDone() {
          var ctx = contexts.get(sessionId);
          if (ctx != null) {
            String userText = ctx.userText.get();
            String aiText = ctx.aiTextBuilder.toString();
            if (!aiText.isEmpty()) {
              saveMessage(sessionId, userText, aiText);
            }
            ctx.reset();
          }
          sendMessage(safeSession, toJson(Map.of("type", "response_done")));
        }

        @Override
        public void onError(String error) {
          sendError(safeSession, error);
        }
      });
    } catch (Exception e) {
      log.error("[OmniWS:{}] Failed to create Omni session", sessionId, e);
      sendError(safeSession, "创建语音会话失败: " + e.getMessage());
    }
  }

  @Override
  protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
    String sessionId = extractSessionId(session);
    try {
      JsonNode msg = objectMapper.readTree(message.getPayload());
      String type = msg.get("type").asText();

      switch (type) {
        case "audio" -> {
          String data = msg.has("data") ? msg.get("data").asText() : null;
          if (data != null && !data.isEmpty()) {
            omniVoiceService.sendAudio(sessionId, data);
          }
        }
        case "control" -> {
          String action = msg.has("action") ? msg.get("action").asText() : "";
          switch (action) {
            case "interrupt" -> omniVoiceService.interrupt(sessionId);
            case "end_interview" -> closeSession(sessionId, session);
            default -> log.warn("[OmniWS:{}] Unknown control action: {}", sessionId, action);
          }
        }
        default -> log.warn("[OmniWS:{}] Unknown message type: {}", sessionId, type);
      }
    } catch (Exception e) {
      log.error("[OmniWS:{}] Error handling message", sessionId, e);
      sendError(session, "消息处理失败: " + e.getMessage());
    }
  }

  @Override
  public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
    String sessionId = extractSessionId(session);
    sessions.remove(sessionId);
    contexts.remove(sessionId);
    omniVoiceService.closeSession(sessionId);
    log.info("[OmniWS:{}] Disconnected, status={}", sessionId, status);

    try {
      interviewService.endSessionIfInProgress(sessionId);
    } catch (Exception e) {
      log.warn("[OmniWS:{}] Failed to auto-end session on disconnect: {}", sessionId, e.getMessage());
    }
  }

  @Override
  public void handleTransportError(WebSocketSession session, Throwable exception) {
    log.error("[OmniWS:{}] Transport error", extractSessionId(session), exception);
  }

  // ---- helpers ----

  private String extractSessionId(WebSocketSession session) {
    String path = session.getUri().getPath();
    return path.substring(path.lastIndexOf('/') + 1);
  }

  private void sendMessage(WebSocketSession session, String json) {
    try {
      if (session.isOpen()) {
        session.sendMessage(new TextMessage(json));
      }
    } catch (Exception e) {
      log.error("Error sending message", e);
    }
  }

  private void sendError(WebSocketSession session, String error) {
    sendMessage(session, toJson(Map.of("type", "error", "message", error)));
  }

  private String toJson(Object obj) {
    try {
      return objectMapper.writeValueAsString(obj);
    } catch (Exception e) {
      return "{}";
    }
  }

  private void closeSession(String sessionId, WebSocketSession session) {
    omniVoiceService.closeSession(sessionId);
    try {
      interviewService.endSession(sessionId);
    } catch (Exception e) {
      log.warn("[OmniWS:{}] Error ending interview session: {}", sessionId, e.getMessage());
    }
    try {
      if (session.isOpen()) {
        session.close(CloseStatus.NORMAL);
      }
    } catch (Exception e) {
      log.debug("[OmniWS:{}] Already closed: {}", sessionId, e.getMessage());
    }
  }

  private VoiceInterviewSessionEntity getSessionEntity(String sessionId) {
    try {
      long id = Long.parseLong(sessionId);
      VoiceInterviewSessionEntity entity = interviewService.getSession(id);
      if (entity == null) {
        throw new BusinessException(ErrorCode.VOICE_SESSION_NOT_FOUND, "会话不存在: " + sessionId);
      }
      return entity;
    } catch (NumberFormatException e) {
      throw new BusinessException(ErrorCode.VOICE_SESSION_NOT_FOUND, "无效的会话ID: " + sessionId);
    }
  }

  private String buildInstructions(VoiceInterviewSessionEntity entity) {
    return """
        你是一位友好、乐于助人的AI语音助手。
        要求：
        - 用中文进行自然流畅的对话
        - 像真人朋友一样聊天，热情但简洁
        - 每次回复控制在2-3句话，不要过长
        - 称呼对方为"你"
        - 对话开始请简单打个招呼
        """;
  }

  private void saveMessage(String sessionId, String userText, String aiText) {
    try {
      interviewService.saveMessage(sessionId,
          userText != null && !userText.isBlank() ? userText : null,
          aiText);
    } catch (Exception e) {
      log.error("[OmniWS:{}] Failed to save message", sessionId, e);
    }
  }

  private static class SessionContext {
    final AtomicReference<String> userText = new AtomicReference<>("");
    final StringBuilder aiTextBuilder = new StringBuilder();
    final ByteArrayOutputStream aiAudioOutput = new ByteArrayOutputStream();

    void reset() {
      userText.set("");
      aiTextBuilder.setLength(0);
      aiAudioOutput.reset();
    }
  }
}
