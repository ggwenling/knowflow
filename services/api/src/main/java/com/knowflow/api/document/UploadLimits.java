package com.knowflow.api.document;

public final class UploadLimits {
    public static final long MAX_FILE_BYTES = 8L * 1024 * 1024;
    public static final int MAX_TEXT_CODE_POINTS = 200_000;
    public static final int MAX_PDF_PAGES = 200;

    private UploadLimits() {}
}
