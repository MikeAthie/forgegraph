package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"hash/fnv"
	"strconv"
	"time"
)

func engineEventTimestamp(now time.Time) string {
	return strconv.FormatInt(now.UnixMilli(), 10)
}

func signEngineEvent(secret string, timestamp string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(timestamp))
	mac.Write([]byte("."))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

func canonicalEventChecksum(envelope map[string]any) (string, error) {
	unsigned := make(map[string]any, len(envelope))
	for key, value := range envelope {
		if key == "checksum" {
			continue
		}
		unsigned[key] = value
	}
	body, err := json.Marshal(unsigned)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(body)
	return hex.EncodeToString(sum[:]), nil
}

func deterministicEventTime(key string) time.Time {
	hasher := fnv.New32a()
	_, _ = hasher.Write([]byte(key))
	offset := time.Duration(hasher.Sum32()%86_400) * time.Second
	return time.Date(2026, 5, 5, 0, 0, 0, 0, time.UTC).Add(offset)
}
