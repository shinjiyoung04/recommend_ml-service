package com.lostmatch3.backend.recommendation;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/api/v1/recommendations")
public class RecommendationController {
    private final RestClient ml;
    public RecommendationController(RestClient mlRestClient) { this.ml = mlRestClient; }

    public record GroupRequest(@NotBlank String roomId, @NotBlank String roundId, @NotEmpty List<Map<String,Object>> members,
                               List<Integer> allowedProviders, List<String> allowedProviderTypes, Integer limit,
                               Boolean includeUnknownWatchPath, List<String> excludedMovieIds) {}

    public record ChatMessageRequest(
            @JsonAlias("room_id") @NotBlank String roomId,
            @JsonAlias("user_id") @NotBlank String userId,
            @NotBlank String text,
            @JsonAlias("reply_to_message_id") Long replyToMessageId,
            @JsonAlias("idempotency_key") String idempotencyKey,
            @JsonAlias("round_id") String roundId
    ) {}

    public record RoomRecommendationRequest(
            @JsonAlias("round_id") @NotBlank String roundId,
            @JsonAlias("expected_state_version") Long expectedStateVersion,
            @JsonAlias("allowed_providers") List<Integer> allowedProviders,
            @JsonAlias("allowed_provider_types") List<String> allowedProviderTypes,
            Integer limit,
            @JsonAlias("include_unknown_watch_path") Boolean includeUnknownWatchPath,
            @JsonAlias("excluded_movie_ids") List<String> excludedMovieIds
    ) {}

    @PostMapping("/group")
    public Object recommend(@Valid @RequestBody GroupRequest request) {
        return ml.post().uri("/v1/recommendations/group").body(Map.of(
                "room_id", request.roomId(), "round_id", request.roundId(), "members", request.members(),
                "allowed_providers", request.allowedProviders() == null ? List.of() : request.allowedProviders(),
                "allowed_provider_types", request.allowedProviderTypes() == null ? List.of() : request.allowedProviderTypes(),
                "limit", request.limit() == null ? 3 : request.limit(),
                "include_unknown_watch_path", request.includeUnknownWatchPath() == null || request.includeUnknownWatchPath(),
                "excluded_movie_ids", request.excludedMovieIds() == null ? List.of() : request.excludedMovieIds()
        )).retrieve().body(Object.class);
    }

    @PostMapping("/events")
    public Object saveEvent(@RequestBody Map<String,Object> event) {
        return ml.post().uri("/v1/recommendation-events").body(event).retrieve().body(Object.class);
    }

    @GetMapping("/events")
    public Object events(@RequestParam(required = false) String roundId) {
        return roundId == null
                ? ml.get().uri("/v1/recommendation-events").retrieve().body(Object.class)
                : ml.get().uri(builder -> builder.path("/v1/recommendation-events").queryParam("round_id", roundId).build())
                .retrieve().body(Object.class);
    }

    @PostMapping("/chat/messages")
    public Object saveMessage(@Valid @RequestBody ChatMessageRequest message) {
        var body = new java.util.HashMap<String, Object>();
        body.put("room_id", message.roomId());
        body.put("user_id", message.userId());
        body.put("text", message.text());
        if (message.replyToMessageId() != null) body.put("reply_to_message_id", message.replyToMessageId());
        if (message.idempotencyKey() != null) body.put("idempotency_key", message.idempotencyKey());
        if (message.roundId() != null) body.put("round_id", message.roundId());
        return ml.post().uri("/v1/chat/messages").body(body).retrieve().body(Object.class);
    }

    @PostMapping("/chat/rooms/{roomId}/recommendations")
    public Object recommendFromAccumulatedState(
            @PathVariable String roomId,
            @Valid @RequestBody RoomRecommendationRequest request
    ) {
        var body = new java.util.HashMap<String, Object>();
        body.put("round_id", request.roundId());
        if (request.expectedStateVersion() != null) body.put("expected_state_version", request.expectedStateVersion());
        body.put("allowed_providers", request.allowedProviders() == null ? List.of() : request.allowedProviders());
        body.put("allowed_provider_types", request.allowedProviderTypes() == null ? List.of() : request.allowedProviderTypes());
        body.put("limit", request.limit() == null ? 3 : request.limit());
        body.put("include_unknown_watch_path", request.includeUnknownWatchPath() == null || request.includeUnknownWatchPath());
        body.put("excluded_movie_ids", request.excludedMovieIds() == null ? List.of() : request.excludedMovieIds());
        return ml.post().uri("/v1/chat/rooms/{id}/recommendations", roomId)
                .body(body).retrieve().body(Object.class);
    }

    @GetMapping("/chat/rooms/{roomId}")
    public Object roomChat(@PathVariable String roomId) {
        return ml.get().uri("/v1/chat/rooms/{id}", roomId).retrieve().body(Object.class);
    }

    @DeleteMapping("/chat/rooms/{roomId}")
    public Object resetRoom(@PathVariable String roomId) {
        return ml.delete().uri("/v1/chat/rooms/{id}", roomId).retrieve().body(Object.class);
    }

    @GetMapping("/movies/{movieId}/watch-providers")
    public Object providers(@PathVariable String movieId) {
        return ml.get().uri("/v1/movies/{id}/watch-providers", movieId).retrieve().body(Object.class);
    }

    @GetMapping("/health")
    public ResponseEntity<Object> health() {
        return ResponseEntity.ok(ml.get().uri("/health").retrieve().body(Object.class));
    }

    @GetMapping("/evaluation")
    public Object evaluation() {
        return ml.get().uri("/v1/evaluation").retrieve().body(Object.class);
    }
}
