ALTER TABLE knowflow.question_sources
    DROP CONSTRAINT question_sources_retention_shape_check;

ALTER TABLE knowflow.question_sources
    ADD CONSTRAINT question_sources_retention_shape_check CHECK (
        (
            (quote IS NULL AND locator_kind IS NULL
                AND source_page IS NULL AND source_start IS NULL AND source_end IS NULL)
            OR (quote IS NOT NULL AND quote <> '' AND (
                (locator_kind = 'pdf_page' AND source_page > 0
                    AND source_start IS NULL AND source_end IS NULL)
                OR (locator_kind = 'text_range' AND source_page IS NULL
                    AND source_start >= 0 AND source_end > source_start)
            ))
        ) IS TRUE
    );
