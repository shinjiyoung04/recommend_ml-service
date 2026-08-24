package com.lostmatch3.backend.recommendation;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "meetup.ml-service")
public record MlServiceProperties(String baseUrl, Duration connectTimeout, Duration readTimeout) {}

