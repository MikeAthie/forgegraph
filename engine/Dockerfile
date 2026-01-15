FROM golang:1.22-alpine AS builder

WORKDIR /app

RUN apk add --no-cache protobuf protobuf-dev

COPY go.mod go.sum* ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o /engine .

FROM alpine:3.19

WORKDIR /app

COPY --from=builder /engine .

EXPOSE 50051

CMD ["./engine"]
