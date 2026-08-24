package com.lostmatch3.backend.recommendation;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestControllerAdvice
class RecommendationExceptionHandler {
    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<String> mlResponse(RestClientResponseException exception) {
        return ResponseEntity.status(exception.getStatusCode())
            .contentType(MediaType.APPLICATION_JSON)
            .body(exception.getResponseBodyAsString());
    }

    @ExceptionHandler(RestClientException.class)
    ResponseEntity<?> unavailable(RestClientException exception) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of("error", Map.of("code", "ML_SERVICE_UNAVAILABLE", "message", "추천 서비스에 연결할 수 없습니다.", "retryable", true)));
    }
}
