package com.knowflow.api;

import java.util.Arrays;

import com.knowflow.api.db.DatabaseMigrationApplication;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication(exclude = {
        DataSourceAutoConfiguration.class,
        FlywayAutoConfiguration.class,
        UserDetailsServiceAutoConfiguration.class
})
@ConfigurationPropertiesScan
public class KnowFlowApiApplication {
    public static void main(String[] args) {
        if (args.length > 0 && "--migrate-only".equals(args[0])) {
            DatabaseMigrationApplication.run(Arrays.copyOfRange(args, 1, args.length));
            return;
        }
        SpringApplication.run(KnowFlowApiApplication.class, args);
    }
}
