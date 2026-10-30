package com.knowflow.api.config;
import java.net.URI;
import java.time.Duration;
import com.knowflow.api.ai.AiInternalHealthClient;
public class QContractProbe {
 public static void main(String[] args) {
  AiServiceProperties p = new AiServiceProperties();
  p.setBaseUrl(URI.create(System.getenv("Q_PYTHON_URL")));
  p.setInternalSharedSecret(System.getenv("KNOWFLOW_INTERNAL_SHARED_SECRET"));
  try {
   var health = new AiInternalHealthClient(new AiHttpClientConfiguration().aiServiceWebClient(p)).check("q-r3-production-client").block(Duration.ofSeconds(7));
   System.out.println("health_client=ACCEPTED");
  } catch (Exception e) {
   System.out.println("health_client=REJECTED");
   System.out.println("exception_type="+e.getClass().getSimpleName());
   System.out.println("message="+e.getMessage());
  }
 }
}
