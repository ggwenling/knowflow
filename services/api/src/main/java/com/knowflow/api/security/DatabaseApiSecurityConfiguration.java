package com.knowflow.api.security;

import com.knowflow.api.config.AiServiceProperties;
import com.knowflow.api.error.ApiErrorWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
@Profile("database")
public class DatabaseApiSecurityConfiguration {
    @Bean
    SecurityFilterChain databaseApiSecurityFilterChain(
            HttpSecurity http,
            AiServiceProperties aiProperties,
            ApiErrorWriter errors,
            JdbcTemplate jdbc) throws Exception {
        RequestIdFilter requestIdFilter = new RequestIdFilter();
        InternalSecretAuthenticationFilter internalAuthFilter =
                new InternalSecretAuthenticationFilter(aiProperties.getInternalSharedSecret());
        OncePerRequestFilter bearerSessionFilter = new BearerSessionAuthenticationFilter(jdbc, errors);
        RequestBodySizeLimitFilter indexBatchLimitFilter = new RequestBodySizeLimitFilter(errors);

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
                        .requestMatchers(HttpMethod.POST,
                                "/api/v1/auth/register", "/api/v1/auth/login").permitAll()
                        .requestMatchers("/internal/**").hasRole("INTERNAL_AI")
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll())
                .addFilterAfter(requestIdFilter, SecurityContextHolderFilter.class)
                .addFilterAfter(internalAuthFilter, RequestIdFilter.class)
                .addFilterAfter(bearerSessionFilter, InternalSecretAuthenticationFilter.class)
                .addFilterAfter(indexBatchLimitFilter, BearerSessionAuthenticationFilter.class);

        return http.build();
    }
}
