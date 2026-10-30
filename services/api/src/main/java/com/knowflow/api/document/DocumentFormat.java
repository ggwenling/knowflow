package com.knowflow.api.document;

import java.io.IOException;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;

public enum DocumentFormat {
    TXT("txt", "text/plain; charset=utf-8"),
    MD("md", "text/markdown; charset=utf-8"),
    PDF("pdf", "application/pdf");

    private final String extension;
    private final String contentType;

    DocumentFormat(String extension, String contentType) {
        this.extension = extension;
        this.contentType = contentType;
    }

    public String extension() { return extension; }
    public String contentType() { return contentType; }

    public static DocumentFormat fromNameAndBytes(String filename, byte[] bytes) {
        int dot = filename.lastIndexOf('.');
        if (dot <= 0 || dot == filename.length() - 1) {
            throw com.knowflow.api.error.ApiFailure.unsupportedContent();
        }
        String extension = filename.substring(dot + 1).toLowerCase(java.util.Locale.ROOT);
        DocumentFormat format = switch (extension) {
            case "txt" -> TXT;
            case "md" -> MD;
            case "pdf" -> PDF;
            default -> throw com.knowflow.api.error.ApiFailure.unsupportedContent();
        };
        if (bytes.length == 0) {
            throw com.knowflow.api.error.ApiFailure.unsupportedContent();
        }
        boolean pdfSignature = containsPdfSignature(bytes);
        if (format == PDF) {
            if (!pdfSignature) {
                throw com.knowflow.api.error.ApiFailure.unsupportedContent();
            }
            try (PDDocument document = Loader.loadPDF(bytes)) {
                if (document.getNumberOfPages() > UploadLimits.MAX_PDF_PAGES) {
                    throw com.knowflow.api.error.ApiFailure.resourceLimit();
                }
            } catch (com.knowflow.api.error.ApiFailure failure) {
                throw failure;
            } catch (IOException | RuntimeException invalidPdf) {
                throw com.knowflow.api.error.ApiFailure.unsupportedContent();
            }
            return format;
        }
        if (pdfSignature) {
            throw com.knowflow.api.error.ApiFailure.unsupportedContent();
        }
        validateUtf8Text(bytes);
        return format;
    }

    private static boolean containsPdfSignature(byte[] bytes) {
        int length = Math.min(bytes.length, 1024);
        byte[] signature = "%PDF-".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        outer:
        for (int start = 0; start <= length - signature.length; start++) {
            for (int offset = 0; offset < signature.length; offset++) {
                if (bytes[start + offset] != signature[offset]) {
                    continue outer;
                }
            }
            return true;
        }
        return false;
    }

    private static void validateUtf8Text(byte[] bytes) {
        try {
            var decoder = java.nio.charset.StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                    .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);
            String text = decoder.decode(java.nio.ByteBuffer.wrap(bytes)).toString();
            if (text.indexOf('\0') >= 0) {
                throw com.knowflow.api.error.ApiFailure.unsupportedContent();
            }
            if (text.codePointCount(0, text.length()) > UploadLimits.MAX_TEXT_CODE_POINTS) {
                throw com.knowflow.api.error.ApiFailure.resourceLimit();
            }
        } catch (java.nio.charset.CharacterCodingException exception) {
            throw com.knowflow.api.error.ApiFailure.unsupportedContent();
        }
    }
}
