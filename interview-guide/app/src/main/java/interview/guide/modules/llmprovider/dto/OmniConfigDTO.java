package interview.guide.modules.llmprovider.dto;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class OmniConfigDTO {
  private String model;
  private String maskedApiKey;
  private String voice;
  private int silenceDurationMs;
}
