package com.knowflow.api.document;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.knowflow.api.config.IndexingProperties;
import com.knowflow.api.security.AuthenticatedUser;
import com.knowflow.api.storage.ObjectStore;
import com.knowflow.api.storage.ObjectStoreException;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class DocumentServiceLoggingTest {
    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void uploadFailureLogsOnlyStableFieldsAndStillCompensates(boolean withCause) {
        String credentialMarker = "SYNTHETIC_UPLOAD_CREDENTIAL_MARKER";
        String bodyMarker = "SYNTHETIC_UPLOAD_RESPONSE_BODY_MARKER";
        String exceptionMessage = "https://storage.invalid/private-object?credential="
                + credentialMarker + " response=" + bodyMarker;
        ObjectStoreException failure = withCause
                ? new ObjectStoreException(exceptionMessage, new IllegalStateException(bodyMarker))
                : new ObjectStoreException(exceptionMessage);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        TransactionTemplate transactions = mock(TransactionTemplate.class);
        ObjectStore objectStore = mock(ObjectStore.class);
        UUID ownerId = UUID.randomUUID();
        UUID knowledgeBaseId = UUID.randomUUID();
        when(jdbc.queryForObject(anyString(), eq(Integer.class), eq(knowledgeBaseId), eq(ownerId)))
                .thenReturn(1);
        doThrow(failure).when(objectStore).putObject(anyString(), anyString(), any(byte[].class));
        DocumentService service = new DocumentService(jdbc, transactions, objectStore,
                mock(DeletionCoordinator.class), new IndexingProperties());
        MockMultipartFile file = new MockMultipartFile("file", "private-title.txt", "text/plain",
                "SYNTHETIC_UPLOAD_DOCUMENT_BODY".getBytes(StandardCharsets.UTF_8));
        Logger logger = (Logger) LoggerFactory.getLogger(DocumentService.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            assertThatThrownBy(() -> service.upload(
                    new AuthenticatedUser(ownerId, "owner@example.invalid", "test-token-hash"),
                    knowledgeBaseId, file)).isSameAs(failure);
            verify(objectStore).deleteObject(startsWith("documents/"));
            verifyNoInteractions(transactions);
            assertThat(appender.list).hasSize(1);
            ILoggingEvent event = appender.list.getFirst();
            assertThat(event.getFormattedMessage())
                    .isEqualTo("stage=source_upload outcome=failure code=OBJECT_STORAGE_FAILED cause_type="
                            + (withCause ? "IllegalStateException" : "none"))
                    .doesNotContain(credentialMarker, bodyMarker, "storage.invalid", "private-object",
                            "private-title.txt", "SYNTHETIC_UPLOAD_DOCUMENT_BODY");
            assertThat(event.getThrowableProxy()).isNull();
            assertThat(event.getArgumentArray()).containsExactly(withCause ? "IllegalStateException" : "none");
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
