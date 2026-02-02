package store

import "github.com/redis/go-redis/v9"

// storeSummaryScript atomically:
// 1. Increments version counter
// 2. Stores versioned backup
// 3. Stores current summary
// 4. Evicts old version if > 5
var storeSummaryScript = redis.NewScript(`
	local versionKey = KEYS[1]
	local currentKey = KEYS[2]
	local versionedKeyPrefix = KEYS[3]
	local data = ARGV[1]
	local ttl = tonumber(ARGV[2])

	-- Increment version atomically
	local version = redis.call('INCR', versionKey)

	-- Build versioned key
	local versionedKey = versionedKeyPrefix .. 'v' .. tostring(version)

	-- Store both versioned and current
	if ttl > 0 then
		redis.call('SET', versionedKey, data, 'EX', ttl)
		redis.call('SET', currentKey, data, 'EX', ttl)
	else
		redis.call('SET', versionedKey, data)
		redis.call('SET', currentKey, data)
	end

	-- Evict old version (keep last 5)
	if version > 5 then
		local oldVersion = version - 5
		local oldKey = versionedKeyPrefix .. 'v' .. tostring(oldVersion)
		redis.call('DEL', oldKey)
	end

	-- Set TTL on version counter too
	if ttl > 0 then
		redis.call('EXPIRE', versionKey, ttl)
	end

	return version
`)

// getSummaryWithVersionScript gets summary and version info atomically
var getSummaryWithVersionScript = redis.NewScript(`
	local versionKey = KEYS[1]
	local currentKey = KEYS[2]

	local version = redis.call('GET', versionKey)
	local current = redis.call('GET', currentKey)

	return {version or '0', current or ''}
`)

// storeFactsScript atomically stores multiple facts for a run
var storeFactsScript = redis.NewScript(`
	local baseKey = KEYS[1]
	local ttl = tonumber(ARGV[1])
	local factCount = tonumber(ARGV[2])

	for i = 1, factCount do
		local idx = 2 + (i - 1) * 2
		local factKey = baseKey .. ':' .. ARGV[idx + 1]
		local factData = ARGV[idx + 2]

		if ttl > 0 then
			redis.call('SET', factKey, factData, 'EX', ttl)
		else
			redis.call('SET', factKey, factData)
		end
	end

	return factCount
`)
