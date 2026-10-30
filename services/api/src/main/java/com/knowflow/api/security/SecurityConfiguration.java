package com.knowflow.api.security;

import com.knowflow.api.config.AiServiceProperties;
import com.knowflow.api.error.ApiErrorWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http,
                                               AiServiceProperties aiProperties,
                                               ApiErrorWriter errors) throws Exception {
        RequestIdFilter requestIdFilter = new RequestIdFilter();
        InternalSecretAuthenticationFilter internalAuthFilter =
                new InternalSecretAuthenticationFilter(aiProperties.getInternalSharedSecret());

        http
                .csrf(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS))
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, cause) -> errors.write(
                                request, response, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED",
                                "Authentication is required."))
                        .accessDeniedHandler((request, response, cause) -> errors.write(
                                request, response, HttpStatus.NOT_FOUND, "ENDPOINT_UNAVAILABLE",
                                "The requested endpoint is not available.")))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/actuator/**").denyAll()
                        .requestMatchers("/internal/**").hasRole("INTERNAL_AI")
                        .anyRequest().denyAll())
                .addFilterAfter(requestIdFilter, SecurityContextHolderFilter.class)
                .addFilterAfter(internalAuthFilter, RequestIdFilter.class);

        return http.build();
    }
}
