# Claude Code Docker API Connection Issues

## Summary

Running Claude Code in Docker containers with `--dangerously-skip-permissions` can experience API connection drops. This document covers known issues and fixes.

---

## Known Issues

### 1. IPv6 Connectivity Timeout (Most Common)

**Symptoms:**
- API works for 1-2 requests, then times out
- `API Error (Request timed out.) · Retrying in 1 seconds…`
- 60-second hangs before timeout

**Root Cause:**
Docker containers may prioritize IPv6 (AAAA DNS records) for API connections even when IPv6 is not fully functional, causing connections to hang.

**Fix:** Disable IPv6 in container (already applied in `.devcontainer/devcontainer.json`)

```json
"runArgs": [
  "--sysctl", "net.ipv6.conf.all.disable_ipv6=1",
  "--sysctl", "net.ipv6.conf.default.disable_ipv6=1"
]
```

**References:**
- [Issue #1771](https://github.com/anthropics/claude-code/issues/1771)
- [Issue #2728](https://github.com/anthropics/claude-code/issues/2728)

---

### 2. Interactive Session Crashes with Compound Instructions

**Symptoms:**
- Session terminates silently with no error
- Happens with compound instructions like "read X and summarize"

**Trigger Conditions (ALL required):**
1. Running inside Docker container
2. `--dangerously-skip-permissions` flag enabled
3. Compound instruction using "and" or comma separator
4. Target file must exist

**Workaround:**
Use period-separated sentences instead of "and":
```
# BAD - will crash
read file.txt and summarize

# GOOD - works
read file.txt. Now summarize.
```

**Reference:** [Issue #14020](https://github.com/anthropics/claude-code/issues/14020)

---

### 3. Connection Reset Errors (ECONNRESET)

**Symptoms:**
- `TypeError (fetch failed)`
- `API Error (Connection error.)`
- TCP RST observed in packet captures

**Potential Causes:**
- Aggressive connection pooling/keep-alive issues
- Firewall/network interference
- Anthropic API rate limiting or overload (529 errors)

**Mitigations:**
- Use reliable DNS servers (8.8.8.8, 8.8.4.4)
- Ensure stable network connectivity
- Retry logic is built-in (10 attempts)

**Reference:** [Issue #4297](https://github.com/anthropics/claude-code/issues/4297)

---

### 4. Re-authentication on Container Restart

**Symptoms:**
- Must re-authenticate every time container restarts

**Fix:** Mount credential files from host (already configured):
```yaml
volumes:
  - ~/.claude:/home/dev/.claude
  - ~/.claude.json:/home/dev/.claude.json
```

**Reference:** [Issue #1736](https://github.com/anthropics/claude-code/issues/1736)

---

## Configuration Checklist

Your current setup should have:

- [x] IPv6 disabled in devcontainer.json
- [x] DNS servers configured (8.8.8.8, 8.8.4.4)
- [x] Claude credentials mounted
- [x] Non-root user (dev)
- [ ] IPv6 disabled in docker-compose.yml (needs fix)
- [ ] TCP keepalive settings
- [ ] Health check for network

---

## Debugging Commands

```bash
# Check IPv6 status inside container
cat /proc/sys/net/ipv6/conf/all/disable_ipv6
# Should return: 1

# Test API connectivity
curl -v https://api.anthropic.com

# Check DNS resolution
nslookup api.anthropic.com

# Monitor network issues
ANTHROPIC_LOG=debug DEBUG=1 claude --dangerously-skip-permissions

# Check if using IPv6
curl -6 https://api.anthropic.com  # Should fail if IPv6 disabled
curl -4 https://api.anthropic.com  # Should work
```

---

## Environment Variables for Stability

```bash
# Force IPv4
export NODE_OPTIONS="--dns-result-order=ipv4first"

# Increase timeout (default 60s)
export ANTHROPIC_TIMEOUT=120000

# Enable debug logging
export ANTHROPIC_LOG=debug
export DEBUG=1
```

---

## Sources

- [Issue #4297: API Connection Error](https://github.com/anthropics/claude-code/issues/4297)
- [Issue #1771: Request Timeout in Dev Container](https://github.com/anthropics/claude-code/issues/1771)
- [Issue #14020: Interactive Session Crashes](https://github.com/anthropics/claude-code/issues/14020)
- [Issue #2728: Constant Timeouts](https://github.com/anthropics/claude-code/issues/2728)
- [Claude Help: API Connection Errors](https://support.claude.com/en/articles/10366432-i-m-getting-an-api-connection-error-how-can-i-fix-it)
- [Docker Claude Code Config](https://docs.docker.com/ai/sandboxes/claude-code/)
