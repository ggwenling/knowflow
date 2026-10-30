package com.knowflow.api.error;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.HttpMediaTypeNotAcceptableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.beans.TypeMismatchException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class ApiExceptionHandler {
    private final ApiErrorWriter errors;

    public ApiExceptionHandler(ApiErrorWriter errors) {
        this.errors = errors;
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentNotValidException.class,
            HandlerMethodValidationException.class, TypeMismatchException.class,
            MissingServletRequestParameterException.class})
    void invalidRequest(HttpServletRequest request, HttpServletResponse response)
            throws java.io.IOException {
        errors.write(request, response, HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "The request is invalid.");
    }

    @ExceptionHandler(ApiFailure.class)
    void apiFailure(HttpServletRequest request, HttpServletResponse response, ApiFailure failure)
            throws java.io.IOException {
        errors.write(request, response, failure.status(), failure.code(), failure.getMessage());
    }

    @ExceptionHandler({NoHandlerFoundException.class, NoResourceFoundException.class})
    void endpointNotFound(HttpServletRequest request, HttpServletResponse response)
            throws java.io.IOException {
        errors.write(request, response, HttpStatus.NOT_FOUND, "ENDPOINT_UNAVAILABLE",
                "The requested endpoint is not available.");
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    void methodNotSupported(HttpServletRequest request, HttpServletResponse response,
                            HttpRequestMethodNotSupportedException exception)
            throws java.io.IOException {
        copyHeaders(exception.getHeaders(), response);
        errors.write(request, response, exception.getStatusCode(), "INVALID_REQUEST",
                "The HTTP method is not supported for this endpoint.");
    }

    @ExceptionHandler(HttpMediaTypeNotAcceptableException.class)
    void notAcceptable(HttpServletRequest request, HttpServletResponse response,
                       HttpMediaTypeNotAcceptableException exception)
            throws java.io.IOException {
        copyHeaders(exception.getHeaders(), response);
        var status = exception.getStatusCode();
        boolean clientError = status.is4xxClientError();
        String code = clientError ? "INVALID_REQUEST" : "INTERNAL_ERROR";
        String message = status.value() == HttpStatus.NOT_ACCEPTABLE.value()
                ? "The requested response media type is not acceptable."
                : "The request could not be processed.";
        errors.write(request, response, status, code, message);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    void unsupportedContentType(HttpServletRequest request, HttpServletResponse response,
                                HttpMediaTypeNotSupportedException exception)
            throws java.io.IOException {
        copyHeaders(exception.getHeaders(), response);
        errors.write(request, response, exception.getStatusCode(), "INVALID_REQUEST",
                "The request content type is not supported.");
    }

    private static void copyHeaders(HttpHeaders headers, HttpServletResponse response) {
        headers.forEach((name, values) -> values.forEach(value -> response.addHeader(name, value)));
    }

    @ExceptionHandler(Exception.class)
    void unexpectedFailure(HttpServletRequest request, HttpServletResponse response)
            throws java.io.IOException {
        errors.write(request, response, HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "The request could not be processed.");
    }
}
