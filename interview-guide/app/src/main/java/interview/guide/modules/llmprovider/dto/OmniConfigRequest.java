package interview.guide.modules.llmprovider.dto;

public record OmniConfigRequest(
    String model,
    String apiKey,
    String voice,
    Integer silenceDurationMs
) {}
