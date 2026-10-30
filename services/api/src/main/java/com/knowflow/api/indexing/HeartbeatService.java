package com.knowflow.api.indexing;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

import com.knowflow.api.config.IndexingProperties;
import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class HeartbeatService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final LeaseAuthorizer leases;
    private final IndexingProperties properties;

    public HeartbeatService(JdbcTemplate jdbc, TransactionTemplate transactions,
                            LeaseAuthorizer leases, IndexingProperties properties) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.leases = leases;
        properties.requireValid();
        this.properties = properties;
    }

    public HeartbeatReceipt heartbeat(UUID routeTaskId, HeartbeatRequest request) {
        if (request == null || !ApiError.CONTRACT_VERSION.equals(request.contractVersion())
                || request.lease() == null || !routeTaskId.equals(request.lease().taskId())) {
            throw ApiFailure.leaseRejected();
        }
        HeartbeatReceipt receipt = transactions.execute(status -> {
            LeaseAuthorizer.AuthorizedExecution execution = leases.lockAndVerify(
                    routeTaskId, request.lease());
            List<OffsetDateTime> expiry = jdbc.query("""
                    UPDATE knowflow.indexing_tasks
                       SET lease_expires_at = clock_timestamp() + (? * INTERVAL '1 second'),
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ? AND status = 'RUNNING' AND lease_id = ? AND fencing = ?
                       AND execution_token_hash = ?
                       AND lease_expires_at > clock_timestamp()
                    RETURNING lease_expires_at
                    """, (result, row) -> result.getObject(1, OffsetDateTime.class),
                    properties.getLeaseSeconds(), execution.taskId(), execution.leaseId(),
                    execution.fencing(), com.knowflow.api.auth.AuthService.sha256(
                            request.lease().executionToken()));
            if (expiry.isEmpty()) {
                throw ApiFailure.leaseRejected();
            }
            return new HeartbeatReceipt(ApiError.CONTRACT_VERSION, request.requestId(),
                    execution.taskId(), expiry.getFirst());
        });
        if (receipt == null) {
            throw new IllegalStateException("Heartbeat transaction returned no receipt");
        }
        return receipt;
    }
}
