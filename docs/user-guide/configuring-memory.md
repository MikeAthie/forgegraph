# Configuring Memory

## Memory Depth
Choose how much conversation history your agent remembers. This controls the local buffer size.

### Presets
- **Short**: Last 10 messages — for simple, focused tasks
- **Medium**: Last 20 messages (default) — balanced
- **Long**: Last 50 messages — for complex conversations
- **Extended**: Last 100 messages — for long-running sessions

You can also choose **Custom** and enter a specific number of messages.

---

## Defaults
- **Memory depth**: Medium (20 messages)
- **Auto-prepend**: Enabled
- **Persistence**: Disabled
- **Summary TTL**: 24 hours
- **Facts TTL**: 7 days

---

## Enable Persistence
When enabled, summaries and facts are stored in Redis for reuse across runs.

---

## Advanced Options

**Auto-prepend memory**  
When enabled, the engine prepends recent buffer messages to each prompt.

**Summary TTL (hours)**  
How long summarized memory persists in Redis.

**Facts TTL (days)**  
How long extracted facts persist in Redis.

---

## Troubleshooting

**Memory not showing up in prompts**
- Ensure auto-prepend is enabled.
- Check the buffer size isn’t set too low.

**Persistence doesn’t work**
- Confirm Redis is configured and healthy.
- Check `/health/redis` on the engine.
