FROM golang:1.22-alpine AS builder

WORKDIR /app

RUN apk add --no-cache protobuf protobuf-dev

COPY go.mod go.sum* ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o /engine .

FROM alpine:3.19

# Install grpcurl for health checks
RUN apk add --no-cache grpcurl ca-certificates

WORKDIR /app

COPY --from=builder /engine .

EXPOSE 50051

# Health check using gRPC reflection
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD grpcurl -plaintext localhost:50051 list || exit 1

CMD ["./engine"]
