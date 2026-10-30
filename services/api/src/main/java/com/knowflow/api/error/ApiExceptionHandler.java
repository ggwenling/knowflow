package com.knowflow.api.error;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiExceptionHandler {
    private final ApiErrorWriter errors;

    public ApiExceptionHandler(ApiErrorWriter errors) {
        this.errors = errors;
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentNotValidException.class,
            HandlerMethodValidationException.class})
    void invalidRequest(HttpServletRequest request, jakarta.servlet.http.HttpServletResponse response)
            throws java.io.IOException {
        errors.write(request, response, HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "The request is invalid.");
    }

    @ExceptionHandler(Exception.class)
    void unexpectedFailure(HttpServletRequest request, jakarta.servlet.http.HttpServletResponse response)
            throws java.io.IOException {
        errors.write(request, response, HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "The request could not be processed.");
    }
}
