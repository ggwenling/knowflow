package com.knowflow.api.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "knowflow.questions")
public class QuestionProperties {
    @Min(1)
    @Max(30)
    private int totalBudgetSeconds = 30;

    public int getTotalBudgetSeconds() {
        return totalBudgetSeconds;
    }

    public void setTotalBudgetSeconds(int value) {
        totalBudgetSeconds = value;
    }
}
