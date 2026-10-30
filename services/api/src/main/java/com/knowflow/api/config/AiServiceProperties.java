package com.knowflow.api.config;

import java.net.URI;
import java.util.Set;
import java.util.regex.Pattern;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "knowflow.ai")
public class AiServiceProperties {
    private static final Set<String> ALLOWED_SCHEMES = Set.of("http", "https");
    private static final Pattern BEARER_TOKEN = Pattern.compile("[A-Za-z0-9._~+/-]+=*\\z");

    @NotNull
    private URI baseUrl = URI.create("http://localhost:8000");

    private String internalSharedSecret;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getInternalSharedSecret() {
        return internalSharedSecret;
    }

    public void setInternalSharedSecret(String internalSharedSecret) {
        this.internalSharedSecret = internalSharedSecret;
    }

    @AssertTrue(message = "AI service base URL must use HTTP(S) and cannot contain credentials, query, or fragment")
    public boolean isBaseUrlAllowed() {
        if (baseUrl == null || baseUrl.getScheme() == null || baseUrl.getHost() == null) {
            return false;
        }
        return ALLOWED_SCHEMES.contains(baseUrl.getScheme().toLowerCase())
                && baseUrl.getUserInfo() == null
                && baseUrl.getQuery() == null
                && baseUrl.getFragment() == null;
    }

    @AssertTrue(message = "AI internal shared secret must contain 32 to 256 valid Bearer token characters")
    public boolean isInternalSharedSecretAllowed() {
        return internalSharedSecret != null
                && internalSharedSecret.length() >= 32
                && internalSharedSecret.length() <= 256
                && BEARER_TOKEN.matcher(internalSharedSecret).matches();
    }
}
