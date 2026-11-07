package com.knowflow.api.indexing;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.knowflow.api.config.IndexingProperties;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class IndexingConfigurationTest {
    @Test
    void warnsAtStartupWhenTheSchedulerIsDisabled() throws Exception {
        IndexingProperties properties = new IndexingProperties();
        Logger logger = (Logger) LoggerFactory.getLogger(IndexingConfiguration.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            new IndexingConfiguration().validateIndexingStartup(properties).run(null);
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
        assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anyMatch(message -> message.contains("KNOWFLOW_INDEXING_SCHEDULER_ENABLED=true"));
    }

    @Test
    void rejectsInvalidSettingsAtStartupEvenWhenSchedulingIsDisabled() {
        IndexingProperties properties = new IndexingProperties();
        properties.setPollDelayMillis(10);

        assertThatThrownBy(() -> new IndexingConfiguration().validateIndexingStartup(properties).run(null))
                .isInstanceOf(IllegalStateException.class);
    }
}
