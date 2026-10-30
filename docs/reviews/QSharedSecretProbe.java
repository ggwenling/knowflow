package com.knowflow.api.config;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.time.Duration;
public class QSharedSecretProbe {
 public static void main(String[] args) throws Exception {
  AiServiceProperties p = new AiServiceProperties();
  p.setInternalSharedSecret("A".repeat(40) + "\n");
  System.out.println("configuration_accepts_newline=" + p.isInternalSharedSecretAllowed());
  HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  server.createContext("/probe", exchange -> { exchange.sendResponseHeaders(200,-1); exchange.close(); });
  server.start();
  p.setBaseUrl(java.net.URI.create("http://127.0.0.1:"+server.getAddress().getPort()));
  try {
   new AiHttpClientConfiguration().aiServiceWebClient(p).get().uri("/probe").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(3));
   System.out.println("outbound_request=SUCCEEDED");
  } catch(Exception e) {
   System.out.println("outbound_request=FAILED");
   for(Throwable t=e;t!=null;t=t.getCause())System.out.println("cause_type="+t.getClass().getSimpleName());
  } finally { server.stop(0); }
 }
}
