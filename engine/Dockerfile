FROM golang:1.23.8-alpine3.21 AS builder

WORKDIR /app

# git can be needed for some module fetches; ca-certs helps TLS downloads
RUN apk add --no-cache protobuf protobuf-dev git ca-certificates

RUN go install github.com/fullstorydev/grpcurl/cmd/grpcurl@v1.8.9

COPY go.mod go.sum* ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o /engine .

FROM alpine:3.21.3

# We only need certs at runtime
RUN apk add --no-cache ca-certificates \
    && addgroup -S forgegraph \
    && adduser -S -G forgegraph forgegraph

WORKDIR /app

COPY --from=builder /engine .
COPY --from=builder /go/bin/grpcurl /usr/local/bin/grpcurl

EXPOSE 50051 9090

# Health check uses the explicit readiness endpoint.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sh -c 'wget -q -O- "http://127.0.0.1:${METRICS_PORT:-9090}/ready" >/dev/null 2>&1 || exit 1'

USER forgegraph

CMD ["./engine"]
