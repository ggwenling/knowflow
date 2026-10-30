package com.knowflow.api.indexing;

import java.util.UUID;

import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database")
public class HeartbeatController {
    private final HeartbeatService heartbeats;

    public HeartbeatController(HeartbeatService heartbeats) {
        this.heartbeats = heartbeats;
    }

    @PostMapping(path = "/internal/v1/tasks/{taskId}/heartbeat",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    HeartbeatReceipt heartbeat(HttpServletRequest servletRequest, @PathVariable UUID taskId,
                               @RequestBody HeartbeatRequest request) {
        Object requestId = servletRequest.getAttribute(RequestIdFilter.ATTRIBUTE);
        if (request.lease() == null || !taskId.equals(request.lease().taskId())
                || !(requestId instanceof String id) || !id.equals(request.requestId())) {
            throw ApiFailure.leaseRejected();
        }
        return heartbeats.heartbeat(taskId, request);
    }
}
